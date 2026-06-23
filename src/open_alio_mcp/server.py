"""ALIO 공공기관 정보 MCP 서버."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from . import data_provider
from . import disclosure_store
from . import guideline_store
from . import handbook_store
from . import law_client
from . import metrics_store
from . import naver_client
from . import news_insights
from . import recruit_store
from .alio_client import (
    AlioAPIError,
    fetch_all_institutions,
    fetch_all_recruitments,
    get_facility_detail,
    get_recruitment_detail,
    list_branches,
    list_businesses,
    list_facilities,
    list_recruitments,
    normalize_business,
    normalize_facility,
    normalize_institution,
    normalize_recruitment,
)
from .disclosure_store import DisclosureError
from .guideline_store import GuidelineError
from .handbook_store import HandbookError
from .law_client import LawAPIError
from .metrics_store import MetricsError
from .naver_client import NaverAPIError
from .security_utils import wrap_fastmcp_tool_registration
from .agent_guide import (
    RECRUITMENT_COVERAGE,
    SERVER_INSTRUCTIONS,
    TOOL_GUIDE,
    recruitment_search_meta,
)

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("open-ALIO-mcp")
mcp = FastMCP("open-ALIO-mcp", instructions=SERVER_INSTRUCTIONS)
mcp.tool = wrap_fastmcp_tool_registration(mcp.tool)

_aliases_raw = data_provider.read_json("aliases.json")
ALIASES: dict[str, str] = {k: v for k, v in _aliases_raw.items() if not k.startswith("_")}

_institution_cache: list[dict] | None = None


def with_source(
    data,
    api_name: str,
    *,
    as_of=None,
    caveats=None,
    meta=None,
    coverage=None,
) -> dict:
    out = {
        "data": data,
        "source": {
            "system": "ALIO 공공기관 경영정보 공개시스템",
            "api": api_name,
            "url": "https://www.alio.go.kr",
            "retrieved_at": datetime.now().isoformat(timespec="seconds"),
            "as_of_year": as_of,
        },
        "caveats": caveats or [],
        "is_error": False,
    }
    if meta is not None:
        out["meta"] = meta
    if coverage is not None:
        out["coverage"] = coverage
    return out


def _load_local_institutions() -> list[dict] | None:
    """data/institutions.json (API+일반현황 CSV 병합본) 로드."""
    data = data_provider.read_json_or_none("institutions.json")
    if not data:
        return None
    try:
        return data["orgs"]
    except KeyError:
        return None


def _get_institutions() -> list[dict]:
    """기관 목록: 로컬 병합본 우선, 없으면 API 호출."""
    global _institution_cache
    if _institution_cache is None:
        local = _load_local_institutions()
        if local:
            _institution_cache = local
            log.info("기관 목록 로컬 로드: %d건 (institutions.json)", len(local))
        else:
            rows = fetch_all_institutions()
            _institution_cache = [normalize_institution(r) for r in rows]
            log.info("기관 목록 API 로드: %d건", len(_institution_cache))
    return _institution_cache


def _valid_count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _institution_count_summary(
    institutions: list[dict],
    *,
    prefer_meta: bool = False,
) -> dict:
    disclosure_units_count = len(institutions)
    subsidiary_count = sum(1 for inst in institutions if inst.get("is_subsidiary") is True)
    institutions_count = disclosure_units_count - subsidiary_count

    if prefer_meta:
        local = data_provider.read_json_or_none("institutions.json")
        meta = local.get("_meta", {}) if isinstance(local, dict) else {}
        if isinstance(meta, dict):
            disclosure_units_count = _valid_count(meta.get("count")) or disclosure_units_count
            subsidiary_count = _valid_count(meta.get("subsidiary_count")) or subsidiary_count
            institutions_count = _valid_count(meta.get("independent_org_count")) or (
                disclosure_units_count - subsidiary_count
            )

    return {
        "institutions_count": institutions_count,
        "subsidiary_count": subsidiary_count,
        "disclosure_units_count": disclosure_units_count,
    }


# 정부조직 개편 전 부처명·통용 약칭 → institutions.json의 현행 부처명
MINISTRY_ALIASES: dict[str, str] = {
    "산업통상자원부": "산업통상부",
    "산자부": "산업통상부",
    "산업부": "산업통상부",
    "기획재정부": "재정경제부",
    "기재부": "재정경제부",
    "환경부": "기후에너지환경부",
    "여성가족부": "성평등가족부",
    "여가부": "성평등가족부",
    "특허청": "지식재산처",
    "통계청": "국가데이터처",
    "방송통신위원회": "방송미디어통신위원회",
    "방통위": "방송미디어통신위원회",
    "국가보훈처": "국가보훈부",
    "보훈처": "국가보훈부",
    "과기정통부": "과학기술정보통신부",
    "과기부": "과학기술정보통신부",
    "국토부": "국토교통부",
    "복지부": "보건복지부",
    "해수부": "해양수산부",
    "농식품부": "농림축산식품부",
    "문체부": "문화체육관광부",
    "행안부": "행정안전부",
    "고용부": "고용노동부",
    "중기부": "중소벤처기업부",
    "식약처": "식품의약품안전처",
}

# 개편으로 기능이 둘 이상 부처로 분리된 경우 — 매핑 caveat에 함께 안내
MINISTRY_SPLIT_NOTES: dict[str, str] = {
    "기획재정부": "예산 기능은 '기획예산처'로 분리 — 기획예산처 산하 기관은 ministry='기획예산처'로 별도 조회",
    "산업통상자원부": "에너지 기능은 '기후에너지환경부'로 이관 — 에너지 공기업 일부는 ministry='기후에너지환경부' 소속",
}

# 도서·섬 지명 및 통용 지역 약칭 → 검색 키워드 목록
# ALIO 기관 소재지(location/address)에는 행정구역 명칭으로 저장되므로
# 비행정구역 지명(강화도 등)은 인접 행정구역으로 확장 매핑
LOCATION_ALIASES: dict[str, list[str]] = {
    "강화도": ["인천광역시 강화군", "인천광역시"],
    "강화": ["인천광역시 강화군", "인천광역시"],
    "영종도": ["인천광역시 중구"],
    "용유도": ["인천광역시 중구"],
    "여의도": ["서울특별시 영등포구"],
    "제주도": ["제주특별자치도"],
    "제주": ["제주특별자치도"],
    "울릉도": ["경상북도 울릉군"],
    "거제도": ["경상남도 거제시"],
    "남해도": ["경상남도 남해군"],
    "진도": ["전라남도 진도군"],
}


def _resolve_ministry(ministry: str) -> tuple[str, list[str]]:
    """구 부처명·약칭을 현행 명칭으로 치환하고 안내 caveat를 돌려준다."""
    m = ministry.strip()
    resolved = MINISTRY_ALIASES.get(m, m)
    caveats: list[str] = []
    if resolved != m:
        caveats.append(f"부처명 '{m}'을(를) 현행 명칭 '{resolved}'(정부조직 개편 반영)으로 해석했습니다.")
        if m in MINISTRY_SPLIT_NOTES:
            caveats.append(MINISTRY_SPLIT_NOTES[m])
    return resolved, caveats


def _available_ministries() -> list[str]:
    return sorted({m for inst in _get_institutions() if (m := (inst.get("ministry") or "").strip())})


def _resolve_query(query: str) -> str:
    q = query.strip()
    if not q:
        return q
    # 대소문자 구분 없이 매칭: 정확→소문자→대문자 순
    return ALIASES.get(q, ALIASES.get(q.lower(), ALIASES.get(q.upper(), q)))


def _alias_candidates(query: str) -> list[str]:
    """별칭 키 부분일치 → 공식 기관명 후보 (직접 매칭 실패 시 fallback)."""
    q = query.strip()
    if len(q) < 2:
        return []
    seen: list[str] = []
    for alias, official in ALIASES.items():
        if q in alias and official not in seen:
            seen.append(official)
    return seen[:10]


def _rank(name: str, q: str) -> int:
    """관련도: 완전일치 > 접두 > 포함."""
    if name == q:
        return 0
    if name.startswith(q):
        return 1
    return 2


def _disclosure_caveats(category: str, *, series: dict | None = None, found: bool = True) -> list[str]:
    """공시 주기 주석 + (요청 연도 범위 대비) 공백 안내."""
    notes: list[str] = []
    try:
        phrase = disclosure_store.schedule_phrase(category)
    except DisclosureError:
        phrase = None
    if phrase:
        notes.append(phrase)
        if not found:
            notes.append(
                "데이터가 비어 있다면 해당 공시 주기가 아직 도래하지 않았거나 기관이 미공시했을 수 있습니다."
            )
        elif series:
            # 연도별 시계열에 비어 있는 연도가 있으면 주기 영향 가능성 안내
            has_gap = any(
                isinstance(ser, dict) and any(v in (None, "", 0) for v in ser.values())
                for ser in series.values()
            )
            if has_gap:
                notes.append(
                    "일부 연도 값이 비어 있을 수 있으며, 이는 공시 주기·기관별 공시 시점 차이에 기인할 수 있습니다."
                )
    return notes


def _resolve_org(org_code: str, query: str) -> dict | None:
    """org_code 또는 query(별칭 치환 포함)로 알려진 기관 1건 반환. 없으면 None."""
    if org_code:
        return next((i for i in _get_institutions() if i.get("org_code") == org_code), None)
    if query:
        resolved = _resolve_query(query)
        return next((i for i in _get_institutions() if i.get("name") == resolved), None)
    return None


def _news_items(terms: list[str], *, days: int, sort: str = "date", max_fetch: int = 300):
    """검색어 목록 → (정제·중복제거·기간필터된 뉴스, 수집 원시건수, oldest_ts, raw_query)."""
    nq = naver_client.build_news_query(terms)
    cutoff = datetime.now().astimezone().timestamp() - days * 86400 if days > 0 else None
    raw_items = naver_client.fetch_news(
        nq,
        sort=sort,
        max_results=min(max(max_fetch, 100), 1000),
        stop_before_ts=cutoff if sort == "date" else None,
    )
    items = naver_client.dedup_news(
        [naver_client.normalize_news_item(it) for it in raw_items]
    )
    if cutoff is not None:
        items = [
            it
            for it in items
            if it["published_at"]
            and datetime.fromisoformat(it["published_at"]).timestamp() >= cutoff
        ]
    oldest_ts = None
    if raw_items and sort == "date":
        last_dt = naver_client.parse_pubdate(raw_items[-1].get("pubDate"))
        oldest_ts = last_dt.timestamp() if last_dt else None
    return items, len(raw_items), oldest_ts, cutoff


def _latest_point(series_item: dict) -> tuple[str | None, float | int | None]:
    """{'2021': v, ...} → (가장 최근 연도, 값). 숫자 아닌 값은 무시."""
    if not series_item:
        return None, None
    for year in sorted(series_item, reverse=True):
        val = series_item[year]
        if isinstance(val, (int, float)):
            return year, val
    return None, None


SUBSIDIARY_SEARCH_CAVEAT = (
    "부설기관은 독립 법인이 아니며 모기관 산하 공시 단위입니다. "
    "유형별 집계는 classification_org_type(모기관 유형 상속)을 참고하세요."
)


def _subsidiary_fields(inst: dict) -> dict:
    return {
        "is_subsidiary": bool(inst.get("is_subsidiary")),
        "parent_org_code": inst.get("parent_org_code"),
        "parent_org_name": inst.get("parent_org_name"),
        "classification_org_type": inst.get("classification_org_type") or inst.get("org_type"),
    }


def _subsidiary_profile_caveat(inst: dict) -> str | None:
    if not inst.get("is_subsidiary"):
        return None
    return (
        f"{inst.get('name')}은(는) {inst.get('parent_org_name')}의 부설기관입니다. "
        f"org_type은 ALIO 공시 지정 유형이며, 동종 비교 시 "
        f"classification_org_type({inst.get('classification_org_type')})을 사용하세요."
    )


@mcp.tool()
def search_institutions(
    query: str = "",
    org_type: str = "",
    ministry: str = "",
    location: str = "",
    limit: int = 10,
) -> dict:
    """공공기관을 이름·유형·주무부처·소재지로 검색합니다. org_code는 다른 도구의 진입점입니다.

    location: 소재지 키워드 (예: '인천', '강화도', '세종', '부산'). 행정구역 명칭 부분일치.
    도서·섬 지명(강화도·제주도 등)은 인접 행정구역으로 자동 확장됩니다.
    """
    try:
        q = _resolve_query(query)
        ministry, ministry_caveats = _resolve_ministry(ministry)
        institutions = _get_institutions()
        loc_q = location.strip()

        # 도서·섬 지명 등 비행정구역 지명 → 인접 행정구역 키워드 목록으로 확장
        loc_terms: list[str] = LOCATION_ALIASES.get(loc_q, [loc_q]) if loc_q else []
        loc_expanded = loc_q in LOCATION_ALIASES

        def _loc_match(inst: dict) -> bool:
            if not loc_terms:
                return True
            combined = (inst.get("location") or "") + " " + (inst.get("address") or "")
            return any(term in combined for term in loc_terms)

        def _match(inst: dict, name_q: str) -> bool:
            return (
                (not name_q or name_q in (inst.get("name") or ""))
                and (not org_type or org_type in (inst.get("org_type") or ""))
                and (not ministry or ministry in (inst.get("ministry") or ""))
                and _loc_match(inst)
            )

        matched = [inst for inst in institutions if _match(inst, q)]
        caveats: list[str] = list(ministry_caveats)

        if loc_expanded:
            caveats.append(
                f"'{loc_q}'은(는) 비행정구역 지명으로, "
                f"인접 행정구역 {loc_terms}(으)로 확장 검색했습니다."
            )

        # 이름 직접 매칭 실패 → 별칭 키 부분일치 fallback ("심평" → 심사평가원 등)
        if not matched and q:
            candidates = set(_alias_candidates(q))
            if candidates:
                matched = [
                    inst
                    for inst in institutions
                    if (inst.get("name") or "") in candidates and _match(inst, "")
                ]
                if matched:
                    caveats.append(f"'{query}' 별칭 부분일치로 검색됨 — 후보 {len(matched)}건")

        if q:
            matched.sort(key=lambda i: (_rank(i.get("name") or "", q), i.get("name") or ""))
        results = []
        for inst in matched[:limit]:
            row = {k: v for k, v in inst.items() if k != "detail"}
            row.update(_subsidiary_fields(inst))
            results.append(row)
        matched_counts = _institution_count_summary(matched)
        if matched_counts["subsidiary_count"]:
            caveats.append(
                "검색 집계: total_matched는 ALIO 공시 단위(부설기관 포함) 기준입니다. "
                "공공기관 수는 public_institutions_matched를 사용하세요."
            )
        if any(r.get("is_subsidiary") for r in results):
            caveats.append(SUBSIDIARY_SEARCH_CAVEAT)

        out = with_source(
            {
                "results": results,
                "count": len(results),
                "total_matched": len(matched),
                "public_institutions_matched": matched_counts["institutions_count"],
                "subsidiary_matched": matched_counts["subsidiary_count"],
                "disclosure_units_matched": matched_counts["disclosure_units_count"],
                "count_basis": (
                    "total_matched/disclosure_units_matched include ALIO disclosure units; "
                    "public_institutions_matched excludes subsidiaries."
                ),
            },
            "재정경제부_공공기관 정보 조회서비스 /list",
            caveats=caveats,
        )
        if not results and q:
            msg = "검색 결과 없음 — 공식 기관명으로 재검색 권장"
            if q != query.strip():
                msg += f" (별칭 '{query}' → '{q}')"
            out["caveats"].append(msg)
        if not results and ministry:
            out["caveats"].append(
                "ministry 필터 결과 없음 — 부처명은 현행 정부조직 명칭으로 저장됩니다. "
                f"보유 부처명: {', '.join(_available_ministries())}"
            )
        if not results and loc_q:
            out["caveats"].append(
                f"location='{loc_q}' 검색 결과 없음 — "
                "행정구역 명칭(시·도·군·구) 또는 통용 지명으로 재시도하세요."
            )
        return out
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e), "hint": "API 키·일일 한도 확인"}


@mcp.tool()
def get_institution_profile(org_code: str, include_detail: bool = True) -> dict:
    """기관코드(instCd)로 기본 프로필을 조회합니다.

    include_detail=True면 일반현황 상세(설립목적·주요기능·경영목표·기관장 등)를 포함합니다.
    """
    try:
        institutions = _get_institutions()
        match = next((i for i in institutions if i.get("org_code") == org_code), None)
        if not match:
            return {
                "data": None,
                "is_error": True,
                "error": f"기관코드 {org_code} 없음",
            }
        profile = dict(match)
        profile.update(_subsidiary_fields(match))
        if not include_detail:
            profile.pop("detail", None)
        caveats = []
        sub_caveat = _subsidiary_profile_caveat(profile)
        if sub_caveat:
            caveats.append(sub_caveat)
        return with_source(
            {"profile": profile},
            "재정경제부_공공기관 정보 조회서비스 /list + ALIO 일반현황(2026)",
            caveats=caveats,
        )
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def list_metric_categories() -> dict:
    """공시지표 카테고리 목록을 조회합니다 (staff·salary·finance·welfare 등 11종).

    get_institution_metrics / compare_institutions의 category 파라미터로 사용합니다.
    """
    try:
        cats = metrics_store.list_categories()
        caveats = []
        fin = next((c for c in cats if c.get("category") == "finance"), None)
        if fin:
            caveats.append(
                f"finance는 크롤 승격으로 전 기관({fin.get('org_count')}개) 결산 재무를 포함합니다"
                " — 반기 항목은 반기 재정현황 공시 대상(공기업·과거 공기업 지정 이력 기관)만 제공"
            )
        return with_source(
            {"categories": cats, "count": len(cats)},
            "ALIO 항목별 공시 엑셀 (로컬 가공)",
            caveats=caveats,
        )
    except MetricsError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def list_disclosure_items(
    query: str = "",
    group: str = "",
    disclosure_type: str = "",
    schedule: str = "",
    metric_category: str = "",
    only_with_metric: bool = False,
    limit: int = 100,
) -> dict:
    """ALIO 경영공시 50개 항목 카탈로그를 조회합니다 (정기/수시·공시주기·분류).

    출처: alio.go.kr 경영공시 제도(공운법 제12조). "재무 공시는 언제 올라와?",
    "수시공시 항목만", "2분기 정기공시 목록" 같은 질문에 사용하세요.

    disclosure_type: '정기' 또는 '수시'.
    schedule: 공시시기 부분일치 (예: '1분기', '매분기').
    metric_category: 특정 지표(staff·finance 등)에 매핑된 공시항목만.
    only_with_metric=True면 본 MCP 지표로 조회 가능한 항목만 반환합니다.
    """
    try:
        result = disclosure_store.search(
            query=query,
            group=group,
            type_filter=disclosure_type,
            schedule=schedule,
            metric_category=metric_category,
            has_metric=True if only_with_metric else None,
            limit=min(max(limit, 1), 100),
        )
        return with_source(
            result,
            "ALIO 경영공시 항목 카탈로그 (managementDisclosure.do)",
            caveats=disclosure_store.get_meta().get("caveats", []),
        )
    except DisclosureError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def list_metric_items(category: str, item_query: str = "", org_code: str = "") -> dict:
    """카테고리 내 지표 항목명을 조회합니다.

    예: category='staff', item_query='정원' → 정원 관련 항목명 목록.
    org_code를 주면 해당 기관이 보유한 항목만 반환합니다.
    """
    try:
        result = metrics_store.list_items(category, item_query, org_code)
        return with_source(
            {"category": category, "items": result["items"], "count": len(result["items"])},
            f"ALIO 항목별 공시 — {result['meta']['label']}",
            caveats=result["meta"].get("caveats", []),
        )
    except MetricsError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_institution_metrics(
    org_code: str,
    category: str,
    item_query: str = "",
    year_from: int = 0,
    year_to: int = 0,
) -> dict:
    """기관의 공시지표 시계열을 조회합니다. (설계서 §4-1 ②)

    category: staff(임직원수)·salary(평균보수)·executive_pay(임원연봉)·recruitment(신규채용)·
    budget(수입지출)·welfare(복리후생비)·work_life(일가정양립)·welfare_etc·tax(법인세)·
    head_expense(기관장업무추진비)·finance(재무 — 결산은 전 기관, 반기 항목은 공기업 계열 한정).
    item_query로 항목을 좁힐 수 있습니다. 예: '정원', '현원', '부채', '기본급'.
    staff(인력) 조회 시: '임직원 총계'·'정원-계'는 정원, '현원-전일제'가 실제 재직 인원.
    인력현황 요약은 get_institution_staff_summary 권장.
    """
    try:
        result = metrics_store.get_metrics(
            org_code,
            category,
            item_query,
            year_from or None,
            year_to or None,
        )
        out = with_source(
            result,
            f"ALIO 항목별 공시 — {result['label']}",
            as_of=(result.get("years") or [None])[-1],
            caveats=result.pop("caveats"),
        )
        out["caveats"].extend(
            _disclosure_caveats(
                category, series=result.get("series"), found=result["found"]
            )
        )
        if not result["found"]:
            out["caveats"].append(
                f"기관 {org_code}의 '{category}' 데이터 없음 — org_code 확인 또는 list_metric_categories 참조"
            )
        return out
    except MetricsError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_institution_staff_summary(
    org_code: str = "",
    query: str = "",
    year_from: int = 0,
    year_to: int = 0,
) -> dict:
    """기관 인력현황 요약 — 정원(authorized) vs 현원(actual)을 구분해 반환합니다.

    '○○기관 인력 몇 명?'·'정원 현원' 질의에 사용. 임직원 총계(A+B+C)는 정원이므로
    headcount.estimated_total(정규 전일제+기간제)을 실제 재직 규모로 참고하세요.
    """
    inst = _resolve_org(org_code, query)
    if not inst:
        return {
            "data": None,
            "is_error": True,
            "error": f"기관을 찾을 수 없음 (org_code='{org_code}', query='{query}')",
            "hint": "search_institutions로 org_code 확인",
        }
    try:
        result = metrics_store.staff_summary(
            inst["org_code"],
            year_from or None,
            year_to or None,
        )
        out = with_source(
            result,
            "ALIO 항목별 공시 — 임직원 수 (정원·현원 구분 요약)",
            caveats=result.pop("caveats"),
        )
        out["caveats"].extend(_disclosure_caveats("staff", found=result["found"]))
        return out
    except MetricsError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def compare_institutions(
    org_codes: list[str],
    category: str,
    item_query: str = "",
    year_from: int = 0,
    year_to: int = 0,
) -> dict:
    """2~5개 기관을 동일 지표로 비교합니다. (설계서 §4-1 ③)

    org_codes: search_institutions로 얻은 instCd 목록 (2~5개).
    item_query로 비교 항목을 좁히면 응답이 가벼워집니다. 예: '부채', '정원', '기본급'.
    """
    try:
        if not 2 <= len(org_codes) <= 5:
            return {
                "data": None,
                "is_error": True,
                "error": f"org_codes는 2~5개여야 합니다 (현재 {len(org_codes)}개)",
            }
        result = metrics_store.compare(
            org_codes,
            category,
            item_query,
            year_from or None,
            year_to or None,
        )
        out = with_source(
            result,
            f"ALIO 항목별 공시 — {result['label']}",
            as_of=(result.get("years") or [None])[-1],
            caveats=result.pop("caveats"),
        )
        out["caveats"].extend(_disclosure_caveats(category, found=bool(result["comparison"])))
        return out
    except MetricsError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def find_institutions_by_criteria(
    category: str,
    item_query: str,
    mode: str = "top_n",
    year_from: int = 0,
    year_to: int = 0,
    org_type: str = "",
    ministry: str = "",
    n: int = 10,
    exclude_subsidiaries: bool = False,
    use_classification_org_type: bool = False,
) -> dict:
    """조건 기반 기관 스크리닝 — 지표 상·하위, 증감률 상위 기관을 찾습니다. (설계서 §4-1 ④)

    mode: top_n(최신값 상위)·bottom_n(하위)·growth_rate(기간 증감률 % 상위).
    item_query는 정렬 기준 항목 (예: category='staff', item_query='정원' 또는 '현원-전일제').
    staff에서 item_query='정원'은 정원 기준, 실제 재직 인원 비교는 '현원-전일제' 사용.
    org_type·ministry로 대상 기관을 좁힐 수 있습니다 (예: org_type='공기업').
    exclude_subsidiaries=True면 부설기관 공시 단위를 제외합니다.
    use_classification_org_type=True이고 org_type을 지정하면 부설기관은 모기관 유형으로 필터합니다.
    결과는 단순 정렬이며 기관 평가·판단의 근거가 아닙니다.
    """
    try:
        ministry, ministry_caveats = _resolve_ministry(ministry)
        org_filter: set[str] | None = None
        if org_type or ministry or exclude_subsidiaries:
            org_filter = {
                inst["org_code"]
                for inst in _get_institutions()
                if (
                    not org_type
                    or org_type in (
                        (inst.get("classification_org_type") if use_classification_org_type else inst.get("org_type"))
                        or ""
                    )
                )
                and (not ministry or ministry in (inst.get("ministry") or ""))
                and (not exclude_subsidiaries or not inst.get("is_subsidiary"))
            }
        result = metrics_store.screen(
            category,
            item_query,
            mode,
            year_from or None,
            year_to or None,
            n,
            org_filter,
        )
        caveats = result.pop("caveats")
        caveats.extend(ministry_caveats)
        if ministry and not org_filter:
            caveats.append(
                "ministry 필터에 해당하는 기관 없음 — 부처명은 현행 정부조직 명칭으로 저장됩니다. "
                f"보유 부처명: {', '.join(_available_ministries())}"
            )
        if exclude_subsidiaries:
            caveats.append("부설기관 공시 단위는 스크리닝 모집단에서 제외했습니다.")
        if use_classification_org_type and org_type:
            caveats.append("org_type 필터에 classification_org_type(부설기관은 모기관 유형 상속)을 사용했습니다.")
        return with_source(
            result,
            f"ALIO 항목별 공시 — {result['label']} (스크리닝)",
            as_of=(result.get("years") or [None])[-1],
            caveats=caveats,
        )
    except (MetricsError, AlioAPIError) as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_institution_branches(org_code: str, limit: int = 20) -> dict:
    """기관코드로 지점 목록을 조회합니다 (/brnch)."""
    try:
        raw = list_branches(inst_cd=org_code, num_of_rows=limit)
        branches = raw.get("result") or []
        return with_source(
            {"org_code": org_code, "branches": branches, "count": len(branches)},
            "재정경제부_공공기관 정보 조회서비스 /brnch",
        )
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def search_public_services(
    query: str = "",
    org_code: str = "",
    service_class: str = "",
    lifecycle: str = "",
    limit: int = 10,
) -> dict:
    """공공기관의 국가사업·대민 편의사업(서비스)을 검색합니다. org_code는 instCd입니다."""
    try:
        raw = list_businesses(
            page_no=1,
            num_of_rows=min(max(limit, 1), 100),
            inst_cd=org_code or None,
            biz_nm=query or None,
            srvc_clsf=service_class or None,
            lifecycl_lst=lifecycle or None,
        )
        rows = raw.get("result") or []
        if query and not org_code:
            # API bizNm 필터 외에 설명·기관명도 보조 검색
            rows = [
                r
                for r in rows
                if query in (r.get("bizNm") or "")
                or query in (r.get("bizExpln") or "")
                or query in (r.get("instNm") or "")
            ]
        results = [normalize_business(r) for r in rows[:limit]]
        return with_source(
            {
                "results": results,
                "count": len(results),
                "total_count": raw.get("totalCount"),
            },
            "재정경제부_공공기관 사업정보 조회서비스 /list",
        )
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def search_facilities(
    org_code: str = "",
    region: str = "",
    district: str = "",
    facility_type_code: str = "",
    free_only: bool = False,
    reservable_only: bool = False,
    query: str = "",
    page: int = 1,
    limit: int = 10,
) -> dict:
    """공공기관이 개방·관리하는 시설을 검색합니다. org_code는 search_institutions 결과의 org_code(instCd)입니다.

    query는 시설명·기관명·이용방법·주소를 통합 검색합니다 (예: '회의', '네이버 예약').
    reservable_only=True면 예약 가능(rsvtPsbltyYn=Y) 시설만 반환합니다.
    결과의 has_more=True면 page를 올려 다음 페이지를 조회하세요.
    """
    try:
        # query·reservable 필터는 클라이언트 측이므로 넉넉히 받아서 거른다
        fetch_rows = 100 if (query or reservable_only) else min(max(limit, 1), 100)
        raw = list_facilities(
            page_no=max(page, 1),
            num_of_rows=fetch_rows,
            mng_inst_cd=org_code or None,
            ctpv_nm=region or None,
            sgg_nm=district or None,
            fclt_type_cd=facility_type_code or None,
            chagfee_yn="N" if free_only else None,
        )
        rows = raw.get("result") or []
        if query:
            rows = [
                r
                for r in rows
                if any(
                    query in (r.get(f) or "")
                    for f in ("fcltNm", "instNm", "utztnMthdExpln", "roadNmAddr", "fcltTypeFullNm")
                )
            ]
        if reservable_only:
            rows = [r for r in rows if r.get("rsvtPsbltyYn") == "Y"]
        total = int(raw.get("totalCount") or 0)
        results = [normalize_facility(r) for r in rows[:limit]]
        return with_source(
            {
                "results": results,
                "count": len(results),
                "total_count": total,
                "page": max(page, 1),
                "has_more": max(page, 1) * fetch_rows < total,
            },
            "재정경제부_공공기관 시설정보 조회서비스 /list",
            caveats=(
                ["query·reservable_only는 현재 페이지 내 필터 — has_more=True면 다음 page도 확인 권장"]
                if (query or reservable_only) and max(page, 1) * fetch_rows < total
                else None
            ),
        )
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_facility_profile(facility_sn: int) -> dict:
    """시설 일련번호(sn/fcltSn)로 상세정보와 첨부파일 메타를 조회합니다."""
    try:
        raw = get_facility_detail(sn=facility_sn)
        detail = raw.get("result")
        if not detail:
            return {"data": None, "is_error": True, "error": f"시설 sn={facility_sn} 없음"}
        return with_source(
            {"facility": detail, "summary": normalize_facility(detail)},
            "재정경제부_공공기관 시설정보 조회서비스 /detail",
        )
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e)}


def _resolve_recruit_org(query: str) -> tuple[str | None, str | None]:
    """질의가 기관명/별칭이면 (org_code, 공식기관명) 반환 — '한전 채용 떴어?' 대응.

    별칭·완전일치는 신뢰. 부분일치는 '연구원' 같은 일반 키워드 오인을 막기 위해
    유일하게 매칭되는 기관이 있을 때만 인정.
    """
    q = query.strip()
    if len(q) < 2:
        return None, None
    official = _resolve_query(q)
    alias_offs = set(_alias_candidates(q)) if official == q else set()
    partial: list[tuple[str, str]] = []
    alias_hits: list[tuple[str, str]] = []
    for inst in _get_institutions():
        name = inst.get("name") or ""
        if name == official:
            return inst.get("org_code"), name
        if name in alias_offs:
            alias_hits.append((inst.get("org_code"), name))
        if len(q) >= 3 and q in name:
            partial.append((inst.get("org_code"), name))
    # 오인 방지: 부분일치·별칭 후보는 유일할 때만 기관으로 해석
    if len(partial) == 1:
        return partial[0]
    if not partial and len(alias_hits) == 1:
        return alias_hits[0]
    return None, None


@mcp.tool()
def search_recruitments(
    query: str = "",
    org_code: str = "",
    ongoing_only: bool = True,
    work_region_code: str = "",
    region: str = "",
    ncs: str = "",
    hire_type: str = "",
    recruit_type: str = "",
    education: str = "",
    pref: str = "",
    closing_within_days: int = 0,
    sort: str = "latest",
    include_cancelled: bool = False,
    use_snapshot: bool = False,
    limit: int = 10,
) -> dict:
    """공공기관·잡알리오·ALIO 채용공고 검색 — 청년인턴(체험형/채용형), 신입·경력, 마감임박(D-day), 지역·NCS 직무별.

    웹검색 대신 이 도구를 우선 사용하세요. query에 기관명·별칭('한전')을 넣으면 해당 기관 공고로 해석합니다.
    org_code는 pblntInstCd(instCd)입니다.
    필터: region(근무지역명), ncs(직무분류명), hire_type(예 '청년인턴'), recruit_type('신입'·'경력'),
    education(학력), pref(우대조건 키워드). closing_within_days>0이면 마감 N일 이내만.
    sort: 'latest'(기본)·'deadline'(마감임박순)·'headcount'(모집인원순).
    use_snapshot=True면 로컬 스냅샷 전수 조회 — 필터·정렬 완전성 보장(meta.is_complete=true).
    필터·정렬 시 스냅샷이 있으면 자동 사용( auto_snapshot_used ). API 경로는 서버 필터+전수 페이지네이션.
    응답 meta.is_complete=false이면 사용자에게 일부만 조회됨을 알리세요.
    중앙부처 청년인턴(청년인재DB)·나라일터는 미포함 — coverage 블록 참조.
    """
    cycle = _disclosure_caveats("recruitment")
    caveats = list(cycle)
    try:
        # 기관명/별칭 질의 → org_code 자동 해석 (API title 검색은 기관명에 안 걸림)
        resolved_org_name = None
        if query and not org_code:
            resolved_code, resolved_org_name = _resolve_recruit_org(query)
            if resolved_code:
                org_code = resolved_code
                query = ""
                caveats.append(f"질의를 기관 '{resolved_org_name}'(org_code={org_code})으로 해석해 검색")
            else:
                caveats.append(
                    f"'{query}'을(를) 기관명으로 해석하지 못해 공고 제목 검색으로 처리됨 — "
                    "특정 기관 공고가 목적이면 search_institutions로 org_code를 먼저 확인하세요. "
                    "0건이어도 '해당 기관 채용 없음'으로 단정할 수 없습니다."
                )

        client_filter_applied = recruit_store.needs_client_side_recruitment_filter(
            region=region,
            ncs=ncs,
            hire_type=hire_type,
            recruit_type=recruit_type,
            education=education,
            pref=pref,
            closing_within_days=closing_within_days,
            sort=sort,
        )

        auto_snapshot = False
        if not use_snapshot and client_filter_applied and recruit_store.snapshot_records() is not None:
            use_snapshot = True
            auto_snapshot = True
            caveats.append(
                "필터·정렬 완전성을 위해 로컬 채용 스냅샷을 자동 사용했습니다 — "
                "최신 공고는 API 직접 조회(use_snapshot=False)로 교차 확인하세요"
            )

        api_params = recruit_store.build_recruitment_api_params(
            org_code=org_code,
            query=query,
            work_region_code=work_region_code,
            region=region,
            ncs=ncs,
            hire_type=hire_type,
            recruit_type=recruit_type,
            education=education,
        )
        api_exhausted = False

        snap = recruit_store.snapshot_records() if use_snapshot else None
        if snap is not None:
            records = snap
            source_api = "채용 스냅샷 (data/snapshots/recruitments_ongoing.json)"
            total = len(records)
            meta_snap = recruit_store.snapshot_meta()
            if meta_snap:
                caveats.append(f"스냅샷 기준 시각: {meta_snap.get('built_at')} — 이후 등록·마감된 공고는 미반영")
        elif client_filter_applied:
            rows, total = fetch_all_recruitments(
                ongoing_yn="Y" if ongoing_only else None,
                **api_params,
            )
            records = [normalize_recruitment(r) for r in rows]
            api_exhausted = len(records) >= total
            source_api = "재정경제부_공공기관 채용정보 조회서비스 /list (API 필터·전수)"
            if not api_exhausted:
                caveats.append(
                    f"API 전수 수집이 {len(records)}/{total}건에서 중단됨 — "
                    "일부 공고가 누락됐을 수 있습니다"
                )
        else:
            raw = list_recruitments(
                page_no=1,
                num_of_rows=min(max(limit, 1), 100),
                ongoing_yn="Y" if ongoing_only else None,
                **api_params,
            )
            rows = raw.get("result") or []
            records = [normalize_recruitment(r) for r in rows]
            source_api = "재정경제부_공공기관 채용정보 조회서비스 /list"
            total = int(raw.get("totalCount") or len(records))

        filtered = recruit_store.filter_records(
            records,
            query=query if snap is not None else "",
            org_code=org_code if snap is not None else "",
            region=region,
            ncs=ncs,
            hire_type=hire_type,
            recruit_type=recruit_type,
            education=education,
            pref=pref,
            closing_within=closing_within_days or None,
            exclude_expired=ongoing_only and snap is not None,
            exclude_cancelled=not include_cancelled,
        )
        filtered = recruit_store.sort_records(filtered, sort)
        results = recruit_store.refresh_days(filtered[:limit])

        if client_filter_applied and snap is None and not api_exhausted and total > len(records):
            caveats.append(
                "필터·정렬 결과가 불완전할 수 있음 — use_snapshot=True 또는 analyze_recruitments 권장"
            )
        if not client_filter_applied and snap is None and total > len(records):
            caveats.append(f"API에서 {len(records)}건만 조회됨 — 전체 {total}건 중 일부일 수 있음")
        if results:
            caveats.append(
                "days_remaining은 마감일 기준 잔여일(0=오늘 마감) — "
                "마감 시각은 deadline_display·공고 원문(apply_url) 확인 필요"
            )
        elif resolved_org_name:
            caveats.append(
                f"'{resolved_org_name}'의 진행중 공고가 현재 없음 — ongoing_only=False로 종료 공고 조회 가능"
            )

        meta = recruitment_search_meta(
            returned=len(results),
            matched=len(filtered),
            corpus_total=total,
            fetched=len(records),
            use_snapshot=snap is not None,
            client_filter_applied=client_filter_applied,
            auto_snapshot=auto_snapshot,
            api_exhausted=api_exhausted,
        )
        if not meta["is_complete"]:
            caveats.append(
                "meta.is_complete=false — 반환 목록은 전체 매칭 결과의 일부일 수 있습니다. "
                "사용자에게 누락 가능성을 알리세요."
            )

        return with_source(
            {
                "results": results,
                "count": len(results),
                "matched": len(filtered),
                "total_count": total,
                "resolved_org": resolved_org_name,
            },
            source_api,
            caveats=caveats,
            meta=meta,
            coverage=RECRUITMENT_COVERAGE,
        )
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def analyze_recruitments(
    dimension: str,
    ongoing_only: bool = True,
    region: str = "",
    ncs: str = "",
    hire_type: str = "",
    pref: str = "",
    top_n: int = 20,
    use_snapshot: bool = True,
) -> dict:
    """진행중 채용공고 분포 집계 — 지역·직무·고용형태·기관별 공고 수·모집인원.

    지원자용: '서울 IT 청년인턴 몇 건?' → dimension='region', hire_type='청년인턴', ncs='정보통신'
    연구·정책용: 전체 분포·수도권 편중·NCS 수요 등 거시 패턴 분석.
    dimension: region·ncs·hire_type·recruit_type·education·org.
    use_snapshot=True(기본)면 로컬 스냅샷 전수 — 없으면 라이브 API 전수 수집.
    중앙부처 청년인턴·나라일터 미포함 — coverage 블록 참조.
    """
    cycle = _disclosure_caveats("recruitment")
    try:
        records = recruit_store.snapshot_records() if use_snapshot else None
        source_note = "채용 스냅샷 (data/snapshots/recruitments_ongoing.json)"
        snapshot_used = records is not None
        if records is None:
            rows, _total = fetch_all_recruitments(ongoing_yn="Y" if ongoing_only else None)
            records = [normalize_recruitment(r) for r in rows]
            source_note = "재정경제부_공공기관 채용정보 조회서비스 /list (라이브 전수)"

        subset = recruit_store.filter_records(
            records, region=region, ncs=ncs, hire_type=hire_type, pref=pref
        )
        dist = recruit_store.distribution(subset, dimension, top_n=min(max(top_n, 1), 100))

        caveats = list(cycle)
        caveats.append("지역·직무·고용형태는 복합값을 분해해 중복 집계될 수 있음 (공고 1건이 여러 지역 포함 가능)")
        meta = recruit_store.snapshot_meta()
        if snapshot_used and meta:
            caveats.append(f"스냅샷 기준 시각: {meta.get('built_at')} ({meta.get('count')}건)")
        elif not snapshot_used:
            caveats.append("진행중 채용 스냅샷 미사용 — 라이브 API 결과로 집계했습니다 (스냅샷이 있으면 오프라인 집계 가능)")
        return with_source(
            dist,
            source_note,
            caveats=caveats,
            meta={"is_complete": True, "filter_scope": "snapshot" if snapshot_used else "api_exhausted"},
            coverage=RECRUITMENT_COVERAGE,
        )
    except (AlioAPIError, ValueError) as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_recruitment_profile(recruitment_sn: int) -> dict:
    """채용공시 일련번호(sn/recrutPblntSn)로 상세·전형단계·첨부파일을 조회합니다."""
    try:
        raw = get_recruitment_detail(sn=recruitment_sn)
        detail = raw.get("result")
        if not detail:
            return {
                "data": None,
                "is_error": True,
                "error": f"채용공시 sn={recruitment_sn} 없음",
            }
        return with_source(
            {"recruitment": detail, "summary": normalize_recruitment(detail)},
            "재정경제부_공공기관 채용정보 조회서비스 /detail",
        )
    except AlioAPIError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_institution_news(
    org_code: str = "",
    query: str = "",
    days: int = 30,
    sort: str = "date",
    limit: int = 10,
    max_fetch: int = 300,
) -> dict:
    """공공기관 관련 최근 뉴스를 네이버 뉴스 API로 검색합니다.

    org_code(instCd)를 주면 공식 기관명 + 안전한 별칭(한전·KEPCO 등)으로 OR 검색합니다.
    org_code 없이 query만 주면 별칭을 공식명으로 치환해 검색합니다 (예: '심평원').
    days>0이면 최근 N일 기사만 반환 (네이버 API는 기간 파라미터가 없어 발행일 기준 필터).
    sort: 'date'(최신순, 기본)·'sim'(정확도순).
    max_fetch: 기간 필터 전 수집할 최대 기사 수(100~1000). 보도량 많은 기관의
    '한 달 전체' 커버리지를 위해 페이지네이션으로 모읍니다. 클수록 호출 수 증가.
    """
    try:
        if not org_code and not query:
            return {"data": None, "is_error": True, "error": "org_code 또는 query가 필요합니다"}
        if org_code:
            inst = _resolve_org(org_code, "")
            if not inst:
                return {"data": None, "is_error": True, "error": f"기관코드 {org_code} 없음"}
        else:
            inst = _resolve_org("", query)
        org_name = (inst.get("name") if inst else "") or ""

        terms = naver_client.news_terms(org_name, ALIASES) if org_name else [query.strip()]

        items, fetched, oldest_ts, cutoff = _news_items(
            terms, days=days, sort=sort, max_fetch=max_fetch
        )
        results = items[:limit]
        caveats = [
            "네이버 뉴스 검색 결과(언론 보도)이며 기관의 공식 입장·공시 정보가 아닙니다.",
            "키워드 기반 검색이라 동명·유사 키워드 기사가 섞일 수 있습니다.",
        ]
        # date 정렬은 가장 오래된 기사가 cutoff보다 과거여야 그 날짜까지 전부 수집됐다고 확신 가능
        period_covered = cutoff is None or (oldest_ts is not None and oldest_ts < cutoff)
        if days > 0 and not period_covered:
            caveats.append(
                f"수집한 {fetched}건이 최근 {days}일을 다 덮지 못했습니다(보도량 과다) — "
                f"max_fetch를 늘리거나 검색어를 좁히세요. 현재 결과는 가장 최근 기사 위주입니다."
            )
        elif days > 0:
            caveats.append(f"최근 {days}일 발행 기사로 필터링했습니다.")
        return {
            "data": {
                "institution": org_name or query,
                "search_terms": terms,
                "results": results,
                "count": len(results),
                "matched": len(items),
                "fetched": fetched,
                "period_fully_covered": period_covered,
            },
            "source": {
                "system": "네이버 뉴스 검색 API",
                "api": "GET /v1/search/news.json",
                "url": "https://developers.naver.com/docs/serviceapi/search/news/news.md",
                "retrieved_at": datetime.now().isoformat(timespec="seconds"),
            },
            "caveats": caveats,
            "is_error": False,
        }
    except (NaverAPIError, AlioAPIError) as e:
        return {
            "data": None,
            "is_error": True,
            "error": str(e),
            "hint": "developers.naver.com에서 발급한 NAVER_CLIENT_ID/SECRET을 .env에 설정하세요",
        }


def _news_source(extra: list[str] | None = None) -> dict:
    return {
        "system": "네이버 뉴스 검색 API",
        "api": "GET /v1/search/news.json",
        "url": "https://developers.naver.com/docs/serviceapi/search/news/news.md",
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }


def _item_pref(name: str) -> int:
    """브리핑 지표 항목 대표성 점수 (낮을수록 우선) — 임원·세부분류보다 직원 대표값 선호."""
    score = 0
    if "현원" in name and "전일제" in name:
        score -= 8
    elif "현원" in name and name.endswith("-계"):
        score -= 6
    elif "현원" in name:
        score -= 4
    if "정원" in name and "현원" not in name:
        score += 6
    if "일반정규직" in name:
        score -= 4
    if ("계(" in name) or ("합계" in name) or name.endswith("-계"):
        score -= 3
    if name.endswith("1인당 평균보수액"):
        score -= 3
    if any(k in name for k in ("단시간", "무기계약", "성과급", "임원", "감사", "별도", "피크")):
        score += 3
    if "남성" in name or "여성" in name:
        score += 2
    return score


def _summ_metric(org_code: str, category: str, item_query: str, years_window: int) -> dict | None:
    """브리핑·교차검증용 지표 요약 — 대표 항목 우선, 최신값 + 기간내 증감률."""
    yf = datetime.now().year - max(years_window, 1) + 1
    try:
        r = metrics_store.get_metrics(org_code, category, item_query, year_from=yf)
    except MetricsError:
        return None
    if not r["found"]:
        return None
    # 대표성 높은 항목 우선: 최신값 0/결측은 뒤로, 임원·세부분류보다 직원 대표값
    def _rank(kv):
        name, ser = kv
        ly, lv = _latest_point(ser)
        return (lv in (None, 0), _item_pref(name), len(name))

    ordered = sorted(r["series"].items(), key=_rank)
    items = []
    for item, ser in ordered[:3]:
        ly, lv = _latest_point(ser)
        nums = sorted(k for k in ser if isinstance(ser[k], (int, float)))
        change = None
        if len(nums) >= 2 and ser[nums[0]]:
            change = round((ser[nums[-1]] - ser[nums[0]]) / abs(ser[nums[0]]) * 100, 1)
        items.append(
            {"item": item, "latest_year": ly, "latest": lv, "change_pct_in_window": change}
        )
    return {"category": category, "label": r["label"], "unit": r["unit"], "items": items}


@mcp.tool()
def get_institution_briefing(
    org_code: str = "",
    query: str = "",
    news_days: int = 14,
    metric_years: int = 3,
    news_count: int = 5,
) -> dict:
    """기관 360° 원샷 브리핑 — 프로필·핵심지표 추세·최근 뉴스·진행중 채용을 한 번에 종합합니다.

    org_code 또는 query(기관명·별칭, 예 '한전')로 기관을 지정합니다.
    프로필(설립목적·기관장·부처) + 정원/보수/부채비율 추세 + 최근 N일 뉴스 헤드라인 +
    진행중 채용 건수를 묶어 반환합니다. "○○기관 한눈에 브리핑해줘"에 사용하세요.
    """
    inst = _resolve_org(org_code, query)
    if not inst:
        return {
            "data": None,
            "is_error": True,
            "error": f"기관을 찾을 수 없음 (org_code='{org_code}', query='{query}')",
            "hint": "search_institutions로 정확한 org_code를 먼저 확인하세요",
        }
    code = inst.get("org_code")
    name = inst.get("name") or ""
    detail = inst.get("detail") or {}

    caveats: list[str] = []
    # 1) 핵심 지표
    metrics_block = []
    try:
        staff = metrics_store.staff_summary(code, year_from=datetime.now().year - max(metric_years, 1) + 1)
    except MetricsError as e:
        staff = {"found": False}
        caveats.append(f"인력 지표 조회 실패: {e}")
    if staff.get("found"):
        metrics_block.append({"category": "staff", "label": "임직원 수", "summary": staff})
    for cat, iq in (("salary", "평균보수"), ("finance", "부채비율")):
        snap = _summ_metric(code, cat, iq, metric_years)
        if snap:
            metrics_block.append(snap)
        elif cat == "finance":
            caveats.append("재무(부채비율) 항목이 이 기관의 조회 범위에 없거나 해당 연도에 미공시일 수 있습니다.")

    # 2) 진행중 채용
    hiring = {"snapshot_available": False, "ongoing_count": 0, "nearest_deadline_days": None}
    snap_records = recruit_store.snapshot_records()
    if snap_records is not None:
        mine = [r for r in snap_records if r.get("org_code") == code]
        dds = [d for d in (recruit_store.parse_days_remaining(r) for r in mine) if d is not None and d >= 0]
        hiring = {
            "snapshot_available": True,
            "ongoing_count": len(mine),
            "nearest_deadline_days": min(dds) if dds else None,
        }

    # 3) 최근 뉴스
    news_block: list[dict] = []
    news_error = None
    try:
        terms = naver_client.news_terms(name, ALIASES)
        items, _f, _o, _c = _news_items(terms, days=news_days, max_fetch=200)
        news_block = items[:news_count]
    except NaverAPIError as e:
        news_error = str(e)
        caveats.append(f"뉴스 조회 실패: {e}")

    profile = {
        "org_code": code,
        "name": name,
        "org_type": inst.get("org_type"),
        **_subsidiary_fields(inst),
        "ministry": inst.get("ministry"),
        "location": inst.get("location"),
        "head": detail.get("head"),
        "purpose": detail.get("purpose"),
    }
    sub_caveat = _subsidiary_profile_caveat(inst)
    if sub_caveat:
        caveats.append(sub_caveat)
        caveats.append("부설기관 지표는 해당 공시 단위 기준입니다. 모기관과 합산하면 이중 집계될 수 있습니다.")
    caveats.append("인력은 key_metrics.staff.summary의 quota(정원) vs headcount(현원)를 구분하세요.")
    caveats.append("뉴스는 언론 보도이며 기관 공식 입장이 아닙니다. 지표는 공시 수치 기준입니다.")
    return {
        "data": {
            "profile": profile,
            "key_metrics": metrics_block,
            "hiring": hiring,
            "recent_news": news_block,
            "news_error": news_error,
        },
        "source": {
            "system": "open-ALIO-mcp 종합 브리핑",
            "components": [
                "재정경제부 공공기관 정보 + ALIO 일반현황",
                "ALIO 항목별 공시 지표",
                "공공기관 채용정보 스냅샷",
                "네이버 뉴스 검색 API",
            ],
            "retrieved_at": datetime.now().isoformat(timespec="seconds"),
        },
        "caveats": caveats,
        "is_error": False,
    }


@mcp.tool()
def cross_check_news_with_metrics(
    topic: str,
    org_code: str = "",
    query: str = "",
    news_days: int = 30,
    metric_years: int = 5,
    news_limit: int = 5,
) -> dict:
    """뉴스 주장을 공시 지표로 교차검증합니다 — '뉴스에서 빚 많다는데 실제 부채는?'.

    topic을 지표 카테고리로 매핑(부채/재무→finance, 정원/인력→staff, 보수→salary,
    채용→recruitment, 복지→welfare, 예산→budget 등)해 해당 시계열과,
    topic 키워드로 필터한 관련 뉴스를 함께 반환합니다.
    org_code 또는 query로 기관을 지정하세요.
    """
    inst = _resolve_org(org_code, query)
    if not inst:
        return {
            "data": None,
            "is_error": True,
            "error": f"기관을 찾을 수 없음 (org_code='{org_code}', query='{query}')",
            "hint": "search_institutions로 org_code 확인",
        }
    resolved = news_insights.resolve_topic(topic)
    if not resolved:
        return {
            "data": None,
            "is_error": True,
            "error": f"'{topic}'을 지표로 매핑할 수 없습니다",
            "hint": f"지원 토픽: {sorted(news_insights.TOPIC_TO_METRIC)}",
        }
    topic_key, entry = resolved
    code = inst.get("org_code")
    name = inst.get("name") or ""
    category = entry["category"]

    try:
        yf = datetime.now().year - max(metric_years, 1) + 1
        metric = metrics_store.get_metrics(code, category, entry["item_query"], year_from=yf)
    except MetricsError as e:
        return {"data": None, "is_error": True, "error": str(e)}

    caveats: list[str] = []
    note = disclosure_store.schedule_phrase(category)
    if note:
        caveats.append(note)
    if not metric["found"]:
        caveats.append(
            f"기관 {code}의 '{category}' 지표 없음 — 공시 주기·기관별 미공시·항목명 차이 가능. "
            "뉴스만 참고하거나 다른 토픽을 시도하세요."
        )

    related_news: list[dict] = []
    news_error = None
    try:
        terms = naver_client.news_terms(name, ALIASES)
        items, _f, _o, _c = _news_items(terms, days=news_days, max_fetch=300)
        related_news = news_insights.filter_by_keywords(items, entry["keywords"])[:news_limit]
    except NaverAPIError as e:
        news_error = str(e)
        caveats.append(f"뉴스 조회 실패: {e}")

    caveats.append("뉴스(정성)와 공시 지표(정량)의 시점·기준이 다를 수 있습니다. 인과로 단정하지 마세요.")
    return {
        "data": {
            "institution": {"org_code": code, "name": name},
            "topic": topic,
            "mapped_to": {"category": category, "item_query": entry["item_query"], "keywords": entry["keywords"]},
            "metric": {
                "label": metric["label"],
                "unit": metric["unit"],
                "years": metric["years"],
                "series": metric["series"],
                "found": metric["found"],
            },
            "related_news": related_news,
            "news_matched": len(related_news),
            "news_error": news_error,
        },
        "source": {
            "system": "open-ALIO-mcp 뉴스·지표 교차검증",
            "components": ["ALIO 항목별 공시 지표", "네이버 뉴스 검색 API", "ALIO 공시 카탈로그(주기 주석)"],
            "retrieved_at": datetime.now().isoformat(timespec="seconds"),
        },
        "caveats": caveats,
        "is_error": False,
    }


@mcp.tool()
def digest_institution_news(
    org_code: str = "",
    query: str = "",
    days: int = 30,
    max_fetch: int = 400,
    per_theme: int = 3,
) -> dict:
    """기관 뉴스를 테마별로 자동 분류·집계합니다 — 보도량 많은 기관의 이슈를 구조화.

    평면적인 기사 목록 대신 테마(재무·실적/채용·인사/안전·재해/감사·비위/사업·협약/
    정책·국회/사회공헌·ESG/기타)별 건수와 대표 헤드라인, 날짜별 타임라인을 반환합니다.
    "캠코 한 달 이슈를 정리해줘"처럼 분포 파악에 사용하세요.
    """
    try:
        if not org_code and not query:
            return {"data": None, "is_error": True, "error": "org_code 또는 query가 필요합니다"}
        inst = _resolve_org(org_code, query)
        org_name = (inst.get("name") if inst else "") or ""
        terms = naver_client.news_terms(org_name, ALIASES) if org_name else [query.strip()]

        items, fetched, oldest_ts, cutoff = _news_items(
            terms, days=days, sort="date", max_fetch=max_fetch
        )
        themes = news_insights.bucket_by_theme(items, per_theme=per_theme)
        timeline = news_insights.timeline_by_date(items)

        caveats = [
            "테마 분류는 키워드 기반 근사치입니다 — 정밀 해석은 본문 확인이 필요합니다.",
            "네이버 뉴스 검색 결과(언론 보도)이며 기관 공식 입장이 아닙니다.",
        ]
        period_covered = cutoff is None or (oldest_ts is not None and oldest_ts < cutoff)
        if days > 0 and not period_covered:
            caveats.append(
                f"수집 {fetched}건이 최근 {days}일을 다 덮지 못했습니다(보도량 과다) — "
                "max_fetch를 늘리거나 days를 줄이세요. 현재 집계는 최근 기사 위주입니다."
            )
        return {
            "data": {
                "institution": org_name or query,
                "search_terms": terms,
                "total_articles": len(items),
                "fetched": fetched,
                "period_fully_covered": period_covered,
                "themes": themes,
                "timeline": timeline,
            },
            "source": _news_source(),
            "caveats": caveats,
            "is_error": False,
        }
    except NaverAPIError as e:
        return {
            "data": None,
            "is_error": True,
            "error": str(e),
            "hint": "developers.naver.com에서 발급한 NAVER_CLIENT_ID/SECRET을 .env에 설정하세요",
        }


# ── 법령·행정규칙 (국가법령정보센터 Open API) ────────────────────────────────

def _law_source(api: str) -> dict:
    return {
        "system": "국가법령정보센터 (법제처)",
        "api": api,
        "url": "https://www.law.go.kr",
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }


def _law_key_hint() -> str:
    return "open.law.go.kr에서 회원가입 후 'Open API 사용 신청'으로 OC(이메일 ID)를 발급받아 .env의 LAW_API_OC에 설정하세요"


@mcp.tool()
def search_laws(query: str, page: int = 1, display: int = 20, scope: int = 1) -> dict:
    """법령(법률·대통령령·부령 등)을 키워드로 검색합니다 — 국가법령정보센터.

    공공기관 관련 질의는 리소스 alio://related-laws의 화이트리스트(공운법 등 핵심 법령
    공식 명칭)를 먼저 참조해 정확한 법령명으로 검색하세요. 복합 키워드는 0건이 나올 수
    있으니 핵심 단어 하나로 검색 후 결과에서 고르세요. scope: 1=법령명 검색, 2=본문 검색.
    결과의 'mst'(법령일련번호)를 get_law_text에 넘기면 조문을 조회합니다.
    """
    try:
        result = law_client.search_laws(query, page=page, display=display, scope=scope)
        caveats = ["현행 법령 기준 검색 결과입니다 — 시행일자(effective_date)를 확인하세요."]
        if result["total"] == 0:
            caveats.append("0건 — 키워드를 줄이거나(한 단어), scope=2(본문 검색)를 시도하세요.")
        return {"data": result, "source": _law_source("lawSearch(law)"), "caveats": caveats, "is_error": False}
    except LawAPIError as e:
        return {"data": None, "is_error": True, "error": str(e), "hint": _law_key_hint()}


@mcp.tool()
def get_law_text(mst: str, article: str = "", full_text: bool = False) -> dict:
    """법령의 조문을 조회합니다 — search_laws 결과의 'mst'(법령일련번호) 필요.

    article을 지정하면(예: '4', '4의2') 해당 조문 전문만 반환합니다.
    article 없이 호출하면 기본정보+조문 목차(번호·제목)만 반환하므로, 먼저 목차에서
    필요한 조문을 찾아 article로 재조회하세요. 전 조문 전문이 꼭 필요할 때만
    full_text=True를 쓰세요(대형 법령은 매우 깁니다).
    """
    try:
        result = law_client.get_law(mst, article=article or None, full_text=full_text)
        caveats = ["현행 조문 기준입니다 — 부칙 경과규정·시행 유예가 있을 수 있습니다."]
        if "toc" in result:
            caveats.append("목차 모드 — 본문이 필요하면 article 파라미터로 조문을 지정해 재조회하세요.")
        return {"data": result, "source": _law_source("lawService(law)"), "caveats": caveats, "is_error": False}
    except LawAPIError as e:
        return {"data": None, "is_error": True, "error": str(e), "hint": _law_key_hint()}


@mcp.tool()
def search_admin_rules(query: str, page: int = 1, display: int = 20, scope: int = 1) -> dict:
    """행정규칙(훈령·예규·고시·지침)을 키워드로 검색합니다 — 국가법령정보센터.

    「공기업·준정부기관의 경영에 관한 지침」 등 기재부 공공기관 지침류는 행정규칙으로
    등재돼 있습니다(리소스 alio://related-laws의 admin_rules 참조). 여기서 0건이면
    연도별 시달 지침(예산운용지침 등)일 수 있으니 search_guidelines(로컬 지침)를
    확인하세요. 결과의 'id'를 get_admin_rule_text에 넘기면 본문을 조회합니다.
    """
    try:
        result = law_client.search_admin_rules(query, page=page, display=display, scope=scope)
        caveats = ["행정규칙은 제·개정이 잦습니다 — status(현행연혁구분)와 발령일자를 확인하세요."]
        if result["total"] == 0:
            caveats.append("0건 — 연도별 시달 지침은 law.go.kr에 없을 수 있습니다. search_guidelines(로컬 지침 파일)를 시도하세요.")
        return {"data": result, "source": _law_source("lawSearch(admrul)"), "caveats": caveats, "is_error": False}
    except LawAPIError as e:
        return {"data": None, "is_error": True, "error": str(e), "hint": _law_key_hint()}


@mcp.tool()
def get_admin_rule_text(rule_id: str) -> dict:
    """행정규칙(훈령·예규·고시·지침)의 본문을 조회합니다 — search_admin_rules 결과의 'id' 필요."""
    try:
        result = law_client.get_admin_rule(rule_id)
        caveats: list[str] = []
        if result.get("has_attachment_only"):
            caveats.append("이 행정규칙은 본문이 별첨 파일(HWP) 형태라 텍스트가 비어 있습니다 — detail_url에서 원문을 확인하세요.")
        return {"data": result, "source": _law_source("lawService(admrul)"), "caveats": caveats, "is_error": False}
    except LawAPIError as e:
        return {"data": None, "is_error": True, "error": str(e), "hint": _law_key_hint()}


# ── 로컬 지침 (law.go.kr에 없는 연도별 시달 지침 — 파일 파싱 적재분) ─────────


def _guideline_source() -> dict:
    return {
        "system": "로컬 지침 저장소 (시달 지침 파일 파싱)",
        "api": "data/guidelines/*.json",
        "url": None,
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }


_GUIDELINE_CAVEAT = "원문 파일(HWPX/PDF)에서 추출한 텍스트입니다 — 표·서식은 손실될 수 있으니 인용 시 원문 대조를 권장합니다."

_HANDBOOK_CAVEAT = (
    "기재부 경영평가편람 PDF에서 추출한 내용입니다 — 표·배점은 원문 대조를 권장하며, "
    "평가 판단·등급 예측의 근거가 아닙니다(보조 참고용)."
)


def _handbook_source() -> dict:
    return {
        "system": "경영평가편람 저장소 (PDF 파싱)",
        "api": "data/handbook/*.json",
        "url": None,
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }


@mcp.tool()
def search_evaluation_handbook(
    query: str,
    year: int = 0,
    part: str = "",
    limit: int = 10,
) -> dict:
    """경영평가편람 본문을 키워드로 검색합니다.

    예: '중대재해', '총인건비', '안전관리등급', '혁신가점'.
    part: '경영실적'·'기관장_경영계약'·'상임감사'·'기관별_별첨' 등으로 범위 축소.
    year: 2025·2026 등 — 미지정 시 적재된 모든 연도 검색.
    """
    try:
        result = handbook_store.search(query, year=year or None, part=part, limit=limit)
        caveats = [_HANDBOOK_CAVEAT]
        if result["total"] == 0:
            caveats.append("0건 — alio://handbook-index로 적재 여부·연도를 확인하세요.")
        return {"data": result, "source": _handbook_source(), "caveats": caveats, "is_error": False}
    except HandbookError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def list_evaluation_org_types(year: int = 0) -> dict:
    """편람에 정의된 기관 유형(공기업 SOC·에너지, 준정부 기금관리형 등) 목록."""
    try:
        result = handbook_store.list_org_subtypes(year=year or None)
        return {
            "data": result,
            "source": _handbook_source(),
            "caveats": [_HANDBOOK_CAVEAT],
            "is_error": False,
        }
    except HandbookError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def list_evaluation_indicators(
    org_class: str = "",
    org_subtype: str = "",
    year: int = 0,
) -> dict:
    """유형별 평가지표·배점(계·비계량·계량) 표를 조회합니다.

    org_class: '공기업'·'준정부기관' 등. org_subtype: 'SOC'·'에너지'·'기금관리형' 등.
    list_evaluation_org_types로 유형 목록을 먼저 확인할 수 있습니다.
    """
    try:
        result = handbook_store.list_indicators(
            year=year or None, org_class=org_class, org_subtype=org_subtype
        )
        return {
            "data": result,
            "source": _handbook_source(),
            "caveats": [_HANDBOOK_CAVEAT],
            "is_error": False,
        }
    except HandbookError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_evaluation_indicator_detail(query: str, year: int = 0) -> dict:
    """평가지표명으로 세부평가내용·배점·지표정의를 조회합니다.

    예: '안전 및 재난관리', '총인건비관리', '윤리경영'.
    """
    try:
        result = handbook_store.get_indicator_detail(query, year=year or None)
        caveats = [_HANDBOOK_CAVEAT]
        if not result.get("details") and result.get("search_fallback"):
            caveats.append("구조화된 세부블록 없음 — 본문 검색 fallback 결과를 포함합니다.")
        return {"data": result, "source": _handbook_source(), "caveats": caveats, "is_error": False}
    except HandbookError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def compare_evaluation_handbook_years(
    query: str,
    year_a: int,
    year_b: int,
    limit: int = 5,
) -> dict:
    """두 연도 편람(예: 2025 수정 vs 2026)에서 동일 키워드 검색 — 변경 추적 보조."""
    try:
        result = handbook_store.compare_years(query, year_a, year_b, limit=limit)
        return {
            "data": result,
            "source": _handbook_source(),
            "caveats": [
                _HANDBOOK_CAVEAT,
                "자동 diff가 아닌 검색 결과 비교입니다 — 변경 여부는 snippet을 대조하세요.",
            ],
            "is_error": False,
        }
    except HandbookError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def search_guidelines(query: str, year: int = 0, issuer: str = "", limit: int = 10) -> dict:
    """로컬에 적재된 지침(예산운용지침 등 law.go.kr 미등재 시달 지침)을 조문 단위로 검색합니다.

    공백으로 구분한 여러 키워드는 AND 조건입니다 (예: '총인건비 인상률').
    연도별 지침은 year로 구분하세요. 적재 목록은 리소스 alio://guideline-index 참조.
    상시 지침(경영지침·혁신지침 등)은 search_admin_rules(law.go.kr)가 우선입니다.
    """
    try:
        result = guideline_store.search(query, year=year or None, issuer=issuer or None, limit=limit)
        caveats = [_GUIDELINE_CAVEAT]
        if result["total"] == 0:
            caveats.append("0건 — 키워드를 줄이거나, 해당 지침이 적재됐는지 alio://guideline-index를 확인하세요.")
        return {"data": result, "source": _guideline_source(), "caveats": caveats, "is_error": False}
    except GuidelineError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_guideline_text(doc_id: str, article: str = "") -> dict:
    """적재된 지침의 조문을 조회합니다 — search_guidelines 결과의 'doc_id' 필요.

    article 지정 시(예: '5', '5의2') 해당 조문 전문, 미지정 시 목차(조문 번호·제목)를 반환합니다.
    """
    try:
        result = guideline_store.get_text(doc_id, article=article or None)
        caveats = [_GUIDELINE_CAVEAT]
        if "toc" in result:
            caveats.append("목차 모드 — 본문이 필요하면 article 파라미터로 조문을 지정해 재조회하세요.")
        return {"data": result, "source": _guideline_source(), "caveats": caveats, "is_error": False}
    except GuidelineError as e:
        return {"data": None, "is_error": True, "error": str(e)}


@mcp.tool()
def get_server_status() -> dict:
    """서버 상태 점검 — API 키·로컬 데이터 적재 현황. 데모 전 점검용."""
    status: dict = {
        "server": "open-ALIO-mcp",
        "api_key_set": bool(os.environ.get("DATA_GO_KR_SERVICE_KEY")),
        "naver_api_key_set": naver_client.has_credentials(),
        "law_api_key_set": law_client.has_credentials(),
        "aliases_count": len(ALIASES),
    }
    try:
        status.update(_institution_count_summary(_get_institutions(), prefer_meta=True))
        status["institution_count_basis"] = (
            "institutions_count excludes subsidiary disclosure units; "
            "disclosure_units_count includes them."
        )
        status["institutions_source"] = (
            "local(institutions.json)" if data_provider.exists("institutions.json") else "api"
        )
    except AlioAPIError as e:
        status["institutions_count"] = None
        status["subsidiary_count"] = None
        status["disclosure_units_count"] = None
        status["institutions_error"] = str(e)
    try:
        idx = metrics_store.get_index()
        status["metrics_built_at"] = idx.get("built_at")
        status["metrics_categories"] = len(idx.get("categories", []))
    except MetricsError as e:
        status["metrics_error"] = str(e)
    status["pdf_parsed_orgs"] = (
        len(data_provider.list_paths("parsed/by-org/"))
    )
    try:
        status["disclosure_items"] = disclosure_store.search(limit=100)["total"]
    except DisclosureError as e:
        status["disclosure_error"] = str(e)
    rec_meta = recruit_store.snapshot_meta()
    status["recruitment_snapshot"] = (
        {"built_at": rec_meta.get("built_at"), "count": rec_meta.get("count")}
        if rec_meta
        else None
    )
    try:
        gl = guideline_store.get_index()
        status["guidelines"] = {"built_at": gl.get("built_at"), "docs": len(gl.get("docs", []))}
    except GuidelineError:
        status["guidelines"] = None  # 미적재는 정상 상태 (선택 기능)
    try:
        hb = handbook_store.get_index()
        status["evaluation_handbook"] = {
            "built_at": hb.get("built_at"),
            "docs": len(hb.get("docs", [])),
        }
    except HandbookError:
        status["evaluation_handbook"] = None
    return with_source(status, "open-ALIO-mcp 서버 자체 점검")


# ── MCP Resources — 모델이 참조하는 읽기 전용 데이터 ─────────────────────────


@mcp.resource("alio://tool-guide")
def tool_guide_resource() -> str:
    """Use-case → MCP tool 매핑 (에이전트 라우팅용)."""
    return json.dumps(TOOL_GUIDE, ensure_ascii=False, indent=2)


@mcp.resource("alio://disclosure-catalog")
def disclosure_catalog_resource() -> str:
    """ALIO 50개 경영공시 항목 카탈로그 (정기/수시·주기·metric 매핑) JSON."""
    try:
        return json.dumps(disclosure_store._load(), ensure_ascii=False, indent=2)
    except DisclosureError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.resource("alio://metric-categories")
def metric_categories_resource() -> str:
    """본 MCP가 보유한 지표 카테고리 인덱스 (조회 전 구조 파악용)."""
    try:
        return json.dumps(metrics_store.get_index(), ensure_ascii=False, indent=2)
    except MetricsError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.resource("alio://related-laws")
def related_laws_resource() -> str:
    """공공기관 핵심 법령·행정규칙 화이트리스트 — search_laws/search_admin_rules 검색어 가이드."""
    try:
        return data_provider.read_text("reference/related_laws.json")
    except (FileNotFoundError, OSError) as e:
        return json.dumps({"error": f"related_laws.json 로드 실패: {e}"}, ensure_ascii=False)


@mcp.resource("alio://handbook-index")
def handbook_index_resource() -> str:
    """경영평가편람 적재 목록 — search_evaluation_handbook 사용 전 확인용."""
    try:
        return json.dumps(handbook_store.get_index(), ensure_ascii=False, indent=2)
    except HandbookError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.resource("alio://guideline-index")
def guideline_index_resource() -> str:
    """로컬 적재 지침 목록 — search_guidelines 사용 전 보유 여부 확인용."""
    try:
        return json.dumps(guideline_store.get_index(), ensure_ascii=False, indent=2)
    except GuidelineError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── MCP Prompts — 출력 양식 템플릿 (tool이 아닌 답변 레시피) ──────────────────


@mcp.prompt()
def summarize_disclosure(institution_name: str) -> str:
    """기관 1곳의 ALIO 공시 요약 양식."""
    return f"""'{institution_name}'의 ALIO 공시 정보를 아래 절차와 양식으로 요약해 주세요.

[절차]
1. search_institutions(query='{institution_name}')로 org_code 확보
2. get_institution_profile로 설립목적·주무부처·기관유형 확인
3. get_institution_metrics로 staff(정원·현원), salary(평균보수), budget(수입·지출) 최근 3~5년 조회
4. finance(자산·부채)도 조회 — 결산 재무는 전 기관 제공, 반기 항목은 공기업 계열만

[출력 양식]
## {institution_name} 공시 요약
### 1. 기관 개요 (유형·주무부처·설립목적 1줄)
### 2. 인력 (정원·현원 추이 표, 단위: 명)
### 3. 보수·예산 (평균보수·수입지출 핵심 수치, 단위 명시: 천원/백만원)
### 4. 재무 (해당 시 — 자산·부채·부채비율)
### 5. 유의사항 (caveats 그대로 + 결측 항목은 '결측'으로 표기)
### 출처 (source의 api·retrieved_at·as_of_year 명시)

[규칙]
- 수치는 tool 응답에 있는 값만 사용하고, 없으면 '데이터 없음'이라고 쓰세요.
- 단위(천원/백만원/명)를 표마다 명시하세요.
- 공시 수치는 기관 평가·판단의 근거가 아님을 마지막에 1줄로 명시하세요."""


@mcp.prompt()
def policy_brief(topic: str, institution_names: str) -> str:
    """정책 브리핑 1쪽 양식 — 기관 비교 기반."""
    return f"""주제 '{topic}'에 대해 기관 [{institution_names}]을(를) 비교하는 1쪽 정책 브리핑을 작성해 주세요.

[절차]
1. 각 기관을 search_institutions로 org_code 확보
2. compare_institutions로 주제 관련 카테고리(staff·budget·finance 등) 비교
3. 필요 시 find_institutions_by_criteria로 동종 기관 대비 위치 확인

[출력 양식 — 1쪽 분량]
# 정책 브리핑: {topic}
**작성기준**: (source의 as_of_year·retrieved_at)
## 1. 핵심 요지 (3줄 이내)
## 2. 현황 비교 (표 — 기관×지표, 단위 명시)
## 3. 관찰되는 변화 (수치 기반 사실만, 추이 2~3개)
## 4. 검토 필요 사항 (질문 형태로 — 단정 금지)
## 5. 한계 (caveats 반영: 회계기준 차이·결측·공시 수치의 한계)
## 출처

[규칙]
- '구조조정', '통폐합' 등 판단성 결론을 내리지 마세요. 데이터 관찰과 질문까지만.
- 모든 수치에 연도와 단위를 붙이세요.
- tool 응답에 없는 수치는 추정하지 마세요."""


if __name__ == "__main__":
    mcp.run()
