"""Validate golden_samples.json against the v2 canonical store (Plan A-2).

사람이 ALIO 화면에서 검증한 golden_samples.json의 수치가, v2 canonical 조회 경로
(`open_alio_mcp.canonical_store.query_records`)로도 그대로 나오는지 대조한다.

이것은 "v2 vs v1"(일관성)이 아니라 "v2 vs ALIO 원문"(정확성) 방향의 첫 측정이다.
참고: docs/accuracy_improvement_plan.md Phase A-2 / A-3.

Usage:
    python scripts/validate_golden_canonical.py --db data/canonical/_golden_canonical.db
    # 또는 OPEN_ALIO_CANONICAL_DB 환경변수로 DB 지정

분류:
    MATCH        값 + 컨텍스트(기금계정/행/열 라벨) 모두 일치
    CTX_MISMATCH 값은 있으나 컨텍스트 불일치 (파서 구조 차이 의심)
    VALUE_MISSING org+item은 DB에 있으나 해당 값을 못 찾음 (파서 손실/기간차 의심)
    NOT_IN_DB    org+item 자체가 DB에 없음 (미크롤/미빌드)
    NON_NUMERIC  골든값이 숫자가 아님 (대조 대상 아님)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

VALUE_TOL = 0.01


def _norm(s: str) -> str:
    return "".join((s or "").split())


def _to_number(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _metric_query(sample: dict) -> str:
    """조회 LIKE 키: row_label 마지막 세그먼트 우선, 없으면 col_label."""
    row = (sample.get("row_label") or "").strip()
    if row:
        return row.split(">")[-1].strip()
    return (sample.get("col_label") or "").strip()


def _context_ok(sample: dict, rec: dict) -> bool:
    sub = (sample.get("sub_account") or "").strip()
    if sub and _norm(sub) not in _norm(rec.get("table_title", "")):
        return False
    row = (sample.get("row_label") or "").strip()
    if row and _norm(row) not in _norm(rec.get("row_header_path", "")):
        return False
    col = (sample.get("col_label") or "").strip()
    if col:
        haystack = _norm(rec.get("col_header_path", "")) + _norm(rec.get("metric_label", "")) + _norm(rec.get("period_label", ""))
        if _norm(col) not in haystack:
            return False
    return True


def _classify(sample: dict, store) -> tuple[str, dict | None]:
    expected = _to_number(sample.get("value"))
    if expected is None:
        return "NON_NUMERIC", None

    org, item = sample["apba_id"], sample["item_no"]
    year = (sample.get("year") or "").strip()

    present = store.query_records(org_code=org, item_no=item, limit=1)
    if present["total"] == 0:
        return "NOT_IN_DB", None

    res = store.query_records(
        org_code=org, item_no=item, period_year=year,
        metric_query=_metric_query(sample), limit=200,
    )
    value_hits = []
    for rec in res["records"]:
        nv = rec.get("normalized_value")
        if nv is None:
            continue
        if abs(float(nv) - expected) <= VALUE_TOL:
            value_hits.append(rec)
    if not value_hits:
        return "VALUE_MISSING", None
    for rec in value_hits:
        if _context_ok(sample, rec):
            return "MATCH", rec
    return "CTX_MISMATCH", value_hits[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, help="canonical SQLite DB (없으면 OPEN_ALIO_CANONICAL_DB)")
    ap.add_argument("--golden", type=Path, default=REPO / "data/reference/golden_samples.json")
    ap.add_argument("--out", type=Path, default=REPO / "data/validation_reports/golden_vs_canonical.json")
    args = ap.parse_args()

    if args.db:
        os.environ["OPEN_ALIO_CANONICAL_DB"] = str(args.db)

    from open_alio_mcp import canonical_store as store

    if not store.available():
        print("[SKIP] canonical DB를 찾을 수 없음 — --db 또는 OPEN_ALIO_CANONICAL_DB 지정 필요")
        return 0

    samples = json.loads(args.golden.read_text(encoding="utf-8"))["samples"]
    results = []
    counts: dict[str, int] = {}
    for s in samples:
        status, rec = _classify(s, store)
        counts[status] = counts.get(status, 0) + 1
        label = f"{s['apba_id']} {s['item_no']} {s.get('sub_account','') } {s.get('row_label') or s.get('col_label','')} {s.get('year','')}".strip()
        got = rec.get("normalized_value") if rec else None
        mark = "OK " if status == "MATCH" else "!! "
        print(f"{mark}[{status:12}] {label} | expected={s['value']} got={got}")
        results.append({"sample": s, "status": status,
                        "matched_table_title": rec.get("table_title") if rec else None})

    numeric = sum(v for k, v in counts.items() if k != "NON_NUMERIC")
    matched = counts.get("MATCH", 0)
    print(f"\n요약: {matched}/{numeric} MATCH  |  {counts}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"db": store.db_path().as_posix(), "summary": {"matched": matched, "numeric": numeric, "counts": counts},
         "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"리포트: {args.out}")

    # 게이트: DB에 존재하는(=검증 가능한) 샘플 중 하나라도 MATCH 실패면 실패 처리
    verifiable = numeric - counts.get("NOT_IN_DB", 0)
    return 0 if matched >= verifiable else 1


if __name__ == "__main__":
    raise SystemExit(main())
