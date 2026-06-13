# -*- coding: utf-8 -*-
"""Offline security checks for MCP hardening.

실행:
    .venv\\Scripts\\python scripts\\security_smoke_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp import security_utils  # noqa: E402
from open_alio_mcp import server  # noqa: E402

FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if not ok:
        FAIL.append(name)
        if detail:
            print(f"        -> {detail}")


masked = security_utils.mask_sensitive_url(
    "https://apis.data.go.kr/test?serviceKey=placeholder-token&query=abc&OC=placeholder-oc"
)
check("mask_sensitive_url", "placeholder-token" not in masked and "serviceKey=***" in masked)

params, blocked = security_utils.build_query_params(
    {"pageNo": 1},
    {"serviceKey": "evil", "numOfRows": 999999, "query": "x"},
    {"serviceKey": "real", "resultType": "json"},
)
check(
    "reserved API params cannot override forced key",
    params["serviceKey"] == "real" and "serviceKey" in blocked and params["numOfRows"] == 999999,
)

r = server.search_institutions(query="x" * 101)
check("tool rejects overlong query", r.get("is_error") and "입력값 검증 실패" in r.get("error", ""), str(r)[:200])

r = server.search_facilities(page=0)
check("tool rejects invalid page", r.get("is_error") and "page" in r.get("error", ""), str(r)[:200])

r = server.search_recruitments(limit=999999)
check("tool rejects oversized limit", r.get("is_error") and "limit" in r.get("error", ""), str(r)[:200])

r = server.get_guideline_text(doc_id="../secret")
check("tool rejects path-like doc_id", r.get("is_error") and "경로" in r.get("error", ""), str(r)[:200])

limited = security_utils.limit_tool_response(
    {"data": {"items": [{"text": "a" * 2000} for _ in range(20)]}, "is_error": False},
    max_chars=1000,
    max_items=5,
)
limited_text = str(limited)
check("response limiter truncates large payload", len(limited_text) < 2000 and "truncated" in limited_text)

print()
if FAIL:
    print(f"FAILED: {len(FAIL)} -> {FAIL}")
    sys.exit(1)
print("ALL PASS")
