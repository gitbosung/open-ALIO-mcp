# ALIO Parser v2 — Design Review Notes

Created: 2026-06-21
Scope: `parse_alio_v2.py`, `scripts/build_canonical_store.py`, `data/canonical/schema.json`
Audience: whoever is actively extending the v2 canonical parser.

## Why this exists

The long-term goal is: **parse *everything* in the crawled ALIO item HTML so the
MCP can call any of it** — not just the numeric time series the v1 pipeline
promoted from XLSX. The current v2 design (one record per semantic table cell,
single 25-field schema, `record_type` discriminator) is the **right foundation
for that goal**. These notes are refinements, not a redesign.

The single most important framing: for an "everything is callable" parser, the
hard part is not the schema — it is being able to **prove nothing was silently
dropped**. Most issues below are about closing silent-loss paths and making
coverage auditable.

## Keep (do not throw away)

- Cell-as-record model with one uniform schema across all items.
- `rowspan`/`colspan` expansion (`expand_rows`) that preserves
  `row_header_path` / `col_header_path` — this is the key win over v1, which
  flattened axes into delimited string keys.
- `record_type` coexistence of `time_series` / `roster` / `attribute` /
  `text_rule` / `attachment`.
- Per-cell attachment override (links become `attachment` records even inside a
  `time_series` table) — good instinct; generalize it (see Issue 2).
- Canonical-as-source-layer, derived-metrics-on-top separation.

---

## Issues (priority order)

### 1. Silent drops — highest priority

For an "all HTML" parser, every place that discards an element without leaving a
trace is a correctness hole, because downstream we cannot tell *missing because
absent* from *missing because the parser skipped it*.

Current silent-drop paths in `parse_alio_v2.py`:

- `parse_doc`: `if el.get("border") != "1": continue` — any data-bearing table
  that is not `border="1"` is dropped with no record.
- `parse_table`: `if not body_grid: return []` — tables that fail grid/header
  inference vanish.
- `nb` paragraph handling: only `해당사항없음`, context-title, and
  `len(text) >= 120` text notes are captured. Shorter standalone notes are
  dropped.

`write_summary` / the build summary count `docs_without_records` and warnings,
but **not "elements skipped inside a doc that did produce records"** — so a doc
can lose half its tables and still look healthy.

Recommended:

- Add a catch-all. When a `border` table or `nb` block yields zero records, emit
  at least one fallback record (e.g. `record_type` left as-is but a new
  `parser_warning` like `unparsed_table` / `skipped_short_nb`, with the raw text
  in `text_value`). Nothing should leave the document without a row or a logged
  gap.
- Track per-document element coverage in the summary: tables seen vs tables that
  produced ≥1 record, `nb` blocks seen vs captured. This is what lets us assert
  "100% of HTML elements are accounted for."

### 2. Single-label table classification hides data

`classify_table` assigns exactly one `record_type` per table via heuristics
(`HEADER_HINTS`, period regex, text-heavy length thresholds, etc.). The memory
of this project already records repeated misclassification (welfare dimensions,
roster/list tables, multi-dimensional grids). Because `canonical_store._where`
filters by `record_type`, **a wrong classification silently removes the data
from any type-filtered query.**

Recommended:

- Treat `record_type` as a *hint*, not a gate. Guarantee that every raw cell is
  retrievable regardless of classification (a query with no `record_type` filter
  must always see it — that already holds, but document it as an invariant and
  test it).
- Add a low-confidence / `unclassified` fallback instead of defaulting
  ambiguous tables to `attribute` (current `classify_table` final `return
  "attribute"`). Misrouting into a "real" type is worse than an explicit
  unknown, because unknown is greppable.
- Consider recording a classification confidence or the signals that fired, so
  reclassification can be done later from stored data without re-parsing HTML.

### 3. No table-level entity

Records are cells. `table_title`, `section_title`, `table_index` are
denormalized onto every cell, and there is **no place to store table-level
facts**: the full multi-row header matrix, `n_rows`/`n_cols`, the original
caption, classification confidence, or "this whole table is one logical unit."

This matters for the end goal because "give me this institution's item 31201
table verbatim" has no clean primitive today — you reassemble it from cells.

Recommended:

- Add a `source_tables` companion table (or JSONL record kind): one row per
  top-level border table, keyed by `(source_html_path, table_index)`, holding
  the header grid, dimensions, caption, `record_type` + confidence, and a stable
  `table_id`. Cells carry `table_id` as a foreign key.
- This also resolves Issue 4 for free.

### 4. Header hierarchy collapses back into a string (watch, not urgent)

`header_paths` / `row_path` join multi-level headers with `" > "`. Good for
display and `LIKE` search, but the header *hierarchy* (e.g. "level-2 column
header = X") is only recoverable by string-splitting. `row_index` / `col_index`
recover cell *position* but not the header tree.

Recommended: do not normalize prematurely. If `source_tables` (Issue 3) stores
the raw header matrix, this is solved without complicating the cell record.
Keep the joined string on the cell for search; keep the structured matrix on the
table.

### 5. No deterministic natural key

Cells get only an autoincrement `id` (`build_canonical_store.py`
`_record_columns_sql`). v1 spent significant effort fighting dedup / conflict
groups; deriving metrics from v2 will hit the same problem without a stable key.

Recommended: define a deterministic natural key now, e.g.
`(org_code, item_no, table_index, row_index, col_index, period_label)` (plus a
disambiguator for repeated roster rows, as v1 had to add `#n`). Store it so
derived-metric dedup and idempotent rebuilds are trivial.

### 6. `normalized_value` precision (low priority)

`normalized_value` is SQLite `REAL`, so integers become floats and values above
2^53 lose precision. Korean financial figures are usually safe, but:

Recommended: treat `raw_value` as the authoritative source; document
`normalized_value` as a convenience field. Optionally validate that no
`raw_value` integer round-trips lossily.

---

## Suggested target shape (sketch)

```
source_tables
  table_id            (stable, e.g. hash of source_html_path + table_index)
  org_code, item_no, source_html_path, table_index
  section_title, table_title, caption
  n_rows, n_cols
  header_matrix       (JSON: full expanded multi-row header grid)
  record_type         (table-level hint)
  classify_confidence
  parser_warning

canonical_records (cells)  -- as today, plus:
  table_id            (FK -> source_tables)
  natural_key         (deterministic, see Issue 5)
  -- record_type stays per-cell so attachment override still works
```

Coverage self-audit (new validation output): per item_no, report
`tables_seen`, `tables_with_records`, `nb_seen`, `nb_captured`,
`unparsed_count`. This is the artifact that turns "we think we parse everything"
into "here is the number."

---

## Out of scope for the parser (mentioned so it isn't re-litigated here)

- Retiring the v1 `data/metrics/*.json` nested store and the duplicate
  `data/crawl/` CSV+JSON raw dumps — that is the MCP/transition cleanup track,
  not the parser. The only parser-relevant lesson from v1 is Issue 5 (natural
  key).
