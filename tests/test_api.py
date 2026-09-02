import unittest
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated",
    category=Warning,
)

from fastapi.testclient import TestClient

from app.api import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_recommend_returns_structured_quote_result(self):
        response = self.client.post(
            "/recommend",
            json={
                "message": "I need a FMT digital X-ray system for US with Focus detector, wall stand, and table.",
                "max_accessories": 3,
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        recommendation = payload["recommendation"]

        self.assertIn("I recommend", payload["answer"])
        self.assertEqual("6704878", recommendation["main_model"]["product_id"])
        self.assertEqual("valid", recommendation["validation"]["status"])
        self.assertEqual(3, len(recommendation["accessories"]))
        self.assertTrue(
            any(
                accessory["product_id"] == "8620148"
                for accessory in recommendation["accessories"]
            )
        )

    def test_recommend_accepts_region_outside_message(self):
        response = self.client.post(
            "/recommend",
            json={
                "message": "I need a FMT digital X-ray system with Focus detector, wall stand, and table.",
                "region": "us",
                "max_accessories": 3,
            },
        )

        self.assertEqual(200, response.status_code)
        recommendation = response.json()["recommendation"]

        self.assertEqual("us", recommendation["request"]["region"])
        self.assertEqual("valid", recommendation["validation"]["status"])
        self.assertNotIn(
            "Please confirm the sales region so region-only rules can be checked.",
            recommendation["notices"],
        )

    def test_recommend_rejects_blank_message(self):
        response = self.client.post("/recommend", json={"message": "   "})

        self.assertEqual(422, response.status_code)

    def test_recommend_rejects_oversized_message(self):
        response = self.client.post("/recommend", json={"message": "x" * 4001})

        self.assertEqual(422, response.status_code)

    def test_validation_check_rejects_too_many_product_ids(self):
        response = self.client.post(
            "/validation/check",
            json={"fields": {"product_ids": [f"{index:07d}" for index in range(101)]}},
        )

        self.assertEqual(422, response.status_code)

    def test_validation_check_rejects_oversized_product_id(self):
        response = self.client.post(
            "/validation/check",
            json={"fields": {"product_ids": ["x" * 41]}},
        )

        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()