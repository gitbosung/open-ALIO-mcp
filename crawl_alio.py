"""ALIO 공시 페이지 일괄 수집기.

사용법:
    python crawl_alio.py crawl [--limit N] [--orgs C0847,...] [--items 2050,...]
    python crawl_alio.py discover --org C0847 [--seed-item 2050]
    python crawl_alio.py parse [--out data/crawl/alio_records.csv]

원칙 (작업지시서):
- 요청 간 지연 1.5초 이상 (DELAY 축소 금지)
- 수집·파싱 분리: HTML 원본은 rawdata/html/ 에 저장 후 파싱
- 이어받기: 이미 받은 파일은 건너뜀
- 실패는 rawdata/html/_failed.log 에 기록
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "rawdata" / "html"
FAILED_LOG = RAW_DIR / "_failed.log"
INSTITUTIONS_JSON = ROOT / "data" / "institutions.json"
ITEMS_JSON = ROOT / "data" / "items.json"

BASE_URL = "https://www.alio.go.kr/item/itemReportTerm.do"

DELAY = 1.5  # 초. 정부 사이트 — 줄이지 말 것

CONTACT = "bobowork320@gmail.com"
# 주의: ALIO는 비브라우저 UA를 403으로 차단함 → UA는 표준 브라우저 형식 유지,
# 연락처는 From 헤더로 전달
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "From": CONTACT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def load_orgs() -> list[dict]:
    data = json.loads(INSTITUTIONS_JSON.read_text(encoding="utf-8"))
    return [{"apba_id": o["org_code"], "org_name": o["name"]} for o in data["orgs"]]


def load_items() -> list[dict]:
    if not ITEMS_JSON.exists():
        print(f"[!] {ITEMS_JSON} 없음 — 항목 목록 파일이 필요합니다.", file=sys.stderr)
        sys.exit(1)
    data = json.loads(ITEMS_JSON.read_text(encoding="utf-8"))
    return data["items"]


def shell_path(apba_id: str, item_no: str) -> Path:
    return RAW_DIR / f"{apba_id}_{item_no}__shell.html"


def doc_path(apba_id: str, item_no: str) -> Path:
    return RAW_DIR / f"{apba_id}_{item_no}__doc.html"


# 셸 페이지에서 실제 보고서 fragment 경로 추출
# 예: $('.doc_con').load("/upload/disclosure/2026/04/13/2026041303148851/doc.html", ...)
DOC_URL_RE = re.compile(r"""\.load\(\s*["'](/upload/disclosure/[^"']+/doc\.html)["']""")


def log_failure(apba_id: str, item_no: str, reason: str) -> None:
    FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')}\t{apba_id}\t{item_no}\t{reason}\n"
    with FAILED_LOG.open("a", encoding="utf-8") as f:
        f.write(line)


def _get(session: requests.Session, url: str, params: dict | None = None) -> requests.Response | None:
    try:
        resp = session.get(url, params=params, headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp


def fetch(session: requests.Session, apba_id: str, item_no: str) -> str | None:
    """셸 페이지 1건 수집. 성공 시 HTML 텍스트, 실패 시 None.

    주의: 실제 데이터 표는 셸이 아니라 별도 doc.html fragment에 있음 → fetch_pair 사용.
    """
    params = {"apbaId": apba_id, "reportFormRootNo": item_no, "disclosureNo": ""}
    resp = _get(session, BASE_URL, params)
    if resp is None:
        log_failure(apba_id, item_no, "shell_request_failed")
        return None
    html = resp.text
    if len(html) < 2000:
        log_failure(apba_id, item_no, f"suspicious_short_response: {len(html)} chars")
        return None
    return html


def fetch_pair(session: requests.Session, apba_id: str, item_no: str) -> tuple[str, str] | None:
    """셸 페이지 + 보고서 fragment(doc.html) 2단계 수집.

    ALIO 페이지는 데이터 표를 jQuery .load()로 정적 fragment에서 불러오므로,
    셸에서 fragment 경로를 추출해 한 번 더 요청한다 (JS 렌더링 불필요).
    """
    shell = fetch(session, apba_id, item_no)
    if shell is None:
        return None

    m = DOC_URL_RE.search(shell)
    if not m:
        # 공시 자체가 없는 기관×항목 조합일 수 있음 — 셸은 남겨서 진단 가능하게
        shell_path(apba_id, item_no).parent.mkdir(parents=True, exist_ok=True)
        shell_path(apba_id, item_no).write_text(shell, encoding="utf-8")
        log_failure(apba_id, item_no, "doc_url_not_found (공시 없음 가능)")
        return None

    time.sleep(DELAY)
    resp = _get(session, "https://www.alio.go.kr" + m.group(1))
    if resp is None:
        log_failure(apba_id, item_no, f"doc_request_failed: {m.group(1)}")
        return None
    return shell, resp.text


def fetch_organ_list(session: requests.Session, item_no: str) -> dict[str, str] | None:
    """항목별 공시 보유 기관 목록 조회 → {apba_id: disclosureNo}.

    공시가 없는 기관을 사전에 건너뛰어 불필요한 요청을 줄인다.
    결과는 rawdata/html/_organlist_{item}.json에 캐시 (이어받기 원칙 동일 적용).
    """
    cache = RAW_DIR / f"_organlist_{item_no}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        resp = session.post(
            "https://www.alio.go.kr/item/itemOrganListJung.json",
            headers={**HEADERS, "Content-Type": "application/json"},
            json={"apbaType": [], "jidtDptm": [], "area": [], "apbaId": "",
                  "reportFormRootNo": item_no, "quart": ""},
            timeout=30,
        )
        resp.raise_for_status()
        organs = resp.json()["data"]["organList"]
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"  [경고] 항목 {item_no} 기관목록 조회 실패({e}) — 전 기관 시도로 진행")
        return None
    finally:
        time.sleep(DELAY)
    result = {o["apbaId"]: o["disclosureNo"] for o in organs if o.get("disclosureNo")}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def cmd_crawl(args: argparse.Namespace) -> None:
    orgs = load_orgs()
    items = load_items()

    if args.orgs:
        wanted = {c.strip().upper() for c in args.orgs.split(",")}
        orgs = [o for o in orgs if o["apba_id"] in wanted]
    if args.items:
        wanted = {c.strip() for c in args.items.split(",")}
        items = [i for i in items if str(i["item_no"]) in wanted]
    if args.limit:
        orgs = orgs[: args.limit]

    total = len(orgs) * len(items)
    print(f"대상: 기관 {len(orgs)}개 × 항목 {len(items)}개 = {total}건")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    done = skipped = no_disc = failed = 0
    for item in items:
        item_no = str(item["item_no"])
        # 공시 보유 기관 사전 필터 (예: 청렴도는 355곳 중 180곳만 공시)
        disclosed = fetch_organ_list(session, item_no)
        for org in orgs:
            apba_id = org["apba_id"]
            out_doc = doc_path(apba_id, item_no)
            if out_doc.exists():
                skipped += 1
                continue
            if disclosed is not None and apba_id not in disclosed:
                no_disc += 1
                continue
            pair = fetch_pair(session, apba_id, item_no)
            time.sleep(DELAY)
            if pair is None:
                failed += 1
                print(f"  [실패] {apba_id} × {item_no} (→ _failed.log)")
                continue
            shell, doc = pair
            shell_path(apba_id, item_no).write_text(shell, encoding="utf-8")
            out_doc.write_text(doc, encoding="utf-8")
            done += 1
            print(f"  [저장] {out_doc.name} ({len(doc):,} chars)")

    print(f"완료: 신규 {done} / 스킵 {skipped} / 공시없음 {no_disc} / 실패 {failed}")


def cmd_discover(args: argparse.Namespace) -> None:
    """공식 항목 카탈로그(formList.json)에서 전체 reportFormRootNo 추출.

    ALIO '항목별 공시' 페이지가 사용하는 엔드포인트로, 92개 항목 전체의
    번호·분류·공시분기를 반환한다. 분기별 항목은 분기마다 번호가 다름
    (예: 임직원 수 = 20201~20204).
    """
    resp = requests.post(
        "https://www.alio.go.kr/item/formList.json",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={}, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["data"]

    items = []
    for it in data:
        items.append({
            "item_name": it["scdnm"] or it["mcdnm"],
            "group": it["lcdnm"],
            "report_nos": it["reportNos"].split(","),
            "is_report": it["reportYn"] == "Y",  # N = 게시판형 (itemReportTerm 미사용)
            "quarters": it["quart"],
        })

    out = ROOT / "data" / "items_catalog.json"
    out.write_text(
        json.dumps({"_meta": {"source": "https://www.alio.go.kr/item/formList.json",
                              "discovered_at": datetime.now().isoformat(timespec="seconds"),
                              "note": "is_report=False 항목은 게시판형이라 itemReportTerm.do로 수집 불가"},
                    "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    reportable = [i for i in items if i["is_report"]]
    print(f"항목 {len(items)}개 (보고서형 {len(reportable)}개) → {out}")
    for i in reportable:
        print(f"  {','.join(i['report_nos']):<28} {i['group']}/{i['item_name']}")


def cmd_parse(args: argparse.Namespace) -> None:
    from parse_alio import parse_all  # 파싱 로직은 parse_alio.py에 분리

    json_out = ROOT / args.json_out if args.json_out else None
    parse_all(RAW_DIR, ROOT / args.out, json_out=json_out)


def main() -> None:
    ap = argparse.ArgumentParser(description="ALIO 공시 페이지 수집/파싱")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_crawl = sub.add_parser("crawl", help="공시 페이지 일괄 수집")
    p_crawl.add_argument("--limit", type=int, help="기관 수 제한 (테스트용)")
    p_crawl.add_argument("--orgs", help="기관코드 지정 (쉼표구분, 예: C0847)")
    p_crawl.add_argument("--items", help="항목번호 지정 (쉼표구분, 예: 2050)")

    p_disc = sub.add_parser("discover", help="공시항목 번호 카탈로그 수집")

    p_parse = sub.add_parser("parse", help="raw HTML → CSV 파싱")
    p_parse.add_argument("--out", default="data/crawl/alio_records.csv")
    p_parse.add_argument("--json-out", default="data/crawl/alio_records.json")

    args = ap.parse_args()
    {"crawl": cmd_crawl, "discover": cmd_discover, "parse": cmd_parse}[args.cmd](args)


if __name__ == "__main__":
    main()
