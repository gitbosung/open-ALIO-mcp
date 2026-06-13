# -*- coding: utf-8 -*-
"""뉴스 정성 분석 유틸 — 테마 분류·타임라인·토픽↔지표 매핑.

순수 함수 모듈 (외부 store 의존 없음). server.py의 결합 도구가 사용:
- digest_institution_news: classify_theme / bucket_by_theme / timeline_by_date
- cross_check_news_with_metrics: resolve_topic / filter_by_keywords
"""

from __future__ import annotations

from collections import Counter

# ── 뉴스 테마 분류 ────────────────────────────────────────────────────────
# (label, keywords) — 위에서부터 우선순위. 리스크성(감사·안전)을 상단에 배치.
THEME_RULES: list[tuple[str, list[str]]] = [
    ("감사·비위", ["감사", "비위", "비리", "횡령", "배임", "징계", "부패", "수사", "압수", "기소", "특혜", "논란", "의혹"]),
    ("안전·재해", ["산재", "사망", "중대재해", "안전사고", "재해", "붕괴", "누출", "화재", "부상"]),
    ("재무·실적", ["부채", "적자", "흑자", "영업이익", "당기순이익", "순손실", "재무", "신용등급", "회사채", "사채", "자금조달", "자본잠식", "결산"]),
    ("채용·인사", ["채용", "신규채용", "공채", "인턴", "사장", "신임", "임명", "인선", "선임", "이사장", "노조", "파업", "노사", "임단협"]),
    ("정책·국회", ["국정감사", "국감", "국회", "법안", "개정", "정부", "장관", "예산안", "정책", "혁신도시", "이전"]),
    ("사업·협약", ["협약", "MOU", "업무협약", "수주", "발주", "낙찰", "착공", "준공", "투자", "공모전", "공모", "출시", "개발", "구축", "체결", "지원사업"]),
    ("사회공헌·ESG", ["사회공헌", "봉사", "기부", "후원", "상생", "나눔", "ESG", "탄소", "친환경", "장학"]),
]

DEFAULT_THEME = "기타·일반"


def classify_theme(title: str, summary: str = "") -> str:
    """제목+요약을 테마 1개로 분류 (우선순위 규칙, 미매칭 시 기타)."""
    text = f"{title} {summary}"
    for label, keywords in THEME_RULES:
        if any(k in text for k in keywords):
            return label
    return DEFAULT_THEME


def bucket_by_theme(items: list[dict], *, per_theme: int = 3) -> list[dict]:
    """뉴스 목록 → 테마별 {label, count, headlines[]} (건수 내림차순)."""
    buckets: dict[str, list[dict]] = {}
    for it in items:
        label = classify_theme(it.get("title") or "", it.get("summary") or "")
        buckets.setdefault(label, []).append(it)
    out = []
    for label, arts in buckets.items():
        out.append(
            {
                "theme": label,
                "count": len(arts),
                "headlines": [
                    {"title": a.get("title"), "published_at": a.get("published_at"), "link": a.get("link")}
                    for a in arts[:per_theme]
                ],
            }
        )
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


def timeline_by_date(items: list[dict]) -> dict[str, int]:
    """발행일(YYYY-MM-DD)별 기사 수 — 최신 날짜부터."""
    c: Counter = Counter()
    for it in items:
        pub = it.get("published_at")
        if pub:
            c[pub[:10]] += 1
    return dict(sorted(c.items(), reverse=True))


# ── 토픽 → 지표 카테고리 매핑 (cross-check용) ──────────────────────────────
# topic 입력 → {category, item_query(지표 좁히기), keywords(뉴스 필터)}
TOPIC_TO_METRIC: dict[str, dict] = {
    "부채": {"category": "finance", "item_query": "부채비율", "keywords": ["부채", "빚", "적자", "재무", "자본", "신용등급"]},
    "재무": {"category": "finance", "item_query": "부채비율", "keywords": ["부채", "적자", "흑자", "재무", "영업이익", "순이익", "자산", "자본"]},
    "자산": {"category": "finance", "item_query": "자산총계", "keywords": ["자산", "재무"]},
    "적자": {"category": "finance", "item_query": "영업이익", "keywords": ["적자", "손실", "영업이익", "순이익"]},
    "정원": {"category": "staff", "item_query": "정원", "keywords": ["정원", "인력", "직원", "증원", "감축", "구조조정"]},
    "인력": {"category": "staff", "item_query": "정원", "keywords": ["인력", "정원", "직원", "현원"]},
    "보수": {"category": "salary", "item_query": "평균보수", "keywords": ["보수", "연봉", "임금", "급여", "성과급"]},
    "연봉": {"category": "salary", "item_query": "평균보수", "keywords": ["연봉", "보수", "임금"]},
    "임원": {"category": "executive_pay", "item_query": "", "keywords": ["임원", "연봉", "성과급", "사장"]},
    "채용": {"category": "recruitment", "item_query": "신규채용", "keywords": ["채용", "신규채용", "인턴", "공채", "일자리"]},
    "복지": {"category": "welfare", "item_query": "복리후생비", "keywords": ["복지", "복리후생", "후생"]},
    "예산": {"category": "budget", "item_query": "", "keywords": ["예산", "수입", "지출", "정부지원"]},
}


def resolve_topic(topic: str) -> tuple[str, dict] | None:
    """입력 토픽 → (정규화 키, 매핑). 직접일치 → 부분일치 순."""
    t = (topic or "").strip()
    if not t:
        return None
    if t in TOPIC_TO_METRIC:
        return t, TOPIC_TO_METRIC[t]
    for key, entry in TOPIC_TO_METRIC.items():
        if key in t or t in key:
            return key, entry
    # 키워드로도 역추적
    for key, entry in TOPIC_TO_METRIC.items():
        if any(kw in t for kw in entry["keywords"]):
            return key, entry
    return None


def filter_by_keywords(items: list[dict], keywords: list[str]) -> list[dict]:
    """제목·요약에 키워드 하나라도 포함된 기사만."""
    if not keywords:
        return items
    out = []
    for it in items:
        text = f"{it.get('title') or ''} {it.get('summary') or ''}"
        if any(k in text for k in keywords):
            out.append(it)
    return out
