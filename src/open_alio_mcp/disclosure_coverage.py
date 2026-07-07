# -*- coding: utf-8 -*-
"""data/reference/disclosure_coverage.json — 항목별·기관별 ALIO 공시 보유 여부."""
from __future__ import annotations

from . import data_provider

_data: dict | None = None
_disclosed_sets_cache: dict[str, set[str]] | None = None


class CoverageError(Exception):
    pass


def _load() -> dict:
    global _data
    if _data is None:
        rel = "reference/disclosure_coverage.json"
        if not data_provider.exists(rel):
            raise CoverageError(
                "data/reference/disclosure_coverage.json 없음 — "
                "크롤 후 python scripts/build_disclosure_coverage.py 실행"
            )
        _data = data_provider.read_json(rel)
    return _data


def get_meta() -> dict:
    return _load()["_meta"]


def _get_disclosed_sets() -> dict[str, set[str]]:
    global _disclosed_sets_cache
    if _disclosed_sets_cache is None:
        _disclosed_sets_cache = {
            item_no: set(entry.get("disclosed_orgs") or [])
            for item_no, entry in _load()["items"].items()
        }
    return _disclosed_sets_cache


def item_nos_for_category(category: str) -> list[str]:
    cats = _load().get("categories", {})
    entry = cats.get(category)
    if not entry:
        return []
    return list(entry.get("item_nos") or [])


def org_listed_for_item(org_code: str, item_no: str) -> bool | None:
    """True=ALIO 공시목록에 있음, False=없음, None=커버리지 데이터 없음."""
    sets = _get_disclosed_sets()
    if item_no not in sets:
        return None
    return org_code in sets[item_no]


def org_listed_for_category(org_code: str, category: str) -> bool | None:
    """카테고리에 매핑된 item_no 중 하나라도 목록에 있으면 True."""
    item_nos = item_nos_for_category(category)
    if not item_nos:
        return None
    results = [org_listed_for_item(org_code, n) for n in item_nos]
    if all(r is None for r in results):
        return None
    return any(r is True for r in results if r is not None)


def item_summary(item_no: str) -> dict | None:
    return _load()["items"].get(item_no)


def resolve_items(*, category: str = "", item_no: str = "") -> list[tuple[str, dict]]:
    data = _load()
    if item_no:
        entry = data["items"].get(item_no)
        return [(item_no, entry)] if entry else []
    if category:
        out = []
        for no in item_nos_for_category(category):
            entry = data["items"].get(no)
            if entry:
                out.append((no, entry))
        return out
    return []


def lookup(org_code: str, *, category: str = "", item_no: str = "") -> dict:
    """기관×항목(또는 metric category) 공시 보유 여부."""
    meta = get_meta()
    total = meta.get("total_orgs", 355)
    items = resolve_items(category=category, item_no=item_no)
    if not items:
        raise CoverageError(
            f"커버리지 없음 — category={category!r} item_no={item_no!r}. "
            "build_disclosure_coverage.py 실행 또는 인자 확인."
        )

    per_item = []
    any_listed = False
    all_unknown = True
    for no, entry in items:
        listed = org_listed_for_item(org_code, no)
        if listed is not None:
            all_unknown = False
        if listed:
            any_listed = True
        per_item.append({
            "item_no": no,
            "item_name": entry["item_name"],
            "listed": listed,
            "disclosed_count": entry.get("disclosed_count"),
        })

    if all_unknown:
        status = "unknown"
    elif any_listed:
        status = "listed"
    else:
        status = "not_listed"

    primary = per_item[0]
    name = primary["item_name"]
    count = primary.get("disclosed_count") or 0

    if status == "not_listed":
        caveat = (
            f"ALIO 공시 기관목록 기준, {org_code}는 '{name}' 항목 공시 등록이 없습니다 "
            f"(전체 {total}개 공시단위 중 이 항목은 {count}곳만 등록). "
            "해당사항 없음·제도상 비대상·평가 비참여·아직 미제출 등일 수 있으며, "
            "단순 '미공시'와 다를 수 있습니다."
        )
    elif status == "listed":
        caveat = (
            f"ALIO 공시 기관목록에는 {org_code}의 '{name}' 등록이 있습니다. "
            "MCP에 수치가 없다면 적재본 미반영·파싱 전·항목명 불일치 가능성을 확인하세요."
        )
    else:
        caveat = "항목별 공시 보유 기관 목록이 없어 공시 여부를 판별할 수 없습니다."

    return {
        "org_code": org_code,
        "category": category or None,
        "item_no": item_no or None,
        "status": status,
        "items": per_item,
        "total_orgs": total,
        "caveat": caveat,
    }


def caveat_for_missing_metrics(org_code: str, category: str, *, label: str | None = None) -> str | None:
    """get_institution_metrics 등에서 found=False일 때 붙일 구체 caveat."""
    try:
        result = lookup(org_code, category=category)
    except CoverageError:
        return None
    if result["status"] == "not_listed":
        return result["caveat"]
    if result["status"] == "listed":
        return result["caveat"]
    return None
