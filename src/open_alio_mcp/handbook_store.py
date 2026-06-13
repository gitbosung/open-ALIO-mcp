# -*- coding: utf-8 -*-
"""data/handbook/*.json — 경영평가편람 저장소 (검색·지표 조회)."""
from __future__ import annotations

import re

from . import data_provider

_index: dict | None = None
_docs: dict[str, dict] = {}

SNIPPET_LEN = 400


class HandbookError(Exception):
    pass


def get_index() -> dict:
    global _index
    if _index is None:
        rel = "handbook/_index.json"
        if not data_provider.exists(rel):
            raise HandbookError(
                "적재된 경영평가편람이 없습니다 — 배포 스냅샷(alio_snapshot.db)이 손상되었거나 "
                "OPEN_ALIO_DATA_DIR/OPEN_ALIO_SNAPSHOT_PATH 설정을 확인하세요."
            )
        _index = data_provider.read_json(rel)
    return _index


def list_docs() -> list[dict]:
    return get_index()["docs"]


def _load(doc_id: str) -> dict:
    if doc_id not in _docs:
        rel = f"handbook/{doc_id}.json"
        if not data_provider.exists(rel):
            valid = ", ".join(d["doc_id"] for d in list_docs())
            raise HandbookError(f"편람 '{doc_id}' 없음. 적재된 편람: {valid}")
        _docs[doc_id] = data_provider.read_json(rel)
    return _docs[doc_id]


def _snippet(text: str, term: str) -> str:
    pos = text.find(term)
    if pos < 0:
        return text[:SNIPPET_LEN]
    start = max(0, pos - SNIPPET_LEN // 4)
    out = text[start : start + SNIPPET_LEN]
    return ("…" if start > 0 else "") + out + ("…" if start + SNIPPET_LEN < len(text) else "")


def search(
    query: str,
    *,
    year: int | None = None,
    part: str = "",
    limit: int = 10,
) -> dict:
    terms = [t for t in query.split() if t]
    if not terms:
        raise HandbookError("query가 비어 있습니다")

    hits: list[dict] = []
    docs = list_docs()
    if year:
        docs = [d for d in docs if d.get("year") == year]

    for meta in docs:
        doc = _load(meta["doc_id"])
        for ch in doc.get("chunks") or []:
            if part and part not in (ch.get("part") or ""):
                continue
            hay = ch["text"]
            counts = [hay.count(t) for t in terms]
            if all(c > 0 for c in counts):
                hits.append(
                    {
                        "doc_id": meta["doc_id"],
                        "year": doc.get("year"),
                        "title": doc.get("title"),
                        "part": ch.get("part"),
                        "page_start": ch.get("page_start"),
                        "page_end": ch.get("page_end"),
                        "snippet": _snippet(hay, terms[0]),
                        "_score": sum(counts),
                    }
                )

    hits.sort(key=lambda h: (-h["_score"], h.get("page_start") or 0))
    for h in hits:
        h.pop("_score")
    return {"total": len(hits), "query": query, "hits": hits[:limit]}


def list_indicators(
    *,
    year: int | None = None,
    org_class: str = "",
    org_subtype: str = "",
) -> dict:
    docs_meta = list_docs()
    if year:
        docs_meta = [d for d in docs_meta if d.get("year") == year]
    if not docs_meta:
        raise HandbookError(f"{year or '해당'} 연도 편람이 없습니다")

    tables: list[dict] = []
    for meta in docs_meta:
        doc = _load(meta["doc_id"])
        for tbl in doc.get("weight_tables") or []:
            if org_class and org_class not in tbl.get("org_class", ""):
                continue
            if org_subtype and org_subtype not in tbl.get("org_subtype", ""):
                continue
            tables.append(
                {
                    "doc_id": meta["doc_id"],
                    "year": doc.get("year"),
                    "org_class": tbl.get("org_class"),
                    "org_subtype": tbl.get("org_subtype"),
                    "page": tbl.get("page"),
                    "indicators": tbl.get("indicators") or [],
                }
            )
    return {"count": len(tables), "tables": tables}


# PDF 표 추출 텍스트의 지표 행: "- 안전 및 재난관리 5 3.5 1.5" (지표명 + 계/비계량/계량)
# 숫자가 공백 없이 붙은 행("…532")은 분해가 모호하므로 파싱하지 않는다.
_SCORE = r"(\d+(?:\.\d+)?|-)"
_INDICATOR_ROW_RE = re.compile(rf"^[-•·]?\s*(?P<name>\D.*?\D)\s+{_SCORE}\s+{_SCORE}\s+{_SCORE}\s*$")


def _parse_indicator_row(text: str | None) -> tuple[str, dict] | None:
    """지표명과 배점(계·비계량·계량)이 공백으로 명확히 구분된 행만 구조화한다."""
    m = _INDICATOR_ROW_RE.match((text or "").strip())
    if not m:
        return None

    def _num(tok: str) -> float | None:
        return None if tok == "-" else float(tok)

    total, non_quant, quant = (_num(t) for t in m.group(2, 3, 4))
    # 배점 정합성 검사: 계 = 비계량 + 계량 (결측 '-'는 0으로 간주)
    if total is None or abs(total - ((non_quant or 0) + (quant or 0))) > 0.01:
        return None
    return m.group("name").strip(), {
        "total": total,
        "non_quantitative": non_quant,
        "quantitative": quant,
    }


def get_indicator_detail(query: str, *, year: int | None = None) -> dict:
    q = query.strip()
    if not q:
        raise HandbookError("query가 필요합니다")

    matches: list[dict] = []
    docs_meta = list_docs()
    if year:
        docs_meta = [d for d in docs_meta if d.get("year") == year]

    for meta in docs_meta:
        doc = _load(meta["doc_id"])
        for block in doc.get("indicator_details") or []:
            hay = block.get("content") or ""
            if (
                q in (block.get("indicator") or "")
                or q in (block.get("sub_indicator") or "")
                or q in hay
            ):
                enriched = {**block, "doc_id": meta["doc_id"], "year": doc.get("year")}
                parsed = _parse_indicator_row(block.get("indicator"))
                if parsed:
                    enriched["indicator_name"], enriched["scores"] = parsed
                matches.append(enriched)

    if not matches:
        sr = search(q, year=year, limit=3)
        return {"query": q, "details": [], "search_fallback": sr.get("hits", [])}

    return {"query": q, "count": len(matches), "details": matches[:5]}


def list_org_subtypes(*, year: int | None = None) -> dict:
    seen: set[tuple] = set()
    out: list[dict] = []
    for tbl in list_indicators(year=year).get("tables") or []:
        key = (tbl.get("org_class"), tbl.get("org_subtype"))
        if key not in seen:
            seen.add(key)
            out.append(
                {"org_class": tbl.get("org_class"), "org_subtype": tbl.get("org_subtype"), "year": tbl.get("year")}
            )
    return {"count": len(out), "subtypes": out}


def compare_years(query: str, year_a: int, year_b: int, limit: int = 5) -> dict:
    a = search(query, year=year_a, limit=limit)
    b = search(query, year=year_b, limit=limit)
    return {
        "query": query,
        "year_a": year_a,
        "year_b": year_b,
        "hits_a": a.get("hits", []),
        "hits_b": b.get("hits", []),
        "count_a": a.get("total", 0),
        "count_b": b.get("total", 0),
    }
