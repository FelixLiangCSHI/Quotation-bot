"""Tests for the Streamlit presentation helpers and free-input fallbacks.

These tests only exercise pure helper functions, so no Streamlit runtime is
required. The multi-turn flows reuse the same core functions that the
Streamlit callbacks use.
"""

from __future__ import annotations

import unittest

from app.quotation import (
    AUTO_APPROVED,
    QuotationValidationError,
    build_quotation_lines,
    is_supported_main_product,
    merge_configuration,
    recalculate_quotation,
)
from app.recommender import QuoteRecommender
from app.serialization import to_jsonable

import streamlit_app


RECOMMENDER = QuoteRecommender()


def advance(configuration: dict, turns: list[str], prompt: str) -> dict:
    """Replay one conversation turn exactly like ``_process_prompt`` does."""
    if streamlit_app.is_low_information_prompt(prompt):
        return {
            "configuration": configuration,
            "reply": streamlit_app.LOW_INFORMATION_REPLY,
            "quick_replies": (),
            "ready": False,
            "totals": None,
        }

    turns.append(prompt)
    conversation_text = "\n".join(turns)
    recommendation = to_jsonable(RECOMMENDER.recommend_from_text(conversation_text))
    merged = merge_configuration(
        configuration,
        prompt,
        conversation_text,
        recommendation,
    )
    merged, blocked = streamlit_app.guard_unsupported_product(merged)
    plan = streamlit_app.plan_next_reply(merged, blocked)
    totals = None
    if plan["ready"]:
        totals = recalculate_quotation(build_quotation_lines(merged))
    return {
        "configuration": merged,
        "reply": plan["reply"],
        "quick_replies": plan["quick_replies"],
        "ready": plan["ready"],
        "totals": totals,
    }


class LowInformationPromptTests(unittest.TestCase):
    def test_low_information_prompt_is_detected(self) -> None:
        for prompt in (
            "hi",
            "Hello.",
            "test",
            "Let me try",
            "I want to try.",
            "Can I try?",
            "start",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(streamlit_app.is_low_information_prompt(prompt))

    def test_normal_sales_request_is_not_low_information(self) -> None:
        self.assertFalse(
            streamlit_app.is_low_information_prompt(
                "ABC Hospital in Singapore needs two DRX Compass systems."
            )
        )
        self.assertFalse(
            streamlit_app.is_low_information_prompt("We need a DRX Compass.")
        )


class MissingQuestionTests(unittest.TestCase):
    def test_next_missing_question_returns_one_question(self) -> None:
        question = streamlit_app.next_missing_question({})
        self.assertIsInstance(question, str)
        self.assertEqual(question.count("?"), 1)

    def test_customer_question_is_first(self) -> None:
        self.assertEqual(
            streamlit_app.next_missing_question({}),
            streamlit_app.FIELD_QUESTIONS["customer_name"],
        )

    def test_region_question_follows_customer(self) -> None:
        self.assertEqual(
            streamlit_app.next_missing_question({"customer_name": "Test Hospital"}),
            streamlit_app.FIELD_QUESTIONS["region"],
        )

    def test_discount_question_is_last(self) -> None:
        configuration = {
            "customer_name": "Test Hospital",
            "region": "Singapore",
            "currency": "USD",
            "main_product": "DRX Compass Digital Radiography System",
            "configuration_description": "1 x DRX Compass",
        }
        self.assertEqual(
            streamlit_app.next_missing_question(configuration),
            streamlit_app.FIELD_QUESTIONS["discount_rate"],
        )
        configuration["discount_rate"] = 0.3
        self.assertIsNone(streamlit_app.next_missing_question(configuration))

    def test_quick_replies_use_natural_language(self) -> None:
        self.assertEqual(
            streamlit_app.quick_reply_prompt("currency", "USD"),
            "Use USD.",
        )
        self.assertEqual(
            streamlit_app.quick_reply_prompt("main_product", "DRX Compass"),
            "Use DRX Compass.",
        )
        self.assertEqual(
            streamlit_app.quick_reply_prompt("discount_rate", "30%"),
            "Apply a 30% discount.",
        )


class SupportedProductTests(unittest.TestCase):
    def test_unsupported_product_is_blocked(self) -> None:
        for product in ("CT scanner", "MRI", "Ultrasound", "Unknown model", ""):
            with self.subTest(product=product):
                self.assertFalse(is_supported_main_product(product))

    def test_supported_compass_is_allowed(self) -> None:
        self.assertTrue(
            is_supported_main_product("DRX Compass Digital Radiography System")
        )

    def test_supported_revolution_is_allowed(self) -> None:
        self.assertTrue(
            is_supported_main_product("DRX Revolution Mobile Radiography System")
        )

    def test_supported_rise_is_allowed(self) -> None:
        self.assertTrue(
            is_supported_main_product("DRX Rise Mobile Radiography System")
        )

    def test_guard_removes_unsupported_product(self) -> None:
        configuration, blocked = streamlit_app.guard_unsupported_product(
            {
                "customer_name": "Test Hospital",
                "main_product": "CT Scanner",
                "configuration_description": "1 x CT Scanner",
            }
        )
        self.assertTrue(blocked)
        self.assertEqual(configuration["main_product"], "")
        self.assertEqual(configuration["configuration_description"], "")
        self.assertEqual(configuration["customer_name"], "Test Hospital")


class WorkflowStageTests(unittest.TestCase):
    def test_stage_progresses_with_state(self) -> None:
        self.assertEqual(streamlit_app.workflow_stage({}), "Requirements")
        self.assertEqual(
            streamlit_app.workflow_stage({"configuration": {"customer_name": "A"}}),
            "Configuration",
        )
        self.assertEqual(
            streamlit_app.workflow_stage(
                {
                    "configuration": {"customer_name": "A"},
                    "quotation_lines": [{"product_code": "DRX-COMPASS"}],
                    "approval_status": "MANAGER_APPROVAL_REQUIRED",
                    "manager_approval_status": "NOT_SUBMITTED",
                }
            ),
            "Quotation",
        )
        self.assertEqual(
            streamlit_app.workflow_stage(
                {
                    "configuration": {"customer_name": "A"},
                    "quotation_lines": [{"product_code": "DRX-COMPASS"}],
                    "approval_status": AUTO_APPROVED,
                    "manager_approval_status": "NOT_SUBMITTED",
                }
            ),
            "Approval",
        )


class FreeInputFlowTests(unittest.TestCase):
    def test_step_by_step_conversation_reaches_auto_approval(self) -> None:
        configuration: dict = {}
        turns: list[str] = []

        turn = advance(configuration, turns, "I want to try.")
        self.assertFalse(turn["ready"])
        self.assertEqual(turn["reply"], streamlit_app.LOW_INFORMATION_REPLY)
        self.assertIsNone(turn["totals"])
        self.assertEqual(turns, [])

        turn = advance(configuration, turns, "The customer is Test Hospital.")
        configuration = turn["configuration"]
        self.assertEqual(configuration["customer_name"], "Test Hospital")
        self.assertIn(streamlit_app.FIELD_QUESTIONS["region"], turn["reply"])
        self.assertIsNone(turn["totals"])

        turn = advance(configuration, turns, "Use Singapore.")
        configuration = turn["configuration"]
        self.assertEqual(configuration["region"], "Singapore")
        self.assertIn(
            streamlit_app.next_missing_question(configuration),
            (
                streamlit_app.FIELD_QUESTIONS["currency"],
                streamlit_app.FIELD_QUESTIONS["main_product"],
            ),
        )
        self.assertIsNone(turn["totals"])

        turn = advance(
            configuration,
            turns,
            "Use USD and configure two DRX Compass systems "
            "with one wireless detector per system.",
        )
        configuration = turn["configuration"]
        self.assertEqual(configuration["currency"], "USD")
        self.assertEqual(configuration["quantity"], 2)
        detectors = [
            item
            for item in configuration["accessories"]
            if item["name"] == "Wireless Detector"
        ]
        self.assertEqual(detectors[0]["quantity"], 2)
        self.assertIn(streamlit_app.FIELD_QUESTIONS["discount_rate"], turn["reply"])
        self.assertIsNone(turn["totals"])

        turn = advance(configuration, turns, "30%.")
        configuration = turn["configuration"]
        totals = turn["totals"]
        self.assertTrue(turn["ready"])
        self.assertIsNotNone(totals)
        self.assertAlmostEqual(totals["discount_rate"], 0.30, places=4)
        self.assertEqual(totals["approval_status"], AUTO_APPROVED)

        from app.quotation import (
            can_export_quotation,
            is_customer_pdf_available,
            MANAGER_NOT_SUBMITTED,
        )

        self.assertTrue(can_export_quotation(configuration, totals))
        self.assertTrue(
            is_customer_pdf_available(
                totals["approval_status"],
                MANAGER_NOT_SUBMITTED,
            )
        )
        summary = streamlit_app.build_conversation_summary(configuration, totals)
        self.assertIn("Test Hospital", summary)
        self.assertIn("30%", summary)

    def test_unsupported_product_never_creates_a_quotation(self) -> None:
        turn = advance(
            {},
            [],
            "Test Hospital needs one CT scanner in Singapore, "
            "quoted in USD with a 30% discount.",
        )
        configuration = turn["configuration"]

        self.assertFalse(turn["ready"])
        self.assertIsNone(turn["totals"])
        self.assertEqual(configuration["main_product"], "")
        self.assertEqual(turn["reply"], streamlit_app.UNSUPPORTED_PRODUCT_MESSAGE)
        self.assertEqual(
            tuple(turn["quick_replies"]),
            streamlit_app.MAIN_PRODUCT_OPTIONS,
        )
        with self.assertRaises(QuotationValidationError):
            build_quotation_lines(configuration)

    def test_unsupported_product_recovers_after_choosing_a_system(self) -> None:
        turns: list[str] = []
        turn = advance(
            {},
            turns,
            "Test Hospital needs one MRI in Singapore, "
            "quoted in USD with a 30% discount.",
        )
        turn = advance(turn["configuration"], turns, "Use DRX Rise.")
        totals = turn["totals"]
        self.assertTrue(turn["ready"])
        self.assertIsNotNone(totals)
        self.assertEqual(totals["approval_status"], AUTO_APPROVED)
        self.assertEqual(totals["lines"][0]["product_code"], "DRX-RISE")


if __name__ == "__main__":
    unittest.main()
