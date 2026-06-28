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
9. After v2 canonical parsing is judged reliable enough for production MCP
   answers, simplify the MCP data path instead of keeping a permanent v1/v2
   dual stack:
   - make v2-derived metrics the default source for validated categories
   - remove temporary feature flags and comparison-only plumbing
   - retire or archive v1 promotion paths that are no longer needed
   - keep only minimal compatibility adapters required by existing tools
   - update tests and docs so canonical-to-MCP is the single documented normal
     flow

## 2026-06-21 Implementation Progress

Initial v2 parser/storage work has started without replacing v1 outputs:

- Added `parse_alio_v2.py`.
- Added tracked canonical schema docs under `data/canonical/`.
- Added `crawl_alio.py parse-v2` as a post-crawl parser entrypoint.
- Added Git ignore rules for generated canonical JSONL/summary artifacts.
- Added `scripts/build_canonical_store.py` to stream v2 records directly into a
  compact SQLite store.
- Added `scripts/validate_canonical_store.py` for canonical v2 quality checks.
- Added `src/open_alio_mcp/canonical_store.py` and initial MCP tools for
  summary, record search, attachment records, and text/rule records.
- Added `scripts/build_metrics_from_canonical.py` to derive isolated v2
  candidate metrics for `finance`, `budget`, and `executive_pay`, then compare
  them against current v1/runtime `data/metrics/*.json`.
- Added focused parser tests for:
  - `rowspan`/`colspan` expansion into row/column header paths
  - attachment link metadata
  - text/rule table classification
  - SQLite store build/query behavior
  - canonical-derived executive-pay metric key behavior

Current v2 output is JSONL, one record per semantic data cell or non-table
`table.nb` disclosure note. Large generated files remain local artifacts.  The
SQLite store is now the preferred local query layer before deriving
category-specific MCP metrics from canonical data.

Initial targeted comparison using `20501,31201,31301,31401` HTML:

- `executive_pay`: 28,768 common v1/v2 points, 0 mismatches, 7 skipped
  canonical conflict groups.
- `budget`: 18,046 common v1/v2 points, 0 mismatches, 20 skipped canonical
  conflict groups.
- `finance`: 47,913 common v1/v2 points, 0 mismatches, 624 skipped canonical
  conflict groups.
- Golden-org mismatch count was 0 for all three categories.

Follow-up conflict-resolution pass:

- Preserved split `기금계정`/`고유사업` context when ALIO emits account context
  and table title in separate `table.nb` blocks.
- Treated `수정 전`/`수정 후` correction columns as data columns, so preceding
  label columns remain part of `row_header_path`.
- Filtered superseded `수정 전` values before canonical metric grouping.
- Kept parenthetical fund-account context such as
  `공무원연금기금(연금충당부채 제외한 경우)` in v2 metric key adaptation.

Updated targeted comparison after rebuilding
`data/canonical/_metrics_seed_canonical.db`:

- `executive_pay`: 28,768 common v1/v2 points, 0 mismatches, 0 skipped
  canonical conflict groups.
- `budget`: 18,046 common v1/v2 points, 0 mismatches, 0 skipped canonical
  conflict groups.
- `finance`: 48,657 common v1/v2 points, 0 mismatches, 434 skipped canonical
  conflict groups.
- Remaining finance conflicts are representative key-design issues around
  table-title/accounting-basis context, for example connected vs separate
  statements, K-IFRS vs K-GAAP, old vs new national accounting standards, and
  summary vs program-level finance tables.
- Golden-org mismatch count remains 0 for all three categories.

Design review triage from `docs/parser_v2_review_notes.md`:

- The current cell-as-record canonical model remains the right foundation.
- Before promoting more v2-derived metrics, close parser silent-loss paths and
  make coverage auditable.  In particular, skipped non-`border="1"` tables,
  zero-record tables, and short standalone `table.nb` notes need fallback rows
  or explicit gap accounting.
- Add per-document coverage counts so a document can report tables/notes seen
  vs captured, instead of only reporting whether the document produced any
  records.
- Implemented the first coverage gate: fallback records now carry
  `unparsed_table`, `table_no_records`, or `skipped_short_nb` warnings, parser
  summaries include per-document coverage rows, and the SQLite `source_docs`
  table stores the same coverage counts.
- After the coverage gate rebuild, the targeted metric comparison still has 0
  common-point mismatches.  `finance` remains at 434 skipped conflict groups.
  Inspecting the conflict rows and source HTML showed all 434 are table-title /
  accounting-basis context collapses in the current v1-compatible finance key:
  418 are K-GAAP/K-IFRS/AUP, connected/separate, or statement-form variants;
  16 are old/new national accounting standard and program-level fund-table
  variants.  Keep skip/report behavior until the v2 finance key deliberately
  preserves this context.
- Added a v2-only `finance_context` candidate metric that preserves normalized
  `table_title` context in the metric key while leaving the v1-compatible
  `finance` comparison path unchanged.  Targeted result:
  51,906 v2-only points, 0 skipped conflicts, and no v1 common-point
  comparison by design.
- Wired the context-preserving finance candidate into the existing MCP finance
  call shape.  Users still call `get_institution_metrics(category="finance")`;
  the default response keeps the v1-compatible `series` and adds a lightweight
  `basis` summary that identifies the representative ALIO table context for
  each returned series.  The context-rich v2 data remains retained internally
  for lossless storage.  When a caller asks for a specific accounting basis or
  statement form through `item_query` (for example `K-GAAP`, `K-IFRS`, or a
  table-title keyword), the lookup can return the matching context-specific
  series instead of attaching all alternatives to every default response.
- Treat table-level entities (`source_tables`), deterministic cell
  `natural_key`, structured header matrices, and classification confidence as
  near-term design work.  These should be designed carefully before broad
  schema changes.
- Therefore the next implementation step should be parser coverage/audit
  hardening first, then rebuild the targeted canonical DB and return to finance
  key-design if the zero-mismatch comparison still holds.

Important follow-through: after v2 reliability gates pass, do not leave the MCP
server with avoidable duplicate data paths. The intended end state is a simple
canonical-to-derived-metrics-to-MCP flow, with v1 retained only as an archive or
temporary fallback during the transition window.
