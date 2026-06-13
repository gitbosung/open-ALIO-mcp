# -*- coding: utf-8 -*-
"""data/guidelines/*.json 지침 저장소 — 조문 단위 검색·조회 (lazy load).

데이터 생성: 지침 파일(.hwpx/.pdf)을 rawdata/guidelines/에 넣고
scripts/build_guidelines.py 실행. law.go.kr 행정규칙에 없는 연도별 시달
지침(예산운용지침 등)을 보완하는 로컬 저장소다.
"""
from __future__ import annotations

from . import data_provider

_index: dict | None = None
_docs: dict[str, dict] = {}

SNIPPET_LEN = 300


class GuidelineError(Exception):
    pass


def get_index() -> dict:
    global _index
    if _index is None:
        rel = "guidelines/_index.json"
        if not data_provider.exists(rel):
            raise GuidelineError(
                "적재된 지침이 없습니다 — 지침 파일(.hwpx/.pdf)을 rawdata/guidelines/에 넣고 "
                "scripts/build_guidelines.py를 실행하세요. (.hwp는 HWPX로 변환 필요)"
            )
        _index = data_provider.read_json(rel)
    return _index


def list_docs() -> list[dict]:
    return get_index()["docs"]


def _load(doc_id: str) -> dict:
    if doc_id not in _docs:
        rel = f"guidelines/{doc_id}.json"
        if not data_provider.exists(rel):
            valid = ", ".join(d["doc_id"] for d in list_docs())
            raise GuidelineError(f"지침 '{doc_id}' 없음. 적재된 지침: {valid}")
        _docs[doc_id] = data_provider.read_json(rel)
    return _docs[doc_id]


def _snippet(text: str, term: str) -> str:
    pos = text.find(term)
    if pos < 0:
        return text[:SNIPPET_LEN]
    start = max(0, pos - SNIPPET_LEN // 3)
    out = text[start:start + SNIPPET_LEN]
    return ("…" if start > 0 else "") + out + ("…" if start + SNIPPET_LEN < len(text) else "")


def search(query: str, *, year: int | None = None, issuer: str | None = None, limit: int = 10) -> dict:
    """조문 텍스트·제목에서 키워드 검색 (공백 구분 AND, 매칭 수로 정렬)."""
    terms = [t for t in query.split() if t]
    if not terms:
        raise GuidelineError("query가 비어 있습니다")

    hits: list[dict] = []
    for meta in list_docs():
        if year and meta.get("year") != year:
            continue
        if issuer and issuer not in (meta.get("issuer") or ""):
            continue
        doc = _load(meta["doc_id"])
        for art in doc["articles"]:
            haystack = f"{art.get('title') or ''}\n{art['text']}"
            counts = [haystack.count(t) for t in terms]
            if all(c > 0 for c in counts):
                hits.append({
                    "doc_id": doc["doc_id"],
                    "doc_title": doc["title"],
                    "year": doc.get("year"),
                    "article": art["article"],
                    "article_title": art.get("title"),
                    "chapter": art.get("chapter") or None,
                    "snippet": _snippet(art["text"], terms[0]),
                    "_score": sum(counts),
                })

    hits.sort(key=lambda h: -h["_score"])
    for h in hits:
        h.pop("_score")
    return {"total": len(hits), "query": query, "hits": hits[:limit]}


def get_text(doc_id: str, *, article: str | None = None) -> dict:
    """지침 전문 또는 특정 조문 조회. article 미지정 시 목차 모드."""
    doc = _load(doc_id)
    meta = {k: doc[k] for k in ("doc_id", "title", "year", "issuer", "effective_date", "source_file")}

    if article:
        want = str(article).replace("제", "").replace("조", "").strip()
        found = [a for a in doc["articles"] if a["article"] == want]
        if not found:
            raise GuidelineError(f"'{doc['title']}'에 제{want}조가 없습니다 (조문 {doc['article_count']}개).")
        return {**meta, "articles": found}

    return {
        **meta,
        "preamble": doc.get("preamble"),
        "article_count": doc["article_count"],
        "toc": [{"article": a["article"], "title": a.get("title"), "chapter": a.get("chapter") or None}
                for a in doc["articles"]],
    }
