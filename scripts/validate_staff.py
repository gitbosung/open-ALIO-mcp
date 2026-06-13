# -*- coding: utf-8 -*-
"""전 기관 staff_summary 무결성 검증 — 정원·현원 구분 로직 일괄 점검.

사용법:
    .venv\\Scripts\\python scripts/validate_staff.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp import metrics_store  # noqa: E402


def main() -> int:
    data = metrics_store._load("staff")
    orgs = data["orgs"]
    errors: list[str] = []
    stats = {
        "total": len(orgs),
        "summary_ok": 0,
        "missing_quota": 0,
        "missing_headcount": 0,
        "same_year_incomplete": 0,
    }

    for code, org in orgs.items():
        s = metrics_store.staff_summary(code)
        if not s.get("found"):
            errors.append(f"{code} {org['name']}: staff_summary not found")
            continue
        stats["summary_ok"] += 1
        if not s["quota"]["total"]:
            stats["missing_quota"] += 1
            errors.append(f"{code} {org['name']}: quota.total missing")
        if s["headcount"]["estimated_total"] is None:
            stats["missing_headcount"] += 1
            errors.append(f"{code} {org['name']}: headcount estimate missing")

    # 최신 공통 연도(2024) 동일 연도 정원·현원 비교 가능 여부
    y = "2024"
    for code, org in orgs.items():
        ser = org["series"]
        need = ("임직원 총계(A+B+C)", "정규직-일반정규직-현원-전일제")
        if any(y not in ser.get(k, {}) for k in need):
            stats["same_year_incomplete"] += 1

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if errors:
        print(f"\n[FAIL] {len(errors)}건")
        for e in errors[:20]:
            print(" ", e)
        return 1
    print(f"\n[OK] {stats['summary_ok']}/{stats['total']} 기관 staff_summary 정상")
    print(
        f"     참고: 2024 동일연도 비교 불가 {stats['same_year_incomplete']}건 - "
        "연도별 결측은 공시 시점 차이일 수 있음"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
