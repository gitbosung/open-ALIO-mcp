# HANDOFF — 현재 작업 상태

> 이 파일이 세션 간 인수인계의 **단일 소스**다. (구 `SESSION_STATE.md` / `NEXT_PROMPT.md` 대체)
> 규칙 · 브랜치 · 핸드오프 절차는 [../AGENTS.md](../AGENTS.md) 참조.
> 세션을 마칠 때 이 파일을 갱신한다: "지금 상태" · "다음 할 일"만 최신으로 유지하면 된다.

Updated: 2026-07-08

## 최우선 방향

**정확도 최우선**: MCP 값 == ALIO 원문 값. 전체 계획·순서·상태는
**[docs/accuracy_improvement_plan.md](../docs/accuracy_improvement_plan.md)** 에서 추적한다 (이게 실행 트래커).

## 지금 상태

- 배포: PyPI `open-alio-mcp==0.1.1` 사용 가능 (v1 데이터). v2는 정확도 게이트 통과 후 배포(Plan Phase E).
- **main에 v2 전체 병합됨** (PR #4·#5·#6 머지 완료). v2 코드·canonical·finance basis·계획서·핸드오프 체계 모두 main에 있음.
- **A-2 완료**: `scripts/validate_golden_canonical.py` → 골든 **7/8 MATCH** (신보 3계정 자산총계 15,774,985 등 정확 일치).

### 열린 PR / 브랜치

- `claude/accuracy-a2-golden-v2` → A-2 하네스 + 계획서 갱신 + 구 `.ai` 정리. main에 머지 대기.

## 다음 할 일

> 상세·우선순위는 [accuracy_improvement_plan.md](../docs/accuracy_improvement_plan.md) 참조.

1. **B-5 파서 수정** — col_year 단일 라벨열 표의 자식행 `(남성)`에 부모행 prefix (v1 Phase 2a를 v2로 포팅). 검증: `C0001 20601` 골든이 MATCH 되도록. ← **다음 착수 유력**
2. **A-3** — 골든 대조 하네스를 전 항목·5분류 태깅으로 확장.
3. Open Question: 2026 Q1 기준점 확보 시 A-1/A-4(라이브 ALIO) 착수.

## 로직 변경 시 재빌드 · 비교 (참고)

```powershell
# 골든 대조 (A-2)
python scripts/build_canonical_store.py --orgs C0247,C0091,C0001,C0005 --items 31201,32211,31501,20601,31701 --out data/canonical/_golden_canonical.db
python scripts/validate_golden_canonical.py --db data/canonical/_golden_canonical.db
# 재무 v1/v2 비교
python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db
# 그다음 AGENTS.md §6 테스트 실행
```

## 로직 변경 시 재빌드 · 비교 (참고)

```powershell
python scripts/build_canonical_store.py --items 20501,31201,31301,31401 --out data/canonical/_metrics_seed_canonical.db
python scripts/build_metrics_from_canonical.py --db data/canonical/_metrics_seed_canonical.db
# 그다음 AGENTS.md §6 테스트 실행
```
