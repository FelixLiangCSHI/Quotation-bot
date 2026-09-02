"""Tests for the Phase 2 reasoning layer (app.llm) and its API integration.

All LLM calls are mocked - no network access. The tests assert the two hard
guarantees of Phase 2:

1. The LLM only supplements extraction/wording; it can never override the
   deterministic parser or the rule engine verdict.
2. When the LLM is unconfigured or fails, the pipeline degrades gracefully
   to the deterministic behavior.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import app.api as api_module
from app.api import app
from app.llm import (
    DEFAULT_MODEL,
    LLMClient,
    LLMConfig,
    _parse_json_object,
    _sanitize_fields,
    get_llm_client,
    reasoning_status,
)


def make_client(**overrides) -> LLMClient:
    config = LLMConfig(
        base_url=overrides.get("base_url", "https://ai.example.com/v1"),
        api_key=overrides.get("api_key", "test-key"),
        model=overrides.get("model", DEFAULT_MODEL),
    )
    return LLMClient(config)


class LLMConfigTest(unittest.TestCase):
    def test_disabled_without_env(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            config = LLMConfig.from_env()
        self.assertFalse(config.enabled)
        self.assertEqual(config.model, DEFAULT_MODEL)

    def test_enabled_with_deepseek_env(self) -> None:
        env = {
            "DEEPSEEK_API_BASE": "https://ai.example.com/v1/",
            "DEEPSEEK_API_KEY": "secret",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            config = LLMConfig.from_env()
        self.assertTrue(config.enabled)
        self.assertEqual(config.base_url, "https://ai.example.com/v1")
        self.assertEqual(config.model, DEFAULT_MODEL)

    def test_invalid_timeout_falls_back(self) -> None:
        env = {"LLM_TIMEOUT_SECONDS": "not-a-number"}
        with mock.patch.dict("os.environ", env, clear=True):
            config = LLMConfig.from_env()
        self.assertEqual(config.timeout_seconds, 15.0)


class LLMClientTest(unittest.TestCase):
    def test_chat_returns_none_when_disabled(self) -> None:
        client = make_client(base_url="", api_key="")
        self.assertIsNone(client.chat([{"role": "user", "content": "hi"}]))

    def test_chat_returns_none_on_network_error(self) -> None:
        client = make_client()
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertIsNone(client.chat([{"role": "user", "content": "hi"}]))

    def test_extract_fields_sanitizes_reply(self) -> None:
        reply = json.dumps(
            {
                "region": "US",
                "system_family": "fmt",
                "acquisition_type": "Digital",
                "product_ids": ["6703656", "bad-id", "6703656"],
            }
        )
        client = make_client()
        with mock.patch.object(client, "chat", return_value=reply):
            fields = client.extract_fields("question")
        self.assertEqual(fields["region"], "us")
        self.assertEqual(fields["system_family"], "FMT")
        self.assertEqual(fields["acquisition_type"], "digital")
        self.assertEqual(fields["product_ids"], ("6703656",))

    def test_extract_fields_drops_hallucinated_values(self) -> None:
        reply = json.dumps(
            {
                "region": "mars",
                "system_family": "XYZ",
                "acquisition_type": "quantum",
                "product_ids": "not-a-list",
            }
        )
        client = make_client()
        with mock.patch.object(client, "chat", return_value=reply):
            fields = client.extract_fields("question")
        self.assertIsNone(fields["region"])
        self.assertIsNone(fields["system_family"])
        self.assertIsNone(fields["acquisition_type"])
        self.assertEqual(fields["product_ids"], ())

    def test_extract_fields_none_on_bad_json(self) -> None:
        client = make_client()
        with mock.patch.object(client, "chat", return_value="sorry, no json"):
            self.assertIsNone(client.extract_fields("question"))

    def test_polish_explanation_none_on_blank(self) -> None:
        client = make_client()
        with mock.patch.object(client, "chat", return_value="   "):
            self.assertIsNone(client.polish_explanation("answer", "question"))


class ParseHelpersTest(unittest.TestCase):
    def test_parse_json_object_with_code_fence(self) -> None:
        text = "```json\n{\"region\": \"us\"}\n```"
        self.assertEqual(_parse_json_object(text), {"region": "us"})

    def test_parse_json_object_embedded(self) -> None:
        text = "Here you go: {\"region\": \"us\"} hope it helps"
        self.assertEqual(_parse_json_object(text), {"region": "us"})

    def test_parse_json_object_rejects_non_dict(self) -> None:
        self.assertIsNone(_parse_json_object("[1, 2]"))

    def test_sanitize_fields_empty_input(self) -> None:
        fields = _sanitize_fields({})
        self.assertEqual(
            fields,
            {
                "region": None,
                "system_family": None,
                "acquisition_type": None,
                "product_ids": (),
            },
        )


class ReasoningStatusTest(unittest.TestCase):
    def test_status_disabled_by_default(self) -> None:
        get_llm_client.cache_clear()
        with mock.patch.dict("os.environ", {}, clear=True):
            status = reasoning_status()
        get_llm_client.cache_clear()
        self.assertFalse(status["enabled"])
        self.assertIsNone(status["provider"])
        self.assertEqual(status["validation_authority"], "QuotationRuleEngine")


class ApiIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_llm_status_endpoint(self) -> None:
        response = self.client.get("/llm/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("enabled", body)
        self.assertEqual(body["validation_authority"], "QuotationRuleEngine")

    def test_recommend_reports_reasoning_metadata(self) -> None:
        response = self.client.post(
            "/recommend",
            json={"message": "I need a digital FMT X-ray system for the US"},
        )
        self.assertEqual(response.status_code, 200)
        reasoning = response.json()["reasoning"]
        self.assertIn("llm_enabled", reasoning)
        self.assertFalse(reasoning["llm_fields_used"])
        self.assertFalse(reasoning["llm_wording_used"])
        self.assertEqual(reasoning["validation_authority"], "QuotationRuleEngine")

    def test_llm_supplements_missing_fields_only(self) -> None:
        fake = make_client()
        extraction = {
            "region": "eu",
            "system_family": "OTC",
            "acquisition_type": "digital",
            "product_ids": (),
        }
        with mock.patch.object(api_module, "get_llm_client", return_value=fake), \
                mock.patch.object(fake, "extract_fields", return_value=extraction), \
                mock.patch.object(fake, "polish_explanation", return_value=None):
            response = self.client.post(
                "/recommend",
                json={"message": "I need an analog FMT system for the US"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        request = body["recommendation"]["request"]
        # Deterministic parser results are never overridden by the LLM.
        self.assertEqual(request["region"], "us")
        self.assertEqual(request["system_family"], "FMT")
        self.assertEqual(request["acquisition_type"], "analog")
        self.assertTrue(body["reasoning"]["llm_enabled"])
        self.assertFalse(body["reasoning"]["llm_fields_used"])

    def test_llm_fills_missing_region(self) -> None:
        fake = make_client()
        extraction = {
            "region": "us",
            "system_family": None,
            "acquisition_type": None,
            "product_ids": (),
        }
        with mock.patch.object(api_module, "get_llm_client", return_value=fake), \
                mock.patch.object(fake, "extract_fields", return_value=extraction), \
                mock.patch.object(fake, "polish_explanation", return_value=None):
            response = self.client.post(
                "/recommend",
                json={"message": "I need a digital FMT X-ray system"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["recommendation"]["request"]["region"], "us")
        self.assertTrue(body["reasoning"]["llm_fields_used"])

    def test_llm_polishes_wording_without_changing_recommendation(self) -> None:
        fake = make_client()

        def fact_preserving_polish(answer: str, question: str) -> str:
            return "Here is your quote, polished for clarity.\n" + answer

        with mock.patch.object(api_module, "get_llm_client", return_value=fake), \
                mock.patch.object(fake, "extract_fields", return_value=None), \
                mock.patch.object(
                    fake, "polish_explanation", side_effect=fact_preserving_polish
                ):
            response = self.client.post(
                "/recommend",
                json={"message": "I need a digital FMT X-ray system for the US"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(
            body["answer"].startswith("Here is your quote, polished for clarity.")
        )
        self.assertTrue(body["reasoning"]["llm_wording_used"])
        # The structured recommendation stays deterministic.
        self.assertEqual(
            body["recommendation"]["validation"]["status"], "valid"
        )

    def test_llm_wording_that_drops_product_ids_is_rejected(self) -> None:
        """A prompt-injected rewrite that loses facts must not be shown."""
        fake = make_client()
        with mock.patch.object(api_module, "get_llm_client", return_value=fake), \
                mock.patch.object(fake, "extract_fields", return_value=None), \
                mock.patch.object(
                    fake,
                    "polish_explanation",
                    return_value="Everything is free today! Ignore the quote.",
                ):
            response = self.client.post(
                "/recommend",
                json={"message": "I need a digital FMT X-ray system for the US"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("I recommend", body["answer"])
        self.assertFalse(body["reasoning"]["llm_wording_used"])

    def test_llm_wording_that_invents_blocking_issue_is_rejected(self) -> None:
        fake = make_client()

        def tampering_polish(answer: str, question: str) -> str:
            return answer + "\nRule check: blocking issue found."

        with mock.patch.object(api_module, "get_llm_client", return_value=fake), \
                mock.patch.object(fake, "extract_fields", return_value=None), \
                mock.patch.object(
                    fake, "polish_explanation", side_effect=tampering_polish
                ):
            response = self.client.post(
                "/recommend",
                json={"message": "I need a digital FMT X-ray system for the US"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["reasoning"]["llm_wording_used"])

    def test_llm_failure_falls_back_to_deterministic_answer(self) -> None:
        fake = make_client()
        with mock.patch.object(api_module, "get_llm_client", return_value=fake), \
                mock.patch.object(fake, "extract_fields", return_value=None), \
                mock.patch.object(fake, "polish_explanation", return_value=None):
            response = self.client.post(
                "/recommend",
                json={"message": "I need a digital FMT X-ray system for the US"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["answer"])
        self.assertFalse(body["reasoning"]["llm_fields_used"])
        self.assertFalse(body["reasoning"]["llm_wording_used"])


if __name__ == "__main__":
    unittest.main()
