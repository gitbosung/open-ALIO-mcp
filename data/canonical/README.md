# Canonical ALIO Parser v2

This directory holds the tracked schema for the v2 canonical parser.

Generated parser outputs are local build artifacts and are intentionally ignored
by Git:

- `alio_canonical_records.jsonl`
- `alio_canonical_summary.json`

Build them from the already-crawled HTML fragments:

```powershell
python parse_alio_v2.py
python parse_alio_v2.py --limit 20
python parse_alio_v2.py --items 31201,70301 --orgs C0091,C0247
```

For MCP/runtime querying, build the compact SQLite store directly from HTML:

```powershell
python scripts/build_canonical_store.py
python scripts/build_canonical_store.py --limit 20 --out data/canonical/_sample_canonical.db
python scripts/validate_canonical_store.py --db data/canonical/alio_canonical.db
```

Candidate MCP metrics can be derived without replacing current runtime metrics:

```powershell
python scripts/build_canonical_store.py --items 20501,31201,31301,31401 --out data/canonical/_metrics_seed_canonical.db
python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db
```

The derived JSON files are written under `data/canonical/metrics_v2/`, and the
v1-vs-v2 comparison report is written under
`data/validation_reports/canonical_v2_metrics_compare.json`.

Latest targeted comparison for `20501,31201,31301,31401`:

- `executive_pay`: 28,768 common points, 0 mismatches, 0 skipped conflicts.
- `budget`: 18,046 common points, 0 mismatches, 0 skipped conflicts.
- `finance`: 48,657 common points, 0 mismatches, 434 skipped conflicts.
- `finance_context`: 51,906 v2-only points, 0 skipped conflicts.  This
  candidate preserves normalized `table_title` context in the metric key and
  intentionally has no v1 common-point comparison.

The v1-compatible `finance` candidate keeps the 434 conflicts skipped so the
current runtime-key comparison remains visible.  The v2-only `finance_context`
candidate demonstrates the proposed key shape for those rows: preserve the
normalized source `table_title` to keep K-GAAP/K-IFRS/AUP, connected/separate
statement, old/new national accounting standard, and program-level fund-table
contexts distinct.

MCP-facing finance lookup now uses this as an internal safety layer: callers
still request `get_institution_metrics(category="finance")`, and the normal
`series` field remains v1-compatible.  When the local `finance_context`
candidate is available, the default response adds a lightweight `basis` summary
that identifies the representative ALIO table context for each returned series.
It does not return all table-context alternatives by default.  If the caller
asks for a specific context in `item_query` (for example `K-GAAP`, `K-IFRS`, or
a statement-form/table-title keyword), the finance lookup can return the
matching context-specific series from the retained v2 candidate.

Before using these candidate metrics as a promotion gate, apply the parser
coverage review in `docs/parser_v2_review_notes.md`: skipped tables/notes must
be auditable, and summary output should report HTML elements seen vs captured.
The current parser records those audit gaps with warnings such as
`unparsed_table`, `table_no_records`, and `skipped_short_nb`; parser summaries
and SQLite `source_docs` rows include per-document table/`nb` coverage counts.

The v2 layer does not replace `data/crawl/alio_records.csv` yet.  It is the
semantic source layer that preserves row/column header paths, periods, text
rules, roster cells, attributes, and attachment links before MCP-facing metric
indexes are derived.

After v2 reliability gates pass, the MCP path should be simplified to use
canonical-derived metrics as the normal source.  The v1 crawl CSV path should
remain only as an archive or temporary fallback, not as a permanent duplicate
stack.
