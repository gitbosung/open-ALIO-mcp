# -*- coding: utf-8 -*-
"""MCP 도구 스모크 테스트 — 데모 시나리오 검증.

실행: .venv/Scripts/python scripts/smoke_test.py [--offline]
--offline: API 호출 도구(시설·사업·채용) 생략
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp import server  # noqa: E402

OFFLINE = "--offline" in sys.argv
FAIL = []


def check(name: str, result: dict, expect=None) -> None:
    ok = not result.get("is_error")
    if ok and expect:
        ok = expect(result)
    status = "PASS" if ok else "FAIL"
    if not ok:
        FAIL.append(name)
    print(f"[{status}] {name}")
    if not ok:
        print(f"        -> {str(result)[:300]}")


# 1. 검색 (별칭)
r = server.search_institutions(query="한전")
check("search_institutions('한전')", r,
      lambda r: r["data"]["count"] >= 1 and r["data"]["results"][0]["name"] == "한국전력공사")
kepco = r["data"]["results"][0]["org_code"]
print(f"        kepco org_code = {kepco}")

# 2. 검색 (유형+부처)
r = server.search_institutions(org_type="공기업", ministry="산업통상부", limit=30)
check("search_institutions(공기업, 산업통상부)", r, lambda r: r["data"]["count"] >= 5)

# 3. 프로필 (상세 포함)
r = server.get_institution_profile(kepco)
check("get_institution_profile(한전)", r,
      lambda r: r["data"]["profile"]["detail"] and r["data"]["profile"]["detail"]["purpose"])

# 3-1. 부설기관 필드 노출
r = server.search_institutions(query="극지")
check("search_institutions(부설기관 필드)", r,
      lambda r: r["data"]["count"] == 1
      and r["data"]["results"][0]["is_subsidiary"]
      and r["data"]["results"][0]["parent_org_code"]
      and any("부설기관" in c for c in r["caveats"]))
kopri = r["data"]["results"][0]["org_code"] if not r.get("is_error") and r["data"]["results"] else ""

r = server.get_institution_profile(kopri)
check("get_institution_profile(부설기관 caveat)", r,
      lambda r: r["data"]["profile"]["is_subsidiary"]
      and r["data"]["profile"]["parent_org_name"] == "한국해양과학기술원"
      and any("부설기관" in c for c in r["caveats"]))

# 4. 지표 카테고리
r = server.list_metric_categories()
check("list_metric_categories", r, lambda r: r["data"]["count"] == 11)

# 5. 지표 항목
r = server.list_metric_items("staff", item_query="현원", org_code=kepco)
check("list_metric_items(staff, 현원)", r, lambda r: r["data"]["count"] >= 1)

# 6. 한전 정원·현원 시계열
r = server.get_institution_metrics(kepco, "staff", item_query="일반정규직-정원")
check("get_institution_metrics(한전, staff)", r, lambda r: r["data"]["found"])

r = server.get_institution_staff_summary(org_code="C1294")
check("get_institution_staff_summary(도공서비스)", r,
      lambda r: r["data"]["found"]
      and r["data"]["quota"]["total"] is not None
      and r["data"]["headcount"]["estimated_total"] is not None
      and r["data"]["quota"]["total"]["value"] != r["data"]["headcount"]["estimated_total"])

# 7. 한전 부채 시계열 (finance)
r = server.get_institution_metrics(kepco, "finance", item_query="부채")
check("get_institution_metrics(한전, finance 부채)", r,
      lambda r: r["data"]["found"] and "부채총계" in r["data"]["series"])
if not r.get("is_error") and r["data"]["found"]:
    print(f"        부채총계 = {r['data']['series'].get('부채총계')}")

# 8. 한전 vs 한수원 비교
r2 = server.search_institutions(query="한수원")
khnp = r2["data"]["results"][0]["org_code"]
r = server.compare_institutions([kepco, khnp], "finance", item_query="부채비율")
check("compare_institutions(한전 vs 한수원, 부채비율)", r,
      lambda r: len(r["data"]["comparison"]) == 2)

# 9. 비공기업 finance 조회 → 크롤 결산 재무 포함
r3 = server.search_institutions(query="예술경영지원센터")
art = r3["data"]["results"][0]["org_code"]
r = server.get_institution_metrics(art, "finance")
check("get_institution_metrics(비공기업, finance) → 크롤 결산", r,
      lambda r: r["data"]["found"] and any("요약 재무상태표(결산)" in k for k in r["data"]["series"]))

# 10. 잘못된 카테고리 → 에러 메시지
r = server.get_institution_metrics(kepco, "nonexistent")
check("get_institution_metrics(잘못된 category)", {"is_error": False} if r.get("is_error") else {"is_error": True})

# 11. 평균보수
r = server.get_institution_metrics(kepco, "salary", item_query="기본급")
check("get_institution_metrics(한전, salary 기본급)", r, lambda r: r["data"]["found"])

# 16. 스크리닝 — 정원 상위 5
r = server.find_institutions_by_criteria("staff", "정원", mode="top_n", n=5)
check("find_institutions_by_criteria(staff 정원 top5)", r,
      lambda r: len(r["data"]["results"]) == 5 and r["data"]["results"][0]["value"] > 0)
if not r.get("is_error"):
    top = r["data"]["results"][0]
    print(f"        1위: {top['name']} {top['value']} ({r['data']['item']})")

r = server.find_institutions_by_criteria(
    "staff", "정원", mode="top_n", n=5, exclude_subsidiaries=True)
check("find_institutions_by_criteria(exclude_subsidiaries)", r,
      lambda r: len(r["data"]["results"]) == 5 and any("부설기관" in c for c in r["caveats"]))

r = server.find_institutions_by_criteria(
    "staff", "정원", mode="top_n", n=5, org_type="기타공공기관", use_classification_org_type=True)
check("find_institutions_by_criteria(classification_org_type)", r,
      lambda r: len(r["data"]["results"]) >= 1 and any("classification_org_type" in c for c in r["caveats"]))

# 17. 스크리닝 — 공기업 부채 증가율
r = server.find_institutions_by_criteria(
    "finance", "부채총계", mode="growth_rate", year_from=2021, n=5, org_type="공기업")
check("find_institutions_by_criteria(finance 부채 growth)", r,
      lambda r: len(r["data"]["results"]) >= 1 and "growth_rate_pct" in r["data"]["results"][0])

# 18. 별칭 부분일치 fallback ("심평" → 건강보험심사평가원)
r = server.search_institutions(query="심평")
check("search_institutions('심평' 별칭 fallback)", r,
      lambda r: r["data"]["count"] >= 1 and "심사평가" in r["data"]["results"][0]["name"])

# 19. 헬스체크
r = server.get_server_status()
check("get_server_status", r,
      lambda r: r["data"]["institutions_count"] == 342
      and r["data"]["subsidiary_count"] == 13
      and r["data"]["disclosure_units_count"] == 355
      and r["data"]["metrics_categories"] == 11)

# 20. metrics 응답 as_of_year
r = server.get_institution_metrics(kepco, "staff", item_query="일반정규직-정원")
check("metrics source.as_of_year", r, lambda r: r["source"]["as_of_year"] is not None)

# 21. 공시 카탈로그 — 전체
r = server.list_disclosure_items()
check("list_disclosure_items(전체)", r, lambda r: r["data"]["total"] >= 90)

# 22. 공시 카탈로그 — 수시공시만
r = server.list_disclosure_items(disclosure_type="수시")
check("list_disclosure_items(수시)", r,
      lambda r: r["data"]["count"] >= 1 and all(i["type"] == "수시" for i in r["data"]["items"]))

# 23. 공시 카탈로그 — finance 매핑
r = server.list_disclosure_items(metric_category="finance")
check("list_disclosure_items(finance 매핑)", r,
      lambda r: r["data"]["count"] >= 1 and "재무" in r["data"]["items"][0]["sub"])

# 24. 지표 응답에 공시 주기 주석 자동 부착
r = server.get_institution_metrics(kepco, "salary", item_query="기본급")
check("metrics 공시주기 주석", r,
      lambda r: any("정기공시" in c for c in r["caveats"]))

# 25. 크롤 승격 finance에도 공시 주기·출처 안내
r = server.get_institution_metrics(art, "finance")
check("metrics 크롤 승격 안내", r,
      lambda r: any("정기공시" in c for c in r["caveats"]) and any("크롤" in c for c in r["caveats"]))

# 26. recruit_store — D-day 계산·분포 집계 (오프라인 단위)
from open_alio_mcp import recruit_store  # noqa: E402

sample = [
    {"title": "A", "work_region": "서울,경기", "ncs": "정보통신", "hire_type": "정규직",
     "recruit_type": "신입", "education": "학력무관", "org_name": "기관1",
     "period_end": "20991231", "headcount": 5},
    {"title": "B", "work_region": "경기", "ncs": "경영·회계·사무", "hire_type": "청년인턴",
     "recruit_type": "경력", "education": "대졸", "org_name": "기관2",
     "period_end": "20991231", "headcount": 3},
]
dist = recruit_store.distribution(sample, "region")
check("recruit_store.distribution(region 복합값 분해)",
      {"is_error": False},
      lambda _: {g["key"] for g in dist["groups"]} >= {"서울", "경기"}
      and next(g for g in dist["groups"] if g["key"] == "경기")["postings"] == 2)
check("recruit_store.parse_days_remaining(미래일)",
      {"is_error": False},
      lambda _: recruit_store.parse_days_remaining(sample[0]) is not None
      and recruit_store.parse_days_remaining(sample[0]) > 0)

# 27. D-day는 스테일 decimalDay 대신 period_end로 재계산
stale = {"period_end": "20991231", "days_remaining": 1}
check("recruit_store.parse_days_remaining(스테일 decimalDay 무시)",
      {"is_error": False},
      lambda _: recruit_store.parse_days_remaining(stale) > 1000)

# 28. 취소 공고 판별·기본 제외
cancelled = {"title": "(공고취소)○○ 채용", "period_end": "20991231"}
check("recruit_store.is_cancelled + filter 기본 제외",
      {"is_error": False},
      lambda _: recruit_store.is_cancelled(cancelled)
      and recruit_store.filter_records([cancelled]) == []
      and len(recruit_store.filter_records([cancelled], exclude_cancelled=False)) == 1)

# 29. 신입·학력 필터 ('신입' 요청 시 '신입+경력' 포함)
mixed = [
    {"title": "A", "recruit_type": "신입+경력", "education": "학력무관,고졸", "period_end": "20991231"},
    {"title": "B", "recruit_type": "경력", "education": "석사,박사", "period_end": "20991231"},
]
check("filter_records(recruit_type='신입', education='고졸')",
      {"is_error": False},
      lambda _: [r["title"] for r in recruit_store.filter_records(
          mixed, recruit_type="신입", education="고졸")] == ["A"])

# 30. 지침 조문 청킹 (오프라인 단위)
sys.path.insert(0, str(ROOT / "scripts"))
from build_guidelines import chunk_articles  # noqa: E402

_arts, _pre = chunk_articles(
    "2026년도 예산운용지침\n제1장 총칙\n제1조(목적) 이 지침은 예산 운용 기준을 정한다.\n"
    "세부 내용 줄.\n제2조의2(정의) 용어 정의.\n"
)
check("build_guidelines.chunk_articles(조문 분할)",
      {"is_error": False},
      lambda _: [a["article"] for a in _arts] == ["1", "2의2"]
      and _arts[0]["title"] == "목적" and _arts[0]["chapter"].startswith("제1장")
      and "2026년도" in _pre)

# 31. 지침 저장소 — 적재 시 검색 동작, 미적재 시 우아한 안내
r = server.search_guidelines("총인건비")
check("search_guidelines(적재 또는 안내)",
      {"is_error": False},
      lambda _: (not r.get("is_error")) or "build_guidelines" in r.get("error", ""))

# 32. 법령 API (LAW_API_OC 설정 시에만)
from open_alio_mcp import law_client  # noqa: E402

if law_client.has_credentials() and not OFFLINE:
    r = server.search_laws("공공기관의 운영에 관한 법률", display=5)
    check("search_laws(공운법)", r,
          lambda r: r["data"]["total"] >= 1
          and any("공공기관의 운영에 관한 법률" == i["name"] for i in r["data"]["items"]))
    if not r.get("is_error") and r["data"]["items"]:
        _mst = next(i["mst"] for i in r["data"]["items"] if i["name"] == "공공기관의 운영에 관한 법률")
        r = server.get_law_text(_mst)
        check("get_law_text(공운법 목차)", r, lambda r: r["data"]["article_count"] >= 30)
        r = server.get_law_text(_mst, article="11")
        check("get_law_text(공운법 제11조 경영공시)", r,
              lambda r: r["data"]["articles"] and "공시" in r["data"]["articles"][0]["text"])
    r = server.search_admin_rules("공기업ㆍ준정부기관의 경영에 관한 지침", display=5)
    if r.get("is_error") or r["data"]["total"] == 0:
        r = server.search_admin_rules("경영에 관한 지침", display=10)
    check("search_admin_rules(경영지침)", r, lambda r: r["data"]["total"] >= 1)
else:
    print("[SKIP] 법령 API 테스트 - LAW_API_OC 미설정 또는 --offline")

if not OFFLINE:
    # 12. 채용 (API)
    r = server.search_recruitments(ongoing_only=True, limit=3)
    check("search_recruitments(진행중)", r)
    # 12b. 채용 — 마감임박 정렬 + 공시 주기 주석
    r = server.search_recruitments(ongoing_only=True, sort="deadline", limit=5)
    check("search_recruitments(마감임박 정렬+주기주석)", r,
          lambda r: any("공시" in c for c in r["caveats"]))
    # 12d. 채용 — 기관명/별칭 자동 해석 ("한전 채용 떴어?")
    r = server.search_recruitments(query="한전", limit=3)
    check("search_recruitments('한전' 기관명 해석)", r,
          lambda r: r["data"]["resolved_org"] == "한국전력공사")
    # 12e. 일반 키워드는 기관으로 오인하지 않음
    r = server.search_recruitments(query="연구원", use_snapshot=True, limit=3)
    check("search_recruitments('연구원' 키워드 유지)", r,
          lambda r: r["data"]["resolved_org"] is None and r["data"]["matched"] >= 1)
    # 12c. 연구자용 분포 집계 (라이브 전수 — snapshot 없으면 API 다수 호출)
    r = server.analyze_recruitments("region", use_snapshot=True)
    if r.get("is_error") or not r["data"]["groups"]:
        r = server.analyze_recruitments("region", use_snapshot=False)
    check("analyze_recruitments(region 분포)", r,
          lambda r: r["data"]["dimension"] == "region" and r["data"]["postings_total"] >= 1)
    # 13. 사업 (API)
    r = server.search_public_services(limit=3)
    check("search_public_services", r)
    # 14. 시설 (API) — 예약·수용인원 필드 포함 확인
    r = server.search_facilities(region="서울특별시", limit=3)
    check("search_facilities(서울)", r,
          lambda r: r["data"]["count"] >= 1 and "reservation" in r["data"]["results"][0])
    # 14b. 시설 통합 query (이용방법 내 텍스트 검색)
    r = server.search_facilities(region="서울특별시", district="강남구", query="회의", limit=10)
    check("search_facilities(강남 '회의' 통합검색)", r, lambda r: r["data"]["count"] >= 1)
    # 15. 지점 (API)
    r = server.get_institution_branches(kepco, limit=5)
    check("get_institution_branches(한전)", r)

print()
if FAIL:
    print(f"FAILED: {len(FAIL)} → {FAIL}")
    sys.exit(1)
print("ALL PASS")
