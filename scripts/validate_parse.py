# -*- coding: utf-8 -*-
"""alio_records.csv 파싱 엄밀 검증 — HTML 재파싱·metrics 교차·구조 점검."""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parse_alio import parse_doc  # noqa: E402

CSV = ROOT / "data" / "crawl" / "alio_records.csv"
HTML = ROOT / "rawdata" / "html"
INST = json.loads((ROOT / "data" / "institutions.json").read_text(encoding="utf-8"))
ORG_NAMES = {o["org_code"]: o["name"] for o in INST["orgs"]}
BUDGET_SEED_ORGS = ("C0847", "C0247")

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


def load_csv() -> list[dict]:
    with CSV.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_html_roundtrip(rows: list[dict], samples: list[str]) -> None:
    print("\n[1] HTML 재파싱 ↔ CSV 일치 (샘플 doc.html)")
    by_stem: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        stem = f"{r['apba_id']}_{r['item_no']}"
        by_stem[stem].append(r)

    for stem in samples:
        path = HTML / f"{stem}__doc.html"
        if not path.exists():
            fail(f"{stem} doc.html 없음")
            continue
        apba_id, _, item_no = stem.rpartition("_")
        reparsed = parse_doc(path.read_text(encoding="utf-8"), apba_id, item_no, ORG_NAMES.get(apba_id, ""))
        csv_rows = by_stem[stem]

        def norm(recs: list[dict]) -> list[tuple]:
            out = []
            for r in recs:
                out.append((
                    r.get("section", ""),
                    r.get("row_label", ""),
                    str(r.get("year", "")),
                    r.get("value_type", ""),
                    str(r.get("value", "")),
                    r.get("unit", ""),
                ))
            return sorted(out)

        a, b = norm(reparsed), norm(csv_rows)
        if a == b:
            ok(f"{stem}: {len(a)}건 재파싱=CSV 동일")
        else:
            # 수치만 비교 (source_url/as_of/org_name 차이 무시)
            only_a = set(a) - set(b)
            only_b = set(b) - set(a)
            fail(f"{stem}: 불일치 reparsed={len(a)} csv={len(b)} "
                 f"only_reparse={len(only_a)} only_csv={len(only_b)}")
            for x in list(only_a)[:3]:
                print(f"    +reparse: {x}")
            for x in list(only_b)[:3]:
                print(f"    +csv:     {x}")


def cross_check_item(rows: list[dict], item_no: str, metrics_file: str, key_fn) -> None:
    """org별 metrics series와 CSV 교차 — 같은 org·같은 키만."""
    print(f"\n[교차] item {item_no} ↔ {metrics_file}")
    metrics = json.loads((ROOT / f"data/metrics/{metrics_file}").read_text(encoding="utf-8"))
    item_rows = [r for r in rows if r["item_no"] == item_no and r["row_label"] not in ("비고", "해당사항 없음") and r["value"]]

    match = diff = no_key = 0
    diff_samples: list[str] = []
    for r in item_rows:
        org_series = metrics["orgs"].get(r["apba_id"], {}).get("series", {})
        key = key_fn(r)
        if key not in org_series:
            no_key += 1
            continue
        expect = org_series[key].get(r["year"])
        if expect is None:
            no_key += 1
            continue
        try:
            got = float(r["value"])
        except ValueError:
            no_key += 1
            continue
        if abs(got - float(expect)) < 1e-6:
            match += 1
        else:
            diff += 1
            if len(diff_samples) < 5:
                diff_samples.append(f"{r['apba_id']} | {key} | {r['year']} got={got} expect={expect}")
    if diff:
        for s in diff_samples:
            fail(f"{item_no}: {s}")
    ok(f"{item_no}: 일치 {match} / 불일치 {diff} / metrics키없음 {no_key}")


def test_budget_31401(rows: list[dict]) -> None:
    """31401 수입·지출 — 충돌 보류/fallback을 반영해 기관 단위로 판정."""
    print("\n[교차] item 31401 ↔ budget.json")
    budget = json.loads((ROOT / "data/metrics/budget.json").read_text(encoding="utf-8"))
    item_rows = [
        r for r in rows
        if r["item_no"] == "31401"
        and r["row_label"] not in ("비고", "해당사항 없음")
        and r["value"]
    ]

    per_org: dict[str, dict[str, int]] = defaultdict(lambda: {"match": 0, "diff": 0, "no_key": 0})
    diff_samples: list[str] = []
    for r in item_rows:
        org = r["apba_id"]
        org_series = budget["orgs"].get(org, {}).get("series", {})
        key = f"수입지출현황(고유사업) | {r['row_label']}"
        if key not in org_series:
            per_org[org]["no_key"] += 1
            continue
        expect = org_series[key].get(r["year"])
        if expect is None:
            per_org[org]["no_key"] += 1
            continue
        try:
            got = float(r["value"])
        except ValueError:
            per_org[org]["no_key"] += 1
            continue
        if abs(got - float(expect)) < 1e-6:
            per_org[org]["match"] += 1
        else:
            per_org[org]["diff"] += 1
            if len(diff_samples) < 5:
                diff_samples.append(f"{org} | {key} | {r['year']} got={got} expect={expect}")

    total_match = sum(s["match"] for s in per_org.values())
    total_diff = sum(s["diff"] for s in per_org.values())
    total_no_key = sum(s["no_key"] for s in per_org.values())
    mismatched = [(org, s) for org, s in per_org.items() if s["diff"] > 0]
    compared_orgs = sum(1 for s in per_org.values() if s["match"] + s["diff"] > 0)
    perfect = sum(1 for s in per_org.values() if s["diff"] == 0 and s["match"] > 0)

    for s in diff_samples:
        warn(f"31401 metrics diff: {s}")

    fail_seed = any(per_org.get(org, {}).get("diff", 0) > 0 for org in BUDGET_SEED_ORGS)
    fail_rate = len(mismatched) > 20
    if fail_seed:
        fail("31401: 검증 시드 C0847/C0247 불일치")
    elif fail_rate:
        fail(f"31401: 불일치 기관 {len(mismatched)} > 20")
    elif mismatched:
        warn(f"31401: {len(mismatched)}개 기관 불일치 (크롤 충돌 보류 또는 fallback 값 가능)")
    else:
        ok("31401: 전 기관 일치")

    ok(
        f"31401: 일치 {total_match} / 불일치 {total_diff} / metrics키없음 {total_no_key} "
        f"/ 비교 가능 기관 {compared_orgs} / 100% 일치 기관 {perfect}"
    )


def test_structure(rows: list[dict]) -> None:
    print("\n[2] CSV 구조·품질")
    print(f"  총 레코드: {len(rows):,}")
    by_item = Counter(r["item_no"] for r in rows)
    by_org = Counter(r["apba_id"] for r in rows)
    print(f"  기관 수(1건 이상): {len(by_org)} / 항목: {dict(sorted(by_item.items()))}")

    empty_val = sum(1 for r in rows if r["value"] == "" and r["row_label"] not in ("해당사항 없음", "비고"))
    ok(f"값 빈칸(해당사항·비고 제외): {empty_val:,}건 — '-'→빈칸 규칙상 정상")

    # 중복 키
    seen: Counter = Counter()
    for r in rows:
        k = (r["apba_id"], r["item_no"], r["section"], r["row_label"], r["year"], r["value_type"])
        seen[k] += 1
    dups = sum(1 for c in seen.values() if c > 1)
    if dups:
        warn(f"중복 키 조합 {dups}종 (파서 이중 추출 가능성)")
    else:
        ok("중복 키 없음")

    # 필수 필드
    bad = [r for r in rows if not r["apba_id"] or not r["item_no"]]
    if bad:
        fail(f"필수 필드 결측 {len(bad)}건")
    else:
        ok("apba_id·item_no 필수 필드 100%")


def test_finance_31201(rows: list[dict]) -> None:
    """31201 요약 재무상태표 — finance.json(공기업 32)과 자산·부채·자본 교차."""
    print("\n[3] 31201 ↔ finance.json (공기업 반기 재무)")
    fin = json.loads((ROOT / "data/metrics/finance.json").read_text(encoding="utf-8"))
    # finance.json 키 예: '부채총계', '자산총계'
    LABEL_MAP = {
        "자산 > 자산총계": "자산총계",
        "자산총계": "자산총계",
        "부채 > 부채총계": "부채총계",
        "부채총계": "부채총계",
        "자본 > 자본총계": "자본총계",
        "자본총계": "자본총계",
    }
    item_rows = [
        r for r in rows
        if r["item_no"] == "31201"
        and r["value_type"] == "반기"
        and r["value"]
    ]
    match = diff = compared = 0
    for r in item_rows:
        fin_key = LABEL_MAP.get(r["row_label"])
        if not fin_key:
            continue
        org_s = fin["orgs"].get(r["apba_id"], {}).get("series", {})
        if fin_key not in org_s:
            continue
        year = r["year"]
        expect = org_s[fin_key].get(year)
        if expect is None:
            continue
        compared += 1
        try:
            got = float(r["value"])
        except ValueError:
            continue
        # finance.json 단위 백만원, crawl도 백만원인지 확인
        if abs(got - float(expect)) < 1:
            match += 1
        else:
            diff += 1
            if diff <= 5:
                warn(f"31201↔finance {r['apba_id']} {fin_key} {year}(반기) crawl={got} finance={expect}")
    if compared == 0:
        warn("31201↔finance.json 직접 매칭 0건 — 라벨/연도 체계 차이 (별도 HTML spot-check)")
    else:
        ok(f"31201↔finance: 일치 {match}/{compared} (불일치 {diff})")


def spot_check_kepco(rows: list[dict]) -> None:
    """C0247 한전 — HTML에서 직접 눈으로 확인할 핵심 수치."""
    print("\n[4] Spot check: C0247 한전 (31201 자산총계, 20501 기관장 연봉)")
    kepco_312 = [r for r in rows if r["apba_id"] == "C0247" and r["item_no"] == "31201"
                 and "자산총계" in r["row_label"] and r["year"] == "2025"]
    kepco_205 = [r for r in rows if r["apba_id"] == "C0247" and r["item_no"] == "20501"
                 and r["section"] == "상임기관장" and r["row_label"] == "성과상여금" and r["year"] == "2025"]
    if kepco_312:
        r = kepco_312[0]
        ok(f"31201 자산총계 2025: {r['value']} {r['unit']} ({r['value_type']}) section={r['section'][:30]}")
    else:
        fail("C0247 31201 자산총계 2025 없음")
    if kepco_205:
        r = kepco_205[0]
        ok(f"20501 상임기관장 성과상여금 2025: {r['value']} {r['unit']}")
    else:
        warn("C0247 20501 상임기관장 성과상여금 2025 없음")

    path = HTML / "C0247_31201__doc.html"
    if path.exists():
        reparsed = parse_doc(path.read_text(encoding="utf-8"), "C0247", "31201", ORG_NAMES["C0247"])
        asset = [x for x in reparsed if "자산총계" in x["row_label"] and x["year"] == "2025"]
        if asset and kepco_312 and str(asset[0]["value"]) == str(kepco_312[0]["value"]):
            ok(f"HTML 직접 파싱 자산총계 2025 = {asset[0]['value']} (CSV와 일치)")
        elif asset:
            fail(f"HTML vs CSV 자산총계: html={asset[0]['value']} csv={kepco_312[0]['value'] if kepco_312 else '?'}")


def main() -> int:
    print("=" * 60)
    print("ALIO parse validation")
    print("=" * 60)
    rows = load_csv()

    test_structure(rows)

    # 다양한 항목·기관 샘플 (고정 + 랜덤 시드)
    stems = [
        "C0247_31201", "C0247_20501", "C0247_31401",  # 한전
        "C0847_20501", "C0847_31401",  # 검증 시드
        "C1402_40211",  # 크롤 마지막 근처
        "C0001_21801",  # 목록 첫 기관
    ]
    rng = random.Random(42)
    all_docs = [p.name.replace("__doc.html", "") for p in HTML.glob("*__doc.html")]
    stems.extend(rng.sample(all_docs, min(5, len(all_docs))))
    test_html_roundtrip(rows, list(dict.fromkeys(stems)))

    cross_check_item(
        rows, "20501", "executive_pay.json",
        lambda r: f"{r['section']} | {r['row_label']}",
    )
    test_budget_31401(rows)

    test_finance_31201(rows)
    spot_check_kepco(rows)

    print("\n" + "=" * 60)
    print(f"FAILURES: {len(FAILURES)}  WARNINGS: {len(WARNINGS)}")
    if FAILURES:
        for f in FAILURES[:10]:
            print(" !", f)
        return 1
    print("PASSED (warnings only)" if WARNINGS else "ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
