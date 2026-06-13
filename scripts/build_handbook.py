# -*- coding: utf-8 -*-
"""경영평가편람 PDF → data/handbook/*.json 빌드."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parse_handbook import build_document  # noqa: E402

SRC = ROOT / "rawdata" / "handbook"
OUT = ROOT / "data" / "handbook"
MANIFEST = SRC / "_manifest.json"


def slugify(name: str) -> str:
    s = re.sub(r"\.pdf$", "", name, flags=re.I)
    s = re.sub(r"[^\w가-힣]+", "_", s).strip("_")
    return s or "handbook"


def main() -> int:
    if not SRC.exists():
        SRC.mkdir(parents=True)
        print(f"[안내] {SRC} 생성 — PDF를 넣고 다시 실행하세요.")
        return 0

    manifest: dict = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    pdfs = sorted(p for p in SRC.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"[안내] {SRC}에 PDF가 없습니다.")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    skipped: list[str] = []

    for path in pdfs:
        try:
            print(f"[처리중] {path.name} — 페이지 추출·표 파싱 (수 분 소요 가능)...", flush=True)
            meta = manifest.get(path.name) or {}
            doc = build_document(path, meta=meta)
            doc_id = slugify(path.name)
            doc["doc_id"] = doc_id
            doc["built_at"] = datetime.now().isoformat(timespec="seconds")
            (OUT / f"{doc_id}.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            index.append(
                {
                    "doc_id": doc_id,
                    "title": doc.get("title"),
                    "year": doc.get("year"),
                    "kind": doc.get("kind"),
                    "source_file": path.name,
                    "page_count": doc.get("page_count"),
                    "weight_table_count": len(doc.get("weight_tables") or []),
                    "chunk_count": len(doc.get("chunks") or []),
                    "indicator_detail_count": len(doc.get("indicator_details") or []),
                }
            )
            print(
                f"[완료] {path.name} → {doc_id}.json "
                f"(표 {len(doc.get('weight_tables') or [])}, "
                f"청크 {len(doc.get('chunks') or [])}, "
                f"세부 {len(doc.get('indicator_details') or [])})",
                flush=True,
            )
        except Exception as e:  # noqa: BLE001
            skipped.append(path.name)
            print(f"[실패] {path.name}: {e}")

    (OUT / "_index.json").write_text(
        json.dumps(
            {"built_at": datetime.now().isoformat(timespec="seconds"), "docs": index, "skipped": skipped},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n총 {len(index)}건 적재 → {OUT}")
    return 0 if not skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
