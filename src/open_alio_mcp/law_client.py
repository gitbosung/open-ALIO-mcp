# -*- coding: utf-8 -*-
"""국가법령정보센터 Open API 클라이언트 — 법령·행정규칙 검색/본문 조회.

키 발급: https://open.law.go.kr → 회원가입 → Open API 사용 신청 → OC(이메일 ID) 발급.
.env에 LAW_API_OC 설정 (예: 이메일이 hong@gmail.com이면 LAW_API_OC=hong).

엔드포인트 (모두 GET, type=XML):
- 목록 검색: http://www.law.go.kr/DRF/lawSearch.do  (target=law|admrul)
- 본문 조회: http://www.law.go.kr/DRF/lawService.do (law는 MST, admrul은 ID)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
import xmltodict
from dotenv import load_dotenv

from .security_utils import build_query_params, mask_sensitive_text, request_get_with_security

load_dotenv()

log = logging.getLogger("law")

LAW_API_OC = os.environ.get("LAW_API_OC", "")
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"

_cache: dict[str, tuple[float, Any]] = {}
TTL = 3600  # 법령은 변동이 적음 — 1시간 캐시


class LawAPIError(Exception):
    pass


def has_credentials() -> bool:
    return bool(LAW_API_OC)


def _require_key() -> None:
    if not has_credentials():
        raise LawAPIError(
            "LAW_API_OC가 .env에 없습니다. open.law.go.kr에서 회원가입 후 "
            "'Open API 사용 신청'으로 OC(이메일 ID)를 발급받으세요."
        )


def _request(url: str, params: dict) -> dict:
    """GET 호출 → XML 파싱. OC 무효 시 law.go.kr이 HTML을 반환하므로 감지해 안내."""
    _require_key()
    public_params = dict(params)
    params, blocked = build_query_params(
        {},
        public_params,
        {"OC": LAW_API_OC, "type": "XML"},
        reserved={"OC", "type"},
    )
    if blocked:
        log.warning("예약 법령 API 파라미터 무시: %s", ", ".join(blocked))
    cache_key = url + str(sorted(public_params.items()))
    if cache_key in _cache and time.time() - _cache[cache_key][0] < TTL:
        return _cache[cache_key][1]

    try:
        r = request_get_with_security(
            url,
            params=params,
            timeout=20,
            retries=1,
            logger=log,
            label="Law API",
        )
    except requests.RequestException as e:
        raise LawAPIError(f"법령정보 API 연결 실패: {mask_sensitive_text(e)}") from e

    if r.status_code != 200:
        raise LawAPIError(f"법령정보 API 오류 (HTTP {r.status_code}) {mask_sensitive_text(r.text[:200])}")

    text = r.text.strip()
    if not text.startswith("<?xml") and "<" not in text[:10]:
        raise LawAPIError(f"법령정보 API 비정상 응답: {mask_sensitive_text(text[:200])}")
    try:
        parsed = xmltodict.parse(text)
    except Exception as e:  # noqa: BLE001 — xmltodict는 다양한 예외를 던짐
        # OC 미승인·오타 시 XML이 아닌 안내 HTML이 내려옴
        raise LawAPIError(
            "법령정보 API 응답 파싱 실패 — LAW_API_OC가 유효한지(발급 승인 여부) 확인하세요. "
            f"응답 앞부분: {mask_sensitive_text(text[:150])}"
        ) from e

    _cache[cache_key] = (time.time(), parsed)
    return parsed


def _as_list(v) -> list:
    """xmltodict는 단건이면 dict, 다건이면 list — 항상 list로 정규화."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


# ── 목록 검색 ────────────────────────────────────────────────────────────────


def search_laws(query: str, *, page: int = 1, display: int = 20, scope: int = 1) -> dict:
    """법령(법률·대통령령·총리령·부령) 검색. scope: 1=법령명, 2=본문.

    복합 키워드는 0건이 나올 수 있음 — 핵심 단어 하나로 검색 권장.
    """
    raw = _request(SEARCH_URL, {
        "target": "law", "query": query,
        "page": max(page, 1), "display": min(max(display, 1), 100), "search": scope,
    })
    body = raw.get("LawSearch", {}) or {}
    items = []
    for it in _as_list(body.get("law")):
        items.append({
            "mst": it.get("법령일련번호"),       # 본문 조회 키 (get_law에 사용)
            "law_id": it.get("법령ID"),
            "name": it.get("법령명한글"),
            "kind": it.get("법령구분명"),
            "department": it.get("소관부처명"),
            "promulgation_date": it.get("공포일자"),
            "effective_date": it.get("시행일자"),
            "revision_type": it.get("제개정구분명"),
            "detail_url": it.get("법령상세링크"),
        })
    return {"total": int(body.get("totalCnt") or 0), "page": int(body.get("page") or page), "items": items}


def search_admin_rules(query: str, *, page: int = 1, display: int = 20, scope: int = 1) -> dict:
    """행정규칙(훈령·예규·고시·지침) 검색. scope: 1=규칙명, 2=본문."""
    raw = _request(SEARCH_URL, {
        "target": "admrul", "query": query,
        "page": max(page, 1), "display": min(max(display, 1), 100), "search": scope,
    })
    body = raw.get("AdmRulSearch", {}) or {}
    items = []
    for it in _as_list(body.get("admrul")):
        items.append({
            "id": it.get("행정규칙일련번호"),     # 본문 조회 키 (get_admin_rule에 사용)
            "name": it.get("행정규칙명"),
            "rule_type": it.get("행정규칙종류"),
            "department": it.get("소관부처명"),
            "issue_date": it.get("발령일자"),
            "issue_no": it.get("발령번호"),
            "status": it.get("현행연혁구분"),
            "effective_date": it.get("시행일자"),
            "detail_url": it.get("행정규칙상세링크"),
        })
    return {"total": int(body.get("totalCnt") or 0), "page": int(body.get("page") or page), "items": items}


# ── 본문 조회 ────────────────────────────────────────────────────────────────


def _flatten_clause(node) -> str:
    """조문 하위(항·호·목) 트리에서 텍스트만 모아 합침."""
    parts: list[str] = []

    def walk(n):
        if isinstance(n, str):
            parts.append(n)
        elif isinstance(n, dict):
            for key in ("조문내용", "항내용", "호내용", "목내용"):
                v = n.get(key)
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, list):
                    parts.extend(x for x in v if isinstance(x, str))
            for key in ("항", "호", "목"):
                for child in _as_list(n.get(key)):
                    walk(child)
        elif isinstance(n, list):
            for child in n:
                walk(child)

    walk(node)
    return "\n".join(p.strip() for p in parts if p and p.strip())


def get_law(mst: str, *, article: str | None = None, full_text: bool = False) -> dict:
    """법령 본문 조회 (MST=법령일련번호).

    - article 지정 시(예: '4' 또는 '4의2'): 해당 조문 전문만 반환
    - 미지정 + full_text=False: 기본정보 + 조문 목차(번호·제목)만 — 대형 법령의 컨텍스트 보호
    - 미지정 + full_text=True: 전 조문 전문
    """
    raw = _request(SERVICE_URL, {"target": "law", "MST": mst})
    body = raw.get("법령", {}) or {}
    if not body:
        raise LawAPIError(f"법령 MST={mst} 조회 결과가 비어 있습니다. search_laws의 'mst' 값인지 확인하세요.")

    basic_raw = body.get("기본정보", {}) or {}
    basic = {
        "name": basic_raw.get("법령명_한글"),
        "law_id": basic_raw.get("법령ID"),
        "kind": (basic_raw.get("법종구분") or {}).get("#text") if isinstance(basic_raw.get("법종구분"), dict) else basic_raw.get("법종구분"),
        "department": (basic_raw.get("소관부처") or {}).get("#text") if isinstance(basic_raw.get("소관부처"), dict) else basic_raw.get("소관부처"),
        "promulgation_date": basic_raw.get("공포일자"),
        "effective_date": basic_raw.get("시행일자"),
        "revision_type": basic_raw.get("제개정구분"),
    }

    units = _as_list((body.get("조문") or {}).get("조문단위"))
    articles = []
    for u in units:
        if not isinstance(u, dict):
            continue
        no = str(u.get("조문번호") or "")
        sub = str(u.get("조문가지번호") or "")
        key = f"{no}의{sub}" if sub and sub != "0" else no
        articles.append({
            "article": key,
            "title": u.get("조문제목"),
            "is_heading": u.get("조문여부") == "전문",  # 장·절 표제 행
            "_unit": u,
        })

    if article:
        want = str(article).replace("제", "").replace("조", "").strip()
        hits = [a for a in articles if a["article"] == want and not a["is_heading"]]
        if not hits:
            raise LawAPIError(f"'{basic['name']}'에 제{want}조가 없습니다.")
        return {
            "basic": basic,
            "articles": [
                {"article": a["article"], "title": a["title"], "text": _flatten_clause(a["_unit"])}
                for a in hits
            ],
        }

    if full_text:
        return {
            "basic": basic,
            "articles": [
                {"article": a["article"], "title": a["title"], "text": _flatten_clause(a["_unit"])}
                for a in articles if not a["is_heading"]
            ],
        }

    # 목차 모드 — 조문이 많은 법령에서 전체 본문 대신 구조만
    return {
        "basic": basic,
        "toc": [
            {"article": a["article"], "title": a["title"]}
            for a in articles if not a["is_heading"] and a["title"]
        ],
        "article_count": sum(1 for a in articles if not a["is_heading"]),
    }


def get_admin_rule(rule_id: str) -> dict:
    """행정규칙 본문 조회 (ID=행정규칙일련번호)."""
    raw = _request(SERVICE_URL, {"target": "admrul", "ID": rule_id})
    body = raw.get("AdmRulService", {}) or {}
    if not body:
        raise LawAPIError(f"행정규칙 ID={rule_id} 조회 결과가 비어 있습니다.")

    info = body.get("행정규칙기본정보", {}) or {}
    basic = {
        "name": info.get("행정규칙명"),
        "rule_type": info.get("행정규칙종류"),
        "department": info.get("소관부처명"),
        "issue_date": info.get("발령일자"),
        "issue_no": info.get("발령번호"),
        "effective_date": info.get("시행일자"),
        "status": info.get("현행연혁구분"),
    }
    # 행정규칙 본문은 조문내용(문자열 목록) 또는 첨부 형태 — 있는 것만 수집
    text_parts: list[str] = []
    for key in ("조문내용", "본문내용"):
        for chunk in _as_list(body.get(key)):
            if isinstance(chunk, str) and chunk.strip():
                text_parts.append(chunk.strip())
            elif isinstance(chunk, dict):
                t = _flatten_clause(chunk)
                if t:
                    text_parts.append(t)
    addenda = [c for c in _as_list(body.get("부칙")) if isinstance(c, str)]
    return {
        "basic": basic,
        "text": "\n\n".join(text_parts) if text_parts else None,
        "addenda": addenda or None,
        "has_attachment_only": not text_parts,  # 본문이 별첨(HWP)뿐인 규칙도 있음
    }
