# ALIO 데이터 정확도 확보 개발 명세

> **목적**: 사용자가 ALIO 웹사이트 대신 open-ALIO-mcp에 질문해도 **공시 원문과 동일한 수치·항목**을 얻을 수 있도록, 데이터 수집·파싱·저장·검증 전 과정의 **단일 정본(canonical) 규칙**을 확정한다.
>
> **배경**: 2026-06 신용보증기금(C0091) 재무 누락 사건 — ALIO에는 공시되어 있었으나, 다계정 기금의 `sub_account` 파싱 누락 → 승격 충돌 → `finance.json`에 5항목만 남는 **침묵 실패(silent failure)** 가 발생했다.
>
> **대상 독자**: 데이터 파이프라인 개발자, Cursor/AI 에이전트, 코드 리뷰어

---

## 0. 미션 정의

| 항목 | 요구사항 |
|------|----------|
| **정확도** | ALIO 공시 화면(또는 동일 시점 raw HTML)과 수치·항목명·단위·연도가 일치해야 한다 |
| **완전성** | 공시된 기관×항목×연도는 누락 없이 조회 가능해야 한다 (미공시는 명시적으로 표기) |
| **추적성** | 모든 수치는 `source_url`, `as_of`, 원천 파일 stem(`{apba_id}_{item_no}`)으로 역추적 가능 |
| **투명성** | 파싱 불가·충돌·미공시는 MCP `caveats` 또는 빌드 리포트에 **반드시** 노출 (조용히 스킵 금지) |
| **대체 사용** | 사용자가 ALIO 대신 MCP를 쓸 때, 응답에 `source.as_of_year`·`unit`·한계가 항상 포함 |

**비목표**: ALIO에 없는 수치를 추정·합산·보간하지 않는다. (통합 시나리오 분석 등은 사용자에게 출처·한계를 명시한 파생 계산으로만 제공)

---

## 1. 설계 원칙 (Accuracy-first)

### 1.1 단일 정본 (Single Source of Truth)

```
rawdata/html/{apba_id}_{item_no}__doc.html   ← ALIO 원문 (최우선 정본)
        ↓ parse_alio.py
data/crawl/alio_records.csv                 ← long-format 정본 (스키마 고정)
        ↓ promote_crawl_metrics.py (+ 향후 전 카테고리 통일)
data/metrics/{category}.json                ← MCP 조회용 파생본
        ↓ build_snapshot.py
dist/alio_snapshot.db                       ← 배포 스냅샷
```

**규칙**

1. **크롤 HTML이 정본**이다. xlsx·반기 xls는 교차검증·초기 시드용이며, 장기적으로 크롤 정본에 흡수하거나 역할을 명시적으로 제한한다.
2. `metrics/*.json`은 파생본이다. 정본 CSV와 불일치하면 **파생본이 틀린 것**으로 간주한다.
3. 병합 시 “애매하면 버린다” 정책은 **데이터 누락을 사용자에게 숨긴다**. 충돌은 리포트·CI 실패·caveats로 노출한다.

### 1.2 Fail Loud (침묵 실패 금지)

| 상황 | 금지 (현재/과거) | 권장 |
|------|------------------|------|
| 동일 키에 값 2개+ | 승격 스킵만 하고 끝 | `_crawl_promotion_report.json` + CI 임계치 초과 시 **빌드 실패** |
| 다계정 기금인데 `sub_account` 빈값 | 키 충돌 후 대량 스킵 | 파서 단계에서 **필수 필드**로 강제 |
| HTML 있으나 CSV 0건 | 무시 | `check_crawl_completeness.py` 실패 |
| metrics 항목 수 급감 | 무시 | 골든 기관 **회귀 테스트** 실패 |

### 1.3 키 정규화는 명시적 규칙만

metric_key는 코드 한 곳(`*_key()` 함수)에서만 생성한다. 암묵적 문자열 조합·공백·접두어 제거 규칙을 바꿀 때는 **골든 샘플 전체 재검증**이 필수다.

---

## 2. 정본 스키마 — `alio_records.csv`

`parse_alio.py`의 `FIELDS`가 스키마 계약이다. **필드 추가·삭제는 breaking change**이며, 모든 downstream 스크립트를 함께 수정한다.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `apba_id` | string | ✓ | ALIO 기관코드 (예: `C0091`) |
| `org_name` | string | ✓ | 기관명 |
| `item_no` | string | ✓ | 공시항목 번호 (`reportFormRootNo`) |
| `item_name` | string | ✓ | 항목명 (cover-title에서 추출) |
| `section` | string | ✓ | 섹션 (예: `1. 고유사업`, `2. 기금계정`, `수입 및 지출 현황`) |
| `sub_account` | string | 조건부 | **기금 하위계정명**. nb 표 `기금계정: 신용보증기금`에서 추출. 단일계정·고유사업은 `""` |
| `row_label` | string | ✓ | 계층형 구분. ` > `로 연결 (예: `자산 > 유동자산`) |
| `year` | string | ✓ | 4자리 연도 |
| `value_type` | string | ✓ | `결산`·`예산`·`반기`·`분기` 등 (헤더에서 추출, 없으면 `""`) |
| `value` | number\|string\|"" | ✓ | 숫자화 가능 시 int/float. `-`·빈칸은 `""` (0 아님). 텍스트(연봉제 등)는 원문 |
| `unit` | string | ✓ | `(단위: 백만원)` 등에서 추출 |
| `as_of` | string | | 기준시점 (예: `2026년 1/4분기`) |
| `source_url` | string | ✓ | ALIO 항목 URL 템플릿 |

### 2.1 `sub_account` 추출 규칙 (다계정 기금 — 필수)

**패턴** (nb 표 텍스트):

```text
요약 재정상태표(구 국가회계기준) 기금계정: 신용보증기금 (단위: 백만원)
수입*지출현황 [기금계정] 신용보증기금 ...
```

**정규식**: `기금계정\s*:\s*([^(\n]+)` → `clean_text()` 후 `sub_account`에 저장.

**상태 전이**:

- SECTION 변경·nb bold 섹션 변경 시 `sub_account = ""` 초기화
- nb 표에서 계정명 추출 시 갱신
- 이후 border=1 데이터 표는 **현재 `sub_account`를 상속** (성질별 재정운용표 등 후속 표 포함)

**검증**: `item_no` ∈ `{31201, 31301, 31401}` 이고 `section`에 `기금`이 포함되며, 동일 stem에 서로 다른 `sub_account`가 2개 이상이면 **다계정 기관**으로 분류 — 골든 테스트 대상.

### 2.2 수치 변환 규칙 (협상 불가)

- 쉼표 제거 후 숫자화
- `-`·빈값 → `""` (**0으로 치환 금지**)
- `해당사항 없음` → `row_label`로 별도 1행 기록
- 텍스트 값(예: `연봉제`)은 원문 보존

---

## 3. metric_key 규칙 — `promote_crawl_metrics.py`

카테고리별 키 함수가 **유일한** 정규화 진입점이다.

### 3.1 finance (`31201`, `31301`)

```text
{item_name}({value_type}) | {section_clean} | [{sub_account} |] {row_label}
```

- `item_name`: `31201` → `요약 재무상태표`, `31301` → `요약 손익계산서`
- `section_clean`: 앞의 `1.`·`2.` 등 번호 접두 제거 (`clean_section`)
- `sub_account`가 비어 있지 않으면 **반드시** section과 row_label 사이에 삽입
- `value_type == "반기"`: `FINANCE_HALF_COMPAT` 매핑으로 xlsx 반기 키와 호환 (별도 문서화)

**예시 (신보 주계정 2024)**:

```text
요약 재무상태표(결산) | 기금계정 | 신용보증기금 | 자산 > 자산총계
요약 재무상태표(결산) | 기금계정 | 신용보증기금 | 부채비율
```

### 3.2 budget (`31401`)

```text
수입지출현황(고유사업) | {row_label}
수입지출현황(기금계정) | {sub_account} | {row_label}
정부순지원수입(고유사업) | {row_label}                  ← row_label이 정부순지원수입으로 시작 시
정부순지원수입(기금계정) | {sub_account} | {row_label}
```

> budget 크롤 승격은 `sub_account`를 포함해 기금계정을 분리한다. `sub_account`가 비어 있는 기금계정 행은 파서 회귀로 보고 `validate_metrics_coverage.py`와 승격 리포트에서 확인한다.

### 3.3 executive_pay (`20501`)

```text
{clean_section} | {row_label}
```

### 3.4 승격 정책 (변경 제안)

**현재**: `(org, metric_key, year)` 그룹에 숫자 값이 2개 이상 → 전체 스킵.

**권장 (단계적)**:

1. **Phase A** (현재): 충돌 수·기관별 충돌을 리포트하고, 골든 기관 충돌 시 CI 실패
2. **Phase B**: 다계정 기금에서 `sub_account` 없는 finance/budget 행은 **승격 전에 차단** (파서 버그 조기 발견)
3. **Phase C**: xlsx fallback 제거 — 크롤만 정본, 충돌 시 담당자 수동 해결 후 재빌드

---

## 4. 엣지 케이스 레지스트리

파서·키 규칙 변경 시 **아래 기관은 반드시 재검증**한다.

| 유형 | org_code | 기관명 | 항목 | 검증 포인트 |
|------|----------|--------|------|-------------|
| **다계정 기금 (3계정)** | C0091 | 신용보증기금 | 31201, 31301, 31401 | `sub_account` 3종 분리, 주계정 자산총계·부채비율 |
| **다계정 기금 (2계정)** | C0130 | 중소벤처기업진흥공단 | 31201, 31401 | `중소기업창업 및 진흥기금` 등 |
| **단일계정 기금** | C0038 | 기술보증기금 | 31201 | `sub_account` 없거나 단일 `기술보증기금`, 키 중복 없음 |
| **공기업 표준** | C0247 | 한국전력공사 | 31201, 20501, 31401 | 반기·결산, HTML↔CSV roundtrip |
| **검증 시드** | C0847 | — | 20501, 31401 | 100% 일치 필수 |
| **다계정 (기타)** | C0013, C0028, C0045, C0187, C0223, C0388, C0412 | — | 31201 | HTML에 `기금계정:` 2회 이상 |
| **부분 공시** | — | 청렴도 등 | 40211 | 180/355 공시 — 미공시는 `해당사항 없음` |
| **명부형 (비시계열)** | — | 노조 | 21021 | deferred — 별도 스키마 필요 |

### 4.1 신보(C0091) 골든 수치 (2024 결산, 백만원)

HTML stem: `C0091_31201`, `sub_account=신용보증기금`

| row_label | value |
|-----------|-------|
| `자산 > 유동자산` | 13,575,522 |
| `자산 > 자산총계` | 15,774,985 |
| `부채 > 부채총계` | 3,578,356 |
| `부채비율` | 29.34 (%) |

이 수치가 `finance.json`·MCP `get_institution_metrics`에서 `item_query=" | 신용보증기금 |"`로 조회되어야 한다.

---

## 5. 전체 파이프라인 절차

새 공시 반영·파서 수정·항목 추가 시 **항상 이 순서**를 따른다.

```powershell
# 0. 환경
Set-Location <repo-root>
# .venv 활성화 권장

# 1. 크롤 (누락 doc 보충 또는 전량 재크롤)
python crawl_alio.py crawl          # 또는 프로젝트별 crawl 진입점
python scripts/check_crawl_completeness.py   # exit 1이면 중단

# 2. 파싱 → 정본 CSV
python parse_alio.py

# 3. 파싱 품질 게이트
python scripts/check_parse_duplicates.py     # 충돌 급증 시 중단
python scripts/validate_parse.py             # HTML↔CSV roundtrip, 시드 교차

# 4. (선택) 라이브 ALIO 대조 — 분기 1회 권장
python scripts/validate_live_alio.py         # 네트워크 필요

# 5. metrics 승격
python scripts/build_metrics.py              # xlsx 시드 (있다면)
python scripts/promote_crawl_metrics.py      # 크롤 → metrics 병합

# 6. 골든·도메인 검증
python scripts/validate_staff.py             # 해당 시
# → data/reference/golden_samples.json 대조 (validate_live_alio 내장)

# 7. 스냅샷·배포
python scripts/build_snapshot.py
$env:OPEN_ALIO_SNAPSHOT_PATH = (Resolve-Path dist\alio_snapshot.db).Path
python tests/test_smoke.py
python scripts/smoke_test.py
```

**파서/키 규칙을 바꿨다면** 2→5→7은 필수. **크롤만 갱신**했다면 1→2→5→7.

---

## 6. 검증 게이트 (CI에 넣을 조건)

| 게이트 | 스크립트 | 실패 조건 (권장) |
|--------|----------|------------------|
| 크롤 완전성 | `check_crawl_completeness.py` | 공시목록 O인데 `__doc.html` 없음 |
| 파싱 중복 | `check_parse_duplicates.py` | `conflict_groups` > baseline×1.5 또는 31201/31301 급증 |
| HTML roundtrip | `validate_parse.py` | 시드 C0847/C0247 budget 불일치, roundtrip FAIL |
| 승격 리포트 | `_crawl_promotion_report.json` | 골든 기관(C0091,C0247,C0038,C0130) conflict > 0 |
| 골든 수치 | `golden_samples.json` + custom | 핵심 수치 불일치 |
| 항목 수 회귀 | `scripts/validate_metrics_coverage.py` | 골든 기관 finance series_count < 기대치, 필수 키·골든 수치 불일치, 골든 기관 conflict > 0 |
| 스냅샷 | `build_snapshot.py` | validate_snapshot 실패 |
| MCP 스모크 | `tests/test_smoke.py` | 도구 응답 기대값 불일치 |

### 6.1 신규 스크립트 권장: `validate_metrics_coverage.py`

골든 기관별 최소 항목 수·필수 키 존재를 검사한다.

```python
# 예시 기대치 (finance, 2024 결산 존재 시)
GOLDEN_FINANCE_MIN = {
    "C0091": {"min_series": 80, "required_keys": [
        "요약 재무상태표(결산) | 기금계정 | 신용보증기금 | 자산 > 자산총계",
        "요약 재무상태표(결산) | 기금계정 | 신용보증기금 | 부채비율",
    ]},
    "C0038": {"min_series": 30, "required_keys": [
        "요약 재무상태표(결산) | 기금계정 | 자산 > 자산총계",
    ]},
    "C0247": {"min_series": 10, "required_keys": ["자산총계"]},  # 반기 키 호환
}
```

---

## 7. 골든 테스트 자산 확장

### 7.1 `data/reference/golden_samples.json`

형식 (기존 유지 + `sub_account` 필드 추가 권장):

```json
{
  "samples": [
    {
      "apba_id": "C0091",
      "item_no": "31201",
      "section": "2. 기금계정",
      "sub_account": "신용보증기금",
      "row_label": "자산 > 자산총계",
      "year": "2024",
      "value_type": "결산",
      "value": 15774985,
      "note": "ALIO 화면 2026-06-14 확인"
    }
  ]
}
```

**추가 우선순위**: §4 엣지 케이스 표의 모든 기관 × 핵심 3~5 수치.

### 7.2 `data/reference/live_validation_seeds.json`

라이브 fetch 시 HTML 변경·ALIO 개편을 조기 탐지. 분기 1회 실행.

---

## 8. 전 기관·전 항목 크롤 확장 로드맵

### 8.1 현재 커버리지 (2026-06 기준)

| item_no | doc.html | 비고 |
|---------|----------|------|
| 31201 | 355/355 | 재무상태표 — 거의 완료 |
| 31301 | 354/355 | 손익 — 1건 누락 |
| 31401 | 354/355 | 수입·지출 |
| 20501 | 344 | 임원연봉 |
| 21801 | 355 | 이직자 비율 |
| 31801 | 225 | 차입금 — 부분 공시 |
| 40211 | 180 | 청렴도 — 부분 공시 |
| 70461 | 335 | 산재 |

전체: **2,504 / 3,195** (355기관 × 9항목 이론치)

### 8.2 항목 확장 절차

1. `python crawl_alio.py discover` → `data/items_catalog.json` 갱신
2. `data/items.json`에 항목 추가 (tier·comment·deferred 사유)
3. **파서 확장** — 표 구조가 다르면 `parse_alio.py`에 item별 후처리 또는 별도 파서
4. **metric_key 함수** 추가 — `promote_crawl_metrics.py`의 `specs`에 등록
5. 골든 샘플 3기관 이상 추가 후 CI 통과
6. `data/metrics/_index.json`·MCP `list_metric_categories` 반영

### 8.3 xlsx 11종과의 관계 (장기)

| xlsx 카테고리 | 권장 최종 상태 |
|---------------|----------------|
| staff, salary, recruitment, welfare… | 크롤 항목번호 매핑 후 **크롤 정본 우선**, xlsx는 회귀 검증 |
| budget, executive_pay | 크롤 승격 + `sub_account` 완료 후 xlsx fallback **제거 검토** |
| finance (반기 xls) | 공기업 반기는 유지, 결산은 31201/31301 크롤만 정본 |

---

## 9. MCP 런타임 정확도 체크리스트

데이터 빌드 후 **반드시** MCP 경로로 확인한다.

```powershell
$env:OPEN_ALIO_DATA_DIR = "<repo-root>\data"
python -c "
from open_alio_mcp.metrics_store import get_metrics
r = get_metrics('C0091', 'finance', item_query=' | 신용보증기금 | 자산 > 자산총계')
assert r['found'] and r['series']
assert r['series'][list(r['series'].keys())[0]]['2024'] == 15774985
print('OK')
"
```

실행 중인 Cursor MCP는 **스냅샷 캐시**를 쓸 수 있다. `OPEN_ALIO_DATA_DIR` 또는 `OPEN_ALIO_SNAPSHOT_PATH` 설정 후 **MCP 서버 재시작** 필수.

---

## 10. AI 에이전트용 개발 프롬프트 (복사용)

아래 블록을 Cursor Agent / 작업 지시에 **그대로 붙여넣어** 사용한다.

---

```markdown
## 작업: open-ALIO-mcp ALIO 데이터 정확도 개선

### 미션
ALIO 공시 원문과 100% 일치하는 로컬 데이터를 만든다. 사용자는 ALIO 웹 대신 MCP에 질문한다.
**정확도 > 완성 속도**. 추정·합산·조용한 스킵 금지.

### 필수 참고 문서
- `docs/data-accuracy-spec.md` (이 명세 — 모든 변경은 여기 원칙을 따름)

### 데이터 계층 (정본 순서)
1. `rawdata/html/{apba_id}_{item_no}__doc.html` — ALIO 원문
2. `data/crawl/alio_records.csv` — parse 정본 (FIELDS 스키마 계약)
3. `data/metrics/*.json` — MCP 파생본
4. `dist/alio_snapshot.db` — 배포

### 스키마 계약 (`parse_alio.py` FIELDS)
apba_id, org_name, item_no, item_name, section, **sub_account**, row_label, year, value_type, value, unit, as_of, source_url

**sub_account**: nb 표 `기금계정: XXX`에서 추출. 다계정 기금(신보 C0091 등)에서 필수.
동일 (apba_id, item_no, section, row_label, year, value_type)에 서로 다른 value가 있으면
**sub_account 누락 버그**를 먼저 의심할 것.

### metric_key 규칙 (`scripts/promote_crawl_metrics.py`)
- finance: `요약 재무상태표(결산) | 기금계정 | {sub_account} | {row_label}`
- budget: `수입지출현황(기금계정) | {sub_account} | {row_label}`
- 충돌 시 스킵만 하지 말고 리포트·테스트·caveats 반영

### 엣지 케이스 골든 기관 (변경 후 무조건 검증)
C0091(신보·3계정), C0038(기보), C0130(중진공), C0247(한전), C0847(시드)

신보 2024 주계정 자산총계 = 15,774,985 (백만원) — ` | 신용보증기금 | 자산 > 자산총계`

### 작업 시 금지
- `-`·빈칸을 0으로 변환
- 충돌 그룹을 사용자에게 숨기고 "미공시"처럼 응답
- metric_key 규칙을 파서 밖에서 임의 문자열로 생성
- 골든 테스트 없이 파서/키 규칙 변경
- 관련 없는 리팩터링·범위 확대

### 작업 완료 후 필수 실행
python parse_alio.py
python scripts/check_parse_duplicates.py
python scripts/validate_parse.py
python scripts/promote_crawl_metrics.py
python scripts/build_snapshot.py
# 골든: C0091 finance series >= 80, conflict 0

### 산출물
- 변경 이유를 명세 §4 엣지 케이스 레지스트리에 반영 (새 패턴이면 행 추가)
- `data/reference/golden_samples.json`에 수치 1건 이상 추가
- `_crawl_promotion_report.json`에서 해당 기관 conflict 0 확인
```

---

## 11. 변경 체크리스트 (PR·커밋 전)

- [ ] `docs/data-accuracy-spec.md` 원칙 위반 없음
- [ ] `parse_alio.py` FIELDS 변경 시 CSV·JSON·검증 스크립트 동기화
- [ ] 다계정 기금 stem HTML 수동 확인 또는 골든 통과
- [ ] `check_parse_duplicates.py` 충돌 수 baseline 대비 급증 없음
- [ ] `validate_parse.py` 시드(C0847,C0247) 통과
- [ ] `_crawl_promotion_report.json` 골든 기관 conflict = 0
- [ ] `golden_samples.json` 핵심 수치 추가/갱신
- [ ] `build_snapshot.py` + `test_smoke.py` 통과
- [ ] MCP `OPEN_ALIO_DATA_DIR`로 골든 조회 확인
- [ ] 사용자-facing caveats 업데이트 (충돌·미공시·다계정 조회법)

---

## 12. 관련 파일 인덱스

| 경로 | 역할 |
|------|------|
| `parse_alio.py` | HTML → CSV 파서, 스키마 정의 |
| `crawl_alio.py` | ALIO HTML 수집 (gitignore 가능) |
| `scripts/promote_crawl_metrics.py` | CSV → metrics 승격·키 규칙 |
| `scripts/build_metrics.py` | xlsx 시드 빌드 |
| `scripts/validate_parse.py` | HTML↔CSV·교차검증 |
| `scripts/validate_live_alio.py` | 라이브 ALIO 대조 |
| `scripts/check_parse_duplicates.py` | CSV 값 충돌 통계 |
| `scripts/check_crawl_completeness.py` | doc.html 누락 |
| `scripts/build_snapshot.py` | 스냅샷 패키징 |
| `data/reference/golden_samples.json` | 골든 수치 |
| `data/reference/live_validation_seeds.json` | 라이브 검증 시드 |
| `data/metrics/_crawl_promotion_report.json` | 승격·충돌 리포트 |
| `src/open_alio_mcp/metrics_store.py` | MCP 조회 레이어 |

---

## 13. 문서 갱신 이력

| 날짜 | 내용 |
|------|------|
| 2026-06-14 | 초안 — 신보 sub_account 사건 반영, 정본 스키마·골든·에이전트 프롬프트 확정 |
