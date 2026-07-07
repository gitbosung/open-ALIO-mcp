# Next Session Prompt

Continue the work in this repository.

First, read these files. If a file does not exist, note that and continue.

- `AGENTS.md`
- `CLAUDE.md`
- `.ai/SESSION_STATE.md`
- `.ai/NEXT_PROMPT.md`
- `docs/parser_v2_transition_plan.md`
- `docs/parser_v2_review_notes.md`
- `data/canonical/README.md`

Then run:

```powershell
git status --short
git log -1 --oneline
```

Do not rely on conversation memory. Verify uncertain details by opening actual
files, reports, DB rows, generated candidates, and source HTML in the
workspace.

Current context:

- This is the ALIO parser v2 transition.
- The v1 parser/data archive must remain preserved.
- The parser coverage/audit gate from `docs/parser_v2_review_notes.md` has been
  implemented for the immediate silent-drop paths.
- Targeted canonical DB exists at
  `data/canonical/_metrics_seed_canonical.db`.
- `scripts/build_metrics_from_canonical.py` emits `finance_context`, a v2-only
  context-preserving candidate:
  - 51,906 v2-only points
  - 0 skipped conflicts
  - metric keys preserve normalized `table_title` as `table=...`
- Existing `finance` remains the v1-compatible comparison candidate:
  - 48,657 common points
  - 0 mismatches
  - 434 skipped conflicts
- MCP finance lookup is now one-call friendly:
  - callers still use `get_institution_metrics(category="finance")`;
  - normal `series` remains v1-compatible;
  - when `data/canonical/metrics_v2/finance_context.json` exists, default
    responses include lightweight `basis` metadata that identifies the
    representative ALIO table context for each returned series;
  - default responses do not attach full table-context alternatives;
  - if a caller asks for a specific context in `item_query` (for example
    `K-GAAP`, `K-IFRS`, or a table-title keyword), the lookup returns matching
    context-specific series and sets `basis.mode` to `context_query`.

Start with this task:

1. Inspect `src/open_alio_mcp/metrics_store.py`, especially
   `_finance_context_lookup`, `_finance_default_basis`,
   `_finance_context_series`, and `get_metrics`.
2. Inspect `tests/test_metrics_store.py`.
3. Manually sample `get_institution_metrics(category="finance")` on one or two
   real institutions:
   - a default query such as `item_query="자산총계"` should return normal
     `series`, `basis.mode == "default_series"`, and no
     `context_alternatives`;
   - a context-specific query such as `item_query="자산총계 K-IFRS"` should
     return context-rich series and `basis.mode == "context_query"`.
4. Decide next integration step:
   - keep `basis` as the public finance ambiguity pattern;
   - refine `basis` names/fields if the current structure is too raw;
   - optionally add a dedicated helper later only if callers need explicit
     discovery of all available accounting/table contexts.
5. Do not overwrite `data/metrics/*.json`.
6. If any parser or metric logic changes, rerun:

```powershell
python scripts/build_canonical_store.py --items 20501,31201,31301,31401 --out data/canonical/_metrics_seed_canonical.db
python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db
python -c "import tests.test_metrics_store as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('metrics_store tests passed')"
python -c "import tests.test_metrics_from_canonical as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('metrics_from_canonical tests passed')"
python -c "import tests.test_parser_v2 as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('parser_v2 tests passed')"
python -c "import tests.test_canonical_store as t; [getattr(t, name)() for name in dir(t) if name.startswith('test_')]; print('canonical_store tests passed')"
python tests/test_smoke.py
```

Rules:

- Do not auto-select values from v1-compatible finance conflict groups.
- Do not promote `executive_pay` or `budget` solely because targeted conflicts
  are 0; define readiness criteria first.
- Keep the longer-term parser review design items deliberate: `source_tables`,
  stable table IDs/header matrices, deterministic `natural_key`, and clearer
  `record_type` confidence or ambiguity handling.
- Once v2 is reliable enough, the final direction is to simplify the MCP data
  path. Do not leave a permanent v1/v2 dual stack.
