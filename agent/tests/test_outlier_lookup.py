import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "mcp-server" / "outliers" / "outlier_lookup.py"
)
SPEC = importlib.util.spec_from_file_location("outlier_lookup", MODULE_PATH)
outlier_lookup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(outlier_lookup)


def _deep_get(doc, dotted_key):
    current = doc
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _matches(doc, query):
    for key, expected in query.items():
        actual = _deep_get(doc, key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in expected["$in"]:
                return False
            continue
        if actual != expected:
            return False
    return True


def _project(doc, projection):
    if not projection:
        return dict(doc)
    projected = {"_id": doc["_id"]}
    for key, enabled in projection.items():
        if not enabled or key == "_id":
            continue
        value = _deep_get(doc, key)
        if value is None:
            continue
        cursor = projected
        parts = key.split(".")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return projected


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def limit(self, value):
        return self.docs[:value]


class FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query, projection=None):
        return FakeCursor(
            [_project(doc, projection) for doc in self.docs if _matches(doc, query)]
        )

    def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None


class OutlierLookupTests(unittest.TestCase):
    def test_find_outliers_returns_ranked_records_with_curve_summary(self):
        tests = [
            {
                "_id": "{TEST-1}",
                "valueColumns": [
                    {
                        "_id": "{FORCE-1}_Value",
                        "valueTableId": "{FORCE-1}",
                        "unitTableId": "Zwick.Unittable.Force",
                        "name": "Standard force",
                    }
                ],
                "TestParametersFlat": {
                    "TYPE_OF_TESTING_STR": "tensile",
                    "SPECIMEN_WIDTH": 10.0,
                    "SPECIMEN_THICKNESS": 2.0,
                    "TEST_SPEED": 1.0,
                    "CUSTOMER": "Company_1",
                    "TESTER": "Tester_1",
                },
            },
            {
                "_id": "{TEST-2}",
                "valueColumns": [
                    {
                        "_id": "{FORCE-2}_Value",
                        "valueTableId": "{FORCE-2}",
                        "unitTableId": "Zwick.Unittable.Force",
                        "name": "Standard force",
                    }
                ],
                "TestParametersFlat": {
                    "TYPE_OF_TESTING_STR": "tensile",
                    "SPECIMEN_WIDTH": 10.2,
                    "SPECIMEN_THICKNESS": 2.1,
                    "TEST_SPEED": 1.0,
                    "CUSTOMER": "Company_1",
                    "TESTER": "Tester_2",
                },
            },
            {
                "_id": "{TEST-3}",
                "valueColumns": [
                    {
                        "_id": "{FORCE-3}_Value",
                        "valueTableId": "{FORCE-3}",
                        "unitTableId": "Zwick.Unittable.Force",
                        "name": "Standard force",
                    }
                ],
                "TestParametersFlat": {
                    "TYPE_OF_TESTING_STR": "tensile",
                    "SPECIMEN_WIDTH": 9.9,
                    "SPECIMEN_THICKNESS": 2.0,
                    "TEST_SPEED": 1.0,
                    "CUSTOMER": "Company_2",
                    "TESTER": "Tester_3",
                },
            },
            {
                "_id": "{TEST-4}",
                "valueColumns": [
                    {
                        "_id": "{FORCE-4}_Value",
                        "valueTableId": "{FORCE-4}",
                        "unitTableId": "Zwick.Unittable.Force",
                        "name": "Standard force",
                    }
                ],
                "TestParametersFlat": {
                    "TYPE_OF_TESTING_STR": "tensile",
                    "SPECIMEN_WIDTH": 10.1,
                    "SPECIMEN_THICKNESS": 2.0,
                    "TEST_SPEED": 1.0,
                    "CUSTOMER": "Company_2",
                    "TESTER": "Tester_4",
                },
            },
            {
                "_id": "{TEST-5}",
                "valueColumns": [
                    {
                        "_id": "{FORCE-5}_Value",
                        "valueTableId": "{FORCE-5}",
                        "unitTableId": "Zwick.Unittable.Force",
                        "name": "Standard force",
                    }
                ],
                "TestParametersFlat": {
                    "TYPE_OF_TESTING_STR": "tensile",
                    "SPECIMEN_WIDTH": 10.0,
                    "SPECIMEN_THICKNESS": 2.0,
                    "TEST_SPEED": 1.0,
                    "CUSTOMER": "Company_3",
                    "TESTER": "Tester_5",
                },
            },
            {
                "_id": "{TEST-OUTLIER}",
                "valueColumns": [
                    {
                        "_id": "{FORCE-X}_Value",
                        "valueTableId": "{FORCE-X}",
                        "unitTableId": "Zwick.Unittable.Force",
                        "name": "Standard force",
                    }
                ],
                "TestParametersFlat": {
                    "TYPE_OF_TESTING_STR": "tensile",
                    "SPECIMEN_WIDTH": 18.0,
                    "SPECIMEN_THICKNESS": 2.0,
                    "TEST_SPEED": 1.0,
                    "CUSTOMER": "Company_X",
                    "TESTER": "Tester_X",
                    "Date": "2026-03-19",
                },
            },
        ]
        values = [
            {
                "_id": "curve-outlier",
                "metadata": {
                    "refId": "{TEST-OUTLIER}",
                    "childId": "{FORCE-X}.{FORCE-X}_Value",
                },
                "values": [0.0, 12.0, -15.0, 8.0],
            }
        ]

        result = outlier_lookup.find_outliers(
            FakeCollection(tests),
            FakeCollection(values),
            limit=3,
            sample_size=10,
            test_type="tensile",
        )

        self.assertEqual(result["sampleSize"], 6)
        self.assertGreaterEqual(len(result["outliers"]), 1)
        self.assertEqual(result["outliers"][0]["testId"], "{TEST-OUTLIER}")
        self.assertEqual(result["outliers"][0]["metrics"][3]["value"], "15")
        self.assertIn("Standard force", result["outliers"][0]["signals"][2])


if __name__ == "__main__":
    unittest.main()
