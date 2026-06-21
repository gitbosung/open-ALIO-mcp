"""Verify that data/crawl/alio_records.csv and .json carry the same records."""

from __future__ import annotations

import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "crawl" / "alio_records.csv"
JSON_PATH = ROOT / "data" / "crawl" / "alio_records.json"
REPORT_PATH = ROOT / "data" / "validation_reports" / "crawl_csv_json_consistency.json"


SCHEMA = [
    "apba_id",
    "org_name",
    "item_no",
    "item_name",
    "section",
    "sub_account",
    "row_label",
    "col_label",
    "year",
    "value_type",
    "value",
    "unit",
    "as_of",
    "source_url",
]


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def same_cell(csv_value: str, json_value: Any) -> bool:
    if json_value is None:
        json_value = ""
    if csv_value == "" and json_value == "":
        return True
    if csv_value == str(json_value):
        return True
    csv_num = parse_decimal(csv_value)
    json_num = parse_decimal(json_value)
    if csv_num is not None and json_num is not None:
        return csv_num == json_num
    return False


def read_json_meta_record_count(path: Path, bytes_to_read: int = 2 * 1024 * 1024) -> int | None:
    with path.open("r", encoding="utf-8") as f:
        prefix = f.read(bytes_to_read)
    match = re.search(r'"record_count"\s*:\s*(\d+)', prefix)
    return int(match.group(1)) if match else None


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JSON_PATH.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)

    records = payload.get("records", [])
    meta_record_count = payload.get("_meta", {}).get("record_count") or read_json_meta_record_count(JSON_PATH)
    mismatches: list[dict[str, Any]] = []
    csv_count = 0

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        csv_header_ok = reader.fieldnames == SCHEMA
        for csv_count, row in enumerate(reader, start=1):
            if csv_count > len(records):
                mismatches.append({"row": csv_count, "field": "_record", "csv": "present", "json": "missing"})
                break
            record = records[csv_count - 1]

            for field in SCHEMA:
                if not same_cell(row.get(field, ""), record.get(field, "")):
                    if len(mismatches) < 50:
                        mismatches.append(
                            {
                                "row": csv_count,
                                "field": field,
                                "csv": row.get(field, ""),
                                "json": record.get(field, ""),
                            }
                        )
                    break

    extra_json = max(0, len(records) - csv_count)

    result = {
        "csv_path": str(CSV_PATH.relative_to(ROOT)),
        "json_path": str(JSON_PATH.relative_to(ROOT)),
        "csv_header_ok": csv_header_ok,
        "csv_rows": csv_count,
        "json_records": len(records),
        "json_meta_record_count": meta_record_count,
        "extra_json_records_after_csv": extra_json,
        "mismatch_count_capped": len(mismatches),
        "sample_mismatches": mismatches,
        "consistent": (
            csv_header_ok
            and not mismatches
            and extra_json == 0
            and meta_record_count == csv_count
            and len(records) == csv_count
        ),
    }

    REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
