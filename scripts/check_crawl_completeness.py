# -*- coding: utf-8 -*-
"""크롤 완료도: _organlist에 있으나 __doc.html 없는 (기관×항목) 0건 확인."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "rawdata" / "html"


def main() -> int:
    orgs = json.loads((ROOT / "data/institutions.json").read_text(encoding="utf-8"))["orgs"]
    items = json.loads((ROOT / "data/items.json").read_text(encoding="utf-8"))["items"]
    names = {o["org_code"]: o["name"] for o in orgs}

    missing: list[tuple[str, str, str]] = []
    for it in items:
        ino = str(it["item_no"])
        ol = HTML / f"_organlist_{ino}.json"
        if ol.exists():
            disclosed = set(json.loads(ol.read_text(encoding="utf-8")).keys())
        else:
            disclosed = {o["org_code"] for o in orgs}
        for o in orgs:
            aid = o["org_code"]
            if aid in disclosed and not (HTML / f"{aid}_{ino}__doc.html").exists():
                missing.append((aid, ino, names[aid]))

    docs = list(HTML.glob("*__doc.html"))
    shells = list(HTML.glob("*__shell.html"))
    failed = HTML / "_failed.log"

    print(f"기관 {len(orgs)} × 항목 {len(items)}")
    print(f"__doc.html: {len(docs)}  __shell.html: {len(shells)}")
    print(f"누락(공시목록 O, doc X): {len(missing)}")

    if missing:
        for aid, ino, name in missing[:30]:
            print(f"  MISSING  {aid} × {ino}  ({name})")
        if len(missing) > 30:
            print(f"  ... 외 {len(missing) - 30}건")

    if failed.exists():
        lines = failed.read_text(encoding="utf-8").strip().splitlines()
        recent = [ln for ln in lines[-20:] if "doc_request_failed" in ln or "shell_request_failed" in ln]
        if recent:
            print(f"\n[주의] _failed.log 최근 요청 실패 {len(recent)}건 (재크롤 검토)")
            for ln in recent[-5:]:
                print(f"  {ln}")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
