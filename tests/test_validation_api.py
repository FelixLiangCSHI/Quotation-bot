"""Tests for POST /validation/check - the Phase 3 deliverable.

The endpoint wraps QuotationRuleEngine.check_configuration directly:
deterministic, no LLM involvement, rule engine as the single validation
authority.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.api import app
from app.data_loader import load_merged_rules


class ValidationCheckEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_message_only_invalid_region(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={"message": "Can I quote product 6703656 for the EU?"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "invalid")
        codes = [issue["code"] for issue in body["issues"]]
        self.assertIn("region_not_allowed", codes)
        self.assertEqual(body["summary"]["errors"], 1)
        self.assertEqual(body["validation_authority"], "QuotationRuleEngine")

    def test_structured_fields_valid(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={"fields": {"product_ids": ["6703656"], "region": "us"}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "valid")
        self.assertEqual(body["summary"], {"errors": 0, "warnings": 0, "infos": 0})

    def test_structured_fields_override_message(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={
                "message": "Quote product 6703656 for europe",
                "fields": {"region": "us"},
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["resolved_input"]["region"], "us")
        self.assertEqual(body["status"], "valid")

    def test_incomplete_when_region_missing(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={"fields": {"product_ids": ["6703656"]}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "incomplete")
        self.assertIn("region", body["missing_fields"])

    def test_unknown_product_reported(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={"fields": {"product_ids": ["9999999"], "region": "us"}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        codes = [issue["code"] for issue in body["issues"]]
        self.assertTrue(codes)
        self.assertEqual(body["status"], "invalid")

    def test_empty_request_rejected(self) -> None:
        response = self.client.post("/validation/check", json={})
        self.assertEqual(response.status_code, 422)

    def test_blank_message_rejected(self) -> None:
        response = self.client.post("/validation/check", json={"message": "   "})
        self.assertEqual(response.status_code, 422)

    def test_unsupported_region_rejected(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={"fields": {"product_ids": ["6703656"], "region": "mars"}},
        )
        self.assertEqual(response.status_code, 422)

    def test_product_ids_from_message_and_fields_are_merged(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={
                "message": "Check product 6703656 in the US",
                "fields": {"product_ids": ["6703656", "6704878"]},
            },
        )
        self.assertEqual(response.status_code, 200)
        resolved = response.json()["resolved_input"]
        self.assertEqual(resolved["product_ids"], ["6703656", "6704878"])

    def test_rule_artifacts_metadata(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={"fields": {"region": "us", "system_family": "FMT"}},
        )
        self.assertEqual(response.status_code, 200)
        artifacts = response.json()["rule_artifacts"]
        self.assertGreater(artifacts["quotation_snapshot"]["products"], 0)
        self.assertGreater(artifacts["quotation_snapshot"]["rule_signals"], 0)
        self.assertEqual(artifacts["merged_rules"]["confirmed_rule_count"], 700)

    def test_detector_grid_fields_accepted(self) -> None:
        response = self.client.post(
            "/validation/check",
            json={
                "fields": {
                    "region": "us",
                    "grid_id": "8621989",
                    "grid_position": "table",
                    "detector_type": "Focus 35C",
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["status"], {"valid", "invalid", "incomplete"})
        self.assertEqual(body["resolved_input"]["grid_id"], "8621989")


class MergedRulesLoaderTest(unittest.TestCase):
    def test_load_merged_rules(self) -> None:
        artifact = load_merged_rules()
        self.assertEqual(artifact["confirmed_rule_count"], 700)
        self.assertEqual(len(artifact["rules"]), 700)

    def test_load_merged_rules_rejects_bad_shape(self) -> None:
        import json
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"not_rules": []}, handle)
            path = handle.name
        with self.assertRaises(ValueError):
            load_merged_rules(path)


if __name__ == "__main__":
    unittest.main()
