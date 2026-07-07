# AGENTS.md — 에이전트 작업 규칙

이 저장소는 여러 AI 에이전트(Codex, Claude Code 등)와 사람이 함께 작업한다.
**모든 에이전트는 세션 시작 시 이 파일을 먼저 읽고 따른다.**
(Claude Code는 `CLAUDE.md`를 통해 이 파일로 안내된다.)

## 0. 황금 규칙

- **진실의 원천은 git과 파일이다. 대화 기억을 믿지 마라.**
- 불확실하면 실제 파일 · `git` · 보고서를 열어서 확인한다.

## 1. 세션 시작 절차 (Startup)

새 세션은 항상 이 순서로 시작한다:

```
git fetch origin
git status -sb
git log --oneline --decorate --graph -8
```

**다른 기기 / 새 컴퓨터에서 시작할 때는** 먼저 최신을 받는다 (fetch만으로는 작업트리가 안 바뀐다):

```
git pull                              # 현재 브랜치를 원격 최신으로
# 이어받을 브랜치가 따로 있으면:  git switch <브랜치> && git pull
```

그다음 **[.ai/HANDOFF.md](.ai/HANDOFF.md)** (현재 상태 · 다음 할 일)와
정확도 작업 트래커 **[docs/accuracy_improvement_plan.md](docs/accuracy_improvement_plan.md)** 를 읽는다.
열린 PR이 있으면 `gh pr view <번호>` 로 확인한다.

## 2. 브랜치 규칙

- **한 에이전트 = 한 브랜치.** 접두사: Codex는 `codex/<주제>`, Claude Code는 `claude/<주제>`.
- 항상 **최신 `origin/main`에서 분기**한다.
- `main`에 직접 커밋 · 푸시하지 않는다. 항상 브랜치 → PR.
- 나중에 머지하는 브랜치가 최신 main을 자기 쪽으로 먼저 병합할 책임을 진다.

## 3. 핸드오프(인수인계) 규칙

멈추기 전에 **반드시**:

1. 작업을 **커밋하고 브랜치를 푸시**한다. (더티 작업트리로 넘기지 않는다)
2. **[.ai/HANDOFF.md](.ai/HANDOFF.md)** 를 현재 상태로 갱신한다.

다음 에이전트는 AGENTS.md + HANDOFF.md를 읽고, `fetch` 후 해당 브랜치를 체크아웃한다.
(새 작업이면 최신 main에서 새 브랜치를 판다.)

> 사람(운영자)이 에이전트를 바꿀 때: 떠나는 쪽에 "커밋·푸시하고 HANDOFF 갱신 후 멈춰줘",
> 켜는 쪽에 "AGENTS.md 읽고 시작 절차 따라줘" 한 줄씩만 전달하면 된다.
> 내용을 사람이 직접 복붙 릴레이하지 않는다 — 브랜치와 HANDOFF.md가 그 역할을 한다.

## 4. 커밋 금지 대상 (생성물)

스크립트로 재생성되는 산출물은 커밋하지 않는다 (`.gitignore` 참조):

- `data/canonical/*.db`, `*.db-shm`, `*.db-wal`, `*.jsonl`
- `data/canonical/metrics_v2*/`
- 생성된 요약 JSON, `data/validation_reports/canonical_v2_*` 산출물

커밋 전 `git status` 로 산출물이 섞이지 않았는지 확인한다.

## 5. 데이터 · 설계 불변식 (깨지 말 것)

- **`data/metrics/*.json` (v1 정본)을 덮어쓰지 않는다.** v2 후보는 `data/canonical/metrics_v2/`에만 쓴다.
- **finance 응답 정책**: 기본 호출은 대표값 + `basis`(기준 설명)만 반환하고,
  기준별 값은 `item_query`로 요청할 때만 반환한다 (`basis.mode == "context_query"`). **되돌리지 않는다.**
- finance 충돌군에서 값을 자동으로 하나 선택하지 않는다.
- `executive_pay` / `budget`은 targeted 비교에서 충돌 0이어도 성급히 promotion하지 않는다. readiness 기준을 먼저 정의한다.
- v1/v2 이중 스택은 임시(transition)다. 최종 목표는 canonical → 파생지표 → MCP 단일 경로.

## 6. 검증

로직 변경 후 다음을 통과시킨다 (pytest 미설치 환경이면 직접 호출):

```
python tests/test_smoke.py
python -c "import tests.test_metrics_store as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"
python -c "import tests.test_parser_v2 as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"
python -c "import tests.test_canonical_store as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"
python -c "import tests.test_metrics_from_canonical as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"
```

파서/지표 로직을 바꿨으면 canonical DB를 재빌드한 뒤 비교 리포트를 확인한다
(명령은 HANDOFF.md 참조).
