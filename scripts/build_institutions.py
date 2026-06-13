# -*- coding: utf-8 -*-
"""NKOD API 기관 목록 + 일반현황 CSV 병합 → data/institutions.json

- PK: org_code (instCd, API)
- CSV(rawdata/csv/일반현황_2026.csv)는 instCd가 없어 기관명으로 조인
- 실행: .venv/Scripts/python scripts/build_institutions.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp.alio_client import fetch_all_institutions, normalize_institution  # noqa: E402

CSV_PATH = ROOT / "rawdata" / "csv" / "일반현황_2026.csv"
OUT_PATH = ROOT / "data" / "institutions.json"

# CSV 본문에 포함된 줄바꿈 치환 코드
CR_TOKEN = "&cr;"

CSV_DETAIL_FIELDS = {
    "설립근거": "legal_basis",
    "설립목적": "purpose",
    "주요기능 및 역할": "functions",
    "기관연혁": "history",
    "경영목표 및 전략": "goals",
    "기관장": "head",
    "기관장 임기": "head_term",
    "기관장 주요경력": "head_career",
    "사업자번호": "biz_reg_no",
    "상위기관": "parent_org",
}


def clean(text: str | None) -> str | None:
    if not text:
        return None
    t = text.replace(CR_TOKEN, "\n").strip()
    return t if t and t != "-" else None


def enrich_subsidiary_fields(institutions: list[dict]) -> tuple[int, list[dict]]:
    """Add subsidiary/parent fields used by MCP responses and statistics."""
    name_to_code = {
        (inst.get("name") or "").strip(): inst.get("org_code")
        for inst in institutions
        if inst.get("name") and inst.get("org_code")
    }
    code_to_org = {
        inst.get("org_code"): inst
        for inst in institutions
        if inst.get("org_code")
    }

    failures: list[dict] = []
    subsidiary_count = 0
    for inst in institutions:
        detail = inst.get("detail") or {}
        parent_name = clean(detail.get("parent_org")) if isinstance(detail, dict) else None
        if parent_name:
            subsidiary_count += 1
            parent_code = name_to_code.get(parent_name)
            inst["is_subsidiary"] = True
            inst["parent_org_name"] = parent_name
            inst["parent_org_code"] = parent_code
            if isinstance(detail, dict):
                detail["parent_org"] = parent_name
            if not parent_code:
                failures.append({"name": inst.get("name"), "parent_org_name": parent_name})
        else:
            inst["is_subsidiary"] = False
            inst["parent_org_name"] = None
            inst["parent_org_code"] = None

        parent = code_to_org.get(inst.get("parent_org_code"))
        if inst["is_subsidiary"] and parent:
            inst["classification_org_type"] = parent.get("org_type") or inst.get("org_type")
        else:
            inst["classification_org_type"] = inst.get("org_type")

    return subsidiary_count, failures


def main() -> None:
    rows = fetch_all_institutions()
    institutions = [normalize_institution(r) for r in rows]
    print(f"API institutions: {len(institutions)}")

    csv_map: dict[str, dict] = {}
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            csv_map[row["기관명"].strip()] = row

    joined = 0
    for inst in institutions:
        c = csv_map.get((inst.get("name") or "").strip())
        if not c:
            inst["detail"] = None
            continue
        joined += 1
        inst["detail"] = {
            en: clean(c.get(ko)) for ko, en in CSV_DETAIL_FIELDS.items()
        }

    subsidiary_count, parent_resolve_failures = enrich_subsidiary_fields(institutions)
    if parent_resolve_failures:
        print(f"WARN parent resolve failures: {len(parent_resolve_failures)}")
        for failure in parent_resolve_failures[:10]:
            print(f"  {failure['name']} -> {failure['parent_org_name']}")

    out = {
        "_meta": {
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "api": "재정경제부_공공기관 정보 조회서비스 /list",
            "csv": CSV_PATH.relative_to(ROOT).as_posix(),
            "count": len(institutions),
            "csv_joined": joined,
            "subsidiary_count": subsidiary_count,
            "independent_org_count": len(institutions) - subsidiary_count,
            "parent_resolve_failures": parent_resolve_failures,
        },
        "orgs": institutions,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"written {OUT_PATH} (joined {joined}/{len(institutions)}, "
        f"subsidiaries {subsidiary_count}, independent {len(institutions) - subsidiary_count})"
    )


if __name__ == "__main__":
    main()
