# -*- coding: utf-8 -*-
"""채용공고 스냅샷 로드 + 필터·정렬·분포 집계.

데이터 출처:
- data/snapshots/recruitments_ongoing.json (scripts/build_recruitments.py 생성)
- 없으면 server가 라이브 API 결과를 직접 넘겨 집계에 사용.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from . import data_provider

_snapshot: dict | None = None

# 분포 집계 가능한 차원 → 레코드 필드
DIMENSIONS = {
    "region": "work_region",
    "ncs": "ncs",
    "hire_type": "hire_type",
    "recruit_type": "recruit_type",
    "education": "education",
    "org": "org_name",
}


def load_snapshot() -> dict | None:
    global _snapshot
    if _snapshot is None:
        _snapshot = data_provider.read_json_or_none(
            "snapshots/recruitments_ongoing.json"
        ) or data_provider.read_json_or_none("cache/recruitments_snapshot.json")
    return _snapshot


def snapshot_records() -> list[dict] | None:
    snap = load_snapshot()
    return snap["recruitments"] if snap else None


def snapshot_meta() -> dict | None:
    snap = load_snapshot()
    return snap.get("_meta") if snap else None


def parse_days_remaining(rec: dict, today: date | None = None) -> int | None:
    """마감일(period_end, YYYYMMDD) 기준 D-day 계산.

    period_end로 항상 재계산 — 스냅샷에 저장된 decimalDay는 빌드 시점 값이라
    시간이 지나면 틀려지므로 period_end 파싱 불가 시에만 fallback.
    """
    end = rec.get("period_end")
    if end and len(str(end)) == 8:
        try:
            end_d = datetime.strptime(str(end), "%Y%m%d").date()
            return (end_d - (today or date.today())).days
        except ValueError:
            pass
    dd = rec.get("days_remaining")
    return int(dd) if isinstance(dd, (int, float)) else None


_CANCEL_MARKERS = ("공고취소", "채용취소", "모집취소", "(취소")


def is_cancelled(rec: dict) -> bool:
    """제목에 취소 표기가 있는 공고 — 구직자 검색에서 기본 제외."""
    title = rec.get("title") or ""
    return any(m in title for m in _CANCEL_MARKERS)


def _split_multi(value: str | None) -> list[str]:
    """'충북,경북' 같은 복합값을 분해 (쉼표/슬래시 구분)."""
    if not value:
        return ["(미지정)"]
    parts = [p.strip() for chunk in str(value).split(",") for p in chunk.split("/")]
    parts = [p for p in parts if p]
    return parts or ["(미지정)"]


def filter_records(
    records: list[dict],
    *,
    query: str = "",
    org_code: str = "",
    region: str = "",
    ncs: str = "",
    hire_type: str = "",
    recruit_type: str = "",
    education: str = "",
    pref: str = "",
    closing_within: int | None = None,
    exclude_expired: bool = False,
    exclude_cancelled: bool = True,
) -> list[dict]:
    out = []
    for r in records:
        if exclude_cancelled and is_cancelled(r):
            continue
        if query and query not in (r.get("title") or "") and query not in (r.get("org_name") or ""):
            continue
        if org_code and r.get("org_code") != org_code:
            continue
        if region and region not in (r.get("work_region") or ""):
            continue
        if ncs and ncs not in (r.get("ncs") or ""):
            continue
        if hire_type and hire_type not in (r.get("hire_type") or ""):
            continue
        # "신입" 요청 시 "신입+경력"(둘 다 지원 가능)도 포함
        if recruit_type and recruit_type not in (r.get("recruit_type") or ""):
            continue
        if education and education not in (r.get("education") or ""):
            continue
        if pref and pref not in (r.get("pref_conditions") or ""):
            continue
        if closing_within is not None or exclude_expired:
            dd = parse_days_remaining(r)
            if exclude_expired and dd is not None and dd < 0:
                continue
            if closing_within is not None and (dd is None or dd < 0 or dd > closing_within):
                continue
        out.append(r)
    return out


def refresh_days(records: list[dict]) -> list[dict]:
    """응답 직전 days_remaining을 오늘 기준으로 재계산한 사본 반환."""
    out = []
    for r in records:
        c = dict(r)
        c["days_remaining"] = parse_days_remaining(r)
        out.append(c)
    return out


def sort_records(records: list[dict], sort: str) -> list[dict]:
    if sort == "deadline":
        return sorted(
            records,
            key=lambda r: (parse_days_remaining(r) if parse_days_remaining(r) is not None else 10**6),
        )
    if sort == "headcount":
        return sorted(records, key=lambda r: (r.get("headcount") or 0), reverse=True)
    return records  # latest (원래 순서, API가 최신순)


def distribution(
    records: list[dict],
    dimension: str,
    *,
    top_n: int = 20,
) -> dict:
    """차원별 공고 수·모집인원 합계 분포."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension은 {list(DIMENSIONS)} 중 하나 (현재 '{dimension}')")
    field = DIMENSIONS[dimension]
    count: Counter = Counter()
    headcount: Counter = Counter()
    multi = dimension in ("region", "ncs", "hire_type")
    for r in records:
        keys = _split_multi(r.get(field)) if multi else [str(r.get(field) or "(미지정)")]
        hc = r.get("headcount") or 0
        for k in keys:
            count[k] += 1
            headcount[k] += hc if isinstance(hc, (int, float)) else 0
    rows = [
        {"key": k, "postings": count[k], "headcount_sum": headcount[k]}
        for k in count
    ]
    rows.sort(key=lambda x: x["postings"], reverse=True)
    return {
        "dimension": dimension,
        "groups": rows[:top_n],
        "group_total": len(rows),
        "postings_total": sum(count.values()),
    }
