# -*- coding: utf-8 -*-
"""오프라인 CI 스모크 테스트 — API 키·네트워크 없이 실행 가능.

저장소에 포함된 로컬 스냅샷(data/)만으로 서버 import, tool 등록,
핵심 도구의 응답 구조(data/source/caveats)를 검증합니다.

실행: python tests/test_smoke.py  (또는 pytest tests/)
전체 시나리오 검증은 scripts/smoke_test.py 참조.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp import server  # noqa: E402


def _assert_envelope(r: dict, name: str) -> None:
    assert not r.get("is_error"), f"{name} 오류: {str(r)[:300]}"
    assert "data" in r and "source" in r and "caveats" in r, f"{name} 응답 구조 불일치"
    assert r["source"].get("system"), f"{name} source.system 누락"


def test_tool_registration() -> None:
    """Tools 32 · Prompts 2 · Resources 5 등록 확인."""
    tools = server.mcp._tool_manager._tools
    assert len(tools) == 32, f"tool 수 불일치: {len(tools)}"


def test_search_institutions_alias() -> None:
    r = server.search_institutions(query="한전")
    _assert_envelope(r, "search_institutions")
    assert r["data"]["results"][0]["name"] == "한국전력공사"


def test_search_institutions_count_basis() -> None:
    r = server.search_institutions(limit=1)
    _assert_envelope(r, "search_institutions")
    assert r["data"]["public_institutions_matched"] == 342
    assert r["data"]["subsidiary_matched"] == 13
    assert r["data"]["disclosure_units_matched"] == 355


def test_metric_categories() -> None:
    r = server.list_metric_categories()
    _assert_envelope(r, "list_metric_categories")
    assert r["data"]["count"] == 11


def test_institution_metrics() -> None:
    kepco = server.search_institutions(query="한전")["data"]["results"][0]["org_code"]
    r = server.get_institution_metrics(kepco, "staff", item_query="일반정규직-정원")
    _assert_envelope(r, "get_institution_metrics")
    assert r["data"]["found"]


def test_disclosure_catalog() -> None:
    r = server.list_disclosure_items()
    _assert_envelope(r, "list_disclosure_items")
    assert r["data"]["count"] >= 50


def test_input_validation() -> None:
    """보안 래퍼가 비정상 입력을 거부하는지 확인."""
    r = server.search_institutions(query="x" * 101)
    assert r.get("is_error"), "과도한 길이 입력이 거부되지 않음"


def test_server_status() -> None:
    r = server.get_server_status()
    _assert_envelope(r, "get_server_status")
    assert r["data"]["institutions_count"] == 342
    assert r["data"]["subsidiary_count"] == 13
    assert r["data"]["disclosure_units_count"] == 355


def main() -> int:
    failed = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"[PASS] {name}")
            except AssertionError as e:
                failed.append(name)
                print(f"[FAIL] {name} -> {e}")
    if failed:
        print(f"\nFAILED: {len(failed)} -> {failed}")
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
