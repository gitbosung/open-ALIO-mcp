"""Build a compact SQLite store for ALIO canonical parser v2 records."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parse_alio_v2 import (  # noqa: E402
    FIELDS,
    DocCoverage,
    _iter_docs,
    _rel,
    coverage_summary,
    load_org_names,
    parse_doc,
    split_csv,
)

DEFAULT_DB = ROOT / "data" / "canonical" / "alio_canonical.db"
DEFAULT_RAW_DIR = ROOT / "rawdata" / "html"


def _record_columns_sql() -> str:
    typed = {
        "table_index": "INTEGER NOT NULL",
        "row_index": "INTEGER",
        "col_index": "INTEGER",
        "normalized_value": "REAL",
    }
    cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for field in FIELDS:
        cols.append(f"{field} {typed.get(field, 'TEXT NOT NULL')}")
    return ",\n            ".join(cols)


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(
        f"""
        CREATE TABLE canonical_records (
            {_record_columns_sql()}
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE source_docs (
            org_code TEXT NOT NULL,
            org_name TEXT NOT NULL,
            item_no TEXT NOT NULL,
            item_name TEXT NOT NULL,
            as_of TEXT NOT NULL,
            source_html_path TEXT NOT NULL PRIMARY KEY,
            record_count INTEGER NOT NULL,
            tables_seen INTEGER NOT NULL,
            tables_with_records INTEGER NOT NULL,
            nb_blocks_seen INTEGER NOT NULL,
            nb_blocks_captured INTEGER NOT NULL,
            unparsed_elements INTEGER NOT NULL
        )
        """
    )
    return conn


def create_indexes(conn: sqlite3.Connection) -> None:
    indexes = (
        "CREATE INDEX idx_canonical_org_item ON canonical_records(org_code, item_no)",
        "CREATE INDEX idx_canonical_type ON canonical_records(record_type)",
        "CREATE INDEX idx_canonical_period ON canonical_records(period_year)",
        "CREATE INDEX idx_canonical_item_type ON canonical_records(item_no, record_type)",
        "CREATE INDEX idx_canonical_metric ON canonical_records(metric_label)",
        "CREATE INDEX idx_canonical_file ON canonical_records(file_name)",
        "CREATE INDEX idx_source_docs_org_item ON source_docs(org_code, item_no)",
    )
    for sql in indexes:
        conn.execute(sql)


def insert_records(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    placeholders = ",".join("?" for _ in FIELDS)
    conn.executemany(
        f"INSERT INTO canonical_records ({','.join(FIELDS)}) VALUES ({placeholders})",
        [[record.get(field) for field in FIELDS] for record in records],
    )


def build_store(
    *,
    raw_dir: Path = DEFAULT_RAW_DIR,
    out: Path = DEFAULT_DB,
    orgs: set[str] | None = None,
    items: set[str] | None = None,
    limit: int | None = None,
    batch_docs: int = 50,
) -> dict[str, Any]:
    org_names = load_org_names()
    conn = init_db(out)
    docs_seen = 0
    docs_with_records = 0
    record_count = 0
    record_types: Counter[str] = Counter()
    item_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    coverage_totals: Counter[str] = Counter()
    docs_with_unparsed_elements = 0

    try:
        conn.execute("BEGIN")
        for path, org_code, item_no in _iter_docs(raw_dir, orgs=orgs, items=items, limit=limit):
            docs_seen += 1
            rel_source = _rel(path)
            coverage = DocCoverage()
            records = parse_doc(
                path.read_text(encoding="utf-8"),
                org_code,
                item_no,
                org_names.get(org_code, ""),
                source_html_path=rel_source,
                coverage=coverage,
            )
            coverage_row = coverage.as_dict()
            coverage_totals.update(coverage_row)
            if coverage_row["unparsed_elements"] > 0:
                docs_with_unparsed_elements += 1
            if records:
                docs_with_records += 1
            insert_records(conn, records)
            record_count += len(records)
            for record in records:
                record_types[str(record["record_type"])] += 1
                item_counts[item_no] += 1
                for warning in str(record.get("parser_warning") or "").split(";"):
                    if warning:
                        warning_counts[warning] += 1
            item_name = records[0]["item_name"] if records else ""
            as_of = records[0]["as_of"] if records else ""
            conn.execute(
                """
                INSERT INTO source_docs
                    (org_code, org_name, item_no, item_name, as_of, source_html_path, record_count,
                     tables_seen, tables_with_records, nb_blocks_seen, nb_blocks_captured,
                     unparsed_elements)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    org_code,
                    org_names.get(org_code, ""),
                    item_no,
                    item_name,
                    as_of,
                    rel_source,
                    len(records),
                    coverage_row["tables_seen"],
                    coverage_row["tables_with_records"],
                    coverage_row["nb_blocks_seen"],
                    coverage_row["nb_blocks_captured"],
                    coverage_row["unparsed_elements"],
                ),
            )
            if docs_seen % max(batch_docs, 1) == 0:
                conn.commit()
                conn.execute("BEGIN")
        conn.commit()
        create_indexes(conn)
        summary = {
            "dataset": "alio_canonical_sqlite",
            "schema_version": "2.0.0",
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "raw_source_dir": _rel(raw_dir),
            "db": _rel(out),
            "docs_seen": docs_seen,
            "docs_with_records": docs_with_records,
            "docs_without_records": docs_seen - docs_with_records,
            "record_count": record_count,
            "record_type_counts": dict(sorted(record_types.items())),
            "item_counts": dict(sorted(item_counts.items())),
            "warning_counts": dict(sorted(warning_counts.items())),
            "element_coverage": coverage_summary(coverage_totals),
            "docs_with_unparsed_elements": docs_with_unparsed_elements,
        }
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [(key, json.dumps(value, ensure_ascii=False)) for key, value in summary.items()],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return summary | {"path": str(out), "bytes": out.stat().st_size if out.exists() else 0}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build data/canonical/alio_canonical.db")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_DB)
    parser.add_argument("--orgs", help="Comma-separated org codes, e.g. C0091,C0247")
    parser.add_argument("--items", help="Comma-separated item numbers, e.g. 31201,70301")
    parser.add_argument("--limit", type=int, help="Limit parsed documents after filters")
    args = parser.parse_args()

    summary = build_store(
        raw_dir=args.raw_dir,
        out=args.out,
        orgs=split_csv(args.orgs or "") or None,
        items=split_csv(args.items or "") or None,
        limit=args.limit,
    )
    print(f"[OK] wrote {summary['path']}")
    print(
        f"docs={summary['docs_seen']} records={summary['record_count']} "
        f"types={summary['record_type_counts']} bytes={summary['bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
