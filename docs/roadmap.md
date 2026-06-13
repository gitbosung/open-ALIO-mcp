# Roadmap

open-ALIO-mcp는 한국 공공부문 AI 지식 레이어(public-sector AI knowledge layer)의
기반(foundation)으로 설계되었습니다. 어려운 도메인 모델링 — 기관 식별·별칭, 공시 주기,
정원/현원 구분, 지표 단위, 출처 표기 — 은 대부분 이미 구현되어 있으며,
남은 작업은 주로 패키징·테스트·데이터 갱신·배포 통제 같은 운영 보강(operational hardening)입니다.

## Phase 1 — 로컬 MCP 프로토타입 ✅ 완료

- ALIO / ALIO Plus(NKOD OpenAPI) 데이터 연결
- 기관 검색 (별칭·부분일치) · 프로필 · 지점
- 지표 11종 시계열 · 비교 · 조건 스크리닝 · 인력 요약
- 대민서비스: 채용·시설·국가사업 검색
- 뉴스 검색 · 360° 브리핑 · 뉴스↔지표 교차검증
- 법령·행정규칙·로컬 지침 · 경영평가편람 조회
- 모든 응답에 source · as_of_year · unit · caveats 표기
- 공통 보안 래퍼 (입력 검증 · 응답 제한) · 보안 점검 보고서

## Phase 2 — 신뢰 가능한 오픈소스 MCP 서버 (진행 중)

- [x] PyPI 배포 (`open-alio-mcp==0.1.1`)
- [x] `uvx open-alio-mcp` 최종 사용자 실행 경로 검증
- [x] GitHub Release `alio_snapshot.db` + `.sha256` asset 배포
- [x] 패키지 설치 환경의 SQLite snapshot provider 검증
- [x] 스모크 테스트 (`scripts/smoke_test.py`, `scripts/security_smoke_test.py`)
- [x] 크롤 데이터 검증·승격 파이프라인
- [x] 표준 문서 정비 (architecture / data_sources / testing / SECURITY / examples)
- [x] 오프라인 CI 스모크 테스트 (GitHub Actions)
- [ ] fixture 기반 회귀 테스트 (API mock 포함)
- [x] `pyproject.toml` 패키징 · `pip install -e .` 지원
- [ ] tool별 입출력 명세 문서 (`tool-schema.md`)

## Phase 3 — 공공부문 AI 지식 레이어 (계획)

- 경영평가 **결과**(등급·지적사항) 데이터 통합
- 국회 의안정보 · 국정감사 자료 연계
- 나라장터(조달) 데이터 연계
- 공공데이터포털 추가 데이터셋 연계
- 기관별 지식카드 (프로필 + 지표 + 뉴스 + 평가 종합)
- 대국민 챗봇 데모
- 데이터 거버넌스 · 출처 검증 체계 고도화

## Phase 4 — 운영 배포 (계획)

- HTTP/SSE 배포 템플릿 (reverse proxy 구성 포함)
- 인증 (SSO 연계 포함) · rate limiting · CORS allowlist · security headers
- 사용자 식별 감사로그 · 모니터링
- 데이터 갱신 자동화 (스케줄 빌드 + 검증 게이트)
- 공공기관 보안성 검토 대응

## 비전

> 공공기관 정보는 이미 공개되어 있지만, 국민과 실무자가 원하는 질문 단위로 접근하기 어렵습니다.
> open-ALIO-mcp는 이 간극을 MCP tool로 메워, 기재부·주무부처·공공기관의 업무지원과
> 대국민 공공기관 정보서비스로 확장 가능한 기반을 지향합니다.
