"""ALIO HTML canonical parser v2.

The v1 parser flattens ALIO item HTML into a metric-friendly long CSV.  This
parser starts one layer earlier: it preserves the semantic table grid shown in
ALIO by expanding row/column spans and carrying row/column header paths for
each data cell.

Default output is local generated data under data/canonical/:

    python parse_alio_v2.py
    python parse_alio_v2.py --limit 20
    python parse_alio_v2.py --items 31201,70301 --orgs C0091,C0247
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent
DEFAULT_RAW_DIR = ROOT / "rawdata" / "html"
DEFAULT_JSONL = ROOT / "data" / "canonical" / "alio_canonical_records.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "canonical" / "alio_canonical_summary.json"

FIELDS = [
    "org_code",
    "org_name",
    "item_no",
    "item_name",
    "as_of",
    "record_type",
    "section_title",
    "table_index",
    "table_title",
    "row_header_path",
    "col_header_path",
    "row_index",
    "col_index",
    "period_label",
    "period_year",
    "period_type",
    "metric_label",
    "unit",
    "raw_value",
    "normalized_value",
    "text_value",
    "file_name",
    "file_href",
    "source_html_path",
    "parser_warning",
]

RECORD_TYPES = {"time_series", "roster", "attribute", "text_rule", "attachment"}
COVERAGE_FIELDS = [
    "tables_seen",
    "tables_with_records",
    "nb_blocks_seen",
    "nb_blocks_captured",
    "unparsed_elements",
]

TITLE_PREFIX_RE = re.compile(r"^\d+(?:-\d+)?\.\s*")
SECTION_CLASS_RE = re.compile(r"SECTION-(\d+)")
AS_OF_RE = re.compile(r"\((20\d{2}년\s*\d\s*/\s*\d\s*분기)\)")
UNIT_RE = re.compile(r"\(?단위\s*[:：]\s*([^)]+)\)?")
YEAR_RE = re.compile(
    r"(20\d{2})\s*년(?:\s*(?:\((\d\s*/\s*\d\s*분기)\)|"
    r"(\d\s*/\s*\d\s*분기|결산|예산|반기|분기)))?"
)
SHORT_YEAR_RE = re.compile(r"(?<!\d)(\d{2})\s*년")
NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
ATTACH_ARG_RE = re.compile(r"report_attach_down\(\s*['\"]([^'\"]+)['\"]")

HEADER_HINTS = {
    "구분",
    "연도",
    "항목",
    "사유",
    "성명",
    "기관명",
    "회사명",
    "첨부파일",
    "첨부 파일",
    "비고",
    "근거규정",
    "지급기준",
    "내용",
}
ATTACH_HINTS = {"첨부파일", "첨부 파일", "파일명"}
TEXT_RULE_HINTS = {
    "근거규정",
    "지급기준",
    "운영기준",
    "규정",
    "기준",
    "내용",
    "사유",
}


@dataclass(frozen=True)
class GridCell:
    tag: Tag
    text: str
    origin_row: int
    origin_col: int
    rowspan: int
    colspan: int


@dataclass(frozen=True)
class Period:
    label: str
    year: str
    period_type: str


@dataclass
class DocCoverage:
    tables_seen: int = 0
    tables_with_records: int = 0
    nb_blocks_seen: int = 0
    nb_blocks_captured: int = 0
    unparsed_elements: int = 0

    def as_dict(self) -> dict[str, int]:
        return {field: int(getattr(self, field)) for field in COVERAGE_FIELDS}


def coverage_summary(totals: dict[str, int] | Counter[str]) -> dict[str, int]:
    summary = {field: int(totals.get(field, 0)) for field in COVERAGE_FIELDS}
    summary["tables_without_records"] = max(
        summary["tables_seen"] - summary["tables_with_records"], 0
    )
    summary["nb_blocks_uncaptured"] = max(
        summary["nb_blocks_seen"] - summary["nb_blocks_captured"], 0
    )
    return summary


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def cell_text(cell: Tag) -> str:
    return clean_text(cell.get_text(" ", strip=True))


def parse_value(raw: str) -> int | float | None:
    text = clean_text(raw)
    if not text or text == "-":
        return None
    plain = text.replace(",", "").replace("%", "").strip()
    if NUMBER_RE.match(plain):
        number = float(plain)
        return int(number) if number.is_integer() else number
    return None


def split_csv(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def _safe_int(value: str | None, default: int = 1) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def expand_rows(rows: list[Tag]) -> list[list[GridCell | None]]:
    """Expand rowspan/colspan into a rectangular grid.

    Each occupied coordinate points to the same GridCell instance for spanned
    cells, so downstream code can still detect that a value came from a span.
    """
    grid: dict[tuple[int, int], GridCell] = {}
    for r, tr in enumerate(rows):
        c = 0
        for tag in tr.find_all(["td", "th"], recursive=False):
            while (r, c) in grid:
                c += 1
            rowspan = _safe_int(tag.get("rowspan"))
            colspan = _safe_int(tag.get("colspan"))
            cell = GridCell(
                tag=tag,
                text=cell_text(tag),
                origin_row=r,
                origin_col=c,
                rowspan=rowspan,
                colspan=colspan,
            )
            for dr in range(rowspan):
                for dc in range(colspan):
                    grid[(r + dr, c + dc)] = cell
            c += colspan
    if not grid:
        return []
    n_rows = max(r for r, _ in grid) + 1
    n_cols = max(c for _, c in grid) + 1
    return [[grid.get((r, c)) for c in range(n_cols)] for r in range(n_rows)]


def _direct_rows(container: Tag) -> list[Tag]:
    rows: list[Tag] = []
    for child in container.children:
        if not isinstance(child, Tag):
            continue
        if child.name in {"thead", "tbody", "tfoot"}:
            rows.extend(child.find_all("tr", recursive=False))
        elif child.name == "tr":
            rows.append(child)
    if not rows:
        rows = container.find_all("tr", recursive=False)
    return rows


def _body_rows_without_thead(table: Tag) -> list[Tag]:
    rows: list[Tag] = []
    for child in table.children:
        if not isinstance(child, Tag) or child.name == "thead":
            continue
        if child.name in {"tbody", "tfoot"}:
            rows.extend(child.find_all("tr", recursive=False))
        elif child.name == "tr":
            rows.append(child)
    return rows


def split_table_grid(table: Tag) -> tuple[list[list[GridCell | None]], list[list[GridCell | None]], bool]:
    thead = table.find("thead", recursive=False)
    if thead is not None:
        head = expand_rows(_direct_rows(thead))
        body = expand_rows(_body_rows_without_thead(table))
        return head, body, True

    grid = expand_rows(_direct_rows(table))
    header_rows = infer_header_row_count(grid)
    if header_rows:
        return grid[:header_rows], grid[header_rows:], False
    return [], grid, False


def infer_header_row_count(grid: list[list[GridCell | None]]) -> int:
    if len(grid) < 2:
        return 0
    first = [cell.text for cell in grid[0] if cell and cell.text]
    if not first:
        return 0
    first_text = " ".join(first)
    if any(hint in first_text for hint in HEADER_HINTS):
        return 1
    first_numbers = sum(parse_value(text) is not None for text in first)
    second = [cell.text for cell in grid[1] if cell and cell.text]
    second_numbers = sum(parse_value(text) is not None for text in second)
    if len(first) > 1 and first_numbers == 0 and second_numbers > 0:
        return 1
    return 0


def header_paths(head_grid: list[list[GridCell | None]], width: int) -> list[str]:
    paths: list[str] = []
    for col in range(width):
        parts: list[str] = []
        for row in head_grid:
            if col >= len(row):
                continue
            cell = row[col]
            text = cell.text if cell else ""
            if text and (not parts or parts[-1] != text):
                parts.append(text)
        paths.append(" > ".join(parts))
    return paths


def row_path(row: list[GridCell | None], width: int) -> str:
    parts: list[str] = []
    for col in range(min(width, len(row))):
        cell = row[col]
        text = re.sub(r"\s*\*+$", "", cell.text if cell else "").strip()
        if text and (not parts or parts[-1] != text):
            parts.append(text)
    return " > ".join(parts)


def extract_period(text: str, *, allow_short_year: bool = False) -> Period | None:
    if not text:
        return None
    for part in re.split(r"\s*>\s*|\s*\|\s*", text):
        part = clean_text(part)
        match = YEAR_RE.search(part)
        if match:
            period_text = match.group(2) or match.group(3) or ""
            if "분기" in period_text and period_text not in {"반기", "분기"}:
                period_type = "분기"
            else:
                period_type = period_text
            return Period(match.group(0), match.group(1), period_type)
    if allow_short_year:
        match = SHORT_YEAR_RE.search(text)
        if match:
            year = 2000 + int(match.group(1))
            return Period(match.group(0), str(year), "")
    return None


def extract_links(cell: Tag) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for anchor in cell.find_all("a"):
        href = clean_text(anchor.get("href") or "")
        name = cell_text(anchor)
        if href:
            match = ATTACH_ARG_RE.search(href)
            if match:
                name = clean_text(match.group(1))
        links.append({"file_name": name, "file_href": href})
    return links


def _has_table_ancestor(el: Tag) -> bool:
    return el.find_parent("table") is not None


def _is_bold_cell(cell: Tag) -> bool:
    style = cell.get("style") or ""
    return "font-weight" in style and "bold" in style


def _section_title_from_levels(levels: list[str]) -> str:
    return " > ".join(part for part in levels if part)


def _is_context_title(text: str, org_name: str) -> bool:
    if not text or text == org_name:
        return False
    if AS_OF_RE.search(text):
        return False
    if text.replace(" ", "") == "해당사항없음":
        return False
    if "기금계정" in text or "고유사업" in text:
        return True
    if UNIT_RE.search(text) and len(text) < 180:
        return True
    return False


def _has_account_context_title(text: str) -> bool:
    return "기금계정" in text or "고유사업" in text


def _combine_table_title(context_title: str, title: str) -> str:
    context_title = clean_text(context_title)
    title = clean_text(title)
    if context_title and title:
        if context_title in title:
            return title
        if title in context_title:
            return context_title
        return f"{context_title} | {title}"
    return title or context_title


def _is_text_note(text: str, org_name: str) -> bool:
    if not text or text == org_name:
        return False
    compact = text.replace(" ", "")
    if compact == "해당사항없음":
        return False
    if AS_OF_RE.search(text):
        return False
    return len(text) >= 120 or text.startswith("ㅇ ") or text.startswith("○ ")


def _has_attachment_hint(col_paths: list[str]) -> bool:
    joined = " ".join(col_paths)
    return any(hint in joined for hint in ATTACH_HINTS)


def _compact_label(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _is_correction_value_header(text: str) -> bool:
    return _compact_label(text) in {"수정전", "수정후"}


def _text_heavy(
    head_grid: list[list[GridCell | None]],
    body_grid: list[list[GridCell | None]],
    col_paths: list[str],
) -> bool:
    joined_headers = " ".join(col_paths)
    if any(hint in joined_headers for hint in TEXT_RULE_HINTS):
        return True
    texts = [cell.text for row in body_grid for cell in row if cell and cell.text]
    if not texts:
        return False
    return max(len(text) for text in texts) >= 180 or (
        len(texts) >= 3 and sum(len(text) for text in texts) / len(texts) >= 80
    )


def classify_table(
    table: Tag,
    head_grid: list[list[GridCell | None]],
    body_grid: list[list[GridCell | None]],
    col_paths: list[str],
    row_header_cols: int,
) -> str:
    if _has_attachment_hint(col_paths):
        return "attachment"
    has_period = any(extract_period(path) for path in col_paths) or any(
        extract_period(row_path(row, row_header_cols)) for row in body_grid
    )
    if has_period:
        return "time_series"
    if table.find("a") is not None:
        return "attachment"
    if _text_heavy(head_grid, body_grid, col_paths):
        return "text_rule"
    if not head_grid and all(len([cell for cell in row if cell]) <= 2 for row in body_grid):
        return "attribute"
    if head_grid and len(body_grid) > 1:
        return "roster"
    return "attribute"


def _metric_label(record_type: str, row_headers: str, col_headers: str, period_source: str) -> str:
    if record_type == "time_series":
        if period_source == "col":
            return row_headers
        if period_source == "row":
            return col_headers
    if record_type == "attribute":
        return row_headers or col_headers
    return col_headers or row_headers


def _record(
    *,
    base: dict[str, Any],
    record_type: str,
    table_index: int,
    table_title: str,
    section_title: str,
    row_headers: str,
    col_headers: str,
    row_index: int | None,
    col_index: int | None,
    raw_value: str,
    normalized_value: int | float | None,
    text_value: str,
    unit: str,
    period: Period | None,
    period_source: str,
    file_name: str = "",
    file_href: str = "",
    warning: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        **base,
        "record_type": record_type,
        "section_title": section_title,
        "table_index": table_index,
        "table_title": table_title,
        "row_header_path": row_headers,
        "col_header_path": col_headers,
        "row_index": row_index,
        "col_index": col_index,
        "period_label": period.label if period else "",
        "period_year": period.year if period else "",
        "period_type": period.period_type if period else "",
        "metric_label": _metric_label(record_type, row_headers, col_headers, period_source),
        "unit": unit,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "text_value": text_value,
        "file_name": file_name,
        "file_href": file_href,
        "parser_warning": ";".join(sorted(set(w for w in warning if w))),
    }


def _fallback_record(
    *,
    base: dict[str, Any],
    table_index: int,
    table_title: str,
    section_title: str,
    raw_text: str,
    unit: str,
    warning: Iterable[str],
) -> dict[str, Any]:
    text = clean_text(raw_text)
    return _record(
        base=base,
        record_type="text_rule",
        table_index=table_index,
        table_title=table_title,
        section_title=section_title,
        row_headers="",
        col_headers="",
        row_index=None,
        col_index=None,
        raw_value=text,
        normalized_value=None,
        text_value=text,
        unit=unit,
        period=None,
        period_source="",
        warning=warning,
    )


def parse_table(
    table: Tag,
    *,
    base: dict[str, Any],
    table_index: int,
    table_title: str,
    section_title: str,
    unit: str,
) -> list[dict[str, Any]]:
    head_grid, body_grid, explicit_thead = split_table_grid(table)
    if not body_grid:
        return [
            _fallback_record(
                base=base,
                table_index=table_index,
                table_title=table_title,
                section_title=section_title,
                raw_text=cell_text(table),
                unit=unit,
                warning=["table_no_records", "unparsed_table"],
            )
        ]

    width = max([len(row) for row in head_grid + body_grid] or [0])
    col_paths = header_paths(head_grid, width) if head_grid else ["" for _ in range(width)]
    period_cols = [idx for idx, path in enumerate(col_paths) if extract_period(path)]
    correction_cols = [idx for idx, path in enumerate(col_paths) if _is_correction_value_header(path)]

    if period_cols:
        row_header_cols = min(period_cols)
        data_cols = period_cols
    elif correction_cols:
        row_header_cols = min(correction_cols)
        data_cols = correction_cols
    elif width <= 1:
        row_header_cols = 0
        data_cols = [0]
    else:
        row_header_cols = 1
        data_cols = list(range(1, width))

    record_type = classify_table(table, head_grid, body_grid, col_paths, row_header_cols)
    warnings: list[str] = []
    if not head_grid:
        warnings.append("no_header_detected")
    elif not explicit_thead:
        warnings.append("inferred_header")

    records: list[dict[str, Any]] = []
    for body_row_index, row in enumerate(body_grid):
        if not any(cell and cell.text for cell in row):
            continue
        headers = row_path(row, row_header_cols)
        row_period = extract_period(headers)
        for col in data_cols:
            cell = row[col] if col < len(row) else None
            if cell is None:
                continue
            raw = cell.text
            links = extract_links(cell.tag)
            if not raw and not links:
                continue
            col_headers = col_paths[col] if col < len(col_paths) else ""
            col_period = extract_period(col_headers)
            period = col_period or row_period
            period_source = "col" if col_period else ("row" if row_period else "")
            normalized = parse_value(raw)
            text = "" if normalized is not None else raw
            cell_warnings = list(warnings)
            if col >= row_header_cols and (cell.rowspan > 1 or cell.colspan > 1):
                cell_warnings.append("spanned_data_cell")

            if links:
                for link in links:
                    file_period = extract_period(link["file_name"], allow_short_year=True)
                    records.append(
                        _record(
                            base=base,
                            record_type="attachment",
                            table_index=table_index,
                            table_title=table_title,
                            section_title=section_title,
                            row_headers=headers,
                            col_headers=col_headers,
                            row_index=body_row_index + len(head_grid),
                            col_index=col,
                            raw_value=raw,
                            normalized_value=normalized,
                            text_value=text,
                            unit=unit,
                            period=period or file_period,
                            period_source=period_source or ("file" if file_period else ""),
                            file_name=link["file_name"],
                            file_href=link["file_href"],
                            warning=cell_warnings,
                        )
                    )
            else:
                records.append(
                    _record(
                        base=base,
                        record_type=record_type,
                        table_index=table_index,
                        table_title=table_title,
                        section_title=section_title,
                        row_headers=headers,
                        col_headers=col_headers,
                        row_index=body_row_index + len(head_grid),
                        col_index=col,
                        raw_value=raw,
                        normalized_value=normalized,
                        text_value=text,
                        unit=unit,
                        period=period,
                        period_source=period_source,
                        warning=cell_warnings,
                    )
                )
    if records:
        return records
    return [
        _fallback_record(
            base=base,
            table_index=table_index,
            table_title=table_title,
            section_title=section_title,
            raw_text=cell_text(table),
            unit=unit,
            warning=[*warnings, "table_no_records"],
        )
    ]


def parse_doc(
    html: str,
    org_code: str,
    item_no: str,
    org_name: str = "",
    *,
    source_html_path: str = "",
    coverage: DocCoverage | None = None,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict[str, Any]] = []
    coverage = coverage if coverage is not None else DocCoverage()

    item_name = ""
    title = soup.find("p", class_="cover-title")
    if title:
        item_name = TITLE_PREFIX_RE.sub("", cell_text(title))

    base = {
        "org_code": org_code,
        "org_name": org_name,
        "item_no": item_no,
        "item_name": item_name,
        "as_of": "",
        "source_html_path": source_html_path,
    }

    as_of = ""
    unit = ""
    table_title = ""
    context_title = ""
    section_levels: list[str] = []
    table_index = 0

    for el in soup.find_all(["p", "table"]):
        if el.name == "table" and _has_table_ancestor(el):
            continue

        if el.name == "p":
            anchor = el.find("a", class_="toc")
            if anchor:
                class_text = " ".join(el.get("class") or [])
                match = SECTION_CLASS_RE.search(class_text)
                if match:
                    level = int(match.group(1))
                    while len(section_levels) < level:
                        section_levels.append("")
                    section_levels[level - 1] = cell_text(anchor)
                    del section_levels[level:]
                    table_title = ""
                    context_title = ""
            continue

        classes = el.get("class") or []
        text = cell_text(el)
        if "nb" in classes:
            coverage.nb_blocks_seen += 1
            if not text:
                continue
            if match := AS_OF_RE.search(text):
                as_of = clean_text(match.group(1))
                base["as_of"] = as_of
                coverage.nb_blocks_captured += 1
                continue
            if match := UNIT_RE.search(text):
                unit = clean_text(match.group(1))
            bold_cells = [td for td in el.find_all("td") if _is_bold_cell(td)]
            if bold_cells:
                table_title = _combine_table_title(context_title, cell_text(bold_cells[0]))
                coverage.nb_blocks_captured += 1
                continue
            section_title = _section_title_from_levels(section_levels)
            if text.replace(" ", "") == "해당사항없음":
                records.append(
                    _record(
                        base={**base, "as_of": as_of},
                        record_type="attribute",
                        table_index=-1,
                        table_title=table_title,
                        section_title=section_title,
                        row_headers="해당사항 없음",
                        col_headers="",
                        row_index=None,
                        col_index=None,
                        raw_value="",
                        normalized_value=None,
                        text_value="해당사항 없음",
                        unit="",
                        period=None,
                        period_source="",
                        warning=["nb_no_applicable"],
                    )
                )
                coverage.nb_blocks_captured += 1
                continue
            if _is_context_title(text, org_name):
                if _has_account_context_title(text):
                    context_title = text
                    table_title = text
                else:
                    table_title = _combine_table_title(context_title, text)
                coverage.nb_blocks_captured += 1
                continue
            if _is_text_note(text, org_name):
                records.append(
                    _record(
                        base={**base, "as_of": as_of},
                        record_type="text_rule",
                        table_index=-1,
                        table_title=table_title,
                        section_title=section_title,
                        row_headers="",
                        col_headers="",
                        row_index=None,
                        col_index=None,
                        raw_value=text,
                        normalized_value=None,
                        text_value=text,
                        unit=unit,
                        period=None,
                        period_source="",
                        warning=["nb_text_note"],
                    )
                )
                coverage.nb_blocks_captured += 1
                continue
            records.append(
                _fallback_record(
                    base={**base, "as_of": as_of},
                    table_index=-1,
                    table_title=table_title,
                    section_title=section_title,
                    raw_text=text,
                    unit=unit,
                    warning=["skipped_short_nb"],
                )
            )
            coverage.nb_blocks_captured += 1
            coverage.unparsed_elements += 1
            continue

        coverage.tables_seen += 1
        section_title = _section_title_from_levels(section_levels)
        if el.get("border") != "1":
            records.append(
                _fallback_record(
                    base={**base, "as_of": as_of},
                    table_index=table_index,
                    table_title=table_title,
                    section_title=section_title,
                    raw_text=text,
                    unit=unit,
                    warning=["non_border_table", "unparsed_table"],
                )
            )
            coverage.tables_with_records += 1
            coverage.unparsed_elements += 1
            table_index += 1
            continue

        table_records = parse_table(
            el,
            base={**base, "as_of": as_of},
            table_index=table_index,
            table_title=table_title,
            section_title=section_title,
            unit=unit,
        )
        if table_records:
            coverage.tables_with_records += 1
        if any(
            warning in str(record.get("parser_warning") or "")
            for record in table_records
            for warning in ("table_no_records", "unparsed_table")
        ):
            coverage.unparsed_elements += 1
        records.extend(table_records)
        table_index += 1

    return records


def parse_doc_with_coverage(
    html: str,
    org_code: str,
    item_no: str,
    org_name: str = "",
    *,
    source_html_path: str = "",
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    coverage = DocCoverage()
    records = parse_doc(
        html,
        org_code,
        item_no,
        org_name,
        source_html_path=source_html_path,
        coverage=coverage,
    )
    return records, coverage.as_dict()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_org_names() -> dict[str, str]:
    path = ROOT / "data" / "institutions.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {org["org_code"]: org.get("name", "") for org in data.get("orgs", [])}


def _iter_docs(
    raw_dir: Path,
    *,
    orgs: set[str] | None = None,
    items: set[str] | None = None,
    limit: int | None = None,
) -> Iterable[tuple[Path, str, str]]:
    count = 0
    for path in sorted(raw_dir.glob("*__doc.html")):
        stem = path.name[: -len("__doc.html")]
        org_code, _, item_no = stem.rpartition("_")
        if orgs and org_code not in orgs:
            continue
        if items and item_no not in items:
            continue
        yield path, org_code, item_no
        count += 1
        if limit is not None and count >= limit:
            break


def write_summary(
    *,
    summary_out: Path,
    raw_dir: Path,
    jsonl_out: Path,
    docs_seen: int,
    docs_with_records: int,
    record_count: int,
    record_types: Counter[str],
    item_counts: Counter[str],
    warning_counts: Counter[str],
    coverage_totals: Counter[str],
    doc_coverage: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {
        "_meta": {
            "dataset": "alio_canonical_records",
            "schema_version": "2.0.0",
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "source_type": "alio_html_doc_fragment",
            "raw_source_dir": _rel(raw_dir),
            "jsonl": _rel(jsonl_out),
            "schema": _rel(ROOT / "data" / "canonical" / "schema.json"),
        },
        "docs_seen": docs_seen,
        "docs_with_records": docs_with_records,
        "docs_without_records": docs_seen - docs_with_records,
        "record_count": record_count,
        "record_type_counts": dict(sorted(record_types.items())),
        "item_counts": dict(sorted(item_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "element_coverage": coverage_summary(coverage_totals),
        "docs_with_unparsed_elements": sum(
            1 for doc in doc_coverage if int(doc.get("unparsed_elements", 0)) > 0
        ),
        "doc_coverage": doc_coverage,
    }
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_all(
    raw_dir: Path = DEFAULT_RAW_DIR,
    jsonl_out: Path = DEFAULT_JSONL,
    *,
    summary_out: Path = DEFAULT_SUMMARY,
    orgs: set[str] | None = None,
    items: set[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    org_names = load_org_names()
    jsonl_out.parent.mkdir(parents=True, exist_ok=True)

    docs_seen = 0
    docs_with_records = 0
    record_count = 0
    record_types: Counter[str] = Counter()
    item_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    coverage_totals: Counter[str] = Counter()
    doc_coverage: list[dict[str, Any]] = []

    with jsonl_out.open("w", encoding="utf-8", newline="\n") as out:
        for path, org_code, item_no in _iter_docs(raw_dir, orgs=orgs, items=items, limit=limit):
            docs_seen += 1
            rel_source = _rel(path)
            html = path.read_text(encoding="utf-8")
            coverage = DocCoverage()
            records = parse_doc(
                html,
                org_code,
                item_no,
                org_names.get(org_code, ""),
                source_html_path=rel_source,
                coverage=coverage,
            )
            coverage_row = {
                "source_html_path": rel_source,
                "org_code": org_code,
                "item_no": item_no,
                "record_count": len(records),
                **coverage.as_dict(),
            }
            doc_coverage.append(coverage_row)
            coverage_totals.update(coverage.as_dict())
            if records:
                docs_with_records += 1
            for record in records:
                out.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                record_count += 1
                record_types[str(record["record_type"])] += 1
                item_counts[item_no] += 1
                for warning in str(record.get("parser_warning") or "").split(";"):
                    if warning:
                        warning_counts[warning] += 1

    return write_summary(
        summary_out=summary_out,
        raw_dir=raw_dir,
        jsonl_out=jsonl_out,
        docs_seen=docs_seen,
        docs_with_records=docs_with_records,
        record_count=record_count,
        record_types=record_types,
        item_counts=item_counts,
        warning_counts=warning_counts,
        coverage_totals=coverage_totals,
        doc_coverage=doc_coverage,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse ALIO doc.html files into canonical v2 JSONL.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--out", default=str(DEFAULT_JSONL))
    parser.add_argument("--summary-out", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--orgs", help="Comma-separated org codes, e.g. C0091,C0247")
    parser.add_argument("--items", help="Comma-separated item numbers, e.g. 31201,70301")
    parser.add_argument("--limit", type=int, help="Limit parsed documents after filters")
    args = parser.parse_args()

    summary = parse_all(
        Path(args.raw_dir),
        Path(args.out),
        summary_out=Path(args.summary_out),
        orgs=split_csv(args.orgs or "") or None,
        items=split_csv(args.items or "") or None,
        limit=args.limit,
    )
    print(
        "canonical v2 parse complete: "
        f"docs={summary['docs_seen']} records={summary['record_count']} "
        f"types={summary['record_type_counts']} out={args.out}"
    )


if __name__ == "__main__":
    main()
