import math
from statistics import median
from typing import Any


NUMERIC_FIELD_SPECS: list[tuple[str, str]] = [
    ("SPECIMEN_WIDTH", "Specimen width"),
    ("SPECIMEN_THICKNESS", "Specimen thickness"),
    ("Diameter", "Diameter"),
    ("TEST_SPEED", "Test speed"),
    ("Grip to grip separation at the start position", "Grip separation"),
]


def safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return numeric


def ref_id_candidates(test_id: Any) -> list[Any]:
    candidates = [test_id]
    if not isinstance(test_id, str):
        candidates.append(str(test_id))
    return candidates


def robust_score(value: float, population: list[float]) -> tuple[float, float, float]:
    center = median(population)
    deviations = [abs(item - center) for item in population]
    mad = median(deviations)
    if mad > 0:
        scale = 1.4826 * mad
        return abs(value - center) / scale, center, scale

    spread = max(population) - min(population)
    if spread > 0:
        return abs(value - center) / spread * 4.0, center, spread

    return (0.0 if value == center else 6.0), center, 0.0


def format_timestamp(flat: dict[str, Any]) -> str:
    for key in ("Date/Clock time", "Date", "date"):
        value = flat.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Unknown"


def build_setup_notes(flat: dict[str, Any], sample_size: int) -> list[str]:
    notes: list[str] = [f"Sample size for this pass: {sample_size} tests."]
    for key, label in (
        ("TESTER", "Tester"),
        ("MACHINE_DATA", "Machine data"),
        ("STANDARD", "Standard"),
        ("NOTES", "Notes"),
    ):
        value = flat.get(key)
        if isinstance(value, str) and value.strip():
            notes.append(f"{label}: {value.strip()}")
    return notes[:4]


def value_column_child_id(value_column: dict[str, Any]) -> str | None:
    value_table_id = value_column.get("valueTableId")
    value_column_id = value_column.get("_id")
    if not isinstance(value_table_id, str) or not isinstance(value_column_id, str):
        return None
    return f"{value_table_id}.{value_column_id}"


def pick_force_curve_column(test_doc: dict[str, Any]) -> dict[str, Any] | None:
    for value_column in test_doc.get("valueColumns", []) or []:
        if not isinstance(value_column, dict):
            continue
        column_id = value_column.get("_id")
        if not isinstance(column_id, str) or not column_id.endswith("_Value"):
            continue
        name = (value_column.get("name") or "").lower()
        unit = (value_column.get("unitTableId") or "").lower()
        if "force" in name or "force" in unit:
            return value_column
    return None


def summarize_force_curve(values_col: Any, test_doc: dict[str, Any]) -> dict[str, Any] | None:
    value_column = pick_force_curve_column(test_doc)
    if value_column is None:
        return None

    child_id = value_column_child_id(value_column)
    if child_id is None:
        return None

    doc = values_col.find_one(
        {
            "metadata.refId": {"$in": ref_id_candidates(test_doc.get("_id"))},
            "metadata.childId": child_id,
        },
        {"values": 1, "valuesCount": 1},
    )
    if not isinstance(doc, dict):
        return None

    raw_values = doc.get("values")
    if not isinstance(raw_values, list):
        return None

    numeric_values = [safe_float(value) for value in raw_values]
    finite_values = [value for value in numeric_values if value is not None]
    if not finite_values:
        return None

    peak_abs = max(abs(value) for value in finite_values)
    return {
        "points": len(raw_values),
        "peakAbs": peak_abs,
        "min": min(finite_values),
        "max": max(finite_values),
        "columnName": value_column.get("name") or "Force curve",
    }


def find_outliers(
    tests_col: Any,
    values_col: Any,
    limit: int = 6,
    sample_size: int = 80,
    test_type: str = "tensile",
) -> dict[str, Any]:
    projection = {
        "_id": 1,
        "valueColumns": 1,
        "TestParametersFlat": 1,
    }
    query = {"TestParametersFlat.TYPE_OF_TESTING_STR": test_type} if test_type else {}
    docs = list(tests_col.find(query, projection).limit(max(sample_size, limit)))

    populations: dict[str, list[float]] = {}
    for key, _label in NUMERIC_FIELD_SPECS:
        values = [
            safe_float((doc.get("TestParametersFlat") or {}).get(key))
            for doc in docs
        ]
        finite_values = [value for value in values if value is not None]
        if len(finite_values) >= 6:
            populations[key] = finite_values

    ranked: list[dict[str, Any]] = []
    for doc in docs:
        flat = doc.get("TestParametersFlat") or {}
        best_match: dict[str, Any] | None = None

        for key, label in NUMERIC_FIELD_SPECS:
            population = populations.get(key)
            value = safe_float(flat.get(key))
            if population is None or value is None:
                continue

            score, center, spread = robust_score(value, population)
            if best_match is None or score > best_match["score"]:
                best_match = {
                    "key": key,
                    "label": label,
                    "value": value,
                    "center": center,
                    "spread": spread,
                    "score": score,
                }

        if best_match is None or best_match["score"] < 0.5:
            continue

        ranked.append(
            {
                "doc": doc,
                "match": best_match,
            }
        )

    ranked.sort(key=lambda item: item["match"]["score"], reverse=True)
    preferred = [item for item in ranked if item["match"]["score"] >= 1.5]
    selected = preferred[:limit] if preferred else ranked[:limit]

    outliers: list[dict[str, Any]] = []
    for index, item in enumerate(selected, start=1):
        doc = item["doc"]
        flat = doc.get("TestParametersFlat") or {}
        match = item["match"]
        curve = summarize_force_curve(values_col, doc)
        score = match["score"]
        severity = "high" if score >= 3.5 else "medium"
        test_id = str(doc.get("_id"))
        title = f"{match['label']} deviates from similar {test_type} runs"
        summary = (
            f"{match['label']} is outside the usual range for the sampled {test_type} tests."
        )
        reason = (
            f"{match['label']} is {match['value']:.6g} while the sample median is {match['center']:.6g}. "
            f"Robust outlier score: {score:.2f}."
        )
        signals = [
            f"Field with strongest deviation: {match['label']}.",
            f"Compared against {len(populations.get(match['key'], []))} sampled values.",
        ]
        if curve is not None:
            signals.append(
                f"{curve['columnName']} available with {curve['points']} points and peak |value| {curve['peakAbs']:.6g}."
            )

        recommended_actions = [
            "Review the test setup and operator notes.",
            "Compare this record against neighboring tests before excluding it.",
            "Contact the tester if the deviation cannot be explained by the specimen or recipe.",
        ]

        metrics = [
            {"label": "Outlier score", "value": f"{score:.2f}", "note": "robust z-style score"},
            {"label": "Field value", "value": f"{match['value']:.6g}", "note": match["label"]},
            {"label": "Sample median", "value": f"{match['center']:.6g}", "note": f"{test_type} sample"},
            {
                "label": "Force peak",
                "value": f"{curve['peakAbs']:.6g}" if curve is not None else "n/a",
                "note": curve["columnName"] if curve is not None else "no force curve joined",
            },
        ]

        outliers.append(
            {
                "id": f"OUT-{index:03d}",
                "severity": severity,
                "title": title,
                "summary": summary,
                "testId": test_id,
                "material": flat.get("MATERIAL") or flat.get("SPECIMEN_TYPE") or "Unknown",
                "customer": flat.get("CUSTOMER") or "Unknown",
                "tester": flat.get("TESTER") or "Unknown",
                "machine": flat.get("MACHINE_DATA") or flat.get("MACHINE") or "Unknown",
                "recordedAt": format_timestamp(flat),
                "reason": reason,
                "setupNotes": build_setup_notes(flat, len(docs)),
                "signals": signals,
                "recommendedActions": recommended_actions,
                "metrics": metrics,
            }
        )

    return {
        "outliers": outliers,
        "sampleSize": len(docs),
        "numericFieldsChecked": [label for _key, label in NUMERIC_FIELD_SPECS if _key in populations],
    }
