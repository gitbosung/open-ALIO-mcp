from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp import canonical_store  # noqa: E402
from scripts.build_canonical_store import build_store  # noqa: E402


HTML = """
<div id="doc-">
  <p class="cover-title"><a class="toc">49-2. 수의계약</a></p>
  <table class="nb"><tr><td>(2026년 1/4분기)</td></tr></table>
  <p class="SECTION-1"><a class="toc">수의계약</a></p>
  <table border="1">
    <tr><td>연도</td><td>첨부파일</td></tr>
    <tr>
      <td>2024년</td>
      <td><a href="javascript:report_attach_down('2024년 수의 계약.xlsx')">다운로드</a></td>
    </tr>
  </table>
  <p class="SECTION-1"><a class="toc">계약 기준</a></p>
  <table border="1">
    <tr><td>사유</td><td>근거규정</td></tr>
    <tr><td>긴급 계약</td><td>계약규정 제1조</td></tr>
  </table>
</div>
"""


def test_canonical_sqlite_store_queries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        raw_dir = base / "raw"
        raw_dir.mkdir()
        (raw_dir / "C0000_70301__doc.html").write_text(HTML, encoding="utf-8")
        db = base / "canonical.db"

        summary = build_store(raw_dir=raw_dir, out=db)
        assert summary["docs_seen"] == 1
        assert summary["record_count"] == 2
        assert summary["element_coverage"]["tables_seen"] == 2
        assert summary["element_coverage"]["tables_with_records"] == 2
        assert summary["element_coverage"]["nb_blocks_seen"] == 1
        assert summary["element_coverage"]["nb_blocks_captured"] == 1

        conn = sqlite3.connect(db)
        try:
            source_doc = conn.execute(
                """
                SELECT tables_seen, tables_with_records, nb_blocks_seen,
                       nb_blocks_captured, unparsed_elements
                FROM source_docs
                """
            ).fetchone()
        finally:
            conn.close()
        assert source_doc == (2, 2, 1, 1, 0)

        old_env = os.environ.get("OPEN_ALIO_CANONICAL_DB")
        os.environ["OPEN_ALIO_CANONICAL_DB"] = str(db)
        try:
            got = canonical_store.summary()
            assert got["record_count"] == 2
            assert canonical_store.attachments(item_no="70301")["count"] == 1
            assert canonical_store.text_rules(query="계약규정")["count"] == 1
            assert canonical_store.query_records(record_type="attachment")["records"][0]["file_name"] == "2024년 수의 계약.xlsx"
        finally:
            canonical_store.close()
            if old_env is None:
                os.environ.pop("OPEN_ALIO_CANONICAL_DB", None)
            else:
                os.environ["OPEN_ALIO_CANONICAL_DB"] = old_env
