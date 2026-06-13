"""신규 항목 파싱 품질 점검 + C0247 재무 교차검증 (1회성)."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

with (ROOT / "data" / "crawl" / "alio_records.csv").open(encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

NEW_ITEMS = ["31201", "31301", "31801", "70461", "21801", "40211"]
by_item = defaultdict(list)
for r in rows:
    by_item[r["item_no"]].append(r)

for item in NEW_ITEMS:
    rs = [r for r in by_item[item] if r["apba_id"] == "C0247"] or by_item[item]
    if not rs:
        print(f"== {item}: 레코드 없음")
        continue
    secs = defaultdict(set)
    for r in rs:
        secs[r["section"]].add(r["row_label"])
    print(f"== {item} {rs[0]['item_name']} | unit={rs[0]['unit']} | {len(rs)}건")
    for s, labels in list(secs.items())[:3]:
        print(f"   [{s}] {sorted(labels)[:5]}")

# ── C0247(한전) 재무상태표 ↔ metrics/finance.json 교차검증 ──
fin = json.loads((ROOT / "data/metrics/finance.json").read_text(encoding="utf-8"))
series = fin["orgs"].get("C0247", {}).get("series", {})
print("\nfinance.json C0247 키 예시:", list(series.keys())[:6])

# 기존 xlsx는 '공기업_반기_재정현황' → 반기 기준 수치와 대조
crawl_fin = [r for r in rows if r["apba_id"] == "C0247" and r["item_no"] == "31201"
             and r["value"] and r["value_type"] == "반기" and r["section"].startswith("1.")]
checked = match = 0
for r in crawl_fin:
    label_tail = r["row_label"].split(" > ")[-1]
    for key, ser in series.items():
        if key.split(" | ")[-1].split(" > ")[-1] == label_tail:
            expect = ser.get(r["year"])
            if expect is None:
                continue
            try:
                got = float(r["value"])
            except ValueError:
                continue
            checked += 1
            if abs(got - expect) < 1e-6:
                match += 1
            else:
                print("불일치:", r["row_label"], r["year"], got, "!=", expect, f"({key})")
            break
print(f"재무상태표 교차검증: 대조 {checked} / 일치 {match}")
