"""Tests for GET /data/sources - Phase 4 (keep Beta data file-based)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.api import app


class DataSourcesEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_reports_file_based_storage(self) -> None:
        response = self.client.get("/data/sources")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["storage"], "file-based (JSON + Markdown)")
        self.assertIsNone(body["database"])
        self.assertIsNone(body["search_index"])
        self.assertIsNone(body["vector_index"])

    def test_reports_snapshot_provenance(self) -> None:
        body = self.client.get("/data/sources").json()
        snapshot = body["sources"]["quotation_snapshot.json"]
        self.assertEqual(snapshot["role"], "product/data source")
        self.assertEqual(snapshot["source_file"], "quotation_data.xlsx")
        self.assertGreater(snapshot["products"], 0)
        self.assertGreater(snapshot["rule_signals"], 0)

    def test_reports_rule_artifact(self) -> None:
        body = self.client.get("/data/sources").json()
        rules = body["sources"]["rules/merged_rules.json"]
        self.assertEqual(rules["role"], "confirmed rule artifact")
        self.assertEqual(rules["confirmed_rule_count"], 700)

    def test_reports_markdown_docs_role(self) -> None:
        body = self.client.get("/data/sources").json()
        self.assertEqual(
            body["sources"]["docs/*.md"]["role"],
            "implementation notes and workflow explanation",
        )


if __name__ == "__main__":
    unittest.main()
