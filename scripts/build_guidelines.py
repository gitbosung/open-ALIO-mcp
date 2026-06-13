# -*- coding: utf-8 -*-
"""지침 파일(HWPX·PDF) → 조문 단위 JSON 빌드.

law.go.kr에 등재되지 않는 연도별 시달 지침(예산운용지침·경영평가편람 등)을
rawdata/guidelines/에 넣고 실행하면 data/guidelines/{slug}.json + _index.json을 생성한다.

지원 포맷:
- .hwpx — zip+XML, 표준 라이브러리로 파싱
- .pdf  — pypdf
- .hwp  — 미지원: 한글에서 '다른 이름으로 저장 → HWPX'로 변환 후 재투입

메타데이터(권장): rawdata/guidelines/_manifest.json
    {"파일명.hwpx": {"title": "...", "year": 2026, "issuer": "기획재정부", "effective_date": "2026-01-01"}}
manifest가 없으면 파일명에서 제목·연도를 추정한다.

사용법:
    .venv\\Scripts\\python scripts\\build_guidelines.py
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "rawdata" / "guidelines"
OUT_DIR = ROOT / "data" / "guidelines"
MANIFEST_PATH = SRC_DIR / "_manifest.json"

# 조문 시작: "제1조(목적)" / "제 12 조의2 (정의)" 등 — 행 머리에서만 매칭
ARTICLE_RE = re.compile(r"^제\s*(\d+)\s*조(?:의\s*(\d+))?\s*(?:\(([^)]*)\)|【([^】]*)】)?")
CHAPTER_RE = re.compile(r"^제\s*\d+\s*[장절관]\s*\S")
ROMAN_HEAD_RE = re.compile(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*(.+)$")
NUM_SECTION_RE = re.compile(r"^(\d+)\.\s+(\S.{0,60})$")
SUB_SECTION_RE = re.compile(r"^\((\d+)\)\s+(\S.{0,60})$")


def extract_hwpx(path: Path) -> str:
    """HWPX(zip+XML)에서 문단 텍스트 추출 — Contents/section*.xml의 <t> 요소."""
    lines: list[str] = []
    with zipfile.ZipFile(path) as zf:
        sections = sorted(n for n in zf.namelist() if re.match(r"Contents/section\d+\.xml$", n))
        if not sections:
            raise ValueError("Contents/section*.xml 없음 — HWPX 파일이 맞는지 확인")
        for name in sections:
            root = ElementTree.fromstring(zf.read(name))
            for p in root.iter():
                if p.tag.split("}")[-1] != "p":  # 문단 단위
                    continue
                texts = [t.text for t in p.iter() if t.tag.split("}")[-1] == "t" and t.text]
                line = "".join(texts).strip()
                if line:
                    lines.append(line)
    return "\n".join(lines)


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("pypdf 필요: .venv\\Scripts\\pip install pypdf")
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages)


def chunk_articles(text: str) -> tuple[list[dict], str]:
    """본문을 조문 단위로 분할. 반환: (조문 목록, 첫 조문 이전의 머리말)."""
    lines = text.splitlines()
    articles: list[dict] = []
    preamble: list[str] = []
    current: dict | None = None
    chapter = ""

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if CHAPTER_RE.match(line):
            chapter = line
            continue
        m = ARTICLE_RE.match(line)
        if m:
            no, sub, title = m.group(1), m.group(2), (m.group(3) or m.group(4) or "")
            key = f"{no}의{sub}" if sub else no
            current = {"article": key, "title": title.strip(), "chapter": chapter, "lines": [line]}
            articles.append(current)
        elif current is not None:
            current["lines"].append(line)
        else:
            preamble.append(line)

    for a in articles:
        a["text"] = "\n".join(a.pop("lines"))
    return articles, "\n".join(preamble)


def chunk_sections(text: str) -> tuple[list[dict], str]:
    """제n조가 없는 지침(예산운용지침 등) — 로마숫자·번호·(n) 목차로 분할."""
    lines = text.splitlines()
    articles: list[dict] = []
    preamble: list[str] = []
    current: dict | None = None
    chapter = ""
    sec_no = 0

    for raw in lines:
        line = raw.strip()
        if not line or re.fullmatch(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+", line):
            continue

        m_roman = ROMAN_HEAD_RE.match(line)
        if m_roman and len(m_roman.group(2)) >= 3:
            chapter = line
            sec_no += 1
            current = {"article": f"R{sec_no}", "title": m_roman.group(2).strip(),
                       "chapter": chapter, "lines": [line]}
            articles.append(current)
            continue

        m_sub = SUB_SECTION_RE.match(line)
        if m_sub:
            parent = current["article"] if current else "S"
            current = {"article": f"{parent}-{m_sub.group(1)}", "title": m_sub.group(2).strip(),
                       "chapter": chapter, "lines": [line]}
            articles.append(current)
            continue

        m_num = NUM_SECTION_RE.match(line)
        if m_num:
            sec_no += 1
            current = {"article": f"S{sec_no}", "title": m_num.group(2).strip(),
                       "chapter": chapter, "lines": [line]}
            articles.append(current)
            continue

        if current is not None:
            current["lines"].append(line)
        else:
            preamble.append(line)

    for a in articles:
        a["text"] = "\n".join(a.pop("lines"))
    return articles, "\n".join(preamble)


def guess_meta(path: Path, text: str) -> dict:
    """manifest 미기재 시 파일명·본문에서 제목·연도 추정."""
    stem = path.stem
    year = None
    m = re.search(r"(20\d{2})", stem) or re.search(r"(20\d{2})\s*년도?", text[:500])
    if m:
        year = int(m.group(1))
    return {"title": re.sub(r"[_\-]+", " ", stem).strip(), "year": year, "issuer": None, "effective_date": None}


def slugify(name: str) -> str:
    s = re.sub(r"\.(hwpx|pdf)$", "", name, flags=re.I)
    s = re.sub(r"[^\w가-힣]+", "_", s).strip("_")
    return s or "guideline"


def main() -> None:
    if not SRC_DIR.exists():
        SRC_DIR.mkdir(parents=True)
        print(f"[안내] {SRC_DIR} 생성 — 지침 파일(.hwpx/.pdf)을 넣고 다시 실행하세요.")
        return

    manifest: dict = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    files = sorted(p for p in SRC_DIR.iterdir() if p.suffix.lower() in (".hwpx", ".pdf", ".hwp"))
    if not files:
        print(f"[안내] {SRC_DIR}에 지침 파일이 없습니다 (.hwpx/.pdf).")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    skipped: list[str] = []

    for path in files:
        if path.suffix.lower() == ".hwp":
            skipped.append(path.name)
            print(f"[건너뜀] {path.name} — 구형 HWP 미지원. 한글에서 HWPX로 변환 후 재투입하세요.")
            continue
        try:
            text = extract_hwpx(path) if path.suffix.lower() == ".hwpx" else extract_pdf(path)
        except Exception as e:  # noqa: BLE001 — 파일별 실패는 기록하고 계속
            skipped.append(path.name)
            print(f"[실패] {path.name}: {e}")
            continue

        articles, preamble = chunk_articles(text)
        chunk_mode = "articles"
        if not articles:
            articles, preamble = chunk_sections(text)
            chunk_mode = "sections"

        meta = {**guess_meta(path, text), **(manifest.get(path.name) or {})}
        doc_id = slugify(path.name)

        doc = {
            "doc_id": doc_id,
            "title": meta["title"],
            "year": meta["year"],
            "issuer": meta["issuer"],
            "effective_date": meta["effective_date"],
            "source_file": path.name,
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "chunk_mode": chunk_mode,
            "article_count": len(articles),
            "preamble": preamble[:2000] or None,
            "articles": articles,
        }
        (OUT_DIR / f"{doc_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        index.append({k: doc[k] for k in
                      ("doc_id", "title", "year", "issuer", "effective_date", "source_file", "article_count")})
        warn = "" if articles else "  ⚠ 조문·목차 패턴 미검출"
        mode_note = " (목차 분할)" if chunk_mode == "sections" else ""
        print(f"[완료] {path.name} → {doc_id}.json (청크 {len(articles)}개{mode_note}){warn}")

    (OUT_DIR / "_index.json").write_text(
        json.dumps({"built_at": datetime.now().isoformat(timespec="seconds"),
                    "docs": index, "skipped": skipped}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n총 {len(index)}건 적재, {len(skipped)}건 건너뜀 → {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
