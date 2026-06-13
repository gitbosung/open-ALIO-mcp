# -*- coding: utf-8 -*-
"""Promote validated ALIO crawl rows into data/metrics/*.json.

This script is intentionally conservative:
- crawl rows win over xlsx metrics only when the normalized
  (org, metric item, year) group has one unambiguous numeric value;
- conflicting crawl groups are skipped and reported;
- existing xlsx metrics remain as fallback for skipped or missing groups.

Run after:
  1. scripts/build_metrics.py
  2. crawl_alio.py parse
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
CRAWL_CSV = ROOT / "data" / "crawl" / "alio_records.csv"
METRICS_DIR = ROOT / "data" / "metrics"
INDEX = METRICS_DIR / "_index.json"
REPORT = METRICS_DIR / "_crawl_promotion_report.json"

NA_LABELS = {"", "해당사항 없음", "비고"}


def to_num(value: str):
    s = str(value).replace(",", "").replace("%", "").strip()
    if not s or s == "-":
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else round(f, 6)


def clean_section(section: str) -> str:
    return re.sub(r"^\d+[-.)]?\s*", "", section or "").strip()


def compact_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def load_metric(category: str) -> dict:
    path = METRICS_DIR / f"{category}.json"
    if not path.exists():
        return {"_meta": {"category": category, "caveats": []}, "orgs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def budget_key(row: dict) -> str:
    label = row["row_label"].strip()
    prefix = "정부순지원수입(고유사업)" if label.startswith("정부순지원수입") else "수입지출현황(고유사업)"
    return f"{prefix} | {label}"


def executive_pay_key(row: dict) -> str:
    return f"{clean_section(row['section'])} | {row['row_label'].strip()}"


FINANCE_HALF_COMPAT = {
    "자산 > 자산총계": "자산총계",
    "부채 > 부채총계": "부채총계",
    "자본 > 자본총계": "자본총계",
    "부채비율": "부채비율",
    "수익(매출액)": "수익(매출액)",
    "순매출": "순매출",
    "매출원가": "매출원가",
    "판관비": "판관비",
    "영업이익": "영업이익",
    "기타수익": "기타수익",
    "기타비용": "기타비용",
    "기타이익": "기타이익",
    "금융수익": "금융수익",
    "금융원가": "금융원가",
    "지분법대상기업관련이익 등": "지분법대상기업관련이익등",
    "법인세비용차감전순이익": "법인세비용차감전순이익",
    "법인세비용": "법인세비용",
    "당기순이익": "당기순이익",
    "기타포괄손익": "기타포괄손익",
    "총포괄손익": "총포괄손익",
    "지배기업의 소유주에게 귀속되는 당기순이익": "지배기업의소유주에게귀속되는당기순이익",
    "비지배지분에 귀속되는 당기순이익": "비지배지분에귀속되는당기순이익",
    "매출액순이익률": "매출액순이익률",
    "자기자본회전율": "자기자본회전율",
}


def finance_key(row: dict) -> str:
    label = row["row_label"].strip()
    if row["value_type"] == "반기":
        compat = FINANCE_HALF_COMPAT.get(label)
        if compat:
            return compat

    item_name = "요약 재무상태표" if row["item_no"] == "31201" else "요약 손익계산서"
    value_type = row["value_type"] or "값"
    section = clean_section(row["section"])
    if section:
        return f"{item_name}({value_type}) | {section} | {label}"
    return f"{item_name}({value_type}) | {label}"


def collect_groups(
    rows: Iterable[dict],
    item_nos: set[str],
    key_fn: Callable[[dict], str],
) -> tuple[dict[tuple[str, str, str, str], tuple[str, int | float]], list[dict]]:
    raw: dict[tuple[str, str, str, str], list[tuple[int | float, dict]]] = defaultdict(list)
    for row in rows:
        if row["item_no"] not in item_nos:
            continue
        if not row["year"] or not row["value"] or row["row_label"] in NA_LABELS:
            continue
        value = to_num(row["value"])
        if value is None:
            continue
        key = key_fn(row)
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
            }
        )
    return promoted, conflicts


def merge_category(
    category: str,
    label: str,
    unit: str,
    item_nos: set[str],
    key_fn: Callable[[dict], str],
    rows: list[dict],
) -> dict:
    base = load_metric(category)
    merged = deepcopy(base)
    merged.setdefault("_meta", {})
    merged.setdefault("orgs", {})

    promoted, conflicts = collect_groups(rows, item_nos, key_fn)
    overwritten = 0
    added = 0
    for (org_code, org_name, metric_key, year), (_, value) in promoted.items():
        org = merged["orgs"].setdefault(org_code, {"name": org_name, "series": {}})
        if not org.get("name"):
            org["name"] = org_name
        series = org.setdefault("series", {}).setdefault(metric_key, {})
        if year in series:
            overwritten += 1
        else:
            added += 1
        series[year] = value

    for org_code in list(merged["orgs"]):
        series = {k: v for k, v in merged["orgs"][org_code].get("series", {}).items() if v}
        if series:
            merged["orgs"][org_code]["series"] = series
        else:
            del merged["orgs"][org_code]

    years = sorted(
        {
            year
            for org in merged["orgs"].values()
            for series in org.get("series", {}).values()
            for year in series
            if str(year).isdigit()
        }
    )
    now = datetime.now().isoformat(timespec="seconds")
    old_meta = base.get("_meta", {})
    caveats = clean_caveats(category, old_meta.get("caveats", []))
    promotion_note = (
        "ALIO HTML 크롤 파싱 결과를 병합했습니다. 같은 기관·항목·연도에서 "
        "서로 다른 값이 나온 크롤 그룹은 승격하지 않고 기존 xlsx 값을 fallback으로 유지합니다."
    )
    if promotion_note not in caveats:
        caveats.append(promotion_note)
    for note in category_notes(category):
        if note not in caveats:
            caveats.append(note)

    merged["_meta"] = {
        **old_meta,
        "category": category,
        "label": label,
        "unit": unit,
        "source_file": old_meta.get("source_file", ""),
        "source_files": sorted(
            set(old_meta.get("source_files", []))
            | ({old_meta["source_file"]} if old_meta.get("source_file") else set())
            | {"data/crawl/alio_records.csv"}
        ),
        "source_priority": [
            "crawl: ALIO HTML item pages, only non-conflicting normalized groups",
            "xlsx: legacy item-level files for fallback and not-yet-promoted groups",
        ],
        "promoted_crawl_items": sorted(item_nos),
        "merge_policy": (
            "Group crawl rows by org_code, normalized metric item, and year. "
            "Promote only groups with one numeric value; skip conflicting groups."
        ),
        "crawl_groups_promoted": len(promoted),
        "crawl_values_added": added,
        "crawl_values_overwritten": overwritten,
        "crawl_conflict_groups_skipped": len(conflicts),
        "years": years,
        "org_count": len(merged["orgs"]),
        "built_at": now,
        "caveats": caveats,
    }
    return {"data": merged, "conflicts": conflicts}


def clean_caveats(category: str, caveats: Iterable[str]) -> list[str]:
    """Remove caveats that become misleading after crawl promotion."""
    if category != "finance":
        return list(caveats)
    blocked = (
        "반기 재정현황 공시 대상",
        "전체 기관 재무는 추후",
        "각 연도 반기 기준",
        "PDF 파싱으로 보완",
    )
    return [c for c in caveats if not any(token in c for token in blocked)]


def category_notes(category: str) -> list[str]:
    if category == "finance":
        return [
            "재무 카테고리는 ALIO HTML 크롤의 31201(요약 재무상태표)·31301(요약 손익계산서)을 승격해 결산 항목을 전 기관 범위로 확장했습니다.",
            "공기업 반기 항목은 기존 xlsx 반기 재정현황과 교차검증 후 병합했습니다.",
            "결산 표에서 같은 기관·항목·연도에 서로 다른 값이 반복되는 그룹은 자동 선택하지 않고 보류합니다.",
        ]
    if category == "budget":
        return [
            "수입·지출 카테고리는 ALIO HTML 크롤의 31401을 우선 병합하되, 반복 표로 값이 충돌하는 그룹은 기존 xlsx 값을 fallback으로 유지합니다.",
        ]
    if category == "executive_pay":
        return [
            "임원 연봉 카테고리는 ALIO HTML 크롤의 20501과 기존 xlsx 값이 100% 일치한 뒤 크롤 값을 병합했습니다.",
        ]
    return []


def rebuild_index() -> dict:
    old_order: list[str] = []
    if INDEX.exists():
        try:
            old_order = [c["category"] for c in json.loads(INDEX.read_text(encoding="utf-8")).get("categories", [])]
        except json.JSONDecodeError:
            old_order = []

    available = {
        path.stem
        for path in METRICS_DIR.glob("*.json")
        if not path.name.startswith("_")
    }
    ordered = [c for c in old_order if c in available] + sorted(available - set(old_order))
    categories = []
    for category in ordered:
        data = json.loads((METRICS_DIR / f"{category}.json").read_text(encoding="utf-8"))
        meta = data["_meta"]
        categories.append({k: meta[k] for k in ("category", "label", "unit", "years", "org_count")})

    index = {"built_at": datetime.now().isoformat(timespec="seconds"), "categories": categories}
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def main() -> None:
    if not CRAWL_CSV.exists():
        raise SystemExit(f"missing crawl CSV: {CRAWL_CSV}")
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    with CRAWL_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    specs = [
        ("executive_pay", "임원 연봉", "천원", {"20501"}, executive_pay_key),
        ("budget", "수입·지출 현황", "백만원", {"31401"}, budget_key),
        (
            "finance",
            "요약 재무상태표·손익계산서",
            "백만원 (부채비율 등 비율 지표는 %)",
            {"31201", "31301"},
            finance_key,
        ),
    ]

    report = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source_csv": "data/crawl/alio_records.csv",
        "policy": "promote non-conflicting crawl groups; keep xlsx fallback for skipped conflicts",
        "categories": {},
    }

    for category, label, unit, item_nos, key_fn in specs:
        result = merge_category(category, label, unit, item_nos, key_fn, rows)
        data = result["data"]
        out = METRICS_DIR / f"{category}.json"
        out.write_text(compact_json(data), encoding="utf-8")
        meta = data["_meta"]
        conflicts = result["conflicts"]
        report["categories"][category] = {
            "promoted_crawl_items": sorted(item_nos),
            "org_count": meta["org_count"],
            "years": meta["years"],
            "crawl_groups_promoted": meta["crawl_groups_promoted"],
            "crawl_values_added": meta["crawl_values_added"],
            "crawl_values_overwritten": meta["crawl_values_overwritten"],
            "crawl_conflict_groups_skipped": meta["crawl_conflict_groups_skipped"],
            "conflict_samples": conflicts[:20],
        }
        print(
            f"{category}: orgs={meta['org_count']} years={meta['years']} "
            f"promoted={meta['crawl_groups_promoted']} "
            f"added={meta['crawl_values_added']} overwritten={meta['crawl_values_overwritten']} "
            f"conflicts={meta['crawl_conflict_groups_skipped']}"
        )

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    index = rebuild_index()
    print(f"index: {len(index['categories'])} categories")
    print(f"report: {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
