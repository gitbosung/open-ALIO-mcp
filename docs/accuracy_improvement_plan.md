# 정확도 개선 계획 (Accuracy Improvement Plan)

> **이 문서의 역할**: "ALIO와 값이 100% 같은가"를 최우선으로, 무엇을 어떤 순서로 개선할지 추적하는 **단일 실행 트래커**다.
> 규칙·원칙의 근거는 [`data-accuracy-spec.md`](data-accuracy-spec.md)에, v2 파서 설계 이슈는 [`parser_v2_review_notes.md`](parser_v2_review_notes.md)(PR #5), 전환 경위는 [`parser_v2_transition_plan.md`](parser_v2_transition_plan.md)에 있다. 이 문서는 그 위에서 **"지금 뭘, 어떤 순서로"** 만 관리한다.
>
> **어디서든 보기**: 이 파일은 GitHub에 올라가므로 다른 컴퓨터·모바일(GitHub 앱/웹)에서 그대로 읽을 수 있다.
> **갱신 규칙**: 작업하며 체크박스를 갱신하고, 세션 끝에 [`../.ai/HANDOFF.md`](../.ai/HANDOFF.md)에 "지금 어디까지"만 적는다.

Updated: 2026-07-08

---

## 0. 북극성 (North Star)

**사용자가 ALIO 웹에서 보는 값 == MCP가 주는 값.** 정원·재무 등 핵심 수치가 원문과 일치해야 한다.
정확도 > 사용자 체감 > 배포 속도. 추정·합산·조용한 스킵 금지 (Fail Loud, spec §1.2).

## 1. 지금 상황 정리 (냉정하게)

- **현재 배포본(`uvx open-alio-mcp` v0.1.1)은 v1이다.** v2 canonical DB·finance 파생물은 `.gitignore`라 패키지에 없다 → 사용자는 v2 개선을 **아직 체감 못 함**.
- **현재 v2 검증은 "정확성"이 아니라 "일관성"만 증명한다.** `build_metrics_from_canonical.py`의 0 mismatch는 **v2 vs v1** 비교다. v1 자체가 축 flatten·항목 누락 손실이 있어(ALIO 대비 최고 96.15%), v1과 같아진다고 ALIO와 같아지는 게 아니다.
- **정확도 측정 장치는 이미 있다 — 단 v1에 묶여 있다.** `data-accuracy-spec.md`가 정의한 골든 샘플(`golden_samples.json`), 라이브 대조(`validate_live_alio.py`), CI 게이트, 엣지 골든 기관(C0091 신보 등)이 v1 파이프라인 기준으로 존재한다. **이걸 v2 canonical로 확장하는 것이 이 계획의 뼈대다.**

## 2. 우선 카테고리

1. **재무** (31201 재무상태표, 31301 손익, 31401 수입·지출) — 다계정 기금·회계기준(K-IFRS/GAAP·연결/별도) 정확도
2. **정원/현원** = **item_no `20201` 임직원 수** (staff 카테고리). 정원≠현원 구분은 v1에 이미 모델링됨 ([metrics_store.py](../src/open_alio_mcp/metrics_store.py) `_STAFF_PRIORITY`/`_STAFF_CAVEATS`) → v2에서 값 일치 검증·승격이 과제.
3. **임원연봉** (20501), **예산** (31401)

각 카테고리는 **ALIO 원문 대비 0 불일치**(정정공시·기간차 제외)를 통과해야 "완료"로 본다.

---

## 3. 실행 순서 (Phase A → E)

### Phase A. 정확도 측정 기반을 v2로 확장 — **최우선**

목표: "v2 canonical의 값이 ALIO 원문과 같은가"를 **수치로** 말할 수 있게 한다.

**A-지금 (기준점: 이미 있는 `golden_samples.json` + 2025 Q1 XLSX 활용)** — 즉시 착수 가능:

- [ ] **A-2. 골든 샘플을 v2 canonical로 대조** — `golden_samples.json`의 검증 수치(예: 신보 C0091 자산총계 15,774,985)를 **v2 canonical 조회 경로로도** 검증하는 테스트 추가. (spec §4.1, §7.1)
- [ ] **A-3. 항목·값 단위 대조 하네스** — v2 → 골든/XLSX 값 비교, **항목별 정확 일치율** 리포트. 불일치를 5분류: `기간차 / 미크롤 / 첨부전용 / 파서구조손실 / 정정공시`. (기존 `build_metrics_from_canonical.py`의 v1비교 로직을 골든 대조로 승격)
- [ ] **A-5. 카테고리별 정확도 스코어카드** 산출물 정의 — 이후 모든 Phase의 합격/불합격 판정 기준.

**A-나중 (기간 맞춘 2026 Q1 기준점 확보 후 — 현재 대기)**:

- [ ] **A-1. 기준점(ground truth) 기간 정합** — HTML=2026 Q1 vs 검증 rawdata=2025 Q1 불일치 해소. 2026 Q1 공식 XLSX 확보 또는 대표 기관 재크롤. ⏳ *기준점 확보 시.* (spec §5-4)
- [ ] **A-4. 라이브 ALIO 대조를 v2에 연결** — `validate_live_alio.py`가 v2 canonical도 검사하도록 확장(분기 1회). ⏳ *A-1 이후.* (spec §5-4, §7.2)

### Phase B. 파서 구조 손실 제거 (불일치의 근본 원인)

`parser_v2_review_notes.md`의 미구현 이슈. 재무·정원 정확도에 직결.

- [x] **B-0. 침묵 손실 게이트** (Issue 1) — `unparsed_table`/`table_no_records`/`skipped_short_nb` 경고 + `source_docs` 문서별 커버리지. *(구현됨)*
- [ ] **B-1. 분류 오류로 데이터 실종 차단** (Issue 2) — `classify_table`이 애매한 표를 무조건 `attribute`로 반환(현재 line 433). `unclassified` fallback + 분류 confidence 저장. "type 필터 없으면 모든 셀이 보인다"를 불변식으로 테스트.
- [ ] **B-2. 표 단위 엔티티 `source_tables`** (Issue 3·4) — table_id, 헤더 매트릭스(JSON), n_rows/cols, caption, confidence. 셀은 table_id FK. → 다층 헤더·차원 붕괴 방지(재무 연결/별도, 정원 정원/현원 구분).
- [ ] **B-3. 결정적 `natural_key`** (Issue 5) — `(org_code, item_no, table_index, row_index, col_index, period_label)` + roster 반복행 순번. dedup·idempotent 재빌드.
- [ ] **B-4. `normalized_value` 정밀도** (Issue 6, 낮음) — `raw_value`를 정본으로 문서화 + 손실 라운드트립 검증.

### Phase C. 카테고리별 정확도 게이트 (재무 · 정원 먼저)

- [ ] **C-1. 재무** — 434 skipped conflict(K-IFRS/GAAP·연결/별도·구/신 국가회계기준)를 `finance_context` 무손실성으로 정량 검증. 기본 대표값이 ALIO 대표표와 일치하는지 확인. 다계정 기금 `sub_account` 3계정 분리 검증(신보 C0091). (spec §2.1, §3.1)
- [ ] **C-2. 정원/현원** — 정원≠현원 구분이 ALIO 표시와 정확히 일치. (항목번호 확정 후)
- [ ] **C-3. 임원연봉(20501)·예산(31401)** — 골든 기관 0 불일치.
- [ ] **C-4. promotion readiness 기준 명문화** — "conflict 0"만으로 승격 금지. 카테고리별 최소 series·필수 키·골든 수치 통과 기준 정의. (spec §3.4, §6.1 `validate_metrics_coverage.py`)

### Phase D. 커버리지 갭 (누락 = 정확도의 극단적 실패)

- [ ] **D-1. 미크롤 항목 크롤 확장** — 21201 징계, 21211 징계처분, 21301 소송, 21311 고문변호사, 21621 에너지, 21631 폐기물, 21641 용수, 31601 투자집행, 31921 퇴직자 재취업. (transition_plan "Rawdata items absent", spec §8.2 절차)
- [ ] **D-2. 구조적 약항목 검증** — 20801 복리후생, 63701 텍스트규정, 31901 roster, 31701 attribute, 32301 첨부, 32311·32101·70301. v2 파싱 결과를 원문과 대조.

### Phase E. 배포 게이트 (검증 통과분만) — **맨 마지막, 카테고리별 조건부**

- [ ] **E-1. canonical 릴리스 파이프라인** — 전체 항목 canonical DB + 파생물을 GitHub Release asset으로. `ensure_snapshot()`이 canonical도 받도록 확장. (현 `alio_snapshot.db` 방식 준용)
- [ ] **E-2. 카테고리별 조건부 배포** — 정확도 게이트(Phase C) 통과 카테고리만 v2 파생을 기본 소스로 승격. 미검증 v2 배포 금지(부정확 확산 방지).
- [ ] **E-3. 이중 스택 정리** — v2 신뢰 확보 후 v1/v2 dual path 제거, canonical→파생→MCP 단일 경로. v1은 아카이브/임시 fallback만. (transition_plan §9)

---

## 4. Open Questions

- [x] **정원/현원 ALIO 항목번호** → **`20201` 임직원 수** (staff 카테고리, 정원/현원 구분 v1에 기구현). *(2026-07-08 해소)*
- [ ] **2026 Q1 기준점 확보** — 기간 맞춘 공식 XLSX/원본. ⏳ **지금은 불가, 나중 확보 예정** → A-1/A-4는 그때까지 대기. 그 전까지는 골든 샘플 + 2025 Q1 XLSX를 기준점으로 A-2/A-3 진행.

## 5. 참고 문서 지도

| 문서 | 역할 |
|---|---|
| [`data-accuracy-spec.md`](data-accuracy-spec.md) | **규칙·원칙**(정본 스키마, metric_key, 골든 기관, CI 게이트, Fail Loud) — 변경의 근거 |
| **이 문서** | **실행 계획·상태 트래커** — 무엇을 어떤 순서로 |
| [`parser_v2_review_notes.md`](parser_v2_review_notes.md) *(PR #5)* | v2 파서 설계 이슈 상세(Issue 1~6) |
| [`parser_v2_transition_plan.md`](parser_v2_transition_plan.md) | v2 전환 경위·커버리지 갭·구현 로그 |
| [`roadmap.md`](roadmap.md) | 제품 전체 Phase 1~4 |
