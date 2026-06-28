# -*- coding: utf-8 -*-
"""data/metrics/*.json 지표 저장소 — 카테고리별 lazy load + 조회.

데이터 출처:
- ALIO 항목별 공시 엑셀 (병합·정규화된 결과를 배포 패키지/Release 스냅샷으로 제공)
- 추후: 기관별 통합공시 PDF 파싱 결과 data/parsed/by-org/{org_code}.json (재무 보완)
"""
from __future__ import annotations

from typing import Any

from . import data_provider

_cache: dict[str, dict] = {}
_index: dict | None = None
_optional_cache: dict[str, dict | None] = {}

FINANCE_CONTEXT_REL = "canonical/metrics_v2/finance_context.json"
FINANCE_CONTEXT_MARKER = " | table="


class MetricsError(Exception):
    pass


def get_index() -> dict:
    global _index
    if _index is None:
        rel = "metrics/_index.json"
        if not data_provider.exists(rel):
            raise MetricsError(
                "data/metrics/_index.json 없음 — 배포 스냅샷(alio_snapshot.db)이 손상되었거나 "
                "OPEN_ALIO_DATA_DIR/OPEN_ALIO_SNAPSHOT_PATH 설정을 확인하세요."
            )
        _index = data_provider.read_json(rel)
    return _index


def list_categories() -> list[dict]:
    return get_index()["categories"]


def _load(category: str) -> dict:
    if category not in _cache:
        rel = f"metrics/{category}.json"
        if not data_provider.exists(rel):
            valid = ", ".join(c["category"] for c in list_categories())
            raise MetricsError(f"카테고리 '{category}' 없음. 가능한 값: {valid}")
        _cache[category] = data_provider.read_json(rel)
    return _cache[category]


def _load_optional(rel: str) -> dict | None:
    if rel not in _optional_cache:
        _optional_cache[rel] = data_provider.read_json_or_none(rel)
    return _optional_cache[rel]


def _load_pdf_parsed(org_code: str) -> dict | None:
    """기관별 통합공시 PDF 파싱 결과(있으면). {item: {year: value}} 형식 가정."""
    return data_provider.read_json_or_none(f"parsed/by-org/{org_code}.json")


# staff 카테고리 — 절단 시 우선 보존할 핵심 항목 (정원·현원 구분)
_STAFF_PRIORITY = (
    "임직원 총계(A+B+C)",
    "정규직-일반정규직-정원-계(B)",
    "정규직-일반정규직-현원-계",
    "정규직-일반정규직-현원-전일제",
    "비정규직-기간제-계",
    "임원-상임임원정원(A)",
)

_STAFF_CAVEATS = [
    "ALIO 임직원수: '임직원 총계(A+B+C)'·'정원-계(B)'는 정원(authorized positions)이며 실제 재직 인원(현원)과 다릅니다.",
    "실제 재직 인원은 '현원-전일제'·'현원-계'(FTE) 또는 get_institution_staff_summary 사용을 권장합니다.",
    "일부 연도·항목은 결산 vs 분기 공시 시점 차이로 외부 보도(ALIO 결산 분석)와 수십 명 차이 날 수 있습니다.",
]


def _staff_item_rank(name: str) -> tuple:
    """staff 절단·대표항목 선택용 — 현원 > 정원, 핵심 항목 우선."""
    score = 0
    for i, key in enumerate(_STAFF_PRIORITY):
        if name == key:
            score -= 100 - i
    if "현원" in name and "전일제" in name:
        score -= 20
    elif "현원" in name and name.endswith("-계"):
        score -= 15
    elif "현원" in name:
        score -= 10
    if "정원" in name and "현원" not in name:
        score += 5
    if name.startswith("비정규직") or name.startswith("여성"):
        score += 3
    return (score, len(name), name)


def _truncate_series(series: dict[str, dict], max_items: int, category: str) -> tuple[dict[str, dict], bool]:
    if len(series) <= max_items:
        return series, False
    if category == "staff":
        ordered = sorted(series, key=_staff_item_rank)
    else:
        ordered = sorted(series)
    keep = ordered[:max_items]
    return {k: series[k] for k in keep}, True


def _latest_year_value(ser: dict[str, Any]) -> tuple[str | None, float | int | None]:
    nums = {k: v for k, v in ser.items() if isinstance(v, (int, float))}
    if not nums:
        return None, None
    year = max(nums, key=lambda k: int(k[:4]))
    return year, nums[year]


def staff_summary(
    org_code: str,
    year_from: int | None = None,
    year_to: int | None = None,
) -> dict:
    """정원·현원을 구분한 인력 요약 — '인력현황' 질의용."""
    data = _load("staff")
    meta = data["_meta"]
    org = data["orgs"].get(org_code)
    if not org:
        return {
            "org_code": org_code,
            "found": False,
            "caveats": list(_STAFF_CAVEATS),
        }

    def _row(key: str) -> dict | None:
        ser = org["series"].get(key)
        if not ser:
            return None
        filtered = _filter_years(ser, year_from, year_to)
        if not filtered:
            return None
        y, v = _latest_year_value(filtered)
        return {"item": key, "year": y, "value": v, "series": filtered}

    quota_total = _row("임직원 총계(A+B+C)")
    regular_quota = _row("정규직-일반정규직-정원-계(B)")
    regular_fte = _row("정규직-일반정규직-현원-계")
    regular_ft = _row("정규직-일반정규직-현원-전일제")
    fixed_term = _row("비정규직-기간제-계")

    headcount_parts: list[float] = []
    if regular_ft and isinstance(regular_ft["value"], (int, float)):
        headcount_parts.append(float(regular_ft["value"]))
    elif regular_fte and isinstance(regular_fte["value"], (int, float)):
        headcount_parts.append(float(regular_fte["value"]))
    if fixed_term and isinstance(fixed_term["value"], (int, float)):
        headcount_parts.append(float(fixed_term["value"]))
    estimated = round(sum(headcount_parts), 1) if headcount_parts else None

    caveats = list(meta.get("caveats", [])) + list(_STAFF_CAVEATS)
    if quota_total and regular_ft and quota_total.get("value") == regular_ft.get("value"):
        caveats.append(
            "정원 총계와 현원이 같아 보이면 항목 혼동 가능 — quota vs headcount 블록을 구분하세요."
        )

    return {
        "org_code": org_code,
        "name": org["name"],
        "unit": meta["unit"],
        "found": True,
        "quota": {
            "total": quota_total,
            "regular": regular_quota,
            "note": "정원(authorized positions) — 실제 재직 인원 아님",
        },
        "headcount": {
            "regular_fulltime": regular_ft,
            "regular_fte": regular_fte,
            "fixed_term": fixed_term,
            "estimated_total": estimated,
            "note": "현원 — 정규 전일제 + 기간제 합(무기·단시간·임원 별도)",
        },
        "caveats": caveats,
    }


def _filter_years(series: dict[str, Any], year_from: int | None, year_to: int | None) -> dict:
    out = {}
    for key, val in series.items():
        year = int(key[:4])
        if year_from and year < year_from:
            continue
        if year_to and year > year_to:
            continue
        out[key] = val
    return out


def _matches_query(text: str, query: str) -> bool:
    if not query:
        return True
    haystack = text.casefold()
    terms = [term.casefold() for term in query.split() if term.strip()]
    return all(term in haystack for term in terms)


def _split_finance_context_item(item: str) -> tuple[str, str]:
    if FINANCE_CONTEXT_MARKER not in item:
        return item, ""
    base, context = item.rsplit(FINANCE_CONTEXT_MARKER, 1)
    return base, context


def _finance_context_lookup(
    org_code: str,
    item_query: str,
    year_from: int | None,
    year_to: int | None,
    max_items: int,
    truncate_groups: bool = True,
) -> dict:
    data = _load_optional(FINANCE_CONTEXT_REL)
    if not data:
        return {
            "available": False,
            "reason": "finance_context candidate not built; run scripts/build_metrics_from_canonical.py",
        }

    org = data.get("orgs", {}).get(org_code)
    groups: dict[str, list[dict[str, Any]]] = {}
    if org:
        for item, ser in org.get("series", {}).items():
            if not _matches_query(item, item_query):
                continue
            filtered = _filter_years(ser, year_from, year_to)
            if not filtered:
                continue
            base, context = _split_finance_context_item(item)
            latest_year, latest_value = _latest_year_value(filtered)
            groups.setdefault(base, []).append(
                {
                    "context": context,
                    "item": item,
                    "latest": {"year": latest_year, "value": latest_value},
                    "series": filtered,
                }
            )

    for alternatives in groups.values():
        alternatives.sort(key=lambda row: row["context"])

    truncated = False
    if truncate_groups and len(groups) > max_items:
        keep = sorted(groups)[:max_items]
        groups = {key: groups[key] for key in keep}
        truncated = True

    ambiguous = {
        key: alternatives
        for key, alternatives in groups.items()
        if len({alt["context"] for alt in alternatives}) > 1
    }
    return {
        "available": True,
        "source": FINANCE_CONTEXT_REL,
        "source_category": data.get("_meta", {}).get("category", "finance_context"),
        "org_name": org.get("name") if org else None,
        "policy": (
            "Default finance calls return the representative v1-compatible series. "
            "Context-rich finance rows are retained internally so callers can request a specific "
            "accounting basis or statement form when needed."
        ),
        "found": bool(groups),
        "groups": groups,
        "group_count": len(groups),
        "ambiguous_group_count": len(ambiguous),
        "truncated": truncated,
    }


def _same_numeric_series(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_nums = {str(k): v for k, v in left.items() if isinstance(v, (int, float))}
    right_nums = {str(k): v for k, v in right.items() if isinstance(v, (int, float))}
    return bool(left_nums) and left_nums == right_nums


def _finance_default_basis(
    series: dict[str, dict],
    context_lookup: dict | None,
) -> dict | None:
    if context_lookup is None:
        return None
    if not context_lookup.get("available"):
        return {
            "available": False,
            "source": FINANCE_CONTEXT_REL,
            "reason": context_lookup.get("reason"),
        }

    groups = context_lookup.get("groups", {})
    items: dict[str, dict[str, Any]] = {}
    for item, ser in series.items():
        alternatives = groups.get(item, [])
        matching = [
            alt
            for alt in alternatives
            if _same_numeric_series(ser, alt.get("series", {}))
        ]
        if len(matching) == 1:
            status = "matched_context"
            representative_context = matching[0]["context"]
        elif len(matching) > 1:
            status = "multiple_contexts_same_values"
            representative_context = matching[0]["context"]
        elif alternatives:
            status = "context_candidates_differ"
            representative_context = None
        else:
            status = "context_candidate_missing"
            representative_context = None

        items[item] = {
            "representative_context": representative_context,
            "status": status,
            "has_other_contexts": max(len(alternatives) - len(matching), 0) > 0,
            "other_context_count": max(len(alternatives) - len(matching), 0),
            "matching_context_count": len(matching),
        }

    return {
        "available": True,
        "source": context_lookup.get("source", FINANCE_CONTEXT_REL),
        "mode": "default_series",
        "policy": context_lookup.get("policy"),
        "items": items,
        "item_count": len(items),
        "ambiguous_item_count": sum(
            1 for row in items.values() if row["status"] != "matched_context"
        ),
        "hint": (
            "To retrieve another accounting basis or statement form, include that context "
            "keyword in item_query, for example K-GAAP, K-IFRS, connected, separate, "
            "or the Korean table title term."
        ),
    }


def _finance_context_series(context_lookup: dict) -> tuple[dict[str, dict], dict]:
    series: dict[str, dict] = {}
    basis_items: dict[str, dict[str, Any]] = {}
    for base_item, alternatives in context_lookup.get("groups", {}).items():
        for alt in alternatives:
            item = alt["item"]
            series[item] = alt["series"]
            basis_items[item] = {
                "context": alt["context"],
                "base_item": base_item,
                "status": "requested_context",
            }

    return series, {
        "available": True,
        "source": context_lookup.get("source", FINANCE_CONTEXT_REL),
        "mode": "context_query",
        "policy": context_lookup.get("policy"),
        "items": basis_items,
        "item_count": len(basis_items),
        "truncated": context_lookup.get("truncated", False),
    }


def _prune_basis_to_series(basis: dict | None, series: dict[str, dict]) -> dict | None:
    if not basis or "items" not in basis:
        return basis
    items = {
        item: basis["items"][item]
        for item in series
        if item in basis["items"]
    }
    pruned = dict(basis)
    pruned["items"] = items
    pruned["item_count"] = len(items)
    if "ambiguous_item_count" in pruned:
        pruned["ambiguous_item_count"] = sum(
            1 for row in items.values() if row.get("status") != "matched_context"
        )
    return pruned


def list_items(category: str, item_query: str = "", org_code: str = "") -> dict:
    """카테고리 내 지표 항목명 목록 (org_code 지정 시 해당 기관 보유 항목만)."""
    data = _load(category)
    items: set[str] = set()
    orgs = data["orgs"]
    targets = [orgs[org_code]] if org_code and org_code in orgs else orgs.values()
    for org in targets:
        items.update(org["series"].keys())
    if item_query:
        items = {i for i in items if _matches_query(i, item_query)}
    return {"meta": data["_meta"], "items": sorted(items)}


def get_metrics(
    org_code: str,
    category: str,
    item_query: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    max_items: int = 30,
) -> dict:
    """단일 기관의 지표 시계열 조회."""
    data = _load(category)
    meta = data["_meta"]
    org = data["orgs"].get(org_code)

    caveats = list(meta.get("caveats", []))
    series: dict[str, dict] = {}
    name = None
    finance_context: dict | None = None
    basis: dict | None = None

    if org:
        name = org["name"]
        for item, ser in org["series"].items():
            if not _matches_query(item, item_query):
                continue
            filtered = _filter_years(ser, year_from, year_to)
            if filtered:
                series[item] = filtered

    # 재무는 PDF 파싱 결과가 있으면 우선 병합 (Phase 3)
    if category == "finance":
        finance_context = _finance_context_lookup(
            org_code,
            item_query,
            year_from,
            year_to,
            max_items,
            truncate_groups=not bool(series),
        )
        if finance_context.get("available") and finance_context.get("found"):
            if not name and finance_context.get("org_name"):
                name = finance_context["org_name"]
            if not series:
                series, basis = _finance_context_series(finance_context)
            else:
                basis = _finance_default_basis(series, finance_context)
            caveats.append(
                "Finance default series is v1-compatible; basis summarizes the representative ALIO table context. "
                "Request a context keyword such as K-GAAP or K-IFRS in item_query for context-specific series."
            )
        else:
            basis = _finance_default_basis(series, finance_context)
        pdf = _load_pdf_parsed(org_code)
        if pdf:
            for item, ser in pdf.items():
                if item.startswith("_"):
                    continue
                if not _matches_query(item, item_query):
                    continue
                filtered = _filter_years(ser, year_from, year_to)
                if filtered:
                    series[item] = filtered
            caveats.append("일부 항목은 기관별 통합공시 PDF 파싱 결과 포함")
        elif not org:
            caveats.append(
                "이 기관의 재무 데이터가 적재본(전 기관 결산 크롤 포함)에 없음 — org_code 확인 또는 미공시 가능성"
            )

    if category == "staff":
        caveats.extend(_STAFF_CAVEATS)

    truncated = False
    if len(series) > max_items:
        series, truncated = _truncate_series(series, max_items, category)
        caveats.append(
            f"항목이 많아 {max_items}개로 절단 — staff는 핵심 정원·현원 항목 우선. "
            "item_query='현원' 또는 get_institution_staff_summary 권장"
        )

    basis = _prune_basis_to_series(basis, series)
    result = {
        "org_code": org_code,
        "name": name,
        "category": category,
        "label": meta["label"],
        "unit": meta["unit"],
        "years": meta.get("years", []),
        "series": series,
        "item_count": len(series),
        "truncated": truncated,
        "caveats": caveats,
        "found": bool(series),
    }
    if basis is not None:
        result["basis"] = basis
    return result


def _series_value(ser: dict[str, Any], key: str) -> float | None:
    v = ser.get(key)
    return v if isinstance(v, (int, float)) else None


def screen(
    category: str,
    item_query: str,
    mode: str = "top_n",
    year_from: int | None = None,
    year_to: int | None = None,
    n: int = 10,
    org_codes_filter: set[str] | None = None,
) -> dict:
    """전 기관 스크리닝 — 단일 지표 항목 기준 정렬.

    mode:
    - top_n / bottom_n: 기간 내 최신값 기준 상·하위
    - growth_rate: 기간 첫값 대비 마지막값 증감률(%) 상위
    """
    if mode not in ("top_n", "bottom_n", "growth_rate"):
        raise MetricsError(f"mode는 top_n·bottom_n·growth_rate 중 하나 (현재 '{mode}')")
    if not item_query:
        raise MetricsError("item_query 필수 — list_metric_items로 항목명을 먼저 확인하세요.")

    data = _load(category)
    meta = data["_meta"]

    # item_query에 매칭되는 항목 중 가장 많은 기관이 보유한 항목 1개 선택
    item_counts: dict[str, int] = {}
    for org in data["orgs"].values():
        for item in org["series"]:
            if item_query in item:
                item_counts[item] = item_counts.get(item, 0) + 1
    if not item_counts:
        raise MetricsError(
            f"'{category}'에 '{item_query}' 매칭 항목 없음 — list_metric_items로 확인하세요."
        )
    # 보유 기관 수 최대 → 합계성 항목('계'·'합계') → 일반정규직 → 항목명 짧은 순
    def _item_rank(k: str) -> tuple:
        is_total = ("합계" in k) or ("계(" in k) or k.endswith("-계") or k == "계"
        is_regular = "일반정규직" in k
        return (-item_counts[k], 0 if is_total else 1, 0 if is_regular else 1, len(k), k)

    item = min(item_counts, key=_item_rank)

    rows = []
    for code, org in data["orgs"].items():
        if org_codes_filter is not None and code not in org_codes_filter:
            continue
        ser = org["series"].get(item)
        if not ser:
            continue
        filtered = _filter_years(ser, year_from, year_to)
        keys = sorted(filtered)
        if not keys:
            continue
        latest_key = keys[-1]
        latest = _series_value(filtered, latest_key)
        if mode == "growth_rate":
            first_key = keys[0]
            first = _series_value(filtered, first_key)
            if first is None or latest is None or first == 0 or first_key == latest_key:
                continue
            value = round((latest - first) / abs(first) * 100, 2)
            rows.append(
                {
                    "org_code": code,
                    "name": org["name"],
                    "growth_rate_pct": value,
                    "from": {first_key: first},
                    "to": {latest_key: latest},
                }
            )
        else:
            if latest is None:
                continue
            rows.append(
                {"org_code": code, "name": org["name"], "year": latest_key, "value": latest}
            )

    sort_key = "growth_rate_pct" if mode == "growth_rate" else "value"
    rows.sort(key=lambda r: r[sort_key], reverse=(mode != "bottom_n"))
    n = max(1, min(n, 50))

    caveats = list(meta.get("caveats", []))
    caveats.append(
        "본 결과는 공시 수치 기준 단순 정렬이며 기관 평가·구조조정 판단의 근거가 아닙니다."
    )
    if len(item_counts) > 1:
        others = sorted(set(item_counts) - {item})[:5]
        caveats.append(f"'{item_query}' 매칭 항목 중 '{item}' 사용 — 다른 후보: {others}")

    return {
        "category": category,
        "label": meta["label"],
        "unit": meta["unit"],
        "years": meta.get("years", []),
        "item": item,
        "mode": mode,
        "results": rows[:n],
        "candidates_total": len(rows),
        "caveats": caveats,
    }


def compare(
    org_codes: list[str],
    category: str,
    item_query: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    max_items: int = 10,
) -> dict:
    """2~5개 기관 동일 카테고리 지표 비교."""
    results = []
    missing = []
    for code in org_codes:
        r = get_metrics(code, category, item_query, year_from, year_to, max_items=max_items)
        if r["found"]:
            results.append(r)
        else:
            missing.append(code)

    meta = _load(category)["_meta"]
    caveats = list(meta.get("caveats", []))
    caveats.append("기관별 회계·공시 기준 차이가 있을 수 있음 — 단순 비교 유의")
    if missing:
        caveats.append(f"데이터 없는 기관: {missing}")

    return {
        "category": category,
        "label": meta["label"],
        "unit": meta["unit"],
        "years": meta.get("years", []),
        "comparison": results,
        "missing": missing,
        "caveats": caveats,
    }
