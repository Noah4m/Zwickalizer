import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "mcp-server" / "db" / "test_metadata.py"
)
SPEC = importlib.util.spec_from_file_location("test_metadata", MODULE_PATH)
test_metadata = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(test_metadata)


class TestMetadataTests(unittest.TestCase):
    def test_normalize_test_document_reads_multiple_aliases(self):
        doc = {
            "_id": "{TEST-1}",
            "valueColumns": [{"name": "Force"}, {"name": "Strain"}],
            "TestParametersFlat": {
                "TYPE_OF_TESTING_STR": "tensile",
                "CUSTOMER": "Company_1",
                "MACHINE_DATA": "Werknr. 104047",
                "TESTER": "Tester_1",
                "STANDARD": "DIN EN",
                "SPECIMEN_WIDTH": 0.015,
                "Diameter": 0.002,
                "Date/Clock time": "2021-11-26T09:42:38+01:00",
            },
        }

        normalized = test_metadata.normalize_test_document(doc)

        self.assertEqual(normalized["testId"], "{TEST-1}")
        self.assertEqual(normalized["testType"], "tensile")
        self.assertEqual(normalized["customer"], "Company_1")
        self.assertEqual(normalized["machine"], "Werknr. 104047")
        self.assertEqual(normalized["standard"], "DIN EN")
        self.assertEqual(normalized["diameter"], 0.002)
        self.assertEqual(normalized["availableColumns"], ["Force", "Strain"])
        self.assertEqual(normalized["date"], "2021-11-26T09:42:38+01:00")

    def test_exact_date_filter_supports_iso_and_dotted_variants(self):
        filt = test_metadata.exact_date_filter("2021-11-26")
        or_clauses = filt["$or"]

        self.assertIn({"TestParametersFlat.date": "2021-11-26"}, or_clauses)
        self.assertIn({"TestParametersFlat.Date": "26.11.2021"}, or_clauses)
        self.assertIn(
            {"TestParametersFlat.Date/Clock time": {"$regex": "^2021\\-11\\-26"}},
            or_clauses,
        )

    def test_equality_filter_uses_aliases(self):
        filt = test_metadata.equality_filter(("CUSTOMER", "Customer"), "Company_7")

        self.assertEqual(
            filt,
            {
                "$or": [
                    {"TestParametersFlat.CUSTOMER": "Company_7"},
                    {"TestParametersFlat.Customer": "Company_7"},
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()
