from __future__ import annotations

import re
from datetime import datetime
from typing import Any


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "testType": ("TYPE_OF_TESTING_STR", "TYPE_OF_TESTING"),
    "customer": ("CUSTOMER", "Customer"),
    "material": ("MATERIAL", "Material"),
    "machine": ("MACHINE", "MACHINE_DATA", "Machine"),
    "machineNr": ("MACHINE_DATA", "MACHINE"),
    "tester": ("TESTER", "Tester"),
    "standard": ("standard", "STANDARD"),
    "specimenWidth": ("SPECIMEN_WIDTH", "Specimen width"),
    "diameter": ("DIAMETER", "Diameter"),
    "machineType": ("MACHINE_TYPE_STR",),
    "notes": ("NOTES",),
    "testSpeed": ("TEST_SPEED",),
    "date": ("date", "Date/Clock time", "Date"),
}


def flat_value(flat: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = flat.get(key)
        if value is not None:
            return value
    return None


def normalize_date_value(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return normalized


def normalize_test_document(doc: dict[str, Any]) -> dict[str, Any]:
    flat = doc.get("TestParametersFlat", {}) or {}
    return {
        "testId": str(doc.get("_id")),
        "name": doc.get("name"),
        "date": normalize_date_value(flat_value(flat, *FIELD_ALIASES["date"])),
        "material": flat_value(flat, *FIELD_ALIASES["material"]),
        "testType": flat_value(flat, *FIELD_ALIASES["testType"]),
        "machine": flat_value(flat, *FIELD_ALIASES["machine"]),
        "tester": flat_value(flat, *FIELD_ALIASES["tester"]),
        "customer": flat_value(flat, *FIELD_ALIASES["customer"]),
        "standard": flat_value(flat, *FIELD_ALIASES["standard"]),
        "specimenWidth": flat_value(flat, *FIELD_ALIASES["specimenWidth"]),
        "diameter": flat_value(flat, *FIELD_ALIASES["diameter"]),
        "machine_type_str": flat_value(flat, *FIELD_ALIASES["machineType"]),
        "notes": flat_value(flat, *FIELD_ALIASES["notes"]),
        "testSpeed": flat_value(flat, *FIELD_ALIASES["testSpeed"]),
        "availableColumns": [
            value_column["name"]
            for value_column in doc.get("valueColumns", [])
            if isinstance(value_column, dict) and "name" in value_column
        ],
    }


def equality_filter(field_aliases: tuple[str, ...], value: str) -> dict[str, Any]:
    clauses = [{"TestParametersFlat." + field_name: value} for field_name in field_aliases]
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def _day_prefixes(date_value: str) -> list[str]:
    normalized = date_value.strip()
    prefixes = [normalized]

    try:
        parsed = datetime.fromisoformat(normalized)
        iso_day = parsed.date().isoformat()
        dotted_day = parsed.strftime("%d.%m.%Y")
        prefixes.extend([iso_day, dotted_day])
    except ValueError:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            year, month, day = normalized.split("-")
            prefixes.append(f"{day}.{month}.{year}")
        elif re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", normalized):
            day, month, year = normalized.split(".")
            prefixes.append(f"{year}-{month}-{day}")

    unique: list[str] = []
    for prefix in prefixes:
        if prefix not in unique:
            unique.append(prefix)
    return unique


def exact_date_filter(date_value: str) -> dict[str, Any]:
    prefixes = _day_prefixes(date_value)
    clauses: list[dict[str, Any]] = []

    for prefix in prefixes:
        clauses.append({"TestParametersFlat.date": prefix})
        clauses.append({"TestParametersFlat.Date": prefix})
        clauses.append({"TestParametersFlat.Date/Clock time": {"$regex": f"^{re.escape(prefix)}"}})

    return {"$or": clauses}

