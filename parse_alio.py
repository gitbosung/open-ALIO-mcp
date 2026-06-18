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
    "row_label", "col_label", "year", "value_type", "value", "unit", "as_of", "source_url",
]

# 표 archetype 분류·핸들러용 상수
CONTACT_HEADERS = {"담당자명", "부서명", "전화번호"}      # 공시 담당자 표 (데이터 아님)
ATTACH_HEADERS = {"첨부파일", "집행상세내역", "집행 상세내역"}  # 첨부/링크 전용 열
YEAR_CELL_RE = re.compile(r"\d{4}\s*년")                 # body 셀이 연도인지 (row_year 판정)
PAREN_LABEL_RE = re.compile(r"^\([^)]*\)$")              # 통째로 괄호인 자식행 라벨 (예: (남성))

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


def _grid_col_texts(head_grid: list[list[Tag | None]]) -> list[str]:
    """헤더 그리드 → 열별 병합 텍스트 (다단 헤더는 행 텍스트를 합침)."""
    if not head_grid:
        return []
    n_cols = len(head_grid[0])
    col_texts: list[str] = []
    for c in range(n_cols):
        parts: list[str] = []
        for row in head_grid:
            cell = row[c] if c < len(row) else None
            t = clean_text(cell.get_text()) if cell is not None else ""
            if t and t not in parts:
                parts.append(t)
        col_texts.append(" ".join(parts))
    return col_texts


def _expand_head_body(el: Tag) -> tuple[list, list]:
    """border=1 표를 (헤더 그리드, body 그리드)로 전개. thead 없으면 헤더는 []."""
    thead = el.find("thead")
    head_grid = expand_rows(thead.find_all("tr", recursive=False)) if thead else []
    body_container = el.find("tbody") or el
    body_grid = expand_rows(body_container.find_all("tr", recursive=False))
    return head_grid, body_grid


def _year_cols(col_texts: list[str]) -> list[int]:
    return [i for i, h in enumerate(col_texts[1:], start=1) if YEAR_HEADER_RE.search(h)]


def _classify_table(col_texts: list[str], data_grid: list, *, header_known: bool) -> str:
    """border=1 표를 col_year | row_year | attr_roster | skip 로 분류 (first-match).

    header_known=False(=thead 없음)이면 col_year/row_year 시그니처가 명확할 때만 채택
    (attr_roster·메타·서술 표 오분류 방지).
    """
    if not col_texts:
        return "skip"
    h0 = col_texts[0]
    if h0.startswith("기준일"):
        return "skip"  # 기준일/제출일 메타 표
    yc = _year_cols(col_texts)
    others = {col_texts[i] for i in range(1, len(col_texts)) if col_texts[i]}
    if "구분" in h0 and not yc and others and others <= CONTACT_HEADERS:
        return "skip"  # 공시 담당자 표
    if "구분" in h0 and yc:
        return "col_year"  # '사업구분'도 매칭
    # 첫 열이 연도인 행들 수집 (row_year 판정)
    year_vals = [clean_text(row[0].get_text()) for row in data_grid
                 if row and row[0] is not None and YEAR_CELL_RE.search(clean_text(row[0].get_text()))]
    distinct = set(year_vals)
    if h0 in ("연도", "년도") or len(year_vals) >= 2:
        # 진짜 transpose는 연도가 distinct·행당 1개. 단일 연도가 여러 행 반복되면
        # (예: 복리후생비 경조비 상세) 다차원 명부표 → 가비지 캡처 방지 위해 skip.
        if len(distinct) >= 2 and len(distinct) >= 0.9 * len(year_vals):
            return "row_year"
        return "skip"
    if header_known and len(col_texts) >= 2 and not yc:
        # 깨끗한 로스터만 채택: 속성(비-첨부) 헤더가 모두 distinct해야 함.
        # 헤더가 중복되는 다차원 그리드(예: 휴가구분|휴가구분|휴가구분)는 같은 col_label
        # 충돌을 만들므로 skip(연기).
        attrs = [col_texts[i] for i in range(1, len(col_texts))
                 if col_texts[i] and col_texts[i] not in ATTACH_HEADERS]
        if attrs and len(set(attrs)) == len(attrs):
            return "attr_roster"
        return "skip"
    return "skip"


def _row_label_path(row: list, width: int) -> str:
    """선두 width개 라벨 열을 ' > '로 연결 (중복·각주 표시 제거)."""
    parts: list[str] = []
    for c in range(min(width, len(row))):
        cell = row[c]
        t = re.sub(r"\s*\*+$", "", clean_text(cell.get_text())) if cell is not None else ""
        if t and (not parts or t != parts[-1]):
            parts.append(t)
    return " > ".join(parts)


def _handle_col_year(col_texts: list[str], data_grid: list, ctx: dict) -> list[dict]:
    """구분 + YYYY년 컬럼 wide표 → long. 첨부 anchor는 셀 단위로만 스킵(행 보존)."""
    out: list[dict] = []
    cols = []  # (col_idx, year, value_type, header_text)
    for i, h in enumerate(col_texts[1:], start=1):
        m = YEAR_HEADER_RE.search(h)
        if m:
            cols.append((i, m.group(1), m.group(2) or "", h))
    if not cols:
        return out
    label_width = min(i for i, *_ in cols)  # 연도 열 앞은 전부 라벨('구분') 열
    last_parent = ""  # 단일 라벨열 표에서 괄호 자식행((남성) 등)이 상속할 직전 부모행
    for row in data_grid:
        if not any(c is not None for c in row):
            continue
        row_label = _row_label_path(row, label_width)
        if not row_label:
            continue
        # 평면행 부모-컨텍스트: 단일 라벨열 표에서 라벨이 통째로 괄호인 자식행은
        # 직전 비괄호 부모행으로 prefix (예: '1인당 평균 보수액 > (남성)' vs '상시 종업원수 > (남성)').
        if label_width == 1:
            if PAREN_LABEL_RE.match(row_label):
                if last_parent:
                    row_label = f"{last_parent} > {row_label}"
            else:
                last_parent = row_label
        for col_idx, year, vtype, htext in cols:
            cell = row[col_idx] if col_idx < len(row) else None
            if cell is None or cell.find("a"):
                continue  # 빈 좌표 또는 첨부 링크 셀만 스킵
            out.append({**ctx, "row_label": row_label, "col_label": htext,
                        "year": year, "value_type": vtype,
                        "value": parse_value(cell.get_text())})
    return out


def _handle_row_year(col_texts: list[str], data_grid: list, ctx: dict) -> list[dict]:
    """연도가 행, 지표가 컬럼인 transposed표 → long (year=행 연도, col_label=지표 헤더)."""
    out: list[dict] = []
    metric_cols = [(i, col_texts[i]) for i in range(1, len(col_texts))
                   if col_texts[i] and col_texts[i] not in ATTACH_HEADERS]
    if not metric_cols:
        return out
    for row in data_grid:
        if not row or row[0] is None:
            continue
        ym = YEAR_HEADER_RE.search(clean_text(row[0].get_text()))
        if not ym:
            continue
        year = ym.group(1)
        for col_idx, htext in metric_cols:
            cell = row[col_idx] if col_idx < len(row) else None
            if cell is None or cell.find("a"):
                continue
            out.append({**ctx, "row_label": "", "col_label": htext,
                        "year": year, "value_type": "",
                        "value": parse_value(cell.get_text())})
    return out


def _handle_attr_roster(col_texts: list[str], data_grid: list, ctx: dict) -> list[dict]:
    """비시계열 2D 속성/명부표 → long (row_label=행 키, col_label=속성 헤더, year='').

    하위표 직종/계정은 nb 섹션 상태(section)로 구분된다. 속성 헤더가 모두 distinct한
    깨끗한 로스터만 _classify_table에서 라우팅되며, 중복헤더 다차원 그리드는 skip된다.

    리스트/명부 표(col0가 rowspan 카테고리, 그 아래 여러 레코드: 자회사·담보 명부 등)는
    같은 행 키가 반복돼 충돌하므로, 표 내에서 반복되는 키에는 순번(#n)을 붙여 분리한다
    (무손실·무충돌; col0가 distinct한 주주명부 등은 그대로 유지).
    """
    attr_cols = [(i, col_texts[i]) for i in range(1, len(col_texts))
                 if col_texts[i] and col_texts[i] not in ATTACH_HEADERS]
    if not attr_cols:
        return []
    # 유효 행과 base 키 수집 (1차)
    rows_keys: list[tuple[list, str]] = []
    for row in data_grid:
        if not row or row[0] is None:
            continue
        key = re.sub(r"\s*\*+$", "", clean_text(row[0].get_text()))
        if key:
            rows_keys.append((row, key))
    total = Counter(k for _, k in rows_keys)
    seq: Counter = Counter()
    out: list[dict] = []
    for row, base in rows_keys:
        seq[base] += 1
        row_key = base if total[base] == 1 else f"{base} #{seq[base]}"
        for col_idx, htext in attr_cols:
            cell = row[col_idx] if col_idx < len(row) else None
            if cell is None or cell.find("a"):
                continue
            out.append({**ctx, "row_label": row_key, "col_label": htext,
                        "year": "", "value_type": "",
                        "value": parse_value(cell.get_text())})
    return out


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
                                "row_label": "해당사항 없음", "col_label": "",
                                "year": "", "value_type": "", "value": "",
                                "unit": "", "as_of": as_of})
            continue

        # ── 데이터 표 (table[border=1]) — archetype 분류 후 핸들러 디스패치 ──
        if el.get("border") != "1":
            continue
        head_grid, body_grid = _expand_head_body(el)
        if not body_grid:
            continue
        if head_grid:
            col_texts = _grid_col_texts(head_grid)
            data_grid = body_grid
        else:
            # thead 없음 — body 첫 행을 헤더 후보로 보고 시그니처가 맞을 때만 채택
            col_texts = _grid_col_texts([body_grid[0]])
            data_grid = body_grid[1:]
        kind = _classify_table(col_texts, data_grid, header_known=bool(head_grid))
        ctx = {**base, "section": section, "sub_account": sub_account,
               "unit": unit, "as_of": as_of}
        if kind == "col_year":
            records.extend(_handle_col_year(col_texts, data_grid, ctx))
        elif kind == "row_year":
            records.extend(_handle_row_year(col_texts, data_grid, ctx))
        elif kind == "attr_roster":
            records.extend(_handle_attr_roster(col_texts, data_grid, ctx))
        # 그 외(skip): 메타·담당자·중복헤더 다차원 그리드 등은 통과.

    # 동일 문서 내 완전 동일 레코드 제거 (반복 표·이중표가 만드는 무정보 중복 안전망)
    seen: set = set()
    deduped: list[dict] = []
    for r in records:
        k = (r["section"], r["sub_account"], r["row_label"], r["col_label"],
             r["year"], r["value_type"], str(r["value"]))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    return deduped


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
