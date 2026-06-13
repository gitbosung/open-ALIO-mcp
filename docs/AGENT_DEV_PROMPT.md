# AI 에이전트 개발 프롬프트 (복사용)

> 상세 배경·스키마·검증 절차: [`data-accuracy-spec.md`](data-accuracy-spec.md)
>
> Cursor Agent, Cloud Agent, 또는 외부 개발자에게 **아래 블록 전체를 붙여넣어** 작업을 시작한다.

---

## 프롬프트 (시작)

```
당신은 open-ALIO-mcp 데이터 정확도 엔지니어다.

## 목표
한국 ALIO(공공기관 경영정보 공개) 공시 데이터를 수집·파싱·저장하여,
사용자가 ALIO 웹사이트 대신 MCP에 질문해도 **동일한 수치·항목·단위**를 받도록 한다.
정확도가 최우선이다. 추정·임의 합산·조용한 데이터 누락은 금지한다.

## 필수 읽기
작업 전 반드시 읽고 따를 것:
- docs/data-accuracy-spec.md (정본 스키마, metric_key, 엣지 케이스, 파이프라인, CI 게이트)

## 데이터 정본 계층
rawdata/html/*__doc.html  →  data/crawl/alio_records.csv  →  data/metrics/*.json  →  dist/alio_snapshot.db

크롤 HTML이 유일한 정본이다. metrics JSON은 파생본이다.

## 스키마 (parse_alio.py FIELDS — breaking change)
apba_id, org_name, item_no, item_name, section, sub_account, row_label, year, value_type, value, unit, as_of, source_url

sub_account: nb 표 "기금계정: 신용보증기금" 패턴에서 추출.
다계정 기금 기관(신보 C0091, 중진공 C0130 등)에서 sub_account 없이 동일 row_label·year에 값이 여러 개면 파서 버그다.

## 수치 규칙 (협상 불가)
- 쉼표 제거 후 숫자화
- "-", 빈칸 → "" (0 아님)
- "해당사항 없음" → 별도 row_label 행

## metric_key (promote_crawl_metrics.py만에서 생성)
finance 31201/31301:
  요약 재무상태표(결산) | 기금계정 | {sub_account} | {row_label}

budget 31401:
  수입지출현황(기금계정) | {sub_account} | {row_label}

승격 정책: 동일 (org, metric_key, year)에 값 2개+ → 현재는 스킵.
스킵 시 반드시 _crawl_promotion_report.json 확인. 골든 기관 conflict는 0이어야 한다.

## 골든 기관 — 모든 파서/키 변경 후 필수 검증
| org_code | 유형 | 필수 확인 |
|----------|------|-----------|
| C0091 | 다계정 기금 3개 | finance 80+ series, 주계정 2024 자산총계=15774985 |
| C0038 | 단일계정 기금 | 부채비율·자산총계 존재 |
| C0130 | 다계정 기금 | sub_account 분리 |
| C0247 | 공기업 | HTML↔CSV roundtrip |
| C0847 | 검증 시드 | budget/executive 100% |

MCP 조회 예 (신보 주계정):
  get_institution_metrics(org_code="C0091", category="finance", item_query=" | 신용보증기금 |")
주의: item_query="신용보증기금"만 쓰면 "산업기반신용보증기금"도 매칭됨.

## 작업 완료 후 반드시 실행 (순서 고정)
python parse_alio.py
python scripts/check_parse_duplicates.py
python scripts/validate_parse.py
python scripts/promote_crawl_metrics.py
python scripts/build_snapshot.py

환경변수로 로컬 data 검증:
  OPEN_ALIO_DATA_DIR=<repo>/data
  python tests/test_smoke.py

## 금지 사항
- 파서/키 변경 without 골든 테스트 갱신
- 충돌을 "미공시"처럼 숨기기
- 요청 범위 밖 대규모 리팩터링
- xlsx와 크롤 값을 임의로 섞어 하나의 수치 만들기

## 산출물
1. 코드 변경 (최소 diff)
2. golden_samples.json 수치 추가 (해당 기관·항목)
3. data-accuracy-spec.md §4 엣지 케이스에 새 패턴 있으면 행 추가
4. 작업 요약: 무엇이 왜 바뀌었는지, 골든 수치 통과 여부, 남은 conflict 수
```

---

## 프롬프트 (전 기관 크롤 확장 시 추가)

```
## 추가 목표: ALIO 전 기관·전 항목 크롤 커버리지 확대

1. python crawl_alio.py discover → items_catalog.json 확인
2. data/items.json에 항목 추가 (tier, deferred 사유 명시)
3. check_crawl_completeness.py → 누락 0 목표 (부분 공시 항목은 "해당사항 없음" 허용)
4. 신규 item_no마다:
   - parse_alio.py 표 구조 샘플 3기관 HTML 분석
   - promote_crawl_metrics.py specs에 category·key_fn 등록
   - golden_samples.json 3건 이상
5. 항목 수 회귀: 골든 기관 finance/budget series_count min 기대치 문서화

부분 공시 항목 (40211 청렴도 등): 미공시 기관은 row 없음 또는 "해당사항 없음" — 둘 중 하나로 통일하고 caveats에 명시.
```

---

## 프롬프트 (버그 수정 — 신보형 다계정 충돌)

```
## 증상
특정 기관 finance/budget 항목 수가 비정상적으로 적음 (예: 5개).
ALIO 웹에는 데이터 있음. MCP는 "데이터 없음" 또는 일부만 조회.

## 진단 순서
1. rawdata/html/{org}_{item}__doc.html 존재 확인
2. alio_records.csv에서 해당 apba_id·item_no 행 수·고유 row_label 수
3. 동일 (section, row_label, year, value_type)에 value 여러 개인지 check_parse_duplicates.py
4. nb 표에 "기금계정: XXX" 반복 있는지 HTML 구조 확인
5. sub_account 필드 비어 있는지 확인
6. _crawl_promotion_report.json에서 해당 org conflict_samples 확인

## 수정 방향
- parse_alio.py: sub_account 추출·상속
- promote_*_key(): sub_account를 metric_key에 포함
- golden_samples.json + validate_metrics_coverage (신규)로 회귀 방지

## 완료 기준
- conflict_groups (해당 org) = 0
- finance series_count >= 기대치 (C0091: 80+)
- MCP get_institution_metrics 골든 수치 일치
```

---

## 프롬프트 (rawdata만 제공받았을 때)

```
## 입력
사용자가 rawdata/html/ 또는 alio_records.csv를 제공했다. ALIO 라이브 크롤 없이 검증·수정한다.

## 절차
1. data-accuracy-spec.md 스키마와 실제 CSV 컬럼 일치 확인
2. validate_parse.py — HTML↔CSV roundtrip (rawdata/html 있을 때)
3. check_parse_duplicates.py — 충돌 패턴 분류 (sub_account 누락 vs 진짜 ALIO 중복)
4. 충돌 원인이 파서면 parse_alio.py 수정 후 CSV 재생성
5. promote → snapshot → smoke

## rawdata 없이 CSV만 있을 때
- 골든_samples.json으로 수치 검증만 가능
- 파서 수정 검증은 불가 — 사용자에게 해당 stem __doc.html 확보 요청
```

---

## 프롬프트 (ALIO 사이트맵 기반 MCP 기능 확장 — Git push 금지)

```
당신은 open-ALIO-mcp 기능 확장 엔지니어다.

## 목표
ALIO 누리집 안내지도(https://alio.go.kr/notice/siteMap.do)와 실제 ALIO JSON/상세 페이지를 참고해,
현재 MCP에 없는 고가치 공시 검색·분석 도구를 추가한다. 작업은 로컬 변경까지만 수행한다.

## 절대 금지
- git push 금지
- 사용자 요청 없이 commit, tag, release, 배포 금지
- 개인정보/민원/인증 영역 크롤링 금지
- 기존 도구와 중복되는 wrapper만 추가 금지

## 필수 읽기
작업 전 반드시 확인:
- README.md — 현재 제공 tool 목록
- docs/data_sources.md — 출처·갱신주기·스냅샷 정책
- data/reference/disclosure_items.json — 공시항목 카탈로그
- src/open_alio_mcp/server.py — 기존 tool 응답 envelope/source/caveats 패턴
- src/open_alio_mcp/alio_client.py — ALIO/NKOD 클라이언트·정규화 패턴
- src/open_alio_mcp/security_utils.py — tool 입력 검증 등록

## 현재 이미 강한 영역
기관 검색/프로필, 지표 11종, 채용, 시설, 국가사업, 뉴스, 법령·행정규칙·로컬 지침,
경영평가편람은 이미 구현되어 있다. 새 기능은 사이트맵의 경영공시 > 주요 수시공시와
최근공시/공시현황 빈틈을 우선한다.

## MVP 우선순위
1. 최근공시 피드
   - tool 후보: search_recent_disclosures
   - endpoint: /status/findRecentDisclosureList.json
   - 가치: 모든 ALIO 공시 변경의 최신 알림 레이어. 기관 브리핑에 최근 공시를 붙일 수 있다.

2. 입찰공고
   - tool 후보: search_bids, get_bid_profile
   - endpoint: /occasional/findBidList.json, /occasional/bidDtl.do
   - 필터: 기관명/제목, 마감일, 등록일, 마감임박
   - 가치: 공공기관 계약·조달 기회 탐색. 샘플 기준 총 78,125건 규모.

3. 국회·감사원·주무부처 지적사항
   - tool 후보: search_external_findings, get_finding_profile, analyze_unresolved_findings
   - endpoint: /occasional/findPointList.json
   - reportFormNo: B1210(국회지적사항), B1220(감사원/주무부처 지적사항)
   - 핵심 필드: 지적사항, 시행기간, 지적사항 등록일, 조치계획 등록일, 조치실행 등록일, 첨부파일
   - 가치: 기관 리스크·사후조치 분석. 조치계획/조치결과 미등록 건을 집계할 수 있다.

4. 내부규정
   - tool 후보: search_internal_rules, get_internal_rule_profile
   - endpoint: /occasional/findRuleList.json, /occasional/ruleDtl.do
   - divis 후보: K1500(직제), K1100(인사·복무·징계), K1200/K1300/K1400(원문 확인 후 라벨 정규화)
   - 가치: 기관별 인사규정·보수규정·직제규정 비교. 샘플 기준 총 42,040건 규모.

5. 연구보고서
   - tool 후보: search_research_reports, get_research_report
   - endpoint: /occasional/findResearchList.json, /occasional/outResearchList.do 계열
   - 필터: 자체/외부용역, 공개/비공개, 기관명, 제목/내용, 발간일
   - 가치: 공공기관 생산 지식문서 검색. 샘플 기준 총 11,494건 규모.

6. 임원 모집공고
   - tool 후보: search_executive_openings
   - endpoint: /occasional/findOfficerList.json, /occasional/officerDtl.do
   - 가치: 기관장·상임이사·감사 공모 모니터링. 일반 직원 채용과 별도 축.

7. 이사회회의록·내부/외부 감사결과
   - tool 후보: search_board_minutes, search_audit_results
   - endpoint: /occasional/findBoardDirectorsList.json
   - reportType: 43005(이사회회의록), 43006(내부·외부감사결과)
   - 가치: 지배구조 이벤트 검색. 최근 이사회/감사결과를 기관 브리핑에 붙일 수 있다.

## 공통 설계 원칙
- 목록 tool은 page/limit/query/org_code/date_from/date_to/sort를 지원하되, ALIO 원본이 제공하지 않는
  필터는 응답 meta.caveats에 명시한다.
- 기관명 검색은 가능하면 기존 search_institutions/별칭 해석 로직과 맞춘다.
- 상세 tool은 원문 상세 URL, 첨부파일 메타, source.retrieved_at, caveats를 포함한다.
- 응답은 기존 with_source/envelope 형식을 따른다.
- HTML 상세 파싱은 BeautifulSoup 등 구조 파서를 우선하고, 정규식만으로 본문을 뜯지 않는다.
- 대량 전수 수집은 온디맨드 tool보다 별도 snapshot 빌드 대상으로 분리한다.
- 네트워크/API 실패 시 사용자에게 라이브 조회 실패와 대체 경로를 명확히 알린다.

## 피해야 할 영역
- 경영개선 제안, 나의 제안확인, 민원신청, 나의 민원확인: 개인정보·인증·민원 처리 영역이므로 MCP 도구화하지 않는다.
- ALIO 통합검색/trending keyword는 보조 기능이다. 최근공시·수시공시 도구보다 우선하지 않는다.

## 완료 기준
1. alio_client.py에 ALIO JSON 호출 함수와 정규화 함수 추가
2. server.py에 tool 등록, source/caveats 포함
3. security_utils.py에 입력 검증 등록
4. README.md tool 목록과 예시 질의 갱신
5. tests/test_smoke.py에 최소 스모크 테스트 추가
6. 네트워크 의존 테스트는 fixture/mock로 격리하거나 선택 실행으로 둔다
7. 최종 보고에는 변경 파일, 실행한 테스트, git push 미수행 여부를 명시
```
