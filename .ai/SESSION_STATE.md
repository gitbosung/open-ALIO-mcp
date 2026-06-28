# Session State

Updated: 2026-06-22

## Current Goal

Continue the ALIO parser v2 transition from preserved HTML crawl data toward a
reliable canonical parser/storage layer, v2-derived metrics, and eventually a
simplified MCP data path.

The current session should stop here.  The next session should continue from the
first task listed below, using repository files and `git status` as the source
of truth.

Continuation update from this session:

- Implemented the parser coverage/audit gate from
  `docs/parser_v2_review_notes.md`.
- Rebuilt the targeted canonical DB and reran v1/v2 metric comparison.
- Confirmed common-point mismatches remain 0 for `executive_pay`, `budget`, and
  `finance`; `finance` still has 434 skipped conflict groups.
- Classified all 434 remaining finance conflict groups as table-title /
  accounting-basis context collisions in the current v1-compatible finance key.
  Keep skip/report behavior until a deliberate v2 finance key preserves that
  context.
- Implemented that deliberate v2-only key shape as `finance_context`: it
  preserves normalized `table_title` context while keeping the v1-compatible
  `finance` comparison path unchanged.
- Wired `finance_context` into the existing MCP finance call shape:
  `get_institution_metrics(category="finance")` still returns normal `series`,
  and now returns a lightweight `basis` summary when the local v2 candidate
  exists.  It no longer attaches all table-context alternatives by default.
  If a caller requests a specific context through `item_query` (for example
  `K-GAAP`, `K-IFRS`, or a table-title keyword), the lookup returns the matching
  context-specific series from the retained v2 candidate.

## Completed Work

- Read `docs/parser_v2_transition_plan.md`.
- Kept v1 parser/data archive intact.
- Added `parse_alio_v2.py`.
  - Expands `rowspan` and `colspan`.
  - Preserves row and column header paths.
  - Classifies records as `time_series`, `roster`, `attribute`, `text_rule`, or
    `attachment`.
  - Extracts period/year/type, units, normalized numeric values, text values,
    attachment metadata, source HTML path, and parser warnings.
- Added canonical schema/docs under `data/canonical/`.
- Added `crawl_alio.py parse-v2`.
- Added generated canonical artifacts to `.gitignore`.
- Added compact SQLite canonical store builder:
  - `scripts/build_canonical_store.py`
  - Builds `data/canonical/alio_canonical.db` or selected item DBs directly from
    `rawdata/html` without requiring a full JSONL intermediate.
- Added canonical quality report:
  - `scripts/validate_canonical_store.py`
- Added runtime canonical query layer:
  - `src/open_alio_mcp/canonical_store.py`
- Added initial MCP canonical tools in `src/open_alio_mcp/server.py`:
  - `get_canonical_summary`
  - `search_canonical_records`
  - `get_canonical_attachments`
  - `search_canonical_text_rules`
- Added security input validation specs for canonical tools in
  `src/open_alio_mcp/security_utils.py`.
- Updated `tests/test_smoke.py` expected tool count from 33 to 37.
- Added tests:
  - `tests/test_parser_v2.py`
  - `tests/test_canonical_store.py`
  - `tests/test_metrics_from_canonical.py`
- Added canonical-to-metrics candidate builder:
  - `scripts/build_metrics_from_canonical.py`
  - Derives isolated v2 candidate metrics for `executive_pay`, `budget`, and
    `finance`.
  - Writes candidates to `data/canonical/metrics_v2/`.
  - Writes v1-vs-v2 comparison report to
    `data/validation_reports/canonical_v2_metrics_compare.json`.
- Updated transition docs:
  - `docs/parser_v2_transition_plan.md`
  - `data/canonical/README.md`
- Built targeted canonical DB for metric comparison:
  - Command:
    `python scripts/build_canonical_store.py --items 20501,31201,31301,31401 --out data/canonical/_metrics_seed_canonical.db`
  - Result after latest rebuild: 1,407 docs, 224,247 records, about 108 MB.
- Continued skipped conflict analysis from the canonical comparison report:
  - Inspected representative source HTML and canonical DB rows for
    `executive_pay`, `budget`, and `finance`.
  - Classified `executive_pay` and most `budget` conflicts as correction-table
    `수정 전`/`수정 후` duplicates.
  - Classified remaining budget conflicts as parser row-header inference issues
    in correction tables with multiple label columns.
  - Classified many finance conflicts as missing table-title/accounting-basis
    context, especially split fund-account context, parenthetical fund variants,
    K-IFRS/K-GAAP, old/new national accounting standards, and summary vs
    program-level tables.
- Updated `parse_alio_v2.py`:
  - Preserves split account context plus table title across adjacent
    `table.nb` blocks.
  - Treats `수정 전`/`수정 후` columns as correction value columns, preserving all
    preceding label columns in `row_header_path`.
- Updated `scripts/build_metrics_from_canonical.py`:
  - Filters superseded `수정 전` rows before grouping.
  - Preserves parenthetical fund-account context such as
    `공무원연금기금(연금충당부채 제외한 경우)`.
- Added v2-only `finance_context` candidate key in
  `scripts/build_metrics_from_canonical.py`, preserving normalized
  `table_title` in finance metric keys while leaving v1-compatible `finance`
  unchanged.
- Added tests for split account context, correction table label paths,
  correction-column filtering, parenthetical fund-account extraction, and
  finance table-title collision preservation.
- Updated `src/open_alio_mcp/metrics_store.py`:
  - `get_metrics(..., category="finance")` keeps v1-compatible `series`.
  - If `data/canonical/metrics_v2/finance_context.json` exists, default finance
    responses add `basis` metadata that identifies the representative
    table-title/accounting-basis context for each returned series.
  - Default responses do not include full context alternatives.  If a query only
    matches context-rich rows, the response returns those context-specific
    series and marks `basis.mode` as `context_query`.
- Added `tests/test_metrics_store.py` for default finance `basis` reporting and
  context-specific finance queries.
- Ran canonical-derived metrics comparison:
  - Command:
    `python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db`
  - Results:
    - `executive_pay`: 28,768 common v1/v2 points, 0 mismatches, 0 skipped
      canonical conflict groups, golden mismatch 0.
    - `budget`: 18,046 common v1/v2 points, 0 mismatches, 0 skipped canonical
      conflict groups, golden mismatch 0.
    - `finance`: 48,657 common v1/v2 points, 0 mismatches, 434 skipped
      canonical conflict groups, golden mismatch 0.
    - `finance_context`: 51,906 v2-only points, 0 skipped conflict groups,
      no v1 common-point comparison by design.
- Reviewed `docs/parser_v2_review_notes.md` after the latest parser-v2 work.
  Decision: do not treat `executive_pay`/`budget` conflict count 0 as a
  promotion-ready gate yet.  The review correctly reframes the next work around
  proving that the canonical parser accounts for all crawled HTML elements.
  The next session should address parser coverage/audit gaps before further
  finance key-design or category promotion work.

## Modified Major Files

New or modified by this parser-v2 work:

- `.gitignore`
- `crawl_alio.py`
- `parse_alio_v2.py`
- `data/canonical/README.md`
- `data/canonical/schema.json`
- `docs/parser_v2_transition_plan.md`
- `scripts/build_canonical_store.py`
- `scripts/validate_canonical_store.py`
- `scripts/build_metrics_from_canonical.py`
- `src/open_alio_mcp/canonical_store.py`
- `src/open_alio_mcp/metrics_store.py`
- `src/open_alio_mcp/server.py`
- `src/open_alio_mcp/security_utils.py`
- `tests/test_smoke.py`
- `tests/test_parser_v2.py`
- `tests/test_canonical_store.py`
- `tests/test_metrics_from_canonical.py`
- `tests/test_metrics_store.py`

Pre-existing unrelated or parallel work already present in the working tree
before/during this session and not owned by the parser-v2 work:

- `data/README.md`
- `data/_report_organ_counts.json`
- `data/reference/disclosure_coverage.json`
- `scripts/build_disclosure_coverage.py`
- `src/open_alio_mcp/disclosure_coverage.py`

Generated local artifacts, intentionally ignored:

- `data/canonical/*.jsonl`
- `data/canonical/*_summary.json`
- `data/canonical/*.db`
- `data/canonical/*.db-shm`
- `data/canonical/*.db-wal`
- `data/canonical/metrics_v2/`
- `data/validation_reports/canonical_v2_quality*.json`
- `data/validation_reports/canonical_v2_metrics*.json`

## Remaining Work

1. Parser coverage/audit gate is now implemented for the immediate review
   items:
   - skipped non-`border="1"` tables emit fallback `unparsed_table` records;
   - zero-record border tables emit `table_no_records` records;
   - short standalone `table.nb` notes emit `skipped_short_nb` records;
   - parser summaries and SQLite `source_docs` store per-document coverage
     counts.
2. Treat the remaining review items as near-term design tasks, but do not rush them
   into a half-schema:
   - `source_tables` / table-level entity, table IDs, header matrices, and
     dimensions should be designed deliberately before implementation;
   - deterministic `natural_key` should be added with schema/store/tests once
     table identity is settled;
   - `record_type` should be documented as a hint, and ambiguous tables should
     eventually become explicit/greppable rather than silently defaulting to a
     misleading real type.
3. Targeted canonical DB was rebuilt after the parser coverage change and the
   metric comparison still has 0 common-point mismatches.
4. Remaining `finance` skipped canonical conflict groups were analyzed:
   - Current count: 434 skipped groups.
   - All 434 are table-title/accounting-basis context collapses under the
     current v1-compatible key.
   - 418 are K-GAAP/K-IFRS/AUP, connected/separate, or statement-form variants.
   - 16 are old/new national accounting standard or program-level fund-table
     variants.
   - `executive_pay` and `budget` are still at 0 skipped groups in the targeted
     comparison.
5. A v2-only `finance_context` key shape is implemented:
   - it preserves normalized `table_title` as `table=...` in the metric key;
   - targeted output has 51,906 v2-only points and 0 skipped conflict groups;
   - it intentionally has no v1 common-point comparison because v1 runtime
     finance keys do not include table context.
6. Keep the v1-compatible `finance` candidate with 434 skipped conflicts for
   regression comparison.  Do not auto-select from those groups.
7. After any further logic change, re-run:
   - `python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db`
   - inspect `data/validation_reports/canonical_v2_metrics_compare.json`
8. Decide readiness criteria for promoting `executive_pay` and `budget`
   category-by-category only after the parser coverage/audit gate is in place.
9. Add more tests around any parser coverage and finance table-context key
   logic.
10. Eventually introduce v2-derived metrics behind a feature flag or isolated
   path, then simplify MCP data path once v2 reliability gates pass.
11. Do not leave a permanent v1/v2 dual stack after v2 is reliable.

## Important Design Decisions

- v1 parser and v1 local parsed data remain archived and are not overwritten.
- Canonical v2 is a transition/source-of-truth layer that preserves table
  structure before metrics are derived.
- Canonical MCP tools are transition/debug/inspection tools, not the intended
  permanent user-facing endpoint shape.
- Runtime querying should use compact SQLite rather than huge JSONL files.
- `data/metrics/*.json` is not overwritten by canonical-derived candidates.
  Candidates live under `data/canonical/metrics_v2/`.
- v2-derived metric comparison uses existing v1 promotion key functions where
  possible, by adapting canonical rows to v1 row shape.
- Conflict groups are skipped and reported; no automatic value choice is made
  when multiple values map to the same metric key/year.
- Current common v1-v2 points for `executive_pay`, `budget`, and `finance`
  have 0 mismatches. `executive_pay` and `budget` have 0 targeted conflict
  groups, but category promotion should still wait for explicit readiness
  criteria rather than relying on targeted comparisons alone.
- The immediate parser silent-loss auditability gate is implemented.  The
  finance key design now has a v2-only candidate path: `finance_context`
  preserves normalized table-title/accounting-basis context while the
  v1-compatible `finance` path keeps conflicts skipped for regression
  comparison.
- MCP `finance` remains a single public call path.  Default calls return the
  v1-compatible `series` plus lightweight `basis` metadata explaining the
  representative ALIO table context.  They do not attach all context
  alternatives by default.  Context-specific queries return retained
  `finance_context` rows only when the caller asks for that context in
  `item_query`.

## Tests Run And Results

Passed:

- `python -m compileall parse_alio_v2.py crawl_alio.py scripts\build_canonical_store.py scripts\validate_canonical_store.py src\open_alio_mcp\canonical_store.py src\open_alio_mcp\server.py src\open_alio_mcp\security_utils.py tests\test_parser_v2.py tests\test_canonical_store.py`
- `python -m compileall parse_alio_v2.py scripts\build_metrics_from_canonical.py tests\test_parser_v2.py tests\test_metrics_from_canonical.py`
- `python -m compileall src\open_alio_mcp\metrics_store.py tests\test_metrics_store.py`
- `python -c "import tests.test_parser_v2 as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('parser_v2 tests passed')"`
- `python -c "import tests.test_canonical_store as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('canonical_store tests passed')"`
- `python -c "import tests.test_metrics_from_canonical as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('metrics_from_canonical tests passed')"`
- `python -c "import tests.test_metrics_store as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('metrics_store tests passed')"`
- `python tests/test_smoke.py`
- `python scripts/build_canonical_store.py --items 20501,31201,31301,31401 --out data/canonical/_metrics_seed_canonical.db`
- `python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db`
- `python scripts/validate_canonical_store.py --db data/canonical/_metrics_seed_canonical.db --out data/validation_reports/canonical_v2_quality_metrics_seed.json --sample-limit 10`

Notes:

- `pytest` is not installed in the active Python or `.venv`, so tests were run
  by direct function invocation where needed.
- Manual real-data sample:
  `get_institution_metrics('C0005', 'finance', item_query='자산총계')` returned
  `basis.mode == "default_series"` and no `context_alternatives`; the context
  query `item_query='자산총계 K-IFRS'` returned `basis.mode == "context_query"`.
- `git status` emits warnings about inaccessible
  `C:\Users\bosun/.config/git/ignore`; this has not blocked work.

## Current Blockers

- No hard blocker.
- The finance key shape decision has an implemented candidate:
  `finance_context` preserves normalized table-title/accounting-basis context.
  The current MCP integration shape is: default `finance` call reports
  representative `basis`; context-specific `item_query` returns the retained
  context series.  The next decision is whether `basis` field names need further
  agent-facing polish, not conflict auto-selection.
- Need to avoid relying on chat history; inspect the actual report files, source
  HTML, canonical DB rows, and key code before changing finance key rules.

## Git Status Summary

Latest commit:

```text
8751a65 Archive v1 ALIO parser validation baseline
```

Current `git status --short` at handoff:

```text
 M .gitignore
 M crawl_alio.py
 M data/README.md
 M docs/parser_v2_transition_plan.md
 M src/open_alio_mcp/security_utils.py
 M src/open_alio_mcp/server.py
 M tests/test_smoke.py
?? .ai/
?? data/_report_organ_counts.json
?? data/canonical/
?? data/reference/disclosure_coverage.json
?? docs/parser_v2_review_notes.md
?? parse_alio_v2.py
?? scripts/build_canonical_store.py
?? scripts/build_disclosure_coverage.py
?? scripts/build_metrics_from_canonical.py
?? scripts/validate_canonical_store.py
?? src/open_alio_mcp/canonical_store.py
?? src/open_alio_mcp/disclosure_coverage.py
?? tests/test_canonical_store.py
?? tests/test_metrics_from_canonical.py
?? tests/test_parser_v2.py
```

`AGENTS.md` and root `CLAUDE.md` were not present at this handoff.  `.claude/`
directory exists.

## Next Session First Task

Open and inspect:

- `docs/parser_v2_transition_plan.md`
- `docs/parser_v2_review_notes.md`
- `data/canonical/README.md`
- `scripts/build_metrics_from_canonical.py`
- `data/validation_reports/canonical_v2_metrics_compare.json`
- `data/validation_reports/canonical_v2_quality_metrics_seed.json`

Then continue with finance readiness and MCP integration design, not parser
coverage:

1. Inspect the new `finance_context` candidate under
   `data/canonical/metrics_v2/finance_context.json`.
2. Confirm the latest comparison report:
   - `finance`: 48,657 common points, 0 mismatches, 434 skipped conflicts.
   - `finance_context`: 51,906 v2-only points, 0 skipped conflicts, no v1
     common-point comparison by design.
3. Review the current MCP finance response shape:
   - default calls keep the v1-compatible `series`;
   - default calls include `basis.mode == "default_series"` when context
     metadata can identify the representative ALIO table title;
   - context-specific queries such as `item_query="자산총계 K-IFRS"` return
     context-rich series and mark `basis.mode == "context_query"`;
   - full table-context alternatives are not returned by default.
4. Decide whether the `basis` metadata needs further shaping for agent
   ergonomics, for example `has_other_contexts`, `representative_context`, or a
   shorter human-facing note.
5. Keep `data/metrics/*.json` untouched.  If any parser or metric logic changes,
   rebuild and compare:

```powershell
python scripts/build_canonical_store.py --items 20501,31201,31301,31401 --out data/canonical/_metrics_seed_canonical.db
python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db
python -c "import tests.test_metrics_store as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('metrics_store tests passed')"
python -c "import tests.test_metrics_from_canonical as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('metrics_from_canonical tests passed')"
python -c "import tests.test_parser_v2 as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('parser_v2 tests passed')"
python -c "import tests.test_canonical_store as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('canonical_store tests passed')"
python tests/test_smoke.py
```

6. In parallel with finance readiness design, plan the deliberate schema work left by
   the parser review: `source_tables`, stable table IDs/header matrices,
   deterministic `natural_key`, and clearer `record_type` confidence or
   ambiguity handling.
