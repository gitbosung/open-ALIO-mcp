"""Validate and summarize the ALIO canonical v2 SQLite store."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "canonical" / "alio_canonical.db"
DEFAULT_OUT = ROOT / "data" / "validation_reports" / "canonical_v2_quality.json"
COVERAGE_FIELDS = {
    "tables_seen",
    "tables_with_records",
    "nb_blocks_seen",
    "nb_blocks_captured",
    "unparsed_elements",
}


def _dict_rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params)]


def _source_docs_has_coverage(conn: sqlite3.Connection) -> bool:
    conn.row_factory = sqlite3.Row
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_docs)")}
    return COVERAGE_FIELDS.issubset(columns)


def validate_store(db_path: Path, *, sample_limit: int = 20) -> dict:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        meta = {
            row["key"]: json.loads(row["value"])
            for row in _dict_rows(conn, "SELECT key, value FROM meta")
        }
        record_type_counts = _dict_rows(
            conn,
            """
            SELECT record_type, COUNT(*) AS count
            FROM canonical_records
            GROUP BY record_type
            ORDER BY count DESC
            """,
        )
        item_counts = _dict_rows(
            conn,
            """
            SELECT item_no, MAX(item_name) AS item_name, COUNT(*) AS count
            FROM canonical_records
            GROUP BY item_no
            ORDER BY count DESC
            LIMIT 100
            """,
        )
        warning_counts = _dict_rows(
            conn,
            """
            SELECT parser_warning, COUNT(*) AS count
            FROM canonical_records
            WHERE parser_warning <> ''
            GROUP BY parser_warning
            ORDER BY count DESC
            LIMIT 100
            """,
        )
        checks = {
            "time_series_missing_period_year": conn.execute(
                """
                SELECT COUNT(*)
                FROM canonical_records
                WHERE record_type = 'time_series' AND period_year = ''
                """
            ).fetchone()[0],
            "time_series_non_numeric": conn.execute(
                """
                SELECT COUNT(*)
                FROM canonical_records
                WHERE record_type = 'time_series'
                  AND normalized_value IS NULL
                  AND raw_value NOT IN ('', '-')
                """
            ).fetchone()[0],
            "attachment_missing_file_name": conn.execute(
                """
                SELECT COUNT(*)
                FROM canonical_records
                WHERE record_type = 'attachment' AND file_name = '' AND raw_value <> '해당사항 없음'
                """
            ).fetchone()[0],
            "records_with_no_header_detected": conn.execute(
                """
                SELECT COUNT(*)
                FROM canonical_records
                WHERE parser_warning LIKE '%no_header_detected%'
                """
            ).fetchone()[0],
            "docs_without_records": conn.execute(
                "SELECT COUNT(*) FROM source_docs WHERE record_count = 0"
            ).fetchone()[0],
        }
        if _source_docs_has_coverage(conn):
            checks.update(
                {
                    "tables_without_records": conn.execute(
                        """
                        SELECT COALESCE(SUM(tables_seen - tables_with_records), 0)
                        FROM source_docs
                        """
                    ).fetchone()[0],
                    "nb_blocks_uncaptured": conn.execute(
                        """
                        SELECT COALESCE(SUM(nb_blocks_seen - nb_blocks_captured), 0)
                        FROM source_docs
                        """
                    ).fetchone()[0],
                    "unparsed_elements": conn.execute(
                        "SELECT COALESCE(SUM(unparsed_elements), 0) FROM source_docs"
                    ).fetchone()[0],
                    "docs_with_unparsed_elements": conn.execute(
                        "SELECT COUNT(*) FROM source_docs WHERE unparsed_elements > 0"
                    ).fetchone()[0],
                }
            )
        samples = {
            "time_series_missing_period_year": _dict_rows(
                conn,
                """
                SELECT org_code, item_no, item_name, section_title, table_index,
                       row_header_path, col_header_path, raw_value, source_html_path
                FROM canonical_records
                WHERE record_type = 'time_series' AND period_year = ''
                LIMIT ?
                """,
                (sample_limit,),
            ),
            "attachment_missing_file_name": _dict_rows(
                conn,
                """
                SELECT org_code, item_no, item_name, row_header_path, col_header_path,
                       raw_value, source_html_path
                FROM canonical_records
                WHERE record_type = 'attachment' AND file_name = '' AND raw_value <> '해당사항 없음'
                LIMIT ?
                """,
                (sample_limit,),
            ),
            "docs_without_records": _dict_rows(
                conn,
                """
                SELECT org_code, item_no, item_name, source_html_path
                FROM source_docs
                WHERE record_count = 0
                LIMIT ?
                """,
                (sample_limit,),
            ),
        }
        if _source_docs_has_coverage(conn):
            samples["docs_with_unparsed_elements"] = _dict_rows(
                conn,
                """
                SELECT org_code, item_no, item_name, source_html_path, record_count,
                       tables_seen, tables_with_records, nb_blocks_seen,
                       nb_blocks_captured, unparsed_elements
                FROM source_docs
                WHERE unparsed_elements > 0
                LIMIT ?
                """,
                (sample_limit,),
            )
    finally:
        conn.close()
    return {
        "_meta": {
            "dataset": "canonical_v2_quality",
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "db": str(db_path),
        },
        "store_meta": meta,
        "record_type_counts": record_type_counts,
        "top_item_counts": item_counts,
        "warning_counts": warning_counts,
        "checks": checks,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ALIO canonical v2 SQLite store")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample-limit", type=int, default=20)
    args = parser.parse_args()

    report = validate_store(args.db, sample_limit=max(args.sample_limit, 1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {args.out}")
    print(json.dumps(report["checks"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
