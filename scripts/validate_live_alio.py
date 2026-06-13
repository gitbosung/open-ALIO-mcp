# -*- coding: utf-8 -*-
"""2단계: 라이브 ALIO fetch ↔ 캐시 HTML ↔ CSV 교차검증."""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawl_alio import DELAY, RAW_DIR, doc_path, fetch_pair  # noqa: E402
from parse_alio import parse_doc  # noqa: E402

SEEDS_FILE = ROOT / "data/reference/live_validation_seeds.json"
GOLDEN_FILE = ROOT / "data/reference/golden_samples.json"
CSV_FILE = ROOT / "data" / "crawl" / "alio_records.csv"

FAILURES: list[str] = []
WARNINGS: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL: {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"  WARN: {msg}")


def ok(msg: str) -> None:
    print(f"  OK: {msg}")


def norm_rows(recs: list[dict]) -> set[tuple]:
    out: set[tuple] = set()
    for r in recs:
        out.add((
            r.get("section", ""),
            r.get("row_label", ""),
            str(r.get("year", "")),
            r.get("value_type", ""),
            str(r.get("value", "")),
            r.get("unit", ""),
        ))
    return out


def load_csv_by_stem() -> dict[str, list[dict]]:
    by_stem: dict[str, list[dict]] = defaultdict(list)
    if not CSV_FILE.exists():
        return by_stem
    for r in csv.DictReader(CSV_FILE.open(encoding="utf-8-sig")):
        stem = f"{r['apba_id']}_{r['item_no']}"
        by_stem[stem].append(r)
    return by_stem


def check_golden(by_stem: dict[str, list[dict]]) -> None:
    print("\n[golden] golden_samples.json ↔ CSV")
    if not GOLDEN_FILE.exists():
        warn("golden_samples.json 없음 — 스킵")
        return
    data = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    samples = data.get("samples", [])
    if not samples:
        warn("golden samples 0건 — ALIO 화면 확인 후 data/reference/golden_samples.json 추가")
        return

    for s in samples:
        stem = f"{s['apba_id']}_{s['item_no']}"
        rows = by_stem.get(stem, [])
        matches = [
            r for r in rows
            if r.get("section", "") == s.get("section", "")
            and r.get("row_label") == s["row_label"]
            and r.get("year") == str(s["year"])
            and (r.get("value_type") or "") == (s.get("value_type") or "")
        ]
        if not matches:
            fail(f"golden {stem} {s['row_label']} {s['year']}: CSV에 해당 row 없음")
            continue
        vals = {r["value"] for r in matches}
        expect = str(s["value"])
        if expect in vals:
            ok(f"golden {stem} {s['row_label']} {s['year']} = {expect}")
        else:
            fail(f"golden {stem} {s['row_label']} {s['year']}: expect={expect} csv={vals}")


def main() -> int:
    import requests

    print("=" * 60)
    print("ALIO live validation (tier 2)")
    print("=" * 60)

    seeds_data = json.loads(SEEDS_FILE.read_text(encoding="utf-8"))
    seeds = seeds_data["seeds"]
    inst = json.loads((ROOT / "data/institutions.json").read_text(encoding="utf-8"))
    names = {o["org_code"]: o["name"] for o in inst["orgs"]}
    by_stem = load_csv_by_stem()

    session = requests.Session()
    live_cache_match = live_csv_match = cache_csv_match = 0
    live_cache_diff = live_csv_diff = cache_csv_diff = 0

    print(f"\n[live] {len(seeds)}건 live fetch (DELAY={DELAY}s)")
    for i, seed in enumerate(seeds):
        apba_id = seed["apba_id"]
        item_no = str(seed["item_no"])
        stem = f"{apba_id}_{item_no}"
        name = names.get(apba_id, "")

        cache_path = doc_path(apba_id, item_no)
        if not cache_path.exists():
            fail(f"{stem}: 캐시 __doc.html 없음 — 1단계 크롤 먼저")
            continue

        if i > 0:
            time.sleep(DELAY)

        pair = fetch_pair(session, apba_id, item_no)
        if pair is None:
            fail(f"{stem}: live fetch 실패")
            continue
        _shell, live_html = pair
        cache_html = cache_path.read_text(encoding="utf-8")

        live_rows = parse_doc(live_html, apba_id, item_no, name)
        cache_rows = parse_doc(cache_html, apba_id, item_no, name)
        csv_rows = by_stem.get(stem, [])

        live_set = norm_rows(live_rows)
        cache_set = norm_rows(cache_rows)
        csv_set = norm_rows(csv_rows)

        if live_set == cache_set:
            live_cache_match += 1
            ok(f"{stem}: live = cache ({len(live_set)} tuples)")
        else:
            live_cache_diff += 1
            only_live = live_set - cache_set
            only_cache = cache_set - live_set
            warn(f"{stem}: live ≠ cache (+live={len(only_live)} +cache={len(only_cache)}) — ALIO 갱신 또는 재크롤 필요")

        if cache_set == csv_set:
            cache_csv_match += 1
        else:
            cache_csv_diff += 1
            fail(f"{stem}: cache ≠ CSV — parse 후 CSV 미동기화? `crawl_alio.py parse` 재실행")

        if live_set == csv_set:
            live_csv_match += 1
        else:
            live_csv_diff += 1
            if live_set != cache_set:
                warn(f"{stem}: live ≠ CSV (live≠cache이므로 재크롤·재파싱 후 재검증)")

    print(f"\n[summary] live=cache {live_cache_match}/{len(seeds)}  cache=csv {cache_csv_match}/{len(seeds)}  live=csv {live_csv_match}/{len(seeds)}")

    check_golden(by_stem)

    print("\n" + "=" * 60)
    print(f"FAILURES: {len(FAILURES)}  WARNINGS: {len(WARNINGS)}")
    for f in FAILURES[:10]:
        print(" !", f)
    if FAILURES:
        return 1
    print("PASSED (warnings only)" if WARNINGS else "ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
