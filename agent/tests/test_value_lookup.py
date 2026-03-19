import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "mcp-server" / "db" / "value_lookup.py"
)
SPEC = importlib.util.spec_from_file_location("value_lookup", MODULE_PATH)
value_lookup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(value_lookup)


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
        if isinstance(expected, dict):
            if "$in" in expected:
                if actual not in expected["$in"]:
                    return False
                continue
            return False
        if actual != expected:
            return False
    return True


def _project(doc, projection):
    if not projection:
        return dict(doc)
    projected = {"_id": doc["_id"]} if projection.get("_id", 1) else {}
    for key, enabled in projection.items():
        if not enabled or key == "_id":
            continue
        parts = key.split(".")
        source = doc
        target = projected
        for index, part in enumerate(parts):
            if not isinstance(source, dict) or part not in source:
                break
            source = source[part]
            if index == len(parts) - 1:
                target[part] = source
            else:
                target = target.setdefault(part, {})
    return projected


class FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query):
        return [_project(doc, None) for doc in self.docs if _matches(doc, query)]


class ValueLookupTests(unittest.TestCase):
    def test_build_expected_value_columns_ignores_key_entries(self):
        test = {
            "_id": "{TEST-1}",
            "valueColumns": [
                {
                    "_id": "{COL-1}_Key",
                    "valueTableId": "{TABLE-1}",
                    "name": "Force",
                    "unitTableId": "Zwick.Unit.Force",
                },
                {
                    "_id": "{COL-1}_Value",
                    "valueTableId": "{TABLE-1}",
                    "name": "Force",
                    "unitTableId": "Zwick.Unit.Force",
                },
            ],
        }

        expected = value_lookup.build_expected_value_columns(test)

        self.assertEqual(
            expected,
            [
                {
                    "testId": "{TEST-1}",
                    "valueColumnId": "{COL-1}_Value",
                    "valueTableId": "{TABLE-1}",
                    "childId": "{TABLE-1}.{COL-1}_Value",
                    "name": "Force",
                    "unitTableId": "Zwick.Unit.Force",
                }
            ],
        )

    def test_resolve_test_value_columns_matches_value_entries_and_flags_duplicates(self):
        test_id = "{TEST-2}"
        tests_col = FakeCollection(
            [
                {
                    "_id": test_id,
                    "valueColumns": [
                        {
                            "_id": "{COL-2}_Value",
                            "valueTableId": "{TABLE-2}",
                            "name": "Strain",
                            "unitTableId": "Zwick.Unit.Strain",
                        },
                        {
                            "_id": "{COL-2}_Key",
                            "valueTableId": "{TABLE-2}",
                            "name": "Strain",
                            "unitTableId": "Zwick.Unit.Strain",
                        },
                    ],
                }
            ]
        )
        values_col = FakeCollection(
            [
                {
                    "_id": "doc-1",
                    "values": [1.5, 2.5],
                    "valuesCount": 2,
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-2}.{COL-2}_Value",
                    },
                },
                {
                    "_id": "doc-2",
                    "values": [3.5],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-2}.{COL-2}_Value",
                    },
                },
                {
                    "_id": "doc-key",
                    "values": [999],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-2}.{COL-2}_Key",
                    },
                },
                {
                    "_id": "doc-other-test",
                    "values": [7.5],
                    "metadata": {
                        "refId": "{TEST-OTHER}",
                        "childId": "{TABLE-2}.{COL-2}_Value",
                    },
                },
            ]
        )

        resolved = value_lookup.resolve_test_value_columns(tests_col, values_col, test_id)

        self.assertEqual(len(resolved), 2)
        self.assertEqual(
            [item["sourceDocumentId"] for item in resolved],
            ["doc-1", "doc-2"],
        )
        self.assertTrue(all(item["duplicate"] for item in resolved))
        self.assertTrue(all(item["duplicateCount"] == 2 for item in resolved))
        self.assertEqual(resolved[0]["childId"], "{TABLE-2}.{COL-2}_Value")
        self.assertEqual(resolved[0]["name"], "Strain")
        self.assertEqual(resolved[0]["unitTableId"], "Zwick.Unit.Strain")
        self.assertNotIn("values", resolved[0])
        self.assertEqual(resolved[1]["valuesCount"], 1)

    def test_resolve_test_value_columns_can_include_truncated_values(self):
        test_id = "{TEST-4}"
        tests_col = FakeCollection(
            [
                {
                    "_id": test_id,
                    "valueColumns": [
                        {
                            "_id": "{COL-4}_Value",
                            "valueTableId": "{TABLE-4}",
                            "name": "Stress",
                        }
                    ],
                }
            ]
        )
        values_col = FakeCollection(
            [
                {
                    "_id": "doc-4",
                    "values": [10, 20, 30],
                    "valuesCount": 3,
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-4}.{COL-4}_Value",
                    },
                }
            ]
        )

        resolved = value_lookup.resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            include_values=True,
            values_limit=2,
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["values"], [10, 20])
        self.assertEqual(resolved[0]["valuesReturned"], 2)
        self.assertTrue(resolved[0]["valuesTruncated"])
        self.assertEqual(resolved[0]["valuesCount"], 3)

    def test_resolve_test_value_columns_can_filter_to_value_column_index(self):
        test_id = "{TEST-4B}"
        tests_col = FakeCollection(
            [
                {
                    "_id": test_id,
                    "valueColumns": [
                        {
                            "_id": "{COL-4B-A}_Value",
                            "valueTableId": "{TABLE-4B-A}",
                            "name": "Strain / Deformation",
                        },
                        {
                            "_id": "{COL-4B-B}_Value",
                            "valueTableId": "{TABLE-4B-B}",
                            "name": "Force",
                        },
                    ],
                }
            ]
        )
        values_col = FakeCollection(
            [
                {
                    "_id": "doc-4b-a",
                    "values": [1, 2, 3],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-4B-A}.{COL-4B-A}_Value",
                    },
                },
                {
                    "_id": "doc-4b-b",
                    "values": [4, 5, 6],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-4B-B}.{COL-4B-B}_Value",
                    },
                },
            ]
        )

        resolved = value_lookup.resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            include_values=True,
            value_column_index=0,
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["sourceDocumentId"], "doc-4b-a")
        self.assertEqual(resolved[0]["name"], "Strain / Deformation")
        self.assertEqual(resolved[0]["values"], [1, 2, 3])

    def test_resolve_test_value_columns_indexed_lookup_keeps_non_value_column(self):
        test_id = "{TEST-4C}"
        tests_col = FakeCollection(
            [
                {
                    "_id": test_id,
                    "valueColumns": [
                        {
                            "_id": "{COL-4C-A}",
                            "valueTableId": "{TABLE-4C-A}",
                            "name": "Strain / Deformation",
                        },
                        {
                            "_id": "{COL-4C-B}_Value",
                            "valueTableId": "{TABLE-4C-B}",
                            "name": "Force",
                        },
                    ],
                }
            ]
        )
        values_col = FakeCollection(
            [
                {
                    "_id": "doc-4c-a",
                    "values": [0.1, 0.2, 0.3],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-4C-A}.{COL-4C-A}",
                    },
                },
                {
                    "_id": "doc-4c-b",
                    "values": [4, 5, 6],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-4C-B}.{COL-4C-B}_Value",
                    },
                },
            ]
        )

        resolved = value_lookup.resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            include_values=True,
            value_column_index=0,
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["sourceDocumentId"], "doc-4c-a")
        self.assertEqual(resolved[0]["valueColumnId"], "{COL-4C-A}")
        self.assertEqual(resolved[0]["values"], [0.1, 0.2, 0.3])

    def test_resolve_test_value_columns_non_strict_returns_all_ref_matches(self):
        test_id = "{TEST-5}"
        tests_col = FakeCollection(
            [
                {
                    "_id": test_id,
                    "valueColumns": [
                        {
                            "_id": "{COL-5}_Value",
                            "valueTableId": "{TABLE-5}",
                            "name": "Force",
                        },
                        {
                            "_id": "{COL-5}_Key",
                            "valueTableId": "{TABLE-5}",
                            "name": "Force",
                        },
                    ],
                }
            ]
        )
        values_col = FakeCollection(
            [
                {
                    "_id": "doc-value",
                    "values": [11],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-5}.{COL-5}_Value",
                    },
                },
                {
                    "_id": "doc-key",
                    "values": [22],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-5}.{COL-5}_Key",
                    },
                },
                {
                    "_id": "doc-unmapped",
                    "values": [33],
                    "metadata": {
                        "refId": test_id,
                        "childId": "legacy.child.id",
                    },
                },
            ]
        )

        resolved = value_lookup.resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            strict=False,
        )

        self.assertEqual(
            [item["sourceDocumentId"] for item in resolved],
            ["doc-unmapped", "doc-key", "doc-value"],
        )
        self.assertFalse(resolved[0]["matchedTestValueColumn"])
        self.assertIsNone(resolved[0]["valueColumnId"])
        self.assertTrue(resolved[1]["matchedTestValueColumn"])
        self.assertEqual(resolved[1]["valueColumnId"], "{COL-5}_Key")
        self.assertEqual(resolved[2]["valueColumnId"], "{COL-5}_Value")

    def test_resolve_test_value_columns_invalid_index_returns_no_matches(self):
        test_id = "{TEST-5B}"
        tests_col = FakeCollection(
            [
                {
                    "_id": test_id,
                    "valueColumns": [
                        {
                            "_id": "{COL-5B}_Value",
                            "valueTableId": "{TABLE-5B}",
                            "name": "Force",
                        }
                    ],
                }
            ]
        )
        values_col = FakeCollection(
            [
                {
                    "_id": "doc-5b",
                    "values": [11],
                    "metadata": {
                        "refId": test_id,
                        "childId": "{TABLE-5B}.{COL-5B}_Value",
                    },
                }
            ]
        )

        resolved = value_lookup.resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            value_column_index=3,
        )

        self.assertEqual(resolved, [])

    def test_extract_value_arrays_returns_only_values_lists(self):
        arrays = value_lookup.extract_value_arrays(
            [
                {"values": [1, 2, 3]},
                {"values": [4]},
                {"valuesCount": 5},
            ]
        )

        self.assertEqual(arrays, [[1, 2, 3], [4]])

    def test_find_value_column_by_name_returns_only_value_variant(self):
        test = {
            "_id": "{TEST-3}",
            "valueColumns": [
                {
                    "_id": "{COL-3}_Key",
                    "valueTableId": "{TABLE-3}",
                    "name": "Modulus",
                },
                {
                    "_id": "{COL-3}_Value",
                    "valueTableId": "{TABLE-3}",
                    "name": "Modulus",
                },
            ],
        }

        value_column = value_lookup.find_value_column_by_name(test, "Modulus")

        self.assertEqual(value_column["_id"], "{COL-3}_Value")

    def test_numeric_values_keeps_ints_and_floats_but_not_bools(self):
        values = value_lookup.numeric_values([1, 2.5, True, "3", None, 4])
        self.assertEqual(values, [1, 2.5, 4])


if __name__ == "__main__":
    unittest.main()
