# -*- coding: utf-8 -*-
"""rawdata/html/_organlist_{item}.json → data/reference/disclosure_coverage.json

ALIO 항목별 공시 보유 기관 목록을 MCP 런타임 참조본으로 승격한다.
크롤 완료 후 실행: python scripts/build_disclosure_coverage.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "rawdata" / "html"
ITEMS_JSON = ROOT / "data" / "items.json"
OUT = ROOT / "data" / "reference" / "disclosure_coverage.json"

# metric category → crawl item_no (finance는 상태표·손익 둘 다)
CATEGORY_ITEMS: dict[str, list[str]] = {
    "staff": ["20201"],
    "salary": ["20601"],
    "recruitment": ["20401"],
    "welfare": ["20801"],
    "welfare_etc": ["63701"],
    "head_expense": ["20701"],
    "work_life": ["21401"],
    "tax": ["32211"],
    "executive_pay": ["20501"],
    "budget": ["31401"],
    "finance": ["31201", "31301"],
}


def main() -> None:
    items_meta = json.loads(ITEMS_JSON.read_text(encoding="utf-8"))["items"]
    item_names = {str(it["item_no"]): it["item_name"] for it in items_meta}
    total_orgs = len(json.loads((ROOT / "data" / "institutions.json").read_text(encoding="utf-8"))["orgs"])

    by_item: dict[str, dict] = {}
    missing_lists: list[str] = []

    for it in items_meta:
        item_no = str(it["item_no"])
        ol = HTML / f"_organlist_{item_no}.json"
        if not ol.exists():
            missing_lists.append(item_no)
            continue
        disclosed = sorted(json.loads(ol.read_text(encoding="utf-8")).keys())
        by_item[item_no] = {
            "item_name": it["item_name"],
            "disclosed_count": len(disclosed),
            "disclosed_orgs": disclosed,
        }

    categories = {
        cat: {"item_nos": nos, "primary_item": nos[0]}
        for cat, nos in CATEGORY_ITEMS.items()
    }

    payload = {
        "_meta": {
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "source": "rawdata/html/_organlist_{item_no}.json (ALIO itemOrganListJung.json)",
            "total_orgs": total_orgs,
            "item_count": len(by_item),
            "build_cmd": "python scripts/build_disclosure_coverage.py",
            "caveats": [
                "disclosed_orgs는 ALIO가 해당 항목에 공시를 등록한 기관 목록이다.",
                "목록에 없으면 해당사항 없음·제도 비대상·평가 비참여·미제출 등 가능성이 있으며, '미공시'와 구분해 해석한다.",
                "공시 주기가 도래하지 않은 항목은 전 기관 0건일 수 있다 (예: 80202 장애인 고용 2분기).",
            ],
            "missing_organlists": missing_lists,
        },
        "items": by_item,
        "categories": categories,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT}")
    print(f"  items: {len(by_item)} / organlist missing: {len(missing_lists)}")
    if missing_lists:
        print(f"  missing: {', '.join(missing_lists)}")


if __name__ == "__main__":
    main()
