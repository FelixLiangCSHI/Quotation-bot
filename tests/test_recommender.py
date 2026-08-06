import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.natural_language import parse_quote_request
from app.recommender import QuoteRecommender, render_recommendation_text


class NaturalLanguageParsingTests(unittest.TestCase):
    def test_extracts_system_fields_and_ignores_budget_words(self):
        request = parse_quote_request(
            "I need a FMT digital X-ray system for US with Focus detector, "
            "wall stand, and table. Budget 200k RMB"
        )

        self.assertEqual("us", request.region)
        self.assertEqual("FMT", request.system_family)
        self.assertEqual("digital", request.acquisition_type)
        self.assertIn("focus", request.keywords)
        self.assertNotIn("budget", request.keywords)
        self.assertNotIn("rmb", request.keywords)
        self.assertNotIn("200", request.keywords)
        self.assertFalse(hasattr(request, "budget"))

    def test_extracts_chinese_aliases(self):
        request = parse_quote_request(
            "\u6211\u9700\u8981\u4e00\u5957\u843d\u5730\u6570\u5b57X\u5149\u7cfb\u7edf"
            "\uff0c\u4e2d\u56fd\u5e02\u573a\uff0c\u8981Focus detector"
            "\uff0c\u80f8\u7247\u67b6\u548c\u6444\u5f71\u5e8a"
        )

        self.assertEqual("china", request.region)
        self.assertEqual("FMT", request.system_family)
        self.assertEqual("digital", request.acquisition_type)
        self.assertIn("x-ray", request.keywords)
        self.assertIn("system", request.keywords)
        self.assertIn("wallstand", request.keywords)
        self.assertIn("table", request.keywords)
        self.assertIn("focus", request.keywords)


class QuoteRecommenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recommender = QuoteRecommender()

    def test_system_request_recommends_base_model_and_focus_accessory(self):
        recommendation = self.recommender.recommend_from_text(
            "I need a FMT digital X-ray system for US with Focus detector, "
            "wall stand, and table. Budget 200k RMB"
        )

        self.assertIsNotNone(recommendation.main_model)
        self.assertEqual("6704878", recommendation.main_model.product_id)
        self.assertEqual("valid", recommendation.validation.status)

        accessory_ids = {item.product_id for item in recommendation.accessories}
        accessory_text = " ".join(item.short_description for item in recommendation.accessories)
        self.assertIn("8620148", accessory_ids)
        self.assertIn("6701585", accessory_ids)
        self.assertIn("6701676", accessory_ids)
        self.assertNotIn("6705222", accessory_ids)
        self.assertIn("FOCUS", accessory_text.upper())

    def test_rendered_response_does_not_discuss_budget(self):
        recommendation = self.recommender.recommend_from_text(
            "I need a FMT digital X-ray system for US with Focus detector, budget 200k RMB"
        )

        rendered = render_recommendation_text(recommendation)

        self.assertNotIn("budget", rendered.casefold())
        self.assertNotIn("price", rendered.casefold())

    def test_drx_detector_preference_uses_drx_accessory(self):
        recommendation = self.recommender.recommend_from_text(
            "I need a FMT digital X-ray system for US with DRX detector, wall stand, and table."
        )

        detector = next(
            item
            for item in recommendation.accessories
            if item.step_id in {"fmt_step_6", "Step 6"}
        )

        self.assertIn("DRX", detector.short_description.upper())
        self.assertNotIn("FOCUS", detector.short_description.upper())

    def test_direct_product_id_keeps_product_and_reports_region_block(self):
        recommendation = self.recommender.recommend_from_text("Need product 6703656 for EU")

        self.assertIsNotNone(recommendation.main_model)
        self.assertEqual("6703656", recommendation.main_model.product_id)
        self.assertEqual("invalid", recommendation.validation.status)
        self.assertTrue(
            any(issue.code == "region_not_allowed" for issue in recommendation.validation.issues)
        )

    def test_missing_region_adds_notice(self):
        recommendation = self.recommender.recommend_from_text(
            "I need a FMT digital X-ray system with DRX detector"
        )

        self.assertIn(
            "Please confirm the sales region so region-only rules can be checked.",
            recommendation.notices,
        )

    def test_max_accessories_limits_output(self):
        recommendation = self.recommender.recommend_from_text(
            "I need a FMT digital X-ray system for US with DRX detector, wall stand, table, grid, and tube.",
            max_accessories=2,
        )

        self.assertEqual(2, len(recommendation.accessories))

    def test_sample_quote_quantity_override_is_returned(self):
        recommendation = self.recommender.recommend_from_text("Need product 6704506 for US")

        self.assertIsNotNone(recommendation.main_model)
        self.assertEqual("6704506", recommendation.main_model.product_id)
        self.assertEqual(2, recommendation.main_model.quantity)

    def test_product_line_requests_return_default_quote_profiles(self):
        cases = [
            ("Need DRX-Rise mobile system for US", "8626004", 10),
            ("Need DRX-Revolution Plus mobile system for US", "8618894", 10),
            (
                "Need Compass FMT digital system for US with DRX detector wall stand table",
                "6704878",
                25,
            ),
            (
                "Need Compass OTC digital system for US with DRX detector wall stand table",
                "8624769",
                20,
            ),
            ("Need DRX-Evolution Plus automatic system for US", "8624264", 12),
        ]

        for text, expected_main_id, minimum_rows in cases:
            with self.subTest(text=text):
                recommendation = self.recommender.recommend_from_text(text)
                row_count = (1 if recommendation.main_model else 0) + len(
                    recommendation.accessories
                )

                self.assertIsNotNone(recommendation.main_model)
                self.assertEqual(expected_main_id, recommendation.main_model.product_id)
                self.assertEqual("valid", recommendation.validation.status)
                self.assertGreaterEqual(row_count, minimum_rows)


if __name__ == "__main__":
    unittest.main()