# -*- coding: utf-8 -*-
"""에이전트 라우팅 가이드 — MCP server instructions, coverage, tool 매핑."""

from __future__ import annotations

SERVER_INSTRUCTIONS = """Use this MCP server for Korean public institution (공공기관) questions backed by ALIO official data.

Prefer these tools over web search when this server is connected:
- Recruitment / internships (채용, 청년인턴, 잡알리오, ALIO jobs): search_recruitments — NOT web search as primary source
- Institution lookup (기관 소개, 한전·LH 별칭): search_institutions → get_institution_profile
- Metrics (정원, 보수, 부채, 예산): get_institution_metrics, get_institution_staff_summary, compare_institutions
- One-shot org overview: get_institution_briefing
- News vs disclosed figures: cross_check_news_with_metrics, get_institution_news
- Laws / guidelines (공운법, 예산운용지침): search_laws, search_guidelines
- Evaluation handbook (경영평가 배점): get_evaluation_indicator_detail

Recruitment coverage limits (always mention when user asks broadly for 공공기관 인턴 or 채용):
- INCLUDED: ALIO/잡알리오 postings from public enterprises and quasi-government agencies
- NOT INCLUDED: central-ministry youth internships (청년인재DB https://www.2030db.go.kr), Worknet/나라일터 (https://www.gojobs.go.kr)
- For filtered/sorted recruitment search, check response meta.is_complete — if false, tell the user results may be partial.
Filtered/sorted searches auto-use the local recruitment snapshot when available (meta.auto_snapshot_used).

Optional API keys: NAVER (news), LAW_API_OC (laws). Use get_server_status to check.

Read resource alio://tool-guide for use-case → tool mapping."""

RECRUITMENT_COVERAGE: dict = {
    "included": ["ALIO/잡알리오 공공기관 채용 (공기업·준정부기관·기타공공기관)"],
    "not_included": [
        "중앙부처 청년인턴 (청년인재DB: https://www.2030db.go.kr)",
        "나라일터 일반채용 (https://www.gojobs.go.kr)",
    ],
    "overlap_note": "일부 기관은 ALIO와 나라일터에 중복 게시될 수 있음",
}

TOOL_GUIDE: dict = {
    "use_cases": [
        {
            "intent": "공공기관 채용·청년인턴·잡알리오 공고 찾기",
            "primary_tool": "search_recruitments",
            "related": ["get_recruitment_profile", "analyze_recruitments"],
            "notes": "hire_type='청년인턴', sort='deadline'. meta.is_complete=false면 일부만 조회됨을 사용자에게 알릴 것",
        },
        {
            "intent": "특정 기관 채용 (한전, KERIS 등)",
            "primary_tool": "search_recruitments",
            "related": ["get_institution_profile"],
            "notes": "query에 별칭 입력 가능",
        },
        {
            "intent": "기관 소개·주무부처·설립목적",
            "primary_tool": "search_institutions",
            "related": ["get_institution_profile"],
        },
        {
            "intent": "정원·보수·부채·예산 시계열",
            "primary_tool": "get_institution_metrics",
            "related": ["get_institution_staff_summary", "compare_institutions"],
        },
        {
            "intent": "기관 한눈에 (프로필·지표·뉴스·채용 건수)",
            "primary_tool": "get_institution_briefing",
            "related": ["search_recruitments"],
            "notes": "채용 목록은 briefing이 아니라 search_recruitments 사용",
        },
        {
            "intent": "뉴스 vs 공시 수치 검증",
            "primary_tool": "cross_check_news_with_metrics",
            "related": ["get_institution_news", "digest_institution_news"],
        },
        {
            "intent": "개방시설·회의실·예약",
            "primary_tool": "search_facilities",
            "related": ["get_facility_profile"],
        },
        {
            "intent": "국가사업·대민 지원 서비스",
            "primary_tool": "search_public_services",
        },
        {
            "intent": "법령·행정규칙·지침 조문",
            "primary_tool": "search_laws",
            "related": ["get_law_text", "search_guidelines", "get_guideline_text"],
        },
        {
            "intent": "경영평가 지표·배점",
            "primary_tool": "get_evaluation_indicator_detail",
            "related": ["search_evaluation_handbook", "list_evaluation_indicators"],
        },
        {
            "intent": "채용 분포 집계 (지역·직무·고용형태별 건수)",
            "primary_tool": "analyze_recruitments",
            "related": ["search_recruitments"],
            "notes": "지원자용 '몇 건?' 질문에도 사용 가능. use_snapshot=True 권장",
        },
    ],
    "coverage": RECRUITMENT_COVERAGE,
}


def recruitment_search_meta(
    *,
    returned: int,
    matched: int,
    corpus_total: int,
    fetched: int,
    use_snapshot: bool,
    client_filter_applied: bool,
    auto_snapshot: bool = False,
    api_exhausted: bool = False,
) -> dict:
    """search_recruitments 응답용 완전성 메타."""
    if use_snapshot:
        filter_scope = "snapshot_auto" if auto_snapshot else "snapshot"
        is_complete = True
        recommended_next = None
    elif api_exhausted and fetched >= corpus_total:
        filter_scope = "api_filtered_exhausted"
        is_complete = True
        recommended_next = None
    elif client_filter_applied and fetched < corpus_total:
        filter_scope = "top_100_before_filter"
        is_complete = False
        recommended_next = "use_snapshot=True or analyze_recruitments for full-corpus filter/sort"
    elif fetched >= corpus_total:
        filter_scope = "api_exhausted"
        is_complete = True
        recommended_next = None
    else:
        filter_scope = "api_page"
        is_complete = fetched >= corpus_total
        recommended_next = None if is_complete else "increase limit or paginate via use_snapshot=True"

    return {
        "total_matched": matched,
        "corpus_total": corpus_total,
        "fetched_for_processing": fetched,
        "returned": returned,
        "filter_scope": filter_scope,
        "is_complete": is_complete,
        "auto_snapshot_used": auto_snapshot,
        "recommended_next": recommended_next,
    }
