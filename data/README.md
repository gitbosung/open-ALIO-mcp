# data — 런타임 데이터

MCP 서버가 읽는 **병합·정규화가 끝난 런타임 데이터**입니다.
이 저장소에는 런타임 데이터와 배포 패키지만 포함하며, 원본 수집·빌드 파이프라인
(엑셀·CSV·HTML 원본, 크롤러·파서·빌드 스크립트)은 별도 데이터 파이프라인 저장소에서 관리합니다.

## 현재 파일

| 파일 | 설명 |
|---|---|
| `aliases.json` | 기관 별칭 사전 (`"한전"` → `"한국전력공사"`) |
| `institutions.json` | 기관 355개 공시 단위 (342 독립 지정 + 13 부설) — 기관코드·주무부처·설립목적 |
| `metrics/` | 항목별 지표 JSON 11종 + `_index.json` |
| `reference/disclosure_items.json` | ALIO 50개 공시항목 카탈로그 (정기/수시·공시주기·metric 매핑) |
| `reference/disclosure_coverage.json` | 항목별 ALIO 공시 보유 기관 목록 (organlist 스냅샷, `build_disclosure_coverage.py`) |
| `reference/related_laws.json` | 공공기관 핵심 법령·행정규칙 화이트리스트 |
| `guidelines/` | 연도별 시달 지침 파싱 JSON + `_index.json` |
| `handbook/` | 경영평가편람 파싱 JSON + `_index.json` |
| `snapshots/recruitments_ongoing.json` | 진행중 채용공고 스냅샷 (검색·분포 집계 오프라인용) |
| `parsed/by-org/` | (Phase 3) 기관별 통합공시 파싱 결과 `{org_code}.json` |
| `cache/` | 런타임 캐시 (git 제외, `.gitkeep`만 추적) |

> 배포(`uvx`) 환경에서는 `data/`가 없을 수 있으며, 서버가 GitHub Release의 `alio_snapshot.db`를
> 내려받아 위 런타임 파일과 동일한 내용을 제공합니다. 스냅샷에 담기는 파일 목록은
> `src/open_alio_mcp/snapshot.py`의 `RUNTIME_DATA_GLOBS` 참조.

## metrics/ 카테고리

`staff`(임직원), `salary`(평균보수), `executive_pay`(임원연봉), `recruitment`(신규채용),
`budget`(수입지출), `welfare`·`welfare_etc`(복리후생), `work_life`(일가정양립),
`tax`(법인세), `head_expense`(업무추진비), `finance`(재무)

공통 구조:

```json
{
  "_meta": {"category": "...", "unit": "...", "years": [...], "caveats": [...]},
  "orgs": {"C0247": {"name": "한국전력공사", "series": {"항목명": {"2021": 123}}}}
}
```

## 주의

- 기관 식별 PK는 `org_code`(=NKOD `instCd`).
- 금액 단위는 카테고리별 상이 (보수·복리후생 천원 / 수입지출·재무 백만원) — `_meta.unit` 참조.
- `finance`, `budget`, `executive_pay`는 ALIO 공시 검증값을 병합한 결과이며, 값이 충돌한 그룹은
  자동 선택하지 않고 기존 엑셀 값을 유지합니다. 병합·승격은 데이터 파이프라인 저장소에서 수행합니다.
