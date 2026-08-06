import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_loader import QuotationSnapshot, load_snapshot
from app.rule_engine import QuotationRuleEngine


class SnapshotLoadingTests(unittest.TestCase):
    def test_loads_current_snapshot(self):
        snapshot = load_snapshot()

        self.assertIsInstance(snapshot, QuotationSnapshot)
        self.assertGreater(len(snapshot.products), 0)
        self.assertGreater(len(snapshot.rule_signals), 0)
        self.assertGreater(len(snapshot.compatibility_matrix), 0)
        self.assertGreater(len(snapshot.detector_grid_supports), 0)
        self.assertGreater(len(snapshot.generator_tube_specs), 0)


class RuleEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = QuotationRuleEngine(load_snapshot())

    def test_us_and_canada_only_product_is_valid_in_us(self):
        result = self.engine.check_configuration(["6703656"], region="US")

        self.assertEqual("valid", result.status)
        self.assertEqual((), result.issues)

    def test_us_and_canada_only_product_is_invalid_in_eu(self):
        result = self.engine.check_configuration(["6703656"], region="EU")

        self.assertEqual("invalid", result.status)
        self.assertTrue(
            any(issue.code == "region_not_allowed" for issue in result.issues)
        )
        self.assertEqual(1, len(result.issues))

    def test_unknown_product_is_invalid(self):
        result = self.engine.check_configuration(["missing-product"], region="US")

        self.assertEqual("invalid", result.status)
        self.assertTrue(any(issue.code == "unknown_product" for issue in result.issues))

    def test_missing_region_is_incomplete(self):
        result = self.engine.check_configuration(["6703656"])

        self.assertEqual("incomplete", result.status)
        self.assertIn("region", result.missing_fields)

    def test_not_supported_system_combination_is_invalid(self):
        result = self.engine.check_configuration(
            [],
            system_family="FMT",
            acquisition_type="digital",
            tube_stand_id="6704522",
            wallstand_id="6701585",
            table_id="6701676",
        )

        self.assertEqual("invalid", result.status)
        self.assertTrue(
            any(issue.code == "system_not_supported" for issue in result.issues)
        )

    def test_conditional_system_combination_returns_warning(self):
        result = self.engine.check_configuration(
            [],
            system_family="FMT",
            acquisition_type="digital",
            tube_stand_id="6704522",
            wallstand_id="6705214",
            table_id="6701676",
        )

        self.assertEqual("valid", result.status)
        self.assertTrue(
            any(
                issue.code == "system_conditionally_supported"
                for issue in result.issues
            )
        )

    def test_partial_system_combination_is_incomplete(self):
        result = self.engine.check_configuration(
            [],
            system_family="FMT",
            acquisition_type="digital",
            tube_stand_id="6704522",
        )

        self.assertEqual("incomplete", result.status)
        self.assertIn("wallstand_id", result.missing_fields)
        self.assertIn("table_id", result.missing_fields)

    def test_supported_detector_grid_combination_is_valid(self):
        result = self.engine.check_configuration(
            [],
            grid_id="8621989",
            grid_position="table",
            detector_type="Focus 43C",
        )

        self.assertEqual("valid", result.status)
        self.assertEqual((), result.issues)

    def test_unsupported_grid_position_is_invalid(self):
        result = self.engine.check_configuration(
            [],
            grid_id="8621989",
            grid_position="wall",
        )

        self.assertEqual("invalid", result.status)
        self.assertTrue(
            any(issue.code == "grid_position_not_supported" for issue in result.issues)
        )

    def test_unsupported_detector_grid_combination_is_invalid(self):
        result = self.engine.check_configuration(
            [],
            grid_id="8621989",
            detector_type="Focus 35C",
        )

        self.assertEqual("invalid", result.status)
        self.assertTrue(
            any(issue.code == "detector_grid_not_supported" for issue in result.issues)
        )

    def test_detector_grid_without_grid_id_is_incomplete(self):
        result = self.engine.check_configuration([], detector_type="Focus 43C")

        self.assertEqual("incomplete", result.status)
        self.assertIn("grid_id", result.missing_fields)

    def test_known_generator_without_tube_spec_is_valid(self):
        result = self.engine.check_configuration([], generator="CGN-80")

        self.assertEqual("valid", result.status)
        self.assertEqual((), result.issues)

    def test_known_generator_tube_spec_returns_info(self):
        result = self.engine.check_configuration(
            [],
            generator="CGN-80",
            tube_spec="w/ E7254 & Ray-15_1/RAD-60",
            spec_category="output_kw_at_100ma",
        )

        self.assertEqual("valid", result.status)
        self.assertTrue(
            any(issue.code == "generator_tube_spec_found" for issue in result.issues)
        )
        self.assertTrue(any(": 80" in issue.message for issue in result.issues))

    def test_generator_tube_without_category_returns_all_matching_specs(self):
        result = self.engine.check_configuration(
            [],
            generator="CGN-80",
            tube_spec="w/ E7254 & Ray-15_1/RAD-60",
        )

        self.assertEqual("valid", result.status)
        self.assertEqual(4, len(result.issues))

    def test_unknown_generator_is_invalid(self):
        result = self.engine.check_configuration([], generator="missing-generator")

        self.assertEqual("invalid", result.status)
        self.assertTrue(any(issue.code == "unknown_generator" for issue in result.issues))

    def test_missing_generator_for_tube_spec_is_incomplete(self):
        result = self.engine.check_configuration([], tube_spec="w/ E7254 & Ray-15_1/RAD-60")

        self.assertEqual("incomplete", result.status)
        self.assertIn("generator", result.missing_fields)

    def test_missing_generator_tube_spec_is_invalid(self):
        result = self.engine.check_configuration(
            [],
            generator="CGF-50-SE (FMT only)",
            tube_spec="Phase Line",
            spec_category="phase_line",
        )

        self.assertEqual("invalid", result.status)
        self.assertTrue(
            any(issue.code == "generator_tube_spec_not_found" for issue in result.issues)
        )


if __name__ == "__main__":
    unittest.main()
