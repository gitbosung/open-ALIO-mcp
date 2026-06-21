# ALIO Parser v2 Transition Plan

Created: 2026-06-21

## Current Decision

Keep the existing HTML crawl results and rebuild the parser/storage layer from
the post-crawl HTML stage.

The current parser and parsed data are preserved as v1:

- Tracked parser snapshot: `archive/v1_html_long_parser_20260621/parse_alio.py`
- Local-only parsed data snapshot: `archive/v1_html_long_parser_20260621/data/`
- Hash manifest: `archive/v1_html_long_parser_20260621/manifest.json`

## What Was Verified

Validation compared the supplied 2025 Q1 raw XLSX extraction under
`rawdata/validation` with the current HTML-parsed CSV/JSON:

- Raw XLSX files opened: 83
- Raw non-blank values extracted: 979,528
- Current parsed CSV rows: 936,981
- Current parsed JSON records: 936,981
- CSV vs JSON record mismatch: 0

Important caveat: the current parsed HTML data is mostly `2026년 1/4분기`, while
the validation XLSX set is `2025년 1분기`. Exact 100% equality is therefore not
possible without the matching 2025 Q1 HTML snapshot.

## Parsing Quality Summary

Good numeric time-series coverage:

- `20401` 신규채용 현황
- `20501` 임원 연봉
- `20601` 직원 평균보수
- `20701` 기관장 업무추진비
- `31201` 요약 재무상태표
- `31301` 요약 손익계산서 또는 요약 포괄손익계산서
- `31401` 수입·지출 현황
- `31501` 주요사업
- `31801` 장단기 차입금 현황
- `32001` 출연 현황
- `70461` 산업재해 사고 사망자 수 및 안전사고 사망자 수

Known v1 structure gaps:

- `20801` 복리후생비: detailed welfare dimensions are not preserved well.
- `63701` 그 밖의 복리후생제도: text/rule tables are mostly unsupported.
- `31901` 투자 및 출자 현황: roster/list structures are not represented well.
- `31701` 자본금 및 주주 현황: attribute-style values are not represented well.
- `32301` 외부회계감사보고서: report attachment metadata is mostly skipped.
- `32311` 자체 감사부서 현황: roster/attribute structures are weak.
- `32101` 경영부담 비용추계: guarantee/collateral roster tables are weak.
- `70301` 수의계약: HTML exists, but v1 intentionally skips attachment cells.

Rawdata items currently absent from parsed CSV and HTML crawl:

- `21201` 징계제도 운영현황
- `21211` 징계처분 결과
- `21301` 소송 및 소송대리인 현황
- `21311` 고문변호사 및 법률자문 현황
- `21621` 에너지 사용량
- `21631` 폐기물 발생량
- `21641` 용수 사용량
- `31601` 투자집행내역
- `31921` 퇴직 임직원 재취업 현황

## Why Match Rate Was Not 100%

After excluding incomparable periods and zero values, values still do not all
match. Main reasons:

- Current HTML is 2026 Q1, while validation rawdata is 2025 Q1.
- ALIO current pages may include correction disclosures after the 2025 Q1 raw
  extraction date.
- v1 flattening loses some row/column axes, especially totals, detailed
  welfare dimensions, roster rows, and attachment/text tables.

For the strong numeric time-series subset, comparable non-zero value match rate
was about 96.15%, not 100%.

## v2 Storage Direction

Do not preserve the HTML DOM mechanically. Preserve the semantic table
structure shown by ALIO.

Recommended canonical fields:

```text
org_code
org_name
item_no
item_name
as_of
record_type
section_title
table_index
table_title
row_header_path
col_header_path
row_index
col_index
period_label
period_year
period_type
metric_label
unit
raw_value
normalized_value
text_value
file_name
file_href
source_html_path
parser_warning
```

Recommended `record_type` values:

- `time_series`: year/period-based numeric values
- `roster`: list/roster tables, such as lawsuits, lawyers, investment targets
- `attribute`: point-in-time attributes, such as capital or shareholder fields
- `text_rule`: policy/rule descriptions and basis text
- `attachment`: attachment/file-link disclosures, such as 수의계약

## Recommended Next Steps

1. Freeze v1 and do not overwrite the local v1 archive.
2. Define a canonical schema under `data/canonical/`.
3. Build a v2 parser that expands `rowspan`/`colspan` into row and column header
   paths.
4. Classify each table into `record_type`.
5. Emit canonical JSONL or Parquet first.
6. Build MCP-facing derived metrics/indexes from canonical data.
7. Re-run rawdata validation by item, separating:
   - period mismatch
   - item not crawled
   - attachment-only disclosure
   - parser structure loss
   - changed/corrected values
8. For true 100% validation against 2025 Q1 rawdata, obtain or reconstruct the
   matching 2025 Q1 HTML snapshot if possible.

