# -*- coding: utf-8 -*-
"""Golden coverage checks for promoted metrics.

This catches silent regressions where a parse/promote change leaves a golden
institution with too few series, missing account-specific keys, or stale values.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METRICS_DIR = ROOT / "data" / "metrics"
GOLDEN_FILE = ROOT / "data" / "reference" / "golden_samples.json"
REPORT_FILE = METRICS_DIR / "_crawl_promotion_report.json"

TITLE_PREFIX_RE = re.compile(r"^\d+[-.)]?\s*")

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

FINANCE_COVERAGE = {
    "C0091": {
        "name": "신용보증기금",
        "min_series": 80,
        "required_keys": [
            "요약 재무상태표(결산) | 기금계정 | 신용보증기금 | 자산 > 자산총계",
            "요약 재무상태표(결산) | 기금계정 | 신용보증기금 | 부채비율",
        ],
    },
    "C0038": {
        "name": "기술보증기금",
        "min_series": 30,
        "required_keys": [
            "요약 재무상태표(결산) | 기금계정 | 기술보증기금 | 자산 > 자산총계",
        ],
    },
    "C0130": {
        "name": "중소벤처기업진흥공단",
        "min_series": 50,
        "required_keys": [
            "요약 재무상태표(결산) | 고유사업 | 자산 > 자산총계",
            "요약 재무상태표(결산) | 기금계정 | 중소기업창업 및 진흥기금 | 자산 > 자산총계",
        ],
    },
    "C0247": {
        "name": "한국전력공사",
        "min_series": 10,
        "required_keys": [
            "자산총계",
            "요약 재무상태표(결산) | 고유사업 | 자산 > 자산총계",
        ],
    },
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_section(section: str) -> str:
    return TITLE_PREFIX_RE.sub("", section or "").strip()


def approx_equal(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) < 0.000001
    except (TypeError, ValueError):
        return str(left) == str(right)


def finance_key(sample: dict) -> str:
    label = sample["row_label"].strip()
    if sample.get("value_type") == "반기":
        compat = FINANCE_HALF_COMPAT.get(label)
        if compat:
            return compat
    item_name = "요약 재무상태표" if str(sample["item_no"]) == "31201" else "요약 손익계산서"
    parts = [f"{item_name}({sample.get('value_type') or '값'})"]
    section = clean_section(sample.get("section", ""))
    sub_account = (sample.get("sub_account") or "").strip()
    if section:
        parts.append(section)
    if sub_account:
        parts.append(sub_account)
    parts.append(label)
    return " | ".join(parts)


def budget_key(sample: dict) -> str:
    label = sample["row_label"].strip()
    kind = "정부순지원수입" if label.startswith("정부순지원수입") else "수입지출현황"
    section = clean_section(sample.get("section", ""))
    sub_account = (sample.get("sub_account") or "").strip()
    account_type = "기금계정" if sub_account or "기금" in section else "고유사업"
    parts = [f"{kind}({account_type})"]
    if sub_account:
        parts.append(sub_account)
    parts.append(label)
    return " | ".join(parts)


def check_finance_coverage(finance: dict, failures: list[str]) -> None:
    for org_code, expected in FINANCE_COVERAGE.items():
        org = finance.get("orgs", {}).get(org_code)
        if not org:
            failures.append(f"finance {org_code}: 기관 데이터 없음")
            continue
        series = org.get("series", {})
        count = len(series)
        if count < expected["min_series"]:
            failures.append(f"finance {org_code}: series {count} < {expected['min_series']}")
        for key in expected["required_keys"]:
            if key not in series:
                failures.append(f"finance {org_code}: 필수 key 누락: {key}")


def check_report_conflicts(report: dict, failures: list[str]) -> None:
    for category in ("finance", "budget"):
        counts = (
            report.get("categories", {})
            .get(category, {})
            .get("golden_conflict_counts", {})
        )
        if not counts:
            failures.append(f"report {category}: golden_conflict_counts 없음")
            continue
        bad = {code: count for code, count in counts.items() if count}
        if bad:
            failures.append(f"report {category}: 골든 기관 conflict 존재 {bad}")


def check_golden_values(metrics: dict[str, dict], failures: list[str]) -> None:
    samples = load_json(GOLDEN_FILE).get("samples", [])
    for sample in samples:
        item_no = str(sample["item_no"])
        if item_no in {"31201", "31301"}:
            category = "finance"
            key = finance_key(sample)
        elif item_no == "31401":
            category = "budget"
            key = budget_key(sample)
        else:
            continue
        org = metrics[category].get("orgs", {}).get(sample["apba_id"], {})
        series = org.get("series", {})
        values = series.get(key)
        year = str(sample["year"])
        if values is None:
            failures.append(f"{category} {sample['apba_id']}: golden key 누락: {key}")
            continue
        actual = values.get(year)
        if not approx_equal(actual, sample["value"]):
            failures.append(
                f"{category} {sample['apba_id']} {key} {year}: "
                f"expect={sample['value']} actual={actual}"
            )


def main() -> int:
    metrics = {
        "finance": load_json(METRICS_DIR / "finance.json"),
        "budget": load_json(METRICS_DIR / "budget.json"),
    }
    report = load_json(REPORT_FILE)
    failures: list[str] = []

    check_finance_coverage(metrics["finance"], failures)
    check_report_conflicts(report, failures)
    check_golden_values(metrics, failures)

    if failures:
        print("FAIL: metrics coverage regression")
        for failure in failures:
            print(f" - {failure}")
        return 1

    for org_code, expected in FINANCE_COVERAGE.items():
        count = len(metrics["finance"]["orgs"][org_code]["series"])
        print(f"OK: finance {org_code} {expected['name']} series={count}")
    print("OK: golden metrics values")
    print("OK: golden conflict counts are zero")
    return 0


if __name__ == "__main__":
    sys.exit(main())
