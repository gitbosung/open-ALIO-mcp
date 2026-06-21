# v1 HTML Long Parser Snapshot

Created: 2026-06-21

This directory preserves the current ALIO HTML parser baseline before the v2
canonical parser/storage redesign.

## Contents

- `parse_alio.py`: tracked copy of the v1 parser.
- `data/alio_records.csv`: local-only ignored copy of the v1 parsed CSV.
- `data/alio_records.json`: local-only ignored copy of the v1 parsed JSON.
- `checksums.sha256`: hashes for the parser and parsed outputs.

The `data/` directory is intentionally ignored by Git because the parsed outputs
are large generated artifacts:

- `alio_records.csv`: 257,556,028 bytes
- `alio_records.json`: 420,776,731 bytes

## Why This Exists

The v1 parser flattens ALIO HTML tables into:

```text
apba_id, org_name, item_no, item_name, section, sub_account,
row_label, col_label, year, value_type, value, unit, as_of, source_url
```

That works reasonably well for numeric annual time-series tables, but it loses
structure for roster, attachment, text-rule, and complex multi-axis tables.

The v2 work should start from already-crawled HTML (`rawdata/html`) and build a
canonical layer that preserves table meaning before deriving MCP-optimized
metrics.

## Related Reports

See:

- `data/validation_reports/rawdata_vs_crawl_findings.md`
- `data/validation_reports/rawdata_vs_crawl_full_audit.md`
- `data/validation_reports/rawdata_vs_crawl_full_audit.json`
- `data/validation_reports/crawl_csv_json_consistency.json`

