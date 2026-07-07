"""Derive MCP metric JSON candidates from canonical v2 SQLite records.

This script does not overwrite data/metrics/*.json.  It writes v2-derived
candidate metrics under data/canonical/metrics_v2/ and compares them with the
current v1/runtime metrics.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.promote_crawl_metrics import (  # noqa: E402
    GOLDEN_ORGS,
    PLACEHOLDER_LABELS,
    budget_key,
    executive_pay_key,
    finance_key,
)

DEFAULT_DB = ROOT / "data" / "canonical" / "alio_canonical.db"
DEFAULT_OUT_DIR = ROOT / "data" / "canonical" / "metrics_v2"
DEFAULT_REPORT = ROOT / "data" / "validation_reports" / "canonical_v2_metrics_compare.json"
V1_METRICS_DIR = ROOT / "data" / "metrics"

FUND_ACCOUNT_RE = re.compile(r"(?:기금계정\s*:\s*|\[기금계정\]\s*)(.+)")
UNIT_TRAILER_RE = re.compile(r"\s*\(단위\s*:\s*[^)]*\)\s*$")


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def compact_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def extract_sub_account(*texts: str) -> str:
    for text in texts:
        match = FUND_ACCOUNT_RE.search(text or "")
        if match:
            value = clean_text(match.group(1))
            value = value.split("|", 1)[0].strip()
            value = UNIT_TRAILER_RE.sub("", value).strip()
            return value
    return ""


def compact_label(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def is_superseded_correction_row(row: dict) -> bool:
    return compact_label(row.get("col_label")) == "수정전"


def canonical_to_v1_row(row: dict) -> dict:
    """Adapt canonical v2 record fields to v1 promotion key functions."""
    section = row["table_title"] if row["item_no"] == "20501" and row["table_title"] else row["section_title"]
    return {
        "apba_id": row["org_code"],
        "org_name": row["org_name"],
        "item_no": row["item_no"],
        "item_name": row["item_name"],
        "section": section,
        "sub_account": extract_sub_account(row["table_title"], row["section_title"]),
        "row_label": row["row_header_path"],
        "col_label": row["col_header_path"],
        "year": row["period_year"],
        "value_type": row["period_type"],
        "value": row["normalized_value"],
        "unit": row["unit"],
        "as_of": row["as_of"],
        "source_html_path": row["source_html_path"],
        "table_title": row["table_title"],
        "table_index": row["table_index"],
    }


def normalize_finance_table_context(table_title: str | None) -> str:
    text = clean_text(table_title)
    text = UNIT_TRAILER_RE.sub("", text).strip()
    return text


def finance_context_key(row: dict) -> str | None:
    """v2-only finance key that preserves table-title/accounting-basis context."""
    base = finance_key(row)
    if not base:
        return None
    context = normalize_finance_table_context(row.get("table_title"))
    if not context:
        return base
    return f"{base} | table={context}"


def iter_canonical_rows(db_path: Path, item_nos: set[str]) -> Iterable[dict]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in item_nos)
        sql = f"""
            SELECT *
            FROM canonical_records
            WHERE record_type = 'time_series'
              AND item_no IN ({placeholders})
              AND period_year <> ''
              AND normalized_value IS NOT NULL
            ORDER BY org_code, item_no, table_index, row_index, col_index, id
        """
        for row in conn.execute(sql, sorted(item_nos)):
            yield dict(row)
    finally:
        conn.close()


def collect_groups(
    rows: Iterable[dict],
    key_fn: Callable[[dict], str | None],
) -> tuple[dict[tuple[str, str, str, str], tuple[str, int | float]], list[dict]]:
    raw: dict[tuple[str, str, str, str], list[tuple[int | float, dict]]] = defaultdict(list)
    for canonical in rows:
        row = canonical_to_v1_row(canonical)
        if not row["year"] or row["row_label"] in PLACEHOLDER_LABELS:
            continue
        if is_superseded_correction_row(row):
            continue
        key = key_fn(row)
        if key is None:
            continue
        value = row["value"]
        if not isinstance(value, (int, float)):
            continue
        raw[(row["apba_id"], row["org_name"], key, row["year"])].append((value, row))

    promoted: dict[tuple[str, str, str, str], tuple[str, int | float]] = {}
    conflicts: list[dict] = []
    for group_key, vals in raw.items():
        distinct = sorted({value for value, _ in vals})
        if len(distinct) == 1:
            org_code, org_name, metric_key, year = group_key
            promoted[(org_code, org_name, metric_key, year)] = (vals[0][1]["item_no"], distinct[0])
            continue
        sample = vals[0][1]
        conflicts.append(
            {
                "org_code": group_key[0],
                "org_name": group_key[1],
                "item_no": sample["item_no"],
                "metric_key": group_key[2],
                "year": group_key[3],
                "values": distinct[:8],
                "count": len(vals),
                "source_html_path": sample.get("source_html_path", ""),
            }
        )
    return promoted, conflicts


def load_v1_metric(category: str) -> dict:
    path = V1_METRICS_DIR / f"{category}.json"
    if not path.exists():
        return {"_meta": {"category": category, "caveats": []}, "orgs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def build_metric(
    *,
    db_path: Path,
    category: str,
    label: str,
    unit: str,
    item_nos: set[str],
    key_fn: Callable[[dict], str | None],
) -> dict:
    promoted, conflicts = collect_groups(iter_canonical_rows(db_path, item_nos), key_fn)
    orgs: dict[str, dict] = {}
    years: set[str] = set()
    for (org_code, org_name, metric_key, year), (_, value) in promoted.items():
        org = orgs.setdefault(org_code, {"name": org_name, "series": {}})
        org["series"].setdefault(metric_key, {})[year] = value
        years.add(year)

    now = datetime.now().isoformat(timespec="seconds")
    caveats = [
        "v2-derived candidate metric built from canonical parser records; not yet the default MCP metric source.",
        "Only non-conflicting canonical groups are promoted. Conflicting groups are reported and skipped.",
    ]
    if category == "finance_context":
        caveats.append(
            "v2-only finance candidate: metric keys preserve normalized table_title context to disambiguate accounting basis and statement form."
        )
        caveats.append("There is no current data/metrics v1 runtime category with matching context-rich keys.")

    data = {
        "_meta": {
            "category": category,
            "label": label,
            "unit": unit,
            "source": "canonical_v2",
            "source_db": str(db_path.relative_to(ROOT) if db_path.is_relative_to(ROOT) else db_path),
            "source_items": sorted(item_nos),
            "built_at": now,
            "years": sorted(years),
            "org_count": len(orgs),
            "canonical_groups_promoted": len(promoted),
            "canonical_conflict_groups_skipped": len(conflicts),
            "caveats": caveats,
        },
        "orgs": orgs,
    }
    return {"data": data, "conflicts": conflicts}


def flatten_metric(data: dict) -> dict[tuple[str, str, str], int | float]:
    flat: dict[tuple[str, str, str], int | float] = {}
    for org_code, org in data.get("orgs", {}).items():
        for item, series in org.get("series", {}).items():
            for year, value in series.items():
                if isinstance(value, (int, float)):
                    flat[(org_code, item, str(year))] = value
    return flat


def compare_metrics(category: str, v2: dict, *, sample_limit: int = 30) -> dict:
    v1 = load_v1_metric(category)
    v1_flat = flatten_metric(v1)
    v2_flat = flatten_metric(v2)
    common = sorted(set(v1_flat) & set(v2_flat))
    v1_only = sorted(set(v1_flat) - set(v2_flat))
    v2_only = sorted(set(v2_flat) - set(v1_flat))

    matches = 0
    mismatches: list[dict] = []
    for key in common:
        left = v1_flat[key]
        right = v2_flat[key]
        if abs(float(left) - float(right)) <= 1e-6:
            matches += 1
        else:
            org_code, metric_key, year = key
            mismatches.append(
                {
                    "org_code": org_code,
                    "metric_key": metric_key,
                    "year": year,
                    "v1": left,
                    "v2": right,
                    "diff": round(float(right) - float(left), 6),
                }
            )
    golden_mismatches = [row for row in mismatches if row["org_code"] in GOLDEN_ORGS]
    return {
        "category": category,
        "v1_points": len(v1_flat),
        "v2_points": len(v2_flat),
        "common_points": len(common),
        "matching_points": matches,
        "mismatch_points": len(mismatches),
        "v1_only_points": len(v1_only),
        "v2_only_points": len(v2_only),
        "golden_mismatch_points": len(golden_mismatches),
        "mismatch_samples": mismatches[:sample_limit],
        "golden_mismatch_samples": golden_mismatches[:sample_limit],
        "v1_only_samples": [
            {"org_code": org, "metric_key": item, "year": year, "value": v1_flat[(org, item, year)]}
            for org, item, year in v1_only[:sample_limit]
        ],
        "v2_only_samples": [
            {"org_code": org, "metric_key": item, "year": year, "value": v2_flat[(org, item, year)]}
            for org, item, year in v2_only[:sample_limit]
        ],
    }


def write_outputs(
    *,
    db_path: Path,
    out_dir: Path,
    report_path: Path,
    categories: list[tuple[str, str, str, set[str], Callable[[dict], str | None]]],
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source_db": str(db_path.relative_to(ROOT) if db_path.is_relative_to(ROOT) else db_path),
        "out_dir": str(out_dir.relative_to(ROOT) if out_dir.is_relative_to(ROOT) else out_dir),
        "policy": "derive isolated v2 candidate metrics from canonical records, then compare with current data/metrics v1 runtime metrics",
        "categories": {},
    }

    for category, label, unit, item_nos, key_fn in categories:
        result = build_metric(
            db_path=db_path,
            category=category,
            label=label,
            unit=unit,
            item_nos=item_nos,
            key_fn=key_fn,
        )
        data = result["data"]
        (out_dir / f"{category}.json").write_text(compact_json(data), encoding="utf-8")
        comparison = compare_metrics(category, data)
        conflicts = result["conflicts"]
        report["categories"][category] = {
            "source_items": sorted(item_nos),
            "v2_meta": data["_meta"],
            "canonical_conflict_samples": conflicts[:30],
            "comparison": comparison,
        }
        print(
            f"{category}: v2_points={comparison['v2_points']} "
            f"common={comparison['common_points']} mismatches={comparison['mismatch_points']} "
            f"v2_conflicts={len(conflicts)}"
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def default_categories() -> list[tuple[str, str, str, set[str], Callable[[dict], str | None]]]:
    return [
        ("executive_pay", "임원 연봉", "천원", {"20501"}, executive_pay_key),
        ("budget", "수입·지출 현황", "백만원", {"31401"}, budget_key),
        (
            "finance",
            "요약 재무상태표·손익계산서",
            "백만원(부채비율 등 비율 지표는 %)",
            {"31201", "31301"},
            finance_key,
        ),
        (
            "finance_context",
            "?붿빟 ?щТ?곹깭?쑣룹넀?듦퀎?곗꽌(table context)",
            "諛깅쭔??遺梨꾨퉬????鍮꾩쑉 吏?쒕뒗 %)",
            {"31201", "31301"},
            finance_context_key,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v2-derived candidate metrics from canonical SQLite")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--categories",
        default="executive_pay,budget,finance,finance_context",
        help="Comma-separated subset: executive_pay,budget,finance,finance_context",
    )
    args = parser.parse_args()

    wanted = {part.strip() for part in args.categories.split(",") if part.strip()}
    specs = [spec for spec in default_categories() if spec[0] in wanted]
    if not specs:
        raise SystemExit("No categories selected")
    write_outputs(db_path=args.db, out_dir=args.out_dir, report_path=args.report, categories=specs)
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
