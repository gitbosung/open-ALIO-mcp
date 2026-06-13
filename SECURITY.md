# Security Policy

## 지원 사용 범위 (Supported usage)

현재 버전은 **로컬 stdio MCP 사용**과 통제된 내부 데모를 기준으로 설계되었습니다.
공개 HTTP/SSE 배포는 아래 [공개 배포 전 점검](#공개-배포-전-점검-public-deployment-notice)을
완료하기 전에는 권장하지 않습니다.

## 민감정보 취급 원칙 (Sensitive information)

- API 키를 코드·문서·테스트 파일에 직접 작성하지 않습니다. 로컬 개발은 `.env`, MCP 클라이언트 실행은 설정 파일의 `env` 블록이나 배포 환경변수로 관리합니다.
- API 키를 URL query parameter로 전달하지 않습니다 — 브라우저 기록·프록시·서버 로그에 남을 수 있습니다.
- `.env`, `.env.*`, 로그 파일, 키가 포함된 curl 기록(`rawdata/**/with-key/`)은 `.gitignore`로 커밋이 차단됩니다.
- 외부 API 오류 로그는 `serviceKey`, `LAW_API_OC`, `NAVER_CLIENT_SECRET` 등 민감값을 마스킹합니다.
- 키가 채팅·로그 등에 노출된 적이 있다면 즉시 폐기하고 재발급하세요 (data.go.kr / developers.naver.com / open.law.go.kr).

## 현재 적용된 보안 통제 (Implemented controls)

- 모든 MCP tool 등록은 공통 보안 래퍼(`security_utils.py`)를 거쳐 입력값의 길이·범위·허용값을 검증합니다.
- 응답 크기는 `MAX_RESPONSE_CHARS`, 항목 수는 `MAX_ITEMS_PER_TOOL`로 제한해 LLM context 오염과
  클라이언트 불안정을 방지합니다.
- 입력 검증 회귀는 `scripts/security_smoke_test.py`로 점검합니다.

## 공개 배포 전 점검 (Public deployment notice)

이 서버를 HTTP/SSE로 외부에 노출하기 전에 다음을 반드시 적용·검토해야 합니다.

- 인증 (authentication) — 익명 접근 차단, 필요 시 SSO 연계
- rate limiting — reverse proxy 또는 앱 서버 레벨
- CORS allowlist — `CORS_ORIGIN=*` 금지, 공식 서비스 도메인만 허용
- security headers
- 요청·사용자 식별 감사로그 (audit logging)
- timeout / retry / cache invalidation 정책
- 데이터 거버넌스·개인정보 검토 — 개인정보성 필드 마스킹 포함
- 내부망 도입 시: 내부 데이터와 공개 데이터 tool 분리 정책 확정

## 취약점 신고 (Reporting a vulnerability)

보안 취약점을 발견하면 공개 이슈 대신 GitHub Security Advisory(Private vulnerability reporting)
또는 저장소 관리자에게 비공개로 알려주세요. 재현 절차와 영향 범위를 함께 보내주시면
빠른 확인에 도움이 됩니다.
