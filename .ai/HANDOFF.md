# HANDOFF — 현재 작업 상태

> 이 파일이 세션 간 인수인계의 **단일 소스**다. (구 `SESSION_STATE.md` / `NEXT_PROMPT.md` 대체)
> 규칙 · 브랜치 · 핸드오프 절차는 [../AGENTS.md](../AGENTS.md) 참조.
> 세션을 마칠 때 이 파일을 갱신한다: "지금 상태" · "다음 할 일"만 최신으로 유지하면 된다.

Updated: 2026-07-06

## 지금 상태

- 배포: PyPI `open-alio-mcp==0.1.1` 사용 가능 (v1 데이터). `uvx open-alio-mcp` 로 실행.
- v2/canonical 작업은 **아직 미배포(전환 중)** — 아래 PR #5에서 진행.
- main 최신: PR #4 머지됨 — `search_institutions(location=...)` + 별칭 대소문자 매칭.

### 진행 중인 브랜치 / PR

- `codex/parser-v2-canonical-finance` → **PR #5 (draft)** "[codex] Add canonical parser v2 and finance basis metadata" (base: main)
  - PR #4 내용을 이 브랜치에 병합 완료(`f4020f0`) + 병합 입력 검증 보강(`6471471`).
- `chore/agent-handoff` → 에이전트 핸드오프 체계 정리(AGENTS.md / CLAUDE.md / 이 파일). ← 지금 이 작업.

## 진행 중 작업 요약 (v2 / canonical)

- ALIO HTML → canonical 셀 레코드 파서 `parse_alio_v2.py` (+ coverage 경고 3종) + SQLite store + MCP 도구 4종.
- canonical 파생 metrics 후보 빌더 + `finance_context`(v2-only, 회계기준 context 보존).
- finance 응답: 기본 대표값 + `basis`, 기준별은 `item_query` 요청 시만 (AGENTS.md §5 불변식).
- disclosure coverage 도구(`get_disclosure_coverage`): 미공시 vs 비대상 구분.

## 다음 할 일

1. PR #5 diff 리뷰 — 생성물이 섞이지 않았는지, 위험 지점 확인.
2. `gh pr checks 5 --repo gitbosung/open-ALIO-mcp` 확인, 실패 시 로그 보고 수정.
3. finance `basis` 필드 agent 친화성 검토 (`representative_context` / `has_other_contexts` / `status`).
4. parser readiness 기준 구체화: `source_tables`, stable table IDs/header matrix, deterministic `natural_key`, `record_type` 신뢰도/모호성 처리.
5. 핸드오프 체계(`chore/agent-handoff`) 머지 후: PR #5에 남아 있는 구 `.ai/SESSION_STATE.md`, `.ai/NEXT_PROMPT.md`는 삭제하고 이 HANDOFF.md로 일원화.

## 로직 변경 시 재빌드 · 비교 (참고)

```powershell
python scripts/build_canonical_store.py --items 20501,31201,31301,31401 --out data/canonical/_metrics_seed_canonical.db
python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db
# 그다음 AGENTS.md §6 테스트 실행
```
