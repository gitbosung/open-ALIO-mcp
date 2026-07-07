"""Query layer for ALIO canonical parser v2 SQLite data."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import data_provider

DEFAULT_REL_DB = "canonical/alio_canonical.db"
ENV_CANONICAL_DB = "OPEN_ALIO_CANONICAL_DB"

RECORD_TYPES = ("time_series", "roster", "attribute", "text_rule", "attachment")

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
COVERAGE_FIELDS = (
    "tables_seen",
    "tables_with_records",
    "nb_blocks_seen",
    "nb_blocks_captured",
    "unparsed_elements",
)

_local = threading.local()
_materialized_path: Path | None = None


class CanonicalStoreError(Exception):
    pass


def _repo_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _candidate_local_path() -> Path | None:
    env_path = os.environ.get(ENV_CANONICAL_DB)
    if env_path:
        path = Path(env_path)
        return path if path.is_file() else None

    desc = data_provider.describe()
    if desc.get("mode") == "local-dir" and desc.get("location"):
        path = Path(desc["location"]) / DEFAULT_REL_DB
        if path.is_file():
            return path

    path = _repo_data_dir() / DEFAULT_REL_DB
    if path.is_file():
        return path
    return None


def _materialize_from_provider() -> Path | None:
    global _materialized_path
    if _materialized_path and _materialized_path.is_file():
        return _materialized_path
    if not data_provider.exists(DEFAULT_REL_DB):
        return None
    raw = data_provider.read_bytes(DEFAULT_REL_DB)
    dest = Path(tempfile.gettempdir()) / "open_alio_canonical_v2.db"
    dest.write_bytes(raw)
    _materialized_path = dest
    return dest


def db_path() -> Path:
    path = _candidate_local_path() or _materialize_from_provider()
    if path is None:
        raise CanonicalStoreError(
            "canonical v2 SQLite store not found. Build it with "
            "`python scripts/build_canonical_store.py` or set OPEN_ALIO_CANONICAL_DB."
        )
    return path


def available() -> bool:
    try:
        db_path()
        return True
    except (CanonicalStoreError, OSError, sqlite3.Error):
        return False


def _conn() -> sqlite3.Connection:
    path = db_path()
    conn = getattr(_local, "conn", None)
    conn_path = getattr(_local, "path", None)
    if conn is None or conn_path != path:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
        _local.path = path
    return conn


def close() -> None:
    """Close the thread-local SQLite connection, mainly for tests and rebuilds."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None
    _local.path = None


def _rows(sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[dict]:
    return [dict(row) for row in _conn().execute(sql, params)]


def _meta() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in _rows("SELECT key, value FROM meta"):
        try:
            out[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError:
            out[row["key"]] = row["value"]
    return out


def _source_docs_where(org_code: str = "", item_no: str = "") -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if org_code:
        clauses.append("org_code = ?")
        params.append(org_code)
    if item_no:
        clauses.append("item_no = ?")
        params.append(item_no)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def _source_docs_has_coverage() -> bool:
    columns = {row["name"] for row in _rows("PRAGMA table_info(source_docs)")}
    return set(COVERAGE_FIELDS).issubset(columns)


def _source_doc_coverage(org_code: str = "", item_no: str = "") -> dict[str, int]:
    if not _source_docs_has_coverage():
        return {}
    where, params = _source_docs_where(org_code=org_code, item_no=item_no)
    row = _conn().execute(
        f"""
        SELECT
            COALESCE(SUM(tables_seen), 0) AS tables_seen,
            COALESCE(SUM(tables_with_records), 0) AS tables_with_records,
            COALESCE(SUM(nb_blocks_seen), 0) AS nb_blocks_seen,
            COALESCE(SUM(nb_blocks_captured), 0) AS nb_blocks_captured,
            COALESCE(SUM(unparsed_elements), 0) AS unparsed_elements,
            COUNT(CASE WHEN unparsed_elements > 0 THEN 1 END) AS docs_with_unparsed_elements
        FROM source_docs
        {where}
        """,
        params,
    ).fetchone()
    coverage = {field: int(row[field]) for field in COVERAGE_FIELDS}
    coverage["tables_without_records"] = max(
        coverage["tables_seen"] - coverage["tables_with_records"], 0
    )
    coverage["nb_blocks_uncaptured"] = max(
        coverage["nb_blocks_seen"] - coverage["nb_blocks_captured"], 0
    )
    coverage["docs_with_unparsed_elements"] = int(row["docs_with_unparsed_elements"])
    return coverage


def _where(
    *,
    org_code: str = "",
    item_no: str = "",
    record_type: str = "",
    period_year: str = "",
    metric_query: str = "",
    text_query: str = "",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if org_code:
        clauses.append("org_code = ?")
        params.append(org_code)
    if item_no:
        clauses.append("item_no = ?")
        params.append(item_no)
    if record_type:
        if record_type not in RECORD_TYPES:
            raise CanonicalStoreError(f"unknown record_type: {record_type}")
        clauses.append("record_type = ?")
        params.append(record_type)
    if period_year:
        clauses.append("period_year = ?")
        params.append(period_year)
    if metric_query:
        like = f"%{metric_query}%"
        clauses.append(
            """
            (metric_label LIKE ? OR row_header_path LIKE ? OR col_header_path LIKE ?
             OR section_title LIKE ? OR table_title LIKE ?)
            """
        )
        params.extend([like, like, like, like, like])
    if text_query:
        like = f"%{text_query}%"
        clauses.append(
            """
            (text_value LIKE ? OR raw_value LIKE ? OR section_title LIKE ?
             OR table_title LIKE ? OR row_header_path LIKE ? OR col_header_path LIKE ?)
            """
        )
        params.extend([like, like, like, like, like, like])
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def summary(org_code: str = "", item_no: str = "") -> dict:
    where, params = _where(org_code=org_code, item_no=item_no)
    record_types = _rows(
        f"""
        SELECT record_type, COUNT(*) AS count
        FROM canonical_records
        {where}
        GROUP BY record_type
        ORDER BY count DESC
        """,
        params,
    )
    items = _rows(
        f"""
        SELECT item_no, MAX(item_name) AS item_name, COUNT(*) AS count,
               COUNT(DISTINCT org_code) AS org_count
        FROM canonical_records
        {where}
        GROUP BY item_no
        ORDER BY count DESC
        LIMIT 100
        """,
        params,
    )
    warnings = _rows(
        f"""
        SELECT parser_warning, COUNT(*) AS count
        FROM canonical_records
        {where + (' AND ' if where else ' WHERE ')} parser_warning <> ''
        GROUP BY parser_warning
        ORDER BY count DESC
        LIMIT 50
        """,
        params,
    )
    doc_where, doc_params = _source_docs_where(org_code=org_code, item_no=item_no)
    doc_count = _conn().execute(
        f"SELECT COUNT(*) FROM source_docs{doc_where}", doc_params
    ).fetchone()[0]
    total = _conn().execute(
        f"SELECT COUNT(*) FROM canonical_records {where}", params
    ).fetchone()[0]
    return {
        "available": True,
        "db_path": str(db_path()),
        "meta": _meta(),
        "filters": {"org_code": org_code, "item_no": item_no},
        "doc_count": doc_count,
        "record_count": total,
        "record_type_counts": record_types,
        "item_counts": items,
        "warning_counts": warnings,
        "element_coverage": _source_doc_coverage(org_code=org_code, item_no=item_no),
    }


def query_records(
    *,
    org_code: str = "",
    item_no: str = "",
    record_type: str = "",
    period_year: str = "",
    metric_query: str = "",
    limit: int = 50,
) -> dict:
    limit = max(1, min(limit, 200))
    where, params = _where(
        org_code=org_code,
        item_no=item_no,
        record_type=record_type,
        period_year=period_year,
        metric_query=metric_query,
    )
    total = _conn().execute(f"SELECT COUNT(*) FROM canonical_records {where}", params).fetchone()[0]
    rows = _rows(
        f"""
        SELECT id, {','.join(FIELDS)}
        FROM canonical_records
        {where}
        ORDER BY org_code, item_no, table_index, row_index, col_index, id
        LIMIT ?
        """,
        params + [limit],
    )
    return {
        "filters": {
            "org_code": org_code,
            "item_no": item_no,
            "record_type": record_type,
            "period_year": period_year,
            "metric_query": metric_query,
        },
        "total": total,
        "count": len(rows),
        "records": rows,
    }


def attachments(
    *,
    org_code: str = "",
    item_no: str = "",
    period_year: str = "",
    limit: int = 50,
) -> dict:
    limit = max(1, min(limit, 200))
    where, params = _where(
        org_code=org_code,
        item_no=item_no,
        record_type="attachment",
        period_year=period_year,
    )
    total = _conn().execute(f"SELECT COUNT(*) FROM canonical_records {where}", params).fetchone()[0]
    rows = _rows(
        f"""
        SELECT org_code, org_name, item_no, item_name, as_of, section_title, table_title,
               row_header_path, col_header_path, period_year, raw_value, file_name,
               file_href, source_html_path, parser_warning
        FROM canonical_records
        {where}
        ORDER BY org_code, item_no, period_year, table_index, row_index, col_index, id
        LIMIT ?
        """,
        params + [limit],
    )
    return {"total": total, "count": len(rows), "attachments": rows}


def text_rules(
    *,
    org_code: str = "",
    item_no: str = "",
    query: str = "",
    limit: int = 50,
) -> dict:
    limit = max(1, min(limit, 200))
    where, params = _where(
        org_code=org_code,
        item_no=item_no,
        record_type="text_rule",
        text_query=query,
    )
    total = _conn().execute(f"SELECT COUNT(*) FROM canonical_records {where}", params).fetchone()[0]
    rows = _rows(
        f"""
        SELECT org_code, org_name, item_no, item_name, as_of, section_title, table_title,
               row_header_path, col_header_path, metric_label, raw_value, text_value,
               source_html_path, parser_warning
        FROM canonical_records
        {where}
        ORDER BY org_code, item_no, table_index, row_index, col_index, id
        LIMIT ?
        """,
        params + [limit],
    )
    return {"total": total, "count": len(rows), "text_rules": rows}
