# docs — 프로젝트 문서

`open-alio-mcp` MCP 서버의 기술·정책 문서입니다.

| 파일 | 내용 |
|---|---|
| [`architecture.md`](architecture.md) | 모듈·데이터 레이어 구조, 설계 원칙 |
| [`data_sources.md`](data_sources.md) | 데이터 출처·기준일·갱신주기·갱신 절차·fallback |
| [`testing.md`](testing.md) | 테스트 종류, 도구별 검증 현황, 테스트 계획 |
| [`roadmap.md`](roadmap.md) | Phase 1~4 로드맵 |
| [`../SECURITY.md`](../SECURITY.md) | 보안 정책 — 로컬 사용 기준·공개 배포 전 점검 |
| [`../examples/`](../examples/) | 질의 예시 모음 + 대표 질의의 기대 동작 |

> 데이터 빌드 파이프라인(크롤러·파서·빌드 스크립트·원본 rawdata)과 개발 이력 문서는
> 별도 데이터 파이프라인 저장소에서 관리합니다. 이 저장소는 배포 패키지와 런타임 데이터만 포함합니다.
