from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.build_canonical_store import build_store  # noqa: E402
from scripts.build_metrics_from_canonical import (  # noqa: E402
    build_metric,
    extract_sub_account,
    finance_context_key,
)
from scripts.promote_crawl_metrics import executive_pay_key, finance_key  # noqa: E402


HTML = """
<div id="doc-">
  <p class="cover-title"><a class="toc">10. 임원 연봉</a></p>
  <table class="nb"><tr><td>(2026년 1/4분기)</td></tr></table>
  <p class="SECTION-1"><a class="toc">임원 연봉 내역</a></p>
  <table class="nb"><tr><td style="font-weight: bold;">상임기관장</td><td>(단위: 천원)</td></tr></table>
  <table border="1">
    <thead><tr><td>구분</td><td>2024년 결산</td></tr></thead>
    <tbody><tr><td>기본급</td><td>100</td></tr></tbody>
  </table>
  <table class="nb"><tr><td style="font-weight: bold;">비상임이사</td><td>(단위: 천원)</td></tr></table>
  <table border="1">
    <thead><tr><td>구분</td><td>2024년 결산</td></tr></thead>
    <tbody><tr><td>기본급</td><td>10</td></tr></tbody>
  </table>
</div>
"""


def test_executive_pay_uses_table_title_as_metric_section() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        raw_dir = base / "raw"
        raw_dir.mkdir()
        (raw_dir / "C0000_20501__doc.html").write_text(HTML, encoding="utf-8")
        db = base / "canonical.db"
        build_store(raw_dir=raw_dir, out=db)

        result = build_metric(
            db_path=db,
            category="executive_pay",
            label="임원 연봉",
            unit="천원",
            item_nos={"20501"},
            key_fn=executive_pay_key,
        )

        assert result["conflicts"] == []
        series = result["data"]["orgs"]["C0000"]["series"]
        assert series["상임기관장 | 기본급"]["2024"] == 100
        assert series["비상임이사 | 기본급"]["2024"] == 10


def test_correction_before_column_is_not_promoted() -> None:
    html = """
    <div id="doc-">
      <p class="cover-title"><a class="toc">10. 임원 연봉</a></p>
      <table border="1">
        <thead>
          <tr><td>항목명</td><td>수정 전</td><td>수정 후</td><td>수정사유</td></tr>
        </thead>
        <tbody>
          <tr><td>상임기관장-2026년 예산-기본급</td><td>100</td><td>200</td><td>정정</td></tr>
        </tbody>
      </table>
    </div>
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        raw_dir = base / "raw"
        raw_dir.mkdir()
        (raw_dir / "C0000_20501__doc.html").write_text(html, encoding="utf-8")
        db = base / "canonical.db"
        build_store(raw_dir=raw_dir, out=db)

        result = build_metric(
            db_path=db,
            category="executive_pay",
            label="임원 연봉",
            unit="천원",
            item_nos={"20501"},
            key_fn=executive_pay_key,
        )

        assert result["conflicts"] == []
        series = result["data"]["orgs"]["C0000"]["series"]
        assert series[" | 상임기관장-2026년 예산-기본급"]["2026"] == 200


def test_finance_context_key_preserves_table_title_collisions() -> None:
    html = """
    <div id="doc-">
      <p class="cover-title"><a class="toc">33. 요약 재무상태표</a></p>
      <p class="SECTION-1"><a class="toc">1. 고유사업</a></p>
      <table class="nb"><tr><td style="font-weight: bold;">요약 재무상태표(K-IFRS)</td><td>(단위: 백만원)</td></tr></table>
      <table border="1">
        <thead><tr><td>구분</td><td>2024년 결산</td></tr></thead>
        <tbody><tr><td>자산총계</td><td>100</td></tr></tbody>
      </table>
      <table class="nb"><tr><td style="font-weight: bold;">요약 재무상태표(K-GAAP)</td><td>(단위: 백만원)</td></tr></table>
      <table border="1">
        <thead><tr><td>구분</td><td>2024년 결산</td></tr></thead>
        <tbody><tr><td>자산총계</td><td>200</td></tr></tbody>
      </table>
    </div>
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        raw_dir = base / "raw"
        raw_dir.mkdir()
        (raw_dir / "C0000_31201__doc.html").write_text(html, encoding="utf-8")
        db = base / "canonical.db"
        build_store(raw_dir=raw_dir, out=db)

        compatible = build_metric(
            db_path=db,
            category="finance",
            label="finance",
            unit="million",
            item_nos={"31201"},
            key_fn=finance_key,
        )
        contextual = build_metric(
            db_path=db,
            category="finance_context",
            label="finance context",
            unit="million",
            item_nos={"31201"},
            key_fn=finance_context_key,
        )

        assert len(compatible["conflicts"]) == 1
        assert contextual["conflicts"] == []
        series = contextual["data"]["orgs"]["C0000"]["series"]
        assert len(series) == 2
        assert any("table=요약 재무상태표(K-IFRS)" in key for key in series)
        assert any("table=요약 재무상태표(K-GAAP)" in key for key in series)


def test_extract_sub_account_keeps_parenthetical_context() -> None:
    assert (
        extract_sub_account("요약 재정상태표 기금계정: 공무원연금기금(연금충당부채 제외한 경우) (단위: 백만원)")
        == "공무원연금기금(연금충당부채 제외한 경우)"
    )
    assert (
        extract_sub_account("요약 재정운영표 기금계정: 공무원연금기금 | 프로그램별 재정운용표 (단위: 백만원)")
        == "공무원연금기금"
    )
