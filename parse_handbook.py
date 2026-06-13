# -*- coding: utf-8 -*-
"""경영평가편람 PDF 파싱 — pdfplumber 기반 텍스트·표·지표 추출."""
from __future__ import annotations

import re

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore

_SPACED_YEAR = re.compile(r"(?<=\b)(?:2\s*){3,4}\d(?=\s*년)")
_SPACED_DIGITS = re.compile(r"\b((?:\d\s+){2,}\d)\b")
_PUA = re.compile(r"[\uE000-\uF8FF]")
_WEIGHT_HDR = re.compile(
    r"(공기업|준정부기관|기타공공기관|강소형)\s*\(([^)]+)\)의\s*지표\s*및\s*가중치\s*기준"
)
_PART_HDR = re.compile(r"제\s*(\d+)\s*편")
_SUB_IND = re.compile(r"^-\s*(.+)$")
_MAIN_IND = re.compile(r"^(\d+)\.\s*(.+)$")
_IND_BLOCK = re.compile(r"^\((\d+)\)\s*(.+)$")
_FIELD = re.compile(r"^(지표정의|적용대상\(배점\)|세부평가내용)\s*(.*)$")


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = _PUA.sub("", text)
    text = text.replace("\u2024", "·").replace("\u2027", "·").replace("․", "·")
    text = text.replace("\u00a0", " ")

    def _year(m: re.Match) -> str:
        return re.sub(r"\s+", "", m.group(0))

    text = _SPACED_YEAR.sub(_year, text)

    def _digits(m: re.Match) -> str:
        return re.sub(r"\s+", "", m.group(1))

    text = _SPACED_DIGITS.sub(_digits, text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(path) -> list[dict]:
    if pdfplumber is None:
        raise ImportError("pdfplumber 필요: pip install pdfplumber")
    pages: list[dict] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, pg in enumerate(pdf.pages):
            raw = pg.extract_text() or ""
            pages.append({"page": i + 1, "text": normalize_text(raw)})
    return pages


def _parse_weight_table(table: list[list], org_class: str, org_subtype: str) -> dict | None:
    if not table or len(table) < 2:
        return None
    header = [c or "" for c in table[0]]
    if "평가지표" not in "".join(header):
        return None

    def _split(cell) -> list[str]:
        if not cell:
            return []
        return [ln.strip() for ln in str(cell).split("\n") if ln.strip()]

    indicators: list[dict] = []
    current_category = ""

    for row in table[1:]:
        cells = [(c or "").strip() for c in row]
        while len(cells) < 5:
            cells.append("")
        cat, ind_cell, total_cell, qual_cell, quant_cell = cells[:5]
        if cat and cat not in ("범주",):
            current_category = cat.replace("\n", " ").strip()

        names = _split(ind_cell)
        if not names:
            continue
        totals = _split(total_cell)
        quals = _split(qual_cell)
        quants = _split(quant_cell)

        def _at(lst: list[str], idx: int) -> str | None:
            return lst[idx] if idx < len(lst) else None

        for j, name in enumerate(names):
            entry: dict = {
                "name": name,
                "category": current_category or None,
                "total": _at(totals, j),
                "qualitative": _at(quals, j),
                "quantitative": _at(quants, j),
            }
            main_m = _MAIN_IND.match(name)
            sub_m = _SUB_IND.match(name)
            if main_m:
                entry["level"] = "main"
            elif sub_m:
                entry["level"] = "sub"
                entry["name"] = sub_m.group(1)
            else:
                entry["level"] = "summary" if "계" in name else "other"
            indicators.append(entry)

    if not indicators:
        return None
    return {"org_class": org_class, "org_subtype": org_subtype, "indicators": indicators}


def parse_weight_tables(path) -> list[dict]:
    if pdfplumber is None:
        raise ImportError("pdfplumber 필요")
    tables: list[dict] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, pg in enumerate(pdf.pages):
            text = normalize_text(pg.extract_text() or "")
            m = _WEIGHT_HDR.search(text)
            if not m:
                continue
            org_class, org_subtype = m.group(1), m.group(2)
            for tbl in pg.extract_tables() or []:
                parsed = _parse_weight_table(tbl, org_class, org_subtype)
                if parsed:
                    parsed["page"] = i + 1
                    tables.append(parsed)
    return tables


def _detect_part(text: str, state: str) -> str:
    if "기관별 경영실적" in text or "[별첨]" in text:
        return "기관별_별첨"
    m = _PART_HDR.search(text)
    if m:
        return {"1": "경영실적", "2": "기관장_경영계약", "3": "상임감사"}.get(m.group(1), state)
    if "기관장 경영계약" in text:
        return "기관장_경영계약"
    if "상임감사" in text and "직무수행" in text:
        return "상임감사"
    return state or "경영실적"


def chunk_pages(pages: list[dict], *, max_chars: int = 1800) -> list[dict]:
    chunks: list[dict] = []
    part = "경영실적"
    buf: list[str] = []
    buf_start = 0
    buf_part = part

    def _flush(end_page: int) -> None:
        nonlocal buf, buf_start, buf_part
        if not buf:
            return
        text = "\n".join(buf).strip()
        if len(text) < 30:
            buf, buf_start = [], 0
            return
        chunks.append(
            {
                "part": buf_part,
                "page_start": buf_start,
                "page_end": end_page,
                "text": text[: max_chars * 2],
            }
        )
        buf, buf_start = [], 0

    for p in pages:
        text = p.get("text") or ""
        if not text or len(text) < 20:
            continue
        part = _detect_part(text, part)
        if not buf:
            buf_start = p["page"]
            buf_part = part
        elif part != buf_part or sum(len(x) for x in buf) + len(text) > max_chars:
            _flush(p["page"] - 1)
            buf_start = p["page"]
            buf_part = part
        buf.append(text)

    if pages:
        _flush(pages[-1]["page"])
    return chunks


def parse_indicator_details(pages: list[dict]) -> list[dict]:
    details: list[dict] = []
    current_indicator = ""
    current_sub = ""
    block_lines: list[str] = []
    block_page = 0
    fields: dict[str, str] = {}

    def _save() -> None:
        nonlocal block_lines, fields
        body = "\n".join(block_lines).strip()
        if len(body) < 40 and not fields:
            block_lines, fields = [], {}
            return
        details.append(
            {
                "indicator": current_indicator or None,
                "sub_indicator": current_sub or None,
                "definition": fields.get("지표정의"),
                "target_scores": fields.get("적용대상(배점)"),
                "content": body,
                "page": block_page,
            }
        )
        block_lines, fields = [], {}

    for p in pages:
        text = p.get("text") or ""
        if "세부평가내용" not in text and not block_lines:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line in ("평가지표", "세부평가내용"):
                continue
            bm = _IND_BLOCK.match(line)
            if bm:
                _save()
                current_sub = bm.group(2).strip()
                block_page = p["page"]
                block_lines = [line]
                continue
            fm = _FIELD.match(line)
            if fm:
                fields[fm.group(1)] = fm.group(2).strip()
                block_lines.append(line)
                continue
            if "관리" in line and len(line) < 35 and ("및" in line or "운영" in line):
                current_indicator = line
            block_lines.append(line)
            if len(block_lines) > 80:
                _save()
                block_page = p["page"]
    _save()
    return details


def guess_meta(path, text: str) -> dict:
    stem = path.stem
    year = None
    m = re.search(r"(20\d{2})", stem) or re.search(r"(20\d{2})\s*년", text[:800])
    if m:
        year = int(m.group(1))
    kind = "revision" if "수정" in stem else "full"
    title = re.sub(r"^[★\s]+", "", re.sub(r"[_\[\]]+", " ", stem)).strip()
    return {"title": title, "year": year, "kind": kind, "issuer": "기획재정부"}


def build_document(path, *, meta: dict | None = None) -> dict:
    """PDF 1건 → 적재용 JSON (단일 패스)."""
    if pdfplumber is None:
        raise ImportError("pdfplumber 필요")
    pages: list[dict] = []
    weight_tables: list[dict] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, pg in enumerate(pdf.pages):
            text = normalize_text(pg.extract_text() or "")
            pages.append({"page": i + 1, "text": text})
            m = _WEIGHT_HDR.search(text)
            if m:
                org_class, org_subtype = m.group(1), m.group(2)
                for tbl in pg.extract_tables() or []:
                    parsed = _parse_weight_table(tbl, org_class, org_subtype)
                    if parsed:
                        parsed["page"] = i + 1
                        weight_tables.append(parsed)
    sample = pages[0]["text"] if pages else ""
    doc_meta = {**guess_meta(path, sample), **(meta or {})}
    return {
        **doc_meta,
        "source_file": path.name,
        "page_count": len(pages),
        "weight_tables": weight_tables,
        "indicator_details": parse_indicator_details(pages),
        "chunks": chunk_pages(pages),
    }
