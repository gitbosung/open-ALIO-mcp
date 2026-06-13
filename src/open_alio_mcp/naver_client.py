# -*- coding: utf-8 -*-
"""네이버 검색 API (뉴스) 클라이언트 — 공공기관 최근 이슈 조회용.

키 발급: https://developers.naver.com → 애플리케이션 등록 → '검색' API 선택.
.env에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 설정.
"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv

from .security_utils import mask_sensitive_text, request_get_with_security

load_dotenv()

log = logging.getLogger("naver")

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

_cache: dict[str, tuple[float, Any]] = {}
TTL = 300  # 뉴스는 신선도가 중요 — 5분만 캐시


class NaverAPIError(Exception):
    pass


def has_credentials() -> bool:
    return bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET)


def search_news(query: str, *, display: int = 100, start: int = 1, sort: str = "date") -> dict:
    """뉴스 검색 GET /v1/search/news.json — sort: 'date'(최신순)·'sim'(정확도순)."""
    if not has_credentials():
        raise NaverAPIError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 .env에 없습니다. "
            "developers.naver.com에서 '검색' API 키를 발급받으세요."
        )
    if sort not in ("date", "sim"):
        raise NaverAPIError(f"sort는 'date' 또는 'sim'이어야 합니다 (현재 '{sort}')")

    params = {"query": query, "display": min(max(display, 1), 100), "start": max(start, 1), "sort": sort}
    cache_key = str(sorted(params.items()))
    if cache_key in _cache and time.time() - _cache[cache_key][0] < TTL:
        return _cache[cache_key][1]

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    try:
        r = request_get_with_security(
            NEWS_URL,
            params=params,
            headers=headers,
            timeout=15,
            retries=1,
            logger=log,
            label="Naver News API",
        )
    except requests.RequestException as e:
        raise NaverAPIError(f"네이버 API 연결 실패: {mask_sensitive_text(e)}") from e

    if r.status_code != 200:
        try:
            body = r.json()
            msg = f"[{body.get('errorCode')}] {body.get('errorMessage')}"
        except ValueError:
            msg = r.text[:200]
        if r.status_code == 429:
            raise NaverAPIError("네이버 API 일일 호출 한도(25,000회) 초과")
        raise NaverAPIError(f"네이버 API 오류 (HTTP {r.status_code}) {msg}")

    data = r.json()
    _cache[cache_key] = (time.time(), data)
    return data


# 네이버 검색 API 페이지네이션 한도: start 최대 1000, display 최대 100
MAX_START = 1000
MAX_DISPLAY = 100


def fetch_news(
    query: str,
    *,
    sort: str = "date",
    max_results: int = 100,
    stop_before_ts: float | None = None,
) -> list[dict]:
    """여러 페이지를 모아 raw item 목록 반환.

    max_results까지 100건씩 페이지네이션. sort='date'일 때 stop_before_ts(epoch)를
    주면 그보다 오래된 기사가 나오는 순간 조기 종료 (기간 필터 시 호출 절약).
    """
    items: list[dict] = []
    target = min(max(max_results, 1), MAX_START)
    start = 1
    while start <= MAX_START and len(items) < target:
        display = min(MAX_DISPLAY, target - len(items))
        raw = search_news(query, display=display, start=start, sort=sort)
        batch = raw.get("items") or []
        if not batch:
            break
        items.extend(batch)
        if sort == "date" and stop_before_ts is not None:
            last = parse_pubdate(batch[-1].get("pubDate"))
            if last and last.timestamp() < stop_before_ts:
                break  # 이후 페이지는 더 오래된 기사뿐
        if len(batch) < display:
            break  # 마지막 페이지
        start += display
    return items


# ── 응답 정제 ─────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"</?b>|</?[a-zA-Z][^>]*>")
_TITLE_NORM_RE = re.compile(r"[\s\W]+", re.UNICODE)


def strip_tags(text: str | None) -> str:
    """네이버 응답의 <b> 강조 태그 제거 + HTML 엔티티 복원."""
    if not text:
        return ""
    return html.unescape(_TAG_RE.sub("", text)).strip()


def parse_pubdate(value: str | None) -> datetime | None:
    """RFC 1123 형식 pubDate ('Mon, 26 Sep 2016 07:50:00 +0900') → datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        return None


def normalize_news_item(item: dict) -> dict:
    """네이버 뉴스 응답 1건 → MCP 공통 스키마."""
    published = parse_pubdate(item.get("pubDate"))
    return {
        "title": strip_tags(item.get("title")),
        "summary": strip_tags(item.get("description")),
        "link": item.get("link"),
        "original_link": item.get("originallink"),
        "published_at": published.isoformat(timespec="seconds") if published else None,
    }


def dedup_news(items: list[dict]) -> list[dict]:
    """제목(공백·기호 무시) 또는 원문 링크가 같은 복제 기사 제거 — 순서 유지."""
    seen_titles: set[str] = set()
    seen_links: set[str] = set()
    out: list[dict] = []
    for it in items:
        title_key = _TITLE_NORM_RE.sub("", (it.get("title") or "").lower())
        link_key = it.get("original_link") or it.get("link") or ""
        if title_key and title_key in seen_titles:
            continue
        if link_key and link_key in seen_links:
            continue
        if title_key:
            seen_titles.add(title_key)
        if link_key:
            seen_links.add(link_key)
        out.append(it)
    return out


# ── 기관명·별칭 → 검색어 구성 ─────────────────────────────────────────────

# 법인격 표기는 기사에서 거의 쓰이지 않음 — 검색어에서 제거
_LEGAL_FORM_RE = re.compile(
    r"^\(주\)|^\(재\)|^\(사\)|^재단법인\s*|^사단법인\s*|^주식회사\s*|^학교법인\s*"
    r"|\(주\)$|주식회사$|\s*주식회사$"
)

# 짧지만 뉴스에서 해당 기관 지칭으로 통용되는 약칭 (동음이의어 위험 낮음)
NEWS_SAFE_SHORT = {"한전", "캠코", "LH", "SRT", "IBK", "HUG", "GKL"}

# 동음이의어·일반명사와 충돌해 뉴스 검색 노이즈가 큰 약칭
NEWS_NOISY = {
    "예보",   # 일기예보
    "도공",   # 陶工
    "수공",   # 手工
    "기보",   # 바둑 기보
    "건공",   # 일반어 충돌
    "TP", "TS", "KR", "SR", "HF", "KIM", "ADD", "aT", "KF", "KOC", "KEF",
    "Arirang", "CARBON", "JobWorld", "K-Food",
}


def clean_org_name(name: str) -> str:
    """공식 기관명에서 (주)·재단법인 등 법인격 표기 제거 → 뉴스 검색용 명칭."""
    return _LEGAL_FORM_RE.sub("", (name or "").strip()).strip()


def _is_news_safe(alias: str) -> bool:
    if alias in NEWS_SAFE_SHORT:
        return True
    if alias in NEWS_NOISY:
        return False
    if alias.isascii():
        return len(alias) >= 4  # 짧은 영문 약어(KR·TS 등)는 오탐 큼
    return len(alias) >= 3  # 2글자 한글 약칭은 동음이의어 위험


def news_terms(official_name: str, alias_map: dict[str, str], *, max_terms: int = 4) -> list[str]:
    """공식 기관명 + 뉴스 검색에 안전한 별칭 목록 (통용 약칭·한글 우선)."""
    base = clean_org_name(official_name)
    aliases = []
    for a, official in alias_map.items():
        if official != official_name or not _is_news_safe(a):
            continue
        cleaned = clean_org_name(a)
        if cleaned and cleaned not in (official_name, base) and cleaned not in aliases:
            aliases.append(cleaned)
    # 통용 약칭(LH·한전 등) > 한글(기사 표기 빈도 높음) > 영문, 짧은 것 우선
    aliases.sort(key=lambda a: (a not in NEWS_SAFE_SHORT, a.isascii(), len(a)))
    terms = [base] if base else []
    for a in aliases:
        if a not in terms:
            terms.append(a)
        if len(terms) >= max_terms:
            break
    return terms


def build_news_query(terms: list[str]) -> str:
    """검색어 목록 → 네이버 OR 연산(|) 쿼리. 구문은 따옴표로 묶어 정확도 확보."""
    quoted = [f'"{t}"' if " " in t or not t.isascii() else t for t in terms]
    return " | ".join(quoted)
