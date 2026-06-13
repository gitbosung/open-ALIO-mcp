# Testing — 검증 체계·도구별 현황

## Release Path Verification

`uvx open-alio-mcp` 배포 경로는 로컬 smoke test와 별도로 검증합니다. 릴리스 전에는 다음 절차를 통과해야 합니다.

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
.\.venv\Scripts\python.exe tests\test_smoke.py
.\.venv\Scripts\python.exe scripts\security_smoke_test.py
.\.venv\Scripts\python.exe scripts\build_snapshot.py --out dist\alio_snapshot.db

$env:OPEN_ALIO_SNAPSHOT_PATH = (Resolve-Path dist\alio_snapshot.db).Path
.\.venv\Scripts\python.exe tests\test_smoke.py
Remove-Item Env:\OPEN_ALIO_SNAPSHOT_PATH

.\.venv\Scripts\python.exe -m build --no-isolation
.\.venv\Scripts\python.exe -m twine check dist\open_alio_mcp-*.tar.gz dist\open_alio_mcp-*.whl
uvx --refresh-package open-alio-mcp --from open-alio-mcp==0.1.1 python -c "import open_alio_mcp; from open_alio_mcp import data_provider, server; print(open_alio_mcp.__version__); print(len(server.mcp._tool_manager._tools)); print(data_provider.describe()['mode'])"
```

기대값은 version `0.1.1`, tools `32`, provider `sqlite-snapshot`입니다. 마지막 검증은 PyPI와 GitHub Release snapshot이 모두 올라간 뒤 실행합니다.

## 테스트 종류

| 테스트 | 실행 | 범위 | 네트워크 |
|---|---|---|---|
| CI 스모크 | `python tests\test_smoke.py` (GitHub Actions) | import·tool 등록·로컬 데이터 기반 핵심 도구 | 불필요 (오프라인 전용) |
| 보안 스모크 | `.venv\Scripts\python scripts\security_smoke_test.py` | 입력 검증(길이·범위·허용값) 회귀 | 불필요 |
| 스냅샷 검증 | `scripts\build_snapshot.py` → `OPEN_ALIO_SNAPSHOT_PATH`로 재실행 | 배포 스냅샷 빌드·필수 문서·재로딩 | 불필요 |

> 원천 데이터의 파싱·라이브 ALIO 대조·크롤 교차검증은 별도 데이터 파이프라인 저장소에서 수행합니다.

CI 스모크는 한국전력공사(별칭 '한전'), 부설기관, 지표 시계열 등 대표 케이스를 포함하며,
단순 호출 성공이 아니라 **기대값 조건**을 검증합니다.

## 도구별 검증 현황 (Tool verification status)

✅ = `scripts/smoke_test.py` 자동 검증 · 🔶 = 수동 시나리오 검증 (자동 테스트 보강 예정)

### 기관 검색·프로필

| Tool | 상태 | 비고 |
|---|---|---|
| `search_institutions` | ✅ | 별칭('한전')·유형+부처 필터·부설기관 필드 케이스 |
| `get_institution_profile` | ✅ | 상세(설립목적)·부설기관 caveat 케이스 |
| `get_institution_branches` | ✅ | 라이브 API — `--offline` 시 생략 |

### 경영공시·지표

| Tool | 상태 | 비고 |
|---|---|---|
| `list_metric_categories` | ✅ | 카테고리 11종 |
| `list_metric_items` | ✅ | |
| `list_disclosure_items` | ✅ | 정기/수시·주기 분류 케이스 |
| `get_institution_metrics` | ✅ | 시계열·크롤 승격 caveat 케이스 |
| `get_institution_staff_summary` | ✅ | 정원 vs 현원·headcount 추정 케이스 |
| `compare_institutions` | ✅ | |
| `find_institutions_by_criteria` | ✅ | 상·하위·증감률·필터 케이스 |

### 대민서비스 (ALIO Plus)

| Tool | 상태 | 비고 |
|---|---|---|
| `search_public_services` | ✅ | 라이브 API |
| `search_facilities` | ✅ | 라이브 API + 입력 검증(보안 스모크) |
| `get_facility_profile` | 🔶 | 검색 결과 기반 수동 확인 |
| `search_recruitments` | ✅ | 기관명 해석·필터·취소공고 제외 케이스 |
| `get_recruitment_profile` | 🔶 | 검색 결과 기반 수동 확인 |
| `analyze_recruitments` | ✅ | 분포 집계 + 오프라인 단위 테스트(D-day·취소 판별·필터) |

### 뉴스·통합 분석

| Tool | 상태 | 비고 |
|---|---|---|
| `get_institution_news` | 🔶 | 네이버 키 필요 — 대표 기관 수동 검증 |
| `get_institution_briefing` | 🔶 | 복합 도구 — 구성 요소는 각각 자동 검증 |
| `cross_check_news_with_metrics` | 🔶 | 토픽↔지표 매핑 수동 검증 |
| `digest_institution_news` | 🔶 | 테마 분류 수동 검증 |

### 법령·행정규칙·지침

| Tool | 상태 | 비고 |
|---|---|---|
| `search_laws` / `get_law_text` | ✅ | `LAW_API_OC` 설정 시에만 실행 |
| `search_admin_rules` / `get_admin_rule_text` | ✅ | 〃 |
| `search_guidelines` | ✅ | 미적재 시 우아한 안내까지 검증 + 조문 청킹 단위 테스트 |
| `get_guideline_text` | ✅ | 입력 검증(보안 스모크) |

### 경영평가편람

| Tool | 상태 | 비고 |
|---|---|---|
| `search_evaluation_handbook` | 🔶 | 중대재해·총인건비 등 대표 키워드 수동 검증 |
| `list_evaluation_org_types` | 🔶 | |
| `list_evaluation_indicators` | 🔶 | |
| `get_evaluation_indicator_detail` | 🔶 | |
| `compare_evaluation_handbook_years` | 🔶 | 2025↔2026 편람 수동 검증 |

### 운영

| Tool | 상태 | 비고 |
|---|---|---|
| `get_server_status` | ✅ | 데이터 적재 상태 점검 |

## 데이터 검증

- 이 저장소는 병합이 끝난 런타임 데이터만 포함합니다. 원천 수집·파싱·교차검증·승격(충돌 그룹은
  자동 선택하지 않음)은 별도 데이터 파이프라인 저장소에서 수행하며, 그 결과 데이터를 동기화합니다.
- 배포 스냅샷은 `scripts/build_snapshot.py` 빌드 시 필수 문서 존재·압축 무결성을 검증합니다
  (`validate_snapshot()`).

## 테스트 계획 (보강 예정)

1. 🔶 도구(뉴스 4종·편람 5종·상세조회 2종)의 fixture 기반 자동 테스트 — API 응답 mock 포함
2. 지표 회귀 테스트 — 대표 기관 golden sample 대조 (파이프라인 저장소 검증 자산 활용)
3. CI 확대 — 현재 오프라인 스모크에서 lint·fixture 테스트까지
