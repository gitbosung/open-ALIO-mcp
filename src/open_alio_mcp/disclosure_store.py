# -*- coding: utf-8 -*-
"""data/reference/disclosure_items.json — ALIO 경영공시 항목 카탈로그 조회.

출처: https://alio.go.kr/guide/managementDisclosure.do (공운법 제12조)
용도:
- list_disclosure_items tool (정기/수시·주기·분류 검색)
- metric_category ↔ 공시항목 매핑 → 지표 응답에 공시 주기 주석 자동 부착
"""
from __future__ import annotations

from . import data_provider

_data: dict | None = None
_by_metric: dict[str, list[dict]] | None = None


class DisclosureError(Exception):
    pass


def _load() -> dict:
    global _data
    if _data is None:
        rel = "reference/disclosure_items.json"
        if not data_provider.exists(rel):
            raise DisclosureError(
                "data/reference/disclosure_items.json 없음 — ALIO 공시 카탈로그 파일을 먼저 준비하세요."
            )
        _data = data_provider.read_json(rel)
    return _data


def get_meta() -> dict:
    return _load()["_meta"]


def _index_by_metric() -> dict[str, list[dict]]:
    global _by_metric
    if _by_metric is None:
        idx: dict[str, list[dict]] = {}
        for it in _load()["items"]:
            mc = it.get("metric_category")
            if mc:
                idx.setdefault(mc, []).append(it)
        _by_metric = idx
    return _by_metric


def schedule_phrase(metric_category: str) -> str | None:
    """metric 카테고리 → '○○ 항목은 △△ 주기로 정기공시' 형태의 한 줄 주석."""
    items = _index_by_metric().get(metric_category)
    if not items:
        return None
    # 동일 카테고리에 여러 공시항목이 매핑될 수 있음 (예: finance = 재무상태표+손익)
    parts = []
    for it in items:
        name = it["item"]
        if it["type"] == "정기":
            sched = it.get("schedule") or "정기"
            parts.append(f"'{name}'은(는) {sched} 정기공시")
        else:
            parts.append(f"'{name}'은(는) 수시공시(고정 주기 없음)")
    uniq = list(dict.fromkeys(parts))
    return "ALIO 공시 기준: " + " · ".join(uniq)


def search(
    query: str = "",
    group: str = "",
    type_filter: str = "",
    schedule: str = "",
    metric_category: str = "",
    has_metric: bool | None = None,
    limit: int = 100,
) -> dict:
    """공시항목 카탈로그 검색.

    query: 항목·중분류·대분류 부분일치
    group: 대분류 (예: 'S(사회)', '경영성과')
    type_filter: '정기' | '수시'
    schedule: 공시시기 부분일치 (예: '1분기', '매분기')
    metric_category: 특정 metric에 매핑된 항목만
    has_metric: True면 metric 연결 항목만, False면 미연결만
    """
    items = _load()["items"]
    out = []
    for it in items:
        if query and not (
            query in it["item"]
            or query in (it.get("sub") or "")
            or query in (it.get("group") or "")
        ):
            continue
        if group and group not in (it.get("group") or ""):
            continue
        if type_filter and it.get("type") != type_filter:
            continue
        if schedule and schedule not in (it.get("schedule") or ""):
            continue
        if metric_category and it.get("metric_category") != metric_category:
            continue
        if has_metric is True and not it.get("metric_category"):
            continue
        if has_metric is False and it.get("metric_category"):
            continue
        out.append(it)
    return {"items": out[:limit], "count": min(len(out), limit), "total": len(out)}
