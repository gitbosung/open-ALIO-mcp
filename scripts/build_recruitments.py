# -*- coding: utf-8 -*-
"""진행중 채용공고 스냅샷 생성 → data/snapshots/recruitments_ongoing.json.

API 일일 한도·속도를 피하고, analyze_recruitments·search_recruitments(use_snapshot)에서
오프라인으로 빠르게 조회하기 위한 로컬 캐시.

실행: .venv/Scripts/python scripts/build_recruitments.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp.alio_client import (  # noqa: E402
    AlioAPIError,
    fetch_all_recruitments,
    normalize_recruitment,
)

OUT = ROOT / "data" / "snapshots" / "recruitments_ongoing.json"


def main() -> int:
    try:
        rows = fetch_all_recruitments(ongoing_yn="Y")
    except AlioAPIError as e:
        print(f"[ERROR] API 호출 실패: {e}")
        return 1

    records = [normalize_recruitment(r) for r in rows]
    payload = {
        "_meta": {
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "ongoing_only": True,
            "count": len(records),
            "source": "재정경제부_공공기관 채용정보 조회서비스 /list",
        },
        "recruitments": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {len(records)}건 → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
