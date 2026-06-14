# -*- coding: utf-8 -*-
"""CSV 중복 키·값 충돌 통계 — metrics 병합 전 점검."""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "crawl" / "alio_records.csv"

# 이전 검증 기준선 (급증 시 회귀 의심)
CONFLICT_BASELINE = 12_000


def main() -> int:
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
    groups: dict[tuple, set[str]] = defaultdict(set)
    key_counts: Counter = Counter()

    for r in rows:
        k = (
            r["apba_id"],
            r["item_no"],
            r["section"],
            r.get("sub_account", ""),
            r["row_label"],
            r.get("col_label", ""),
            r["year"],
            r["value_type"],
        )
        groups[k].add(r["value"])
        key_counts[k] += 1

    dup_key_kinds = sum(1 for c in key_counts.values() if c > 1)
    conflicts = {k: v for k, v in groups.items() if len(v) > 1}
    empty_vs_num = sum(1 for v in conflicts.values() if "" in v and any(x for x in v if x))

    print(f"총 row: {len(rows):,}")
    print(f"중복 키 종류 (동일키 2행+): {dup_key_kinds:,}")
    print(f"값 충돌 그룹 (서로 다른 value): {len(conflicts):,}")
    print(f"  └ 빈값+숫자 패턴: {empty_vs_num:,}")

    by_item: Counter = Counter()
    for k in conflicts:
        by_item[k[1]] += 1
    print("항목별 충돌:", dict(sorted(by_item.items())))

    print("\n샘플 (최대 5):")
    for k, v in list(conflicts.items())[:5]:
        # k = (apba, item, section, sub_account, row_label, col_label, year, value_type)
        print(f"  {k[0]} / {k[1]} / sub={k[3]} / {k[4]} / col={k[5]} / {k[6]!r} → {v}")

    exit_code = 0
    if len(conflicts) > CONFLICT_BASELINE * 2:
        print(f"\nFAIL: conflict_groups {len(conflicts)} > baseline×2 ({CONFLICT_BASELINE * 2})")
        exit_code = 1
    else:
        print(f"\nOK: conflict_groups within expected range (baseline ~{CONFLICT_BASELINE})")
        print("WARN: metrics 병합 시 반기 우선·non-empty 우선 dedupe 필요")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
