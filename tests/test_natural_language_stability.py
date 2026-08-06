import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.natural_language import parse_discount_rate
from app.quotation import (
    DEMO_A_PROMPT,
    merge_configuration,
    merge_duplicate_quotation_lines,
    normalize_configuration,
)
from app.recommender import QuoteRecommender
from app.serialization import to_jsonable


def _accessory_quantity(configuration, name):
    for accessory in configuration.get("accessories") or []:
        if accessory["name"] == name:
            return accessory["quantity"]
    return 0


class PerSystemQuantityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recommender = QuoteRecommender()

    def _configure(self, text):
        recommendation = to_jsonable(self.recommender.recommend_from_text(text))
        return normalize_configuration(text, recommendation)

    def test_one_detector_per_system(self):
        configuration = self._configure(
            "ABC Hospital needs two systems with one wireless detector per system."
        )

        self.assertEqual(2, configuration["quantity"])
        self.assertEqual(
            2,
            _accessory_quantity(configuration, "Wireless Detector"),
        )

    def test_two_detectors_per_system(self):
        configuration = self._configure(
            "ABC Hospital needs 3 systems with 2 detectors per system."
        )

        self.assertEqual(3, configuration["quantity"])
        self.assertEqual(
            6,
            _accessory_quantity(configuration, "Wireless Detector"),
        )

    def test_for_each_system_quantity(self):
        for phrase in ("for each system", "for every system"):
            with self.subTest(phrase=phrase):
                configuration = self._configure(
                    f"ABC Hospital needs two systems with one detector {phrase}."
                )

                self.assertEqual(2, configuration["quantity"])
                self.assertEqual(
                    2,
                    _accessory_quantity(configuration, "Wireless Detector"),
                )

    def test_plain_accessory_quantity_is_not_scaled(self):
        configuration = self._configure(
            "ABC Hospital needs two systems and two wireless detectors."
        )

        self.assertEqual(2, configuration["quantity"])
        self.assertEqual(
            2,
            _accessory_quantity(configuration, "Wireless Detector"),
        )


class LatestCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recommender = QuoteRecommender()
        cls.base_configuration = normalize_configuration(
            DEMO_A_PROMPT,
            to_jsonable(cls.recommender.recommend_from_text(DEMO_A_PROMPT)),
        )

    def _merge(self, latest_turn):
        full_conversation = f"{DEMO_A_PROMPT}\n{latest_turn}"
        recommendation = to_jsonable(
            self.recommender.recommend_from_text(full_conversation)
        )
        return merge_configuration(
            self.base_configuration,
            latest_turn,
            full_conversation,
            recommendation,
        )

    def test_latest_region_correction_wins(self):
        merged = self._merge("Actually change the region to Malaysia")

        self.assertEqual("Malaysia", merged["region"])
        self.assertEqual("ABC Hospital", merged["customer_name"])

    def test_latest_currency_correction_wins(self):
        merged = self._merge("Use SGD instead")

        self.assertEqual("SGD", merged["currency"])

    def test_latest_product_correction_wins(self):
        merged = self._merge("Replace DRX Compass with DRX Revolution")

        self.assertEqual(
            "DRX Revolution Mobile Radiography System",
            merged["main_product"],
        )

    def test_latest_quantity_correction_wins(self):
        merged = self._merge("The quantity should be three")

        self.assertEqual(3, merged["quantity"])

    def test_latest_discount_correction_wins(self):
        merged = self._merge("Change the discount to 40%")

        self.assertAlmostEqual(0.40, merged["discount_rate"])

    def test_confirmed_fields_survive_a_discount_only_turn(self):
        merged = self._merge("35%")

        self.assertAlmostEqual(0.35, merged["discount_rate"])
        self.assertEqual("Singapore", merged["region"])
        self.assertEqual("USD", merged["currency"])
        self.assertEqual("ABC Hospital", merged["customer_name"])
        self.assertEqual(2, merged["quantity"])


class DiscountParsingTests(unittest.TestCase):
    def test_deposit_percentage_is_not_discount(self):
        for text in (
            "We agreed on a 30% deposit",
            "The customer pays a 30% down payment",
            "There is a 30% tax on this order",
            "Invoice 30% installation completion",
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_discount_rate(text))

    def test_bare_percentage_after_discount_question(self):
        self.assertAlmostEqual(0.30, parse_discount_rate("30%"))
        self.assertAlmostEqual(
            0.30,
            parse_discount_rate("ABC Hospital needs two systems.\n30%"),
        )

    def test_bare_percentage_can_be_disabled(self):
        self.assertIsNone(parse_discount_rate("30%", allow_bare_percentage=False))

    def test_discount_markers_are_recognised(self):
        self.assertAlmostEqual(0.30, parse_discount_rate("Apply a 30% discount"))
        self.assertAlmostEqual(
            0.35,
            parse_discount_rate("Give the customer 35 percent off"),
        )
        self.assertAlmostEqual(0.40, parse_discount_rate("Change the discount to 40%"))

    def test_discount_wins_over_unrelated_percentage(self):
        self.assertAlmostEqual(
            0.25,
            parse_discount_rate("A 30% deposit applies and a 25% discount"),
        )


class DuplicateAccessoryTests(unittest.TestCase):
    def test_duplicate_accessories_are_merged(self):
        configuration = normalize_configuration(
            "ABC Hospital needs two systems, two wireless detectors "
            "and wireless detectors.",
            {},
        )
        detectors = [
            accessory
            for accessory in configuration["accessories"]
            if accessory["name"] == "Wireless Detector"
        ]

        self.assertEqual(1, len(detectors))
        self.assertEqual(2, detectors[0]["quantity"])

    def test_focus_detector_does_not_duplicate_wireless_detector(self):
        configuration = normalize_configuration(
            "ABC Hospital needs one system with Focus wireless detectors.",
            {},
        )
        names = [accessory["name"] for accessory in configuration["accessories"]]

        self.assertEqual(["Focus Detector"], names)

    def test_duplicate_quotation_lines_are_merged(self):
        lines = [
            {
                "product_code": "DET-WL-01",
                "description": "Wireless Detector",
                "quantity": 2,
                "list_unit_price": 15_000.0,
                "quotation_unit_price": 10_500.0,
            },
            {
                "product_code": "DET-WL-01",
                "description": "Wireless Detector",
                "quantity": 1,
                "list_unit_price": 15_000.0,
                "quotation_unit_price": 10_500.0,
            },
        ]

        merged = merge_duplicate_quotation_lines(lines)

        self.assertEqual(1, len(merged))
        self.assertEqual(2, merged[0]["quantity"])

    def test_different_accessories_are_kept(self):
        lines = [
            {"product_code": "DET-WL-01", "quantity": 2},
            {"product_code": "WAR-3Y-01", "quantity": 1},
        ]

        merged = merge_duplicate_quotation_lines(lines)

        self.assertEqual(["DET-WL-01", "WAR-3Y-01"], [line["product_code"] for line in merged])


if __name__ == "__main__":
    unittest.main()
