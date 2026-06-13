# Data sources — 출처·갱신주기·갱신 절차

open-ALIO-mcp는 갱신 주기가 서로 다른 공공 데이터 소스를 사용합니다.
모든 tool 응답에는 `source`(시스템·API·기준연도·조회시각)와 `caveats`(유의사항)가 포함됩니다.

## 데이터 카테고리별 출처

| 카테고리 | 원천 | 형태 | 갱신 주기 | 비고 |
|---|---|---|---|---|
| 기관 기본정보 (355개 ALIO 공시 단위) | NKOD OpenAPI + ALIO 일반현황 CSV | 로컬 스냅샷 `data/institutions.json` | 수동 (공시 갱신 시) | 342개 독립 지정기관 + 13개 부설기관, 기관코드·주무부처·설립목적 구분 |
| 지표 11종 시계열 | ALIO 항목별 공시 엑셀 | 로컬 스냅샷 `data/metrics/*.json` | 수동 (분기·연간 공시 후) | 기준연도·단위는 카테고리별 — `_index.json` 자동 집계 |
| 크롤 검증값 (finance·budget·executive_pay) | ALIO 공시 페이지 HTML | 검증 후 metrics에 병합 | 수동 | 충돌 시 엑셀값 유지 (병합은 데이터 파이프라인 저장소에서 수행) |
| 공시항목 카탈로그 (50개·세부 92종) | ALIO 항목 카탈로그 | 로컬 `data/reference/disclosure_items.json` | 수동 | 정기/수시·공시주기·ESG 분류 |
| 채용·시설·국가사업 | NKOD OpenAPI (ALIO Plus) | **온디맨드 API** (+채용 스냅샷) | 실시간 / 스냅샷 수동 | `DATA_GO_KR_SERVICE_KEY` 필요 |
| 뉴스 | 네이버 뉴스 검색 API | **온디맨드 API** | 실시간 | 언론 보도 — 공식 공시 아님 |
| 법령·행정규칙 | 국가법령정보센터 Open API | **온디맨드 API** | 현행 기준 | `LAW_API_OC` 필요, 법률 자문 아님 |
| 연도별 시달 지침 | 기재부 시달 문서 (HWPX/PDF) | 로컬 `data/guidelines/` | 수동 (개정 시) | 사용자가 파일 투입 |
| 경영평가편람 | 기재부 편람 PDF | 로컬 `data/handbook/` | 수동 (연 1회 + 수정판) | 사용자가 파일 투입 |

## 기준일 확인 방법

- 지표: `list_metric_categories` tool 또는 `data/metrics/_index.json` — 카테고리별 기관 수·연도 자동 집계
- 전체 적재 상태: `get_server_status` tool — 기관·지표·공시·채용스냅샷·편람·지침 일괄 점검
- 응답 단위: 각 응답의 `source.as_of_year`, `unit` 필드

## 직접 갱신하는 방법

이 저장소에는 **병합이 끝난 런타임 데이터(`data/`)** 만 포함됩니다. ALIO 공시 엑셀·크롤
수집·파싱·검증·승격으로 `data/`를 만들어내는 **빌드 파이프라인은 별도 데이터 저장소**에서
관리합니다. 갱신 흐름:

1. 데이터 파이프라인 저장소에서 새 공시를 반영해 `data/`를 재생성한다.
2. 런타임 부분집합(institutions·aliases·metrics·reference·guidelines·handbook·snapshots)을
   이 저장소의 `data/`로 동기화한다.
3. `scripts/build_snapshot.py`로 `dist/alio_snapshot.db`를 빌드하고 `scripts/smoke_test.py`로 검증한다.
4. 스냅샷과 `.sha256`을 GitHub Release에 올린다 — `uvx` 사용자가 자동으로 내려받는다.

## 갱신 실패 시 fallback

- `data/institutions.json`이 없으면 서버가 기관 목록을 API로 직접 로드합니다 (키 필요).
- 손상된 배포 스냅샷은 `validate_snapshot()`이 거부하고 재다운로드합니다.
- 지표 공백은 오류가 아니라 **공시 주기 미도래·미공시 가능성**으로 caveats에 안내됩니다.

## 알려진 한계

- 로컬 스냅샷은 빌드 시점 기준이며 실시간 최신성을 보장하지 않습니다 — 갱신은 현재 수동입니다
  (갱신 자동화는 [roadmap.md](roadmap.md) Phase 4 항목).
- 지침·편람은 HWPX/PDF 추출 텍스트라 표·서식이 손실될 수 있어 인용 시 원문 대조를 권장합니다.
- 뉴스 동음이의어 제외·중복 제거는 휴리스틱이므로 누락·오포함 가능성이 있습니다.
