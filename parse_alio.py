"""ALIO 공시 보고서 fragment(doc.html) → long-format 레코드 파서.

출력 스키마 (작업지시서 확정):
    apba_id, org_name, item_no, item_name, section, sub_account, row_label,
    year, value_type(결산/예산), value, unit, as_of, source_url

sub_account: 기금 하위계정명(예: 신용보증기금). 다계정 기관의 재무·손익 표 구분용.

페이지 구조 규칙:
- 보고서 제목      : p.cover-title > a (예: "10. 임원 연봉")
- 기준시점/기관명   : table.nb (테두리 없는 라벨용 표)
- 섹션 제목        : 굵은 글씨(font-weight: bold) td 또는 p.SECTION-* > a
- 단위            : "(단위: X)" 텍스트
- 데이터 표        : table[border=1] — thead '구분' + "YYYY년 결산/예산" 헤더
- "해당사항 없음"   : 섹션 라벨 뒤 table.nb 단일 셀

수치 변환 규칙 (협상 불가):
- 쉼표 제거 후 숫자화
- '-'·빈값 → 빈칸 (0 아님)
- "해당사항 없음" → row_label로 별도 기록
- 그 외 텍스트 값(예: "연봉제")은 원문 그대로 보존
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent

FIELDS = [
    "apba_id", "org_name", "item_no", "item_name", "section", "sub_account",
    "row_label", "year", "value_type", "value", "unit", "as_of", "source_url",
]

FUND_ACCOUNT_RE = re.compile(r"(?:기금계정\s*:\s*|\[기금계정\]\s*)([^(\n]+)")

YEAR_HEADER_RE = re.compile(r"(\d{4})\s*년\s*(결산|예산|반기|분기)?")
UNIT_RE = re.compile(r"\(단위\s*[::]\s*([^)]+)\)")
AS_OF_RE = re.compile(r"\((\d{4}년\s*\d\s*/\s*\d\s*분기)\)")
NUMBER_RE = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
TITLE_PREFIX_RE = re.compile(r"^\d+(?:-\d+)?\.\s*")

SOURCE_URL_TPL = (
    "https://www.alio.go.kr/item/itemReportTerm.do"
    "?apbaId={apba_id}&reportFormRootNo={item_no}&disclosureNo="
)

DEFAULT_CSV = ROOT / "data" / "crawl" / "alio_records.csv"
DEFAULT_JSON = ROOT / "data" / "crawl" / "alio_records.json"


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_fund_account(text: str) -> str:
    m = FUND_ACCOUNT_RE.search(text)
    return clean_text(m.group(1)) if m else ""


def parse_value(raw: str) -> str | int | float:
    """쉼표 제거 후 숫자화. '-'·빈값은 빈칸(0 아님), 텍스트는 원문 보존."""
    t = clean_text(raw)
    if t in ("", "-", "–", "—"):
        return ""
    plain = t.replace(",", "")
    if NUMBER_RE.match(plain):
        return float(plain) if "." in plain else int(plain)
    return t  # 텍스트 값 (예: "연봉제") 원문 보존


def _is_bold(td: Tag) -> bool:
    return "font-weight" in (td.get("style") or "") and "bold" in (td.get("style") or "")


def expand_rows(trs: list[Tag]) -> list[list[Tag | None]]:
    """rowspan/colspan을 전개해 각 행을 동일 길이 셀 그리드로 변환.

    병합 셀은 원본 Tag를 해당 좌표 전체에 복제한다 (계층형 '구분' 열 대응).
    """
    grid: dict[tuple[int, int], Tag] = {}
    for r, tr in enumerate(trs):
        c = 0
        for cell in tr.find_all(["td", "th"], recursive=False):
            while (r, c) in grid:
                c += 1
            rs = int(cell.get("rowspan") or 1)
            cs = int(cell.get("colspan") or 1)
            for dr in range(rs):
                for dc in range(cs):
                    grid[(r + dr, c + dc)] = cell
            c += cs
    if not grid:
        return []
    n_rows = max(r for r, _ in grid) + 1
    n_cols = max(c for _, c in grid) + 1
    return [[grid.get((r, c)) for c in range(n_cols)] for r in range(n_rows)]


def _has_table_ancestor(el: Tag) -> bool:
    return el.find_parent("table") is not None


def parse_doc(html: str, apba_id: str, item_no: str, org_name: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []

    item_name = ""
    title = soup.find("p", class_="cover-title")
    if title:
        item_name = TITLE_PREFIX_RE.sub("", clean_text(title.get_text()))

    base = {
        "apba_id": apba_id,
        "org_name": org_name,
        "item_no": item_no,
        "item_name": item_name,
        "source_url": SOURCE_URL_TPL.format(apba_id=apba_id, item_no=item_no),
    }

    as_of = ""
    section = ""
    sub_account = ""
    unit = ""

    for el in soup.find_all(["p", "table"]):
        if el.name == "table" and _has_table_ancestor(el):
            continue  # 중첩 표는 부모 표 처리 시 함께 다룸

        if el.name == "p":
            a = el.find("a", class_="toc")
            if a and "SECTION" in " ".join(el.get("class") or []):
                section = clean_text(a.get_text())
                sub_account = ""
            continue

        classes = el.get("class") or []

        # ── 라벨용 표 (table.nb) ──
        if "nb" in classes:
            text = clean_text(el.get_text())
            if not text:
                continue
            if not as_of:
                m = AS_OF_RE.search(text)
                if m:
                    as_of = clean_text(m.group(1))
                    continue
            m = UNIT_RE.search(text)
            if m:
                unit = clean_text(m.group(1))
            acct = extract_fund_account(text)
            if acct:
                sub_account = acct
            elif "[고유사업]" in text:
                sub_account = ""
            bold_tds = [td for td in el.find_all("td") if _is_bold(td)]
            if bold_tds:
                section = clean_text(bold_tds[0].get_text())
                if not acct:
                    sub_account = ""
                continue
            if text.replace(" ", "") == "해당사항없음":
                records.append({**base, "section": section, "sub_account": sub_account,
                                "row_label": "해당사항 없음",
                                "year": "", "value_type": "", "value": "",
                                "unit": "", "as_of": as_of})
            continue

        # ── 데이터 표 (table[border=1]) ──
        if el.get("border") != "1":
            continue
        thead = el.find("thead")
        if not thead:
            continue
        head_grid = expand_rows(thead.find_all("tr", recursive=False))
        if not head_grid:
            continue
        # 헤더 그리드의 열별 텍스트 (다단 헤더는 행 텍스트를 합침)
        n_cols = len(head_grid[0])
        col_texts = []
        for c in range(n_cols):
            parts = []
            for row in head_grid:
                cell = row[c]
                t = clean_text(cell.get_text()) if cell is not None else ""
                if t and t not in parts:
                    parts.append(t)
            col_texts.append(" ".join(parts))
        if not col_texts or "구분" not in col_texts[0]:
            continue
        year_cols: list[tuple[int, str, str]] = []  # (col_idx, year, value_type)
        for i, h in enumerate(col_texts[1:], start=1):
            m = YEAR_HEADER_RE.search(h)
            if m:
                year_cols.append((i, m.group(1), m.group(2) or ""))
        if not year_cols:
            continue  # 연도 헤더 없는 표(담당자 등)는 데이터 표 아님
        label_width = min(i for i, _, _ in year_cols)  # 연도 열 앞은 전부 라벨('구분') 열

        tbody = el.find("tbody") or el
        for row in expand_rows(tbody.find_all("tr", recursive=False)):
            cells_in_row = [c for c in row if c is not None]
            if not cells_in_row:
                continue
            if any(c.find("a") for c in cells_in_row):
                continue  # 첨부파일 링크 행 등 제외
            # 계층형 '구분'은 라벨 열들을 " > "로 연결 (중복·각주 표시 제거)
            label_parts: list[str] = []
            for c in range(min(label_width, len(row))):
                cell = row[c]
                t = re.sub(r"\s*\*+$", "", clean_text(cell.get_text())) if cell is not None else ""
                if t and (not label_parts or t != label_parts[-1]):
                    label_parts.append(t)
            row_label = " > ".join(label_parts)
            if not row_label:
                continue
            for col_idx, year, vtype in year_cols:
                if col_idx >= len(row) or row[col_idx] is None:
                    continue
                records.append({**base, "section": section, "sub_account": sub_account,
                                "row_label": row_label,
                                "year": year, "value_type": vtype,
                                "value": parse_value(row[col_idx].get_text()),
                                "unit": unit, "as_of": as_of})

    return records


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def write_records_json(records: list[dict], out_json: Path, *, source_csv: Path, raw_dir: Path) -> None:
    """크롤 파싱 레코드를 MCP/후속 빌드가 읽기 쉬운 JSON 데이터셋으로 저장."""
    item_counts = Counter(str(r.get("item_no", "")) for r in records)
    org_counts = Counter(str(r.get("apba_id", "")) for r in records)
    payload = {
        "_meta": {
            "dataset": "alio_crawl_records",
            "source_type": "alio_html_crawl_parse",
            "raw_source_dir": _rel(raw_dir),
            "source_csv": _rel(source_csv),
            "schema": FIELDS,
            "record_count": len(records),
            "org_count": len(org_counts),
            "item_counts": dict(sorted(item_counts.items())),
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "caveats": [
                "rawdata/html의 ALIO doc.html fragment를 파싱한 long-format 데이터",
                "동일 키에 빈값과 숫자 또는 다중 표 값이 공존할 수 있어 metrics 병합 시 dedupe 정책 필요",
            ],
        },
        "records": records,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def parse_all(raw_dir: Path, out_csv: Path, json_out: Path | None = None) -> list[dict]:
    inst = json.loads((ROOT / "data" / "institutions.json").read_text(encoding="utf-8"))
    org_names = {o["org_code"]: o["name"] for o in inst["orgs"]}

    all_records: list[dict] = []
    summary: dict[str, int] = {}
    docs = sorted(raw_dir.glob("*__doc.html"))
    if not docs:
        print(f"[!] {raw_dir} 에 *__doc.html 없음 — 먼저 crawl 실행")
        return []

    for path in docs:
        stem = path.name[: -len("__doc.html")]
        apba_id, _, item_no = stem.rpartition("_")
        recs = parse_doc(path.read_text(encoding="utf-8"),
                         apba_id, item_no, org_names.get(apba_id, ""))
        summary[stem] = len(recs)
        all_records.extend(recs)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:  # 엑셀 한글 호환
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_records)

    print(f"파싱 완료: 파일 {len(docs)}개 → 레코드 {len(all_records)}건 → {out_csv}")
    if json_out:
        write_records_json(all_records, json_out, source_csv=out_csv, raw_dir=raw_dir)
        print(f"JSON 저장: {json_out}")
    print("기관×항목별 레코드 수 (0건 = 점검 대상):")
    for stem, n in sorted(summary.items()):
        flag = "  [WARN]" if n == 0 else ""
        print(f"  {stem}: {n}{flag}")
    return all_records


if __name__ == "__main__":
    parse_all(ROOT / "rawdata" / "html", DEFAULT_CSV, json_out=DEFAULT_JSON)
