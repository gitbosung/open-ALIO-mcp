# -*- coding: utf-8 -*-
"""Validate subsidiary institution fields in data/institutions.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTITUTIONS = ROOT / "data" / "institutions.json"
GOLDEN = ROOT / "data" / "reference" / "subsidiary_orgs.json"

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"FAIL: {message}")


def ok(message: str) -> None:
    print(f"OK: {message}")


def _pair(org: dict) -> tuple[str, str | None]:
    return (org.get("name") or "", org.get("parent_org_name"))


def _has_cycle(code: str, by_code: dict[str, dict]) -> bool:
    seen: set[str] = set()
    cur = code
    while cur:
        if cur in seen:
            return True
        seen.add(cur)
        cur = by_code.get(cur, {}).get("parent_org_code")
    return False


def main() -> int:
    data = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    orgs = data["orgs"]
    meta = data.get("_meta", {})
    by_code = {o["org_code"]: o for o in orgs if o.get("org_code")}
    by_name = {o["name"]: o for o in orgs if o.get("name")}
    subsidiaries = [o for o in orgs if o.get("is_subsidiary")]

    golden_pairs = {
        (row["name"], row["parent_org_name"])
        for row in golden["subsidiaries"]
    }
    actual_pairs = {_pair(o) for o in subsidiaries}

    if meta.get("subsidiary_count") != len(subsidiaries):
        fail(f"_meta.subsidiary_count {meta.get('subsidiary_count')} != actual {len(subsidiaries)}")
    else:
        ok(f"subsidiary_count={len(subsidiaries)}")

    independent = len(orgs) - len(subsidiaries)
    if meta.get("independent_org_count") != independent:
        fail(f"_meta.independent_org_count {meta.get('independent_org_count')} != actual {independent}")
    else:
        ok(f"independent_org_count={independent}")

    failures = meta.get("parent_resolve_failures") or []
    if failures:
        fail(f"parent_resolve_failures not empty: {failures[:5]}")
    else:
        ok("parent_resolve_failures=0")

    if actual_pairs != golden_pairs:
        missing = sorted(golden_pairs - actual_pairs)
        extra = sorted(actual_pairs - golden_pairs)
        fail(f"golden subsidiary list mismatch missing={missing} extra={extra}")
    else:
        ok("golden subsidiary list matches")

    for org in orgs:
        is_sub = bool(org.get("is_subsidiary"))
        parent_name = org.get("parent_org_name")
        parent_code = org.get("parent_org_code")
        detail_parent = (org.get("detail") or {}).get("parent_org") if isinstance(org.get("detail"), dict) else None

        if is_sub != bool(parent_name):
            fail(f"{org.get('name')}: is_subsidiary/parent_org_name mismatch")
        if is_sub:
            if detail_parent != parent_name:
                fail(f"{org.get('name')}: detail.parent_org not synced")
            if not parent_code or parent_code not in by_code:
                fail(f"{org.get('name')}: parent_org_code unresolved")
            if parent_name not in by_name:
                fail(f"{org.get('name')}: parent_org_name not found in institutions")
            parent = by_code.get(parent_code, {})
            if org.get("classification_org_type") != parent.get("org_type"):
                fail(
                    f"{org.get('name')}: classification_org_type "
                    f"{org.get('classification_org_type')} != parent org_type {parent.get('org_type')}"
                )
        else:
            if parent_code is not None:
                fail(f"{org.get('name')}: non-subsidiary has parent_org_code")
            if org.get("classification_org_type") != org.get("org_type"):
                fail(f"{org.get('name')}: non-subsidiary classification_org_type changed")

        if _has_cycle(org.get("org_code"), by_code):
            fail(f"{org.get('name')}: parent cycle detected")

    if not FAILURES:
        ok("subsidiary fields valid")
        return 0
    print(f"\nFAILED: {len(FAILURES)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
