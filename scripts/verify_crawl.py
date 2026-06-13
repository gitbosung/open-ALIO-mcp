"""크롤링 CSV ↔ 기존 xlsx 기반 metrics 교차검증 (임원연봉, C0847)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

xlsx = json.loads((ROOT / "data/metrics/executive_pay.json").read_text(encoding="utf-8"))

with (ROOT / "data" / "crawl" / "alio_records.csv").open(encoding="utf-8-sig") as f:
    rows = [r for r in csv.DictReader(f)
            if r["item_no"] == "20501" and r["row_label"] not in ("비고", "해당사항 없음")]

match = diff = missing = 0
for r in rows:
    series = xlsx["orgs"].get(r["apba_id"], {}).get("series", {})
    key = f"{r['section']} | {r['row_label']}"
    if key not in series:
        missing += 1
        continue
    expect = series[key].get(r["year"])
    got = float(r["value"]) if r["value"] else 0.0  # xlsx 빌드는 빈값을 0으로 적재
    if expect is not None and abs(got - expect) < 1e-9:
        match += 1
    else:
        diff += 1
        print("불일치:", r["apba_id"], key, r["year"], got, "!=", expect)

print(f"일치 {match} / 불일치 {diff} / xlsx에 없는 키 {missing}")
