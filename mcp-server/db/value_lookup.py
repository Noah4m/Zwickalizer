from typing import Any

try:
    from bson import ObjectId
except ModuleNotFoundError:  # pragma: no cover - optional for unit tests
    ObjectId = None


def _dedupe(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def build_test_id_candidates(test_id: Any) -> list[Any]:
    candidates = [test_id]

    if isinstance(test_id, str):
        stripped = test_id.strip()
        if stripped and stripped != test_id:
            candidates.append(stripped)
        if ObjectId is not None:
            try:
                candidates.append(ObjectId(test_id))
            except Exception:
                pass
    else:
        candidates.append(str(test_id))

    return _dedupe(candidates)


def build_ref_id_query(test_id: Any) -> Any:
    candidates = build_test_id_candidates(test_id)
    if len(candidates) == 1:
        return candidates[0]
    return {"$in": candidates}


def find_test_by_id(tests_col: Any, test_id: Any, projection: dict | None = None) -> dict | None:
    for candidate in build_test_id_candidates(test_id):
        test = tests_col.find_one({"_id": candidate}, projection)
        if test is not None:
            return test
    return None


def is_value_column(value_column: dict[str, Any]) -> bool:
    value_column_id = value_column.get("_id")
    return isinstance(value_column_id, str) and value_column_id.endswith("_Value")


def build_child_id(value_column: dict[str, Any]) -> str | None:
    value_table_id = value_column.get("valueTableId")
    value_column_id = value_column.get("_id")
    if not isinstance(value_table_id, str) or not isinstance(value_column_id, str):
        return None
    return f"{value_table_id}.{value_column_id}"


def build_expected_value_columns(
    test: dict[str, Any],
    value_only: bool = True,
    value_column_index: int | None = None,
) -> list[dict[str, Any]]:
    test_id = str(test.get("_id"))
    expected: list[dict[str, Any]] = []
    value_columns = test.get("valueColumns", []) or []
    if isinstance(value_column_index, int):
        if value_column_index < 0 or value_column_index >= len(value_columns):
            return []
        value_columns = [value_columns[value_column_index]]

    for value_column in value_columns:
        if not isinstance(value_column, dict):
            continue
        if value_only and not is_value_column(value_column):
            continue

        child_id = build_child_id(value_column)
        if child_id is None:
            continue

        expected.append(
            {
                "testId": test_id,
                "valueColumnId": value_column["_id"],
                "valueTableId": value_column["valueTableId"],
                "childId": child_id,
                "name": value_column.get("name"),
                "unitTableId": value_column.get("unitTableId"),
            }
        )

    return expected


def find_value_column_by_name(test: dict[str, Any], column_name: str) -> dict[str, Any] | None:
    for value_column in test.get("valueColumns", []) or []:
        if not isinstance(value_column, dict):
            continue
        if value_column.get("name") != column_name:
            continue
        if is_value_column(value_column):
            return value_column
    return None


def resolve_value_column_documents(
    values_col: Any, test_id: Any, value_column: dict[str, Any]
) -> list[dict[str, Any]]:
    if not is_value_column(value_column):
        return []

    child_id = build_child_id(value_column)
    if child_id is None:
        return []

    docs = list(
        values_col.find(
            {
                "metadata.refId": build_ref_id_query(test_id),
                "metadata.childId": child_id,
            }
        )
    )

    return [
        doc
        for doc in docs
        if doc.get("metadata", {}).get("childId") == child_id and str(child_id).endswith("_Value")
    ]


def resolve_test_value_columns(
    tests_col: Any,
    values_col: Any,
    test_id: Any,
    strict: bool = True,
    include_values: bool = False,
    values_limit: int | None = None,
    value_column_index: int | None = None,
) -> list[dict[str, Any]] | None:
    test = find_test_by_id(
        tests_col,
        test_id,
        {"_id": 1, "valueColumns": 1},
    )
    if test is None:
        return None

    expected = build_expected_value_columns(
        test,
        value_only=False if value_column_index is not None else strict,
        value_column_index=value_column_index,
    )
    if (strict or value_column_index is not None) and not expected:
        return []

    expected_by_child_id = {entry["childId"]: entry for entry in expected}
    query: dict[str, Any] = {
        "metadata.refId": build_ref_id_query(test["_id"]),
    }
    if strict or value_column_index is not None:
        query["metadata.childId"] = {"$in": list(expected_by_child_id)}

    docs = list(values_col.find(query))

    if strict or value_column_index is not None:
        matching_docs = [
            doc
            for doc in docs
            if doc.get("metadata", {}).get("childId") in expected_by_child_id
            and (
                value_column_index is not None
                or not strict
                or str(doc.get("metadata", {}).get("childId", "")).endswith("_Value")
            )
        ]
    else:
        matching_docs = docs

    duplicate_counts: dict[str, int] = {}
    for doc in matching_docs:
        child_id = doc.get("metadata", {}).get("childId")
        if not isinstance(child_id, str):
            continue
        duplicate_counts[child_id] = duplicate_counts.get(child_id, 0) + 1

    results: list[dict[str, Any]] = []
    for doc in matching_docs:
        child_id = doc.get("metadata", {}).get("childId")
        if not isinstance(child_id, str):
            continue
        values = doc.get("values")
        normalized_values = values if isinstance(values, list) else []
        limited_values = normalized_values
        if isinstance(values_limit, int) and values_limit >= 0:
            limited_values = normalized_values[:values_limit]
        values_count = doc.get("valuesCount")
        if not isinstance(values_count, int):
            values_count = len(normalized_values)

        match = expected_by_child_id.get(child_id)
        result = {
            "testId": str(test.get("_id")),
            "valueColumnId": match.get("valueColumnId") if match else None,
            "valueTableId": match.get("valueTableId") if match else None,
            "childId": child_id,
            "name": match.get("name") if match else None,
            "unitTableId": match.get("unitTableId") if match else None,
            "valuesCount": values_count,
            "sourceDocumentId": str(doc.get("_id")),
            "duplicate": duplicate_counts[child_id] > 1,
            "duplicateCount": duplicate_counts[child_id],
            "matchedTestValueColumn": match is not None,
        }
        if include_values:
            result["values"] = limited_values
            result["valuesReturned"] = len(limited_values)
            result["valuesTruncated"] = len(limited_values) < len(normalized_values)
        results.append(result)

    results.sort(key=lambda item: (item["childId"], item["sourceDocumentId"]))
    return results


def numeric_values(values: list[Any]) -> list[float]:
    return [
        value
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]


def extract_value_arrays(
    resolved_value_columns: list[dict[str, Any]],
) -> list[list[Any]]:
    arrays: list[list[Any]] = []
    for entry in resolved_value_columns:
        values = entry.get("values")
        if isinstance(values, list):
            arrays.append(values)
    return arrays
