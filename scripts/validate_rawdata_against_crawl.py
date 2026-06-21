# -*- coding: utf-8 -*-
"""Compare 2025 Q1 ALIO raw XLSX exports against parsed crawl CSV/JSON.

This is a broad audit script, not a promotion step.  It extracts all non-blank
value cells from every workbook under rawdata/validation, maps each workbook to
an ALIO item number, and compares those raw values with data/crawl/alio_records.

The comparison deliberately separates two questions:
1. value_presence: is the same non-zero value present for the same
   org/item/year/period anywhere in the parsed CSV?
2. structure_key: does the raw row/column shape map cleanly to the parsed
   section/sub_account/row_label/col_label shape?

Zero values are reported separately because a loose "0 exists somewhere" match
is not meaningful in ALIO tables with many zero cells.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import openpyxl

from validate_2025q1_rawdata import (  # reuse the item mapping already curated
    CRAWL_CSV,
    HTML_DIR,
    INSTITUTIONS,
    ROOT,
    VALIDATION_DIR,
    clean,
    header_row,
    mapped_item_for_file,
    to_num,
)

REPORT_DIR = ROOT / "data" / "validation_reports"
CRAWL_JSON = ROOT / "data" / "crawl" / "alio_records.json"
YEAR_RE = re.compile(r"(20\d{2})")
MONTH_RE = re.compile(r"^(\d{1,2})월$")

META_HEADERS = {"기관명", "기관유형", "주무부처", "상위기관"}
ROW_YEAR_HEADERS = {"연도", "년도"}
DIM_HEADERS = {
    "구분", "분류", "분류1", "분류2", "항목", "기금명", "고용형태", "상세내역",
    "사유", "지급사유", "휴가사유", "가산지급 사유", "공가구분", "대상자",
    "사업장구분", "사업장명", "회사구분", "법인명", "채무자", "관계", "채권자",
    "거래상대방", "회사와의관계", "거래종류", "거래기간", "주요사업", "설립일자",
    "임직원 구분", "퇴직 임직원", "직위(급)", "퇴직 회사", "징계처분일", "징계종류",
    "징계사유", "담보제공기간", "담보제공재산", "채무보증기간", "소요재원",
    "무상/유상", "항목구분", "년도",
}
VALUE_HEADER_HINTS = (
    "금액", "수", "건", "비율", "세액", "과세표준", "잔액", "자본금", "지분율",
    "정원", "현원", "인원", "등급", "여부", "명단", "기간", "일수", "기준",
    "규정", "첨부", "파일", "비고", "대상", "결과", "운영", "사용량", "발생량",
    "취득가액", "장부가액", "평가액", "순이익", "매출", "기본재산",
)


@dataclass
class RawRecord:
    file: str
    item_no: str | None
    org_name: str
    org_code: str | None
    year: str
    period: str
    raw_key: str
    value: int | float | str
    value_kind: str
    sheet: str
    row: int
    column: str


def load_name_to_code() -> dict[str, str]:
    data = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    return {org["name"]: org["org_code"] for org in data["orgs"] if org.get("org_code")}


def norm_text(value: object) -> str:
    text = clean(value)
    text = text.replace("∙", "·")
    text = re.sub(r"\([^)]*A[+/][^)]*\)", "", text)
    text = re.sub(r"\([A-Z/]+\)", "", text)
    text = re.sub(r"\s+", "", text)
    text = text.replace("일반정규직", "일반").replace("무기계약직", "무기")
    text = text.replace("급여성복리후생비", "급여성").replace("비급여성복리후생비", "비급여성")
    text = text.replace("법인세산출세액", "법인세산출세액")
    return text


def norm_value(value: object) -> tuple[str, object]:
    num = to_num(value)
    if num is not None:
        return ("num", num)
    return ("text", norm_text(value))


def value_kind(value: object) -> str:
    num = to_num(value)
    if num is None:
        return "text"
    return "zero" if float(num) == 0 else "nonzero"


def is_blank_like(value: object) -> bool:
    return clean(value) in {"", "-", "–", "—", "해당사항 없음"}


def period_from_header(header: str) -> tuple[str, str, str]:
    """Return (year, period, axis_label) from a header."""
    h = clean(header)
    year_match = YEAR_RE.search(h)
    year = year_match.group(1) if year_match else ""
    if "1/4" in h or "분기" in h:
        period = "quarter"
    elif "반기" in h:
        period = "half"
    elif "예산" in h:
        period = "budget"
    elif MONTH_RE.match(h):
        period = "month"
    else:
        period = "annual"
    axis = h
    if year:
        axis = YEAR_RE.sub("", axis)
    axis = axis.replace("년", "").replace("결산", "").replace("예산", "")
    axis = axis.replace("반기", "").replace("1/4분기", "").replace("(1/4분기)", "")
    axis = axis.replace("합계 :", "").strip(" -:/()")
    return year, period, clean(axis)


def period_from_parsed(row: dict[str, str]) -> str:
    text = " ".join([row.get("value_type", ""), row.get("col_label", "")])
    if "1/4" in text or "분기" in text:
        return "quarter"
    if "반기" in text:
        return "half"
    if "예산" in text:
        return "budget"
    return "annual"


def is_year_header(header: str) -> bool:
    return bool(YEAR_RE.search(clean(header)) or MONTH_RE.match(clean(header)))


def is_value_header(header: str) -> bool:
    h = clean(header)
    if h in META_HEADERS or h in ROW_YEAR_HEADERS:
        return False
    if h in DIM_HEADERS:
        return False
    return any(token in h for token in VALUE_HEADER_HINTS)


def make_raw_key(parts: Iterable[object]) -> str:
    cleaned = [clean(p) for p in parts if clean(p) and clean(p) not in {"-", "해당사항 없음"}]
    return " | ".join(cleaned) if cleaned else "값"


def extract_raw_records(name_to_code: dict[str, str]) -> tuple[list[RawRecord], Counter]:
    records: list[RawRecord] = []
    counters: Counter = Counter()
    for path in sorted(VALIDATION_DIR.rglob("*.xlsx")):
        item_no = mapped_item_for_file(path.name)
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            for ws in wb.worksheets:
                hdr = header_row(ws)
                if not hdr:
                    counters["sheets_without_org_header"] += 1
                    continue
                hdr_row, headers = hdr
                headers = [clean(h) for h in headers]
                org_idx = headers.index("기관명")
                year_header_idxs = [i for i, h in enumerate(headers) if is_year_header(h)]
                row_year_idxs = [i for i, h in enumerate(headers) if h in ROW_YEAR_HEADERS]
                for excel_row_no, row in enumerate(
                    ws.iter_rows(min_row=hdr_row + 1, values_only=True),
                    start=hdr_row + 1,
                ):
                    org_name = clean(row[org_idx] if org_idx < len(row) else "")
                    if not org_name:
                        continue
                    org_code = name_to_code.get(org_name)
                    if not org_code:
                        counters["unmatched_org_rows"] += 1

                    if year_header_idxs:
                        dim_parts = [
                            row[i] if i < len(row) else None
                            for i, h in enumerate(headers)
                            if h not in META_HEADERS and i not in year_header_idxs
                        ]
                        base_key = make_raw_key(dim_parts)
                        for i in year_header_idxs:
                            header = headers[i]
                            year, period, axis = period_from_header(header)
                            raw_value = row[i] if i < len(row) else None
                            if is_blank_like(raw_value):
                                counters["blank_like_cells"] += 1
                                continue
                            raw_key = make_raw_key([base_key, axis])
                            val = to_num(raw_value)
                            value = val if val is not None else clean(raw_value)
                            records.append(RawRecord(
                                file=path.name,
                                item_no=item_no,
                                org_name=org_name,
                                org_code=org_code,
                                year=year,
                                period=period,
                                raw_key=raw_key,
                                value=value,
                                value_kind=value_kind(value),
                                sheet=ws.title,
                                row=excel_row_no,
                                column=header,
                            ))
                        continue

                    if row_year_idxs:
                        year_idx = row_year_idxs[0]
                        year_text = clean(row[year_idx] if year_idx < len(row) else "")
                        ym = YEAR_RE.search(year_text)
                        year = ym.group(1) if ym else ""
                        dim_parts = [
                            row[i] if i < len(row) else None
                            for i, h in enumerate(headers)
                            if h not in META_HEADERS and h not in ROW_YEAR_HEADERS and h in DIM_HEADERS
                        ]
                        value_idxs = [
                            i for i, h in enumerate(headers)
                            if h not in META_HEADERS and h not in ROW_YEAR_HEADERS and h not in DIM_HEADERS
                        ]
                        for i in value_idxs:
                            header = headers[i]
                            raw_value = row[i] if i < len(row) else None
                            if is_blank_like(raw_value):
                                counters["blank_like_cells"] += 1
                                continue
                            val = to_num(raw_value)
                            value = val if val is not None else clean(raw_value)
                            records.append(RawRecord(
                                file=path.name,
                                item_no=item_no,
                                org_name=org_name,
                                org_code=org_code,
                                year=year,
                                period="annual",
                                raw_key=make_raw_key([*dim_parts, header]),
                                value=value,
                                value_kind=value_kind(value),
                                sheet=ws.title,
                                row=excel_row_no,
                                column=header,
                            ))
                        continue

                    value_idxs = [
                        i for i, h in enumerate(headers)
                        if h not in META_HEADERS and is_value_header(h)
                    ]
                    dim_parts = [
                        row[i] if i < len(row) else None
                        for i, h in enumerate(headers)
                        if h not in META_HEADERS and i not in value_idxs
                    ]
                    for i in value_idxs:
                        header = headers[i]
                        raw_value = row[i] if i < len(row) else None
                        if is_blank_like(raw_value):
                            counters["blank_like_cells"] += 1
                            continue
                        val = to_num(raw_value)
                        value = val if val is not None else clean(raw_value)
                        records.append(RawRecord(
                            file=path.name,
                            item_no=item_no,
                            org_name=org_name,
                            org_code=org_code,
                            year="",
                            period="attribute",
                            raw_key=make_raw_key([*dim_parts, header]),
                            value=value,
                            value_kind=value_kind(value),
                            sheet=ws.title,
                            row=excel_row_no,
                            column=header,
                        ))
        finally:
            wb.close()
    return records, counters


def parsed_key(row: dict[str, str]) -> str:
    col = clean(row.get("col_label"))
    year = row.get("year", "")
    col_axis = col
    if year:
        col_axis = YEAR_RE.sub("", col_axis)
    col_axis = col_axis.replace("년", "").replace("결산", "").replace("예산", "")
    col_axis = col_axis.replace("반기", "").replace("1/4분기", "").replace("(1/4분기)", "")
    col_axis = col_axis.strip(" -:/()")
    return make_raw_key([
        re.sub(r"^\d+[-.)]?\s*", "", clean(row.get("section"))),
        row.get("sub_account", ""),
        row.get("row_label", ""),
        col_axis,
    ])


def build_parsed_indexes() -> tuple[dict, dict, dict, dict, Counter]:
    loose: dict[tuple, int] = Counter()
    keyed: dict[tuple, int] = Counter()
    item_years: dict[str, set[tuple[str, str]]] = defaultdict(set)
    item_orgs: dict[str, set[str]] = defaultdict(set)
    item_counts: Counter = Counter()

    with CRAWL_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item = row["item_no"]
            item_counts[item] += 1
            item_orgs[item].add(row["apba_id"])
            period = period_from_parsed(row)
            year = row.get("year", "")
            item_years[item].add((year, period))
            if is_blank_like(row.get("value")):
                continue
            kind, value = norm_value(row.get("value"))
            base = (row["apba_id"], item, year, period, kind, value)
            loose[base] += 1
            keyed[(*base, norm_text(parsed_key(row)))] += 1
    return loose, keyed, item_years, item_orgs, item_counts


def html_doc_counts() -> Counter:
    counts: Counter = Counter()
    for path in HTML_DIR.glob("*__doc.html"):
        parts = path.name.split("_")
        if len(parts) > 1:
            counts[parts[1]] += 1
    return counts


def json_meta_summary() -> dict:
    if not CRAWL_JSON.exists():
        return {"exists": False}
    prefix = CRAWL_JSON.open(encoding="utf-8").read(50000)
    record_match = re.search(r'"record_count"\s*:\s*(\d+)', prefix)
    built_match = re.search(r'"built_at"\s*:\s*"([^"]+)"', prefix)
    return {
        "exists": True,
        "record_count_meta": int(record_match.group(1)) if record_match else None,
        "built_at": built_match.group(1) if built_match else None,
        "file_size": CRAWL_JSON.stat().st_size,
    }


def comparable_period(record: RawRecord, item_years: dict[str, set[tuple[str, str]]]) -> bool:
    if not record.item_no:
        return False
    if record.period in {"quarter", "month", "budget"}:
        return (record.year, record.period) in item_years.get(record.item_no, set())
    if record.period == "attribute":
        return ("", "annual") in item_years.get(record.item_no, set()) or ("", "attribute") in item_years.get(record.item_no, set())
    return (record.year, record.period) in item_years.get(record.item_no, set())


def compare(records: list[RawRecord]) -> dict:
    loose, keyed, item_years, item_orgs, parsed_counts = build_parsed_indexes()
    docs = html_doc_counts()
    file_stats: dict[str, Counter] = defaultdict(Counter)
    item_stats: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, list[dict]] = defaultdict(list)

    for rec in records:
        file_counter = file_stats[rec.file]
        item_counter = item_stats[rec.item_no or "(unmapped)"]
        for counter in (file_counter, item_counter):
            counter["raw_values"] += 1
            counter[f"raw_{rec.value_kind}"] += 1

        status = ""
        if not rec.item_no:
            status = "unmapped_file"
        elif rec.item_no not in parsed_counts:
            status = "item_not_in_parsed_csv"
        elif not rec.org_code:
            status = "unmatched_org"
        elif not comparable_period(rec, item_years):
            status = "period_not_comparable"
        else:
            kind, value = norm_value(rec.value)
            base = (rec.org_code, rec.item_no, rec.year, rec.period, kind, value)
            if rec.value_kind == "zero":
                # Loose zero matches are weak evidence; require key where possible.
                key = norm_text(rec.raw_key)
                if keyed.get((*base, key), 0):
                    status = "key_match_zero"
                elif loose.get(base, 0):
                    status = "loose_zero_only"
                else:
                    status = "missing_zero"
            else:
                if loose.get(base, 0):
                    status = "value_match"
                    key = norm_text(rec.raw_key)
                    if keyed.get((*base, key), 0):
                        status = "value_and_key_match"
                else:
                    status = "missing_or_changed_value"

        for counter in (file_counter, item_counter):
            counter[status] += 1
            if rec.item_no:
                counter["html_doc_count"] = docs.get(rec.item_no, 0)
                counter["parsed_csv_rows"] = parsed_counts.get(rec.item_no, 0)
                counter["parsed_org_count"] = len(item_orgs.get(rec.item_no, set()))

        if status in {
            "item_not_in_parsed_csv",
            "period_not_comparable",
            "missing_or_changed_value",
            "missing_zero",
            "loose_zero_only",
        } and len(samples[rec.file]) < 10:
            samples[rec.file].append({
                **asdict(rec),
                "status": status,
                "normalized_key": norm_text(rec.raw_key),
            })

    files = []
    for file, counter in sorted(file_stats.items()):
        raw_values = counter["raw_values"] or 1
        nonzero_compared = (
            counter["value_match"]
            + counter["value_and_key_match"]
            + counter["missing_or_changed_value"]
        )
        files.append({
            "file": file,
            "mapped_item_no": mapped_item_for_file(file),
            **dict(counter),
            "nonzero_value_match_rate": round(
                (counter["value_match"] + counter["value_and_key_match"]) / nonzero_compared,
                6,
            ) if nonzero_compared else None,
            "issue_rate": round(
                (counter["missing_or_changed_value"] + counter["missing_zero"] + counter["item_not_in_parsed_csv"]) / raw_values,
                6,
            ),
            "samples": samples[file],
        })

    items = []
    for item, counter in sorted(item_stats.items()):
        nonzero_compared = (
            counter["value_match"]
            + counter["value_and_key_match"]
            + counter["missing_or_changed_value"]
        )
        items.append({
            "item_no": item,
            **dict(counter),
            "nonzero_value_match_rate": round(
                (counter["value_match"] + counter["value_and_key_match"]) / nonzero_compared,
                6,
            ) if nonzero_compared else None,
        })

    return {
        "files": files,
        "items": items,
        "parsed_csv": {
            "rows": sum(parsed_counts.values()),
            "item_count": len(parsed_counts),
            "item_counts": dict(sorted(parsed_counts.items())),
        },
        "html_doc_counts": dict(sorted(docs.items())),
    }


def write_report(report: dict) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "rawdata_vs_crawl_full_audit.json"
    md_path = REPORT_DIR / "rawdata_vs_crawl_full_audit.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Rawdata vs Parsed Crawl Full Audit",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- raw_xlsx_files: {report['raw_extract']['xlsx_files']}",
        f"- raw_value_records: {report['raw_extract']['raw_value_records']:,}",
        f"- parsed_csv_rows: {report['comparison']['parsed_csv']['rows']:,}",
        f"- parsed_json_meta: {report['parsed_json_meta']}",
        "",
        "## Item Summary",
        "",
        "| item_no | raw_values | html_docs | parsed_rows | nonzero_match_rate | missing_or_changed | not_in_csv | period_not_comparable |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["comparison"]["items"]:
        rate = "" if item.get("nonzero_value_match_rate") is None else f"{item['nonzero_value_match_rate']:.2%}"
        lines.append(
            f"| {item['item_no']} | {item.get('raw_values', 0):,} | "
            f"{item.get('html_doc_count', 0):,} | {item.get('parsed_csv_rows', 0):,} | "
            f"{rate} | {item.get('missing_or_changed_value', 0):,} | "
            f"{item.get('item_not_in_parsed_csv', 0):,} | {item.get('period_not_comparable', 0):,} |"
        )

    lines.extend([
        "",
        "## File Summary",
        "",
        "| file | item_no | raw_values | nonzero_match_rate | missing_or_changed | not_in_csv | period_not_comparable |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for item in report["comparison"]["files"]:
        rate = "" if item.get("nonzero_value_match_rate") is None else f"{item['nonzero_value_match_rate']:.2%}"
        lines.append(
            f"| {item['file']} | {item.get('mapped_item_no') or ''} | {item.get('raw_values', 0):,} | "
            f"{rate} | {item.get('missing_or_changed_value', 0):,} | "
            f"{item.get('item_not_in_parsed_csv', 0):,} | {item.get('period_not_comparable', 0):,} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- `nonzero_match_rate` is based on same org/item/year/period non-zero values. It is strong evidence for numeric/text value preservation but does not prove the row axis is correct.",
        "- `period_not_comparable` mainly means the raw XLSX period is 2020, 2025 Q1, budget, monthly, or an uncrawled period while the parsed CSV currently comes from 2026 Q1 HTML.",
        "- Zero values are counted in JSON as `key_match_zero`, `loose_zero_only`, `missing_zero`, and raw_zero; loose zero matches are intentionally weak evidence.",
        "- Samples for each file are available in the JSON report.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    name_to_code = load_name_to_code()
    records, extract_counters = extract_raw_records(name_to_code)
    comparison = compare(records)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "validation_dir": str(VALIDATION_DIR.relative_to(ROOT)),
            "crawl_csv": str(CRAWL_CSV.relative_to(ROOT)),
            "purpose": "full raw XLSX value audit against parsed ALIO HTML crawl records",
        },
        "raw_extract": {
            "xlsx_files": len(list(VALIDATION_DIR.rglob("*.xlsx"))),
            "raw_value_records": len(records),
            **dict(extract_counters),
        },
        "parsed_json_meta": json_meta_summary(),
        "comparison": comparison,
    }
    json_path, md_path = write_report(report)
    print(f"raw value records: {len(records):,}")
    print(f"parsed csv rows: {comparison['parsed_csv']['rows']:,}")
    print(f"reports: {json_path.relative_to(ROOT)}, {md_path.relative_to(ROOT)}")

    attention = [
        item for item in comparison["items"]
        if item.get("item_not_in_parsed_csv", 0)
        or item.get("missing_or_changed_value", 0) > 100
        or item.get("nonzero_value_match_rate") in (None, 0)
    ]
    print("attention items:")
    for item in attention[:20]:
        print(
            f"  {item['item_no']}: raw={item.get('raw_values', 0):,} "
            f"match_rate={item.get('nonzero_value_match_rate')} "
            f"missing_or_changed={item.get('missing_or_changed_value', 0):,} "
            f"not_in_csv={item.get('item_not_in_parsed_csv', 0):,} "
            f"period_not_comparable={item.get('period_not_comparable', 0):,}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
