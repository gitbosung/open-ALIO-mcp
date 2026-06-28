from __future__ import annotations

from parse_alio_v2 import parse_doc, parse_doc_with_coverage


def test_v2_time_series_expands_header_paths() -> None:
    html = """
    <div id="doc-">
      <p class="cover-title"><a class="toc">33. 요약 재무상태표</a></p>
      <table class="nb"><tr><td>(2026년 1/4분기)</td></tr></table>
      <p class="SECTION-1"><a class="toc">2. 기금계정</a></p>
      <table class="nb"><tr><td>요약 재정상태표 기금계정: 테스트기금 (단위: 백만원)</td></tr></table>
      <table border="1">
        <thead><tr><td colspan="2">구분</td><td>2024년 결산</td></tr></thead>
        <tbody>
          <tr><td rowspan="2">자산</td><td>유동자산</td><td>1,234</td></tr>
          <tr><td>자산총계</td><td>-</td></tr>
        </tbody>
      </table>
    </div>
    """

    rows = parse_doc(html, "C0000", "31201", "테스트기관", source_html_path="rawdata/html/test.html")

    assert rows[0]["record_type"] == "time_series"
    assert rows[0]["row_header_path"] == "자산 > 유동자산"
    assert rows[0]["col_header_path"] == "2024년 결산"
    assert rows[0]["period_year"] == "2024"
    assert rows[0]["period_type"] == "결산"
    assert rows[0]["normalized_value"] == 1234
    assert rows[0]["unit"] == "백만원"
    assert rows[1]["row_header_path"] == "자산 > 자산총계"
    assert rows[1]["normalized_value"] is None


def test_v2_attachment_records_keep_file_metadata() -> None:
    html = """
    <div id="doc-">
      <p class="cover-title"><a class="toc">49-2. 수의계약</a></p>
      <p class="SECTION-1"><a class="toc">수의계약</a></p>
      <table border="1">
        <tr><td>연도</td><td>첨부파일</td></tr>
        <tr>
          <td>2024년</td>
          <td><a href="javascript:report_attach_down('2024년 수의 계약.xlsx')">다운로드</a></td>
        </tr>
      </table>
    </div>
    """

    rows = parse_doc(html, "C0000", "70301", "테스트기관")

    assert len(rows) == 1
    assert rows[0]["record_type"] == "attachment"
    assert rows[0]["row_header_path"] == "2024년"
    assert rows[0]["col_header_path"] == "첨부파일"
    assert rows[0]["period_year"] == "2024"
    assert rows[0]["file_name"] == "2024년 수의 계약.xlsx"
    assert rows[0]["file_href"].startswith("javascript:report_attach_down")


def test_v2_combines_split_account_context_with_table_title() -> None:
    html = """
    <div id="doc-">
      <p class="cover-title"><a class="toc">34. 요약 손익계산서</a></p>
      <p class="SECTION-1"><a class="toc">2. 기금계정</a></p>
      <table class="nb">
        <tr><td>요약 재정운영표(구 국가회계기준)</td></tr>
        <tr><td>기금계정:</td><td>테스트기금(특수조건)</td></tr>
      </table>
      <table class="nb"><tr><td>프로그램별 재정운용표</td><td>(단위: 백만원)</td></tr></table>
      <table border="1">
        <thead><tr><td>구분</td><td>2024년 결산</td></tr></thead>
        <tbody><tr><td>프로그램순원가</td><td>100</td></tr></tbody>
      </table>
    </div>
    """

    rows = parse_doc(html, "C0000", "31301", "테스트기관")

    assert len(rows) == 1
    assert "테스트기금(특수조건)" in rows[0]["table_title"]
    assert "프로그램별 재정운용표" in rows[0]["table_title"]
    assert " | " in rows[0]["table_title"]


def test_v2_correction_table_keeps_all_label_columns() -> None:
    html = """
    <div id="doc-">
      <p class="cover-title"><a class="toc">37. 수입 지출 현황</a></p>
      <table border="1">
        <thead><tr><td colspan="2">항목명</td><td>수정 전</td><td>수정 후</td><td>수정사유</td></tr></thead>
        <tbody>
          <tr><td rowspan="2">수입*지출 현황 (2026년 예산)</td><td>보조금</td><td>100</td><td>200</td><td>정정</td></tr>
          <tr><td>소계</td><td>300</td><td>400</td><td>정정</td></tr>
        </tbody>
      </table>
    </div>
    """

    rows = parse_doc(html, "C0000", "31401", "테스트기관")

    assert [row["row_header_path"] for row in rows] == [
        "수입*지출 현황 (2026년 예산) > 보조금",
        "수입*지출 현황 (2026년 예산) > 보조금",
        "수입*지출 현황 (2026년 예산) > 소계",
        "수입*지출 현황 (2026년 예산) > 소계",
    ]
    assert [row["col_header_path"] for row in rows] == ["수정 전", "수정 후", "수정 전", "수정 후"]


def test_v2_audits_previously_silent_drop_paths() -> None:
    html = """
    <div id="doc-">
      <table class="nb"><tr><td>short standalone note</td></tr></table>
      <table><tr><td>non-border table data</td></tr></table>
      <table border="1"><tbody><tr></tr></tbody></table>
    </div>
    """

    rows, coverage = parse_doc_with_coverage(html, "C0000", "99999", "Test Org")
    warnings = {warning for row in rows for warning in row["parser_warning"].split(";") if warning}

    assert "skipped_short_nb" in warnings
    assert "unparsed_table" in warnings
    assert "non_border_table" in warnings
    assert "table_no_records" in warnings
    assert coverage == {
        "tables_seen": 2,
        "tables_with_records": 2,
        "nb_blocks_seen": 1,
        "nb_blocks_captured": 1,
        "unparsed_elements": 3,
    }


def test_v2_text_rule_classification() -> None:
    html = """
    <div id="doc-">
      <p class="cover-title"><a class="toc">14. 기타 복리후생제도</a></p>
      <p class="SECTION-1"><a class="toc">1. 휴직급여</a></p>
      <table border="1">
        <tr><td>사유</td><td>급여 지급기준</td><td>근거규정</td></tr>
        <tr><td>업무상 공상</td><td>통상임금 전액</td><td>보수규정 제8조</td></tr>
      </table>
    </div>
    """

    rows = parse_doc(html, "C0000", "63701", "테스트기관")

    assert {row["record_type"] for row in rows} == {"text_rule"}
    assert rows[0]["row_header_path"] == "업무상 공상"
    assert rows[0]["col_header_path"] == "급여 지급기준"
    assert rows[1]["col_header_path"] == "근거규정"
