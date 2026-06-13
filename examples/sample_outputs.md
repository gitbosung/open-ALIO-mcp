# 대표 질의의 기대 동작 (Sample outputs)

각 예시는 사용자 질문 → AI의 tool 조합 → 기대 동작·응답 형식을 보여줍니다.
모든 tool 응답은 공통 구조를 가집니다:

```json
{
  "data": { "...": "조회 결과" },
  "source": {
    "system": "ALIO 공공기관 경영정보 공개시스템",
    "api": "사용한 데이터 소스",
    "url": "https://www.alio.go.kr",
    "retrieved_at": "조회 시각",
    "as_of_year": "기준연도"
  },
  "caveats": ["해석상 유의사항"],
  "is_error": false
}
```

> 수치는 갱신 시점에 따라 달라지므로 아래 예시는 **형식과 동작**을 보여주는 것이며,
> 실제 값은 각자 환경의 데이터 기준입니다.

## Example 1. 기관 재무현황 요약

### 질문

한국전력공사의 최근 5년 재무현황을 알려줘.

### 기대 동작

1. `search_institutions("한국전력공사")` — 기관명 정규화 ('한전'도 동일하게 해석)
2. `get_institution_metrics(org_code, "finance")` — 연도별 자산·부채·자본·손익 시계열
3. 응답에 기준연도 범위(예: 2021–2025), 단위(백만원), 출처(ALIO 공시) 표시
4. caveats에 공시 주기·크롤 승격값 병합 여부 등 유의사항 표시

## Example 2. 정원 vs 현원

### 질문

국립공원공단 직원 몇 명이야?

### 기대 동작

1. `get_institution_staff_summary(org_code)` 호출
2. **정원(authorized)과 현원(actual)을 구분**해 답변 — "몇 명"이라는 모호한 질문에
   두 수치를 모두 제시
3. 현원 데이터가 없으면 추정하지 않고 headcount 추정치임을 명시

## Example 3. 조건 스크리닝

### 질문

부채 증가율 상위 공기업을 찾아줘.

### 기대 동작

1. `find_institutions_by_criteria(category="finance", ..., org_type="공기업")` — 증감률 상위 추출
2. 기관별 수치·기준연도·단위를 표로 제시
3. 필요 시 `get_institution_metrics`로 개별 기관 추이 심층 조회

## Example 4. 뉴스 ↔ 공시지표 교차검증

### 질문

뉴스에서 LH 빚 많다는데 실제 부채비율은?

### 기대 동작

1. `cross_check_news_with_metrics(org, topic="부채")` — 토픽을 공시지표로 매핑
2. 부채 시계열 + 최근 관련 뉴스 + 공시 주기를 함께 제시
3. caveats에 "뉴스는 언론 보도이며 공식 공시가 아님" 명시 — 판단은 사용자 몫

## Example 5. 경영평가편람 조회

### 질문

2026 경영평가에서 안전관리 지표 배점은?

### 기대 동작

1. `get_evaluation_indicator_detail(indicator="안전", year=2026)` 호출
2. 지표명·배점(계/비계량/계량)·세부평가내용 제시
3. caveats에 "PDF 추출 텍스트로 표·서식 손실 가능 — 원문 대조 권장" 명시

## Example 6. 데이터가 없을 때

### 질문

○○기관의 2026년 복리후생비는?

### 기대 동작

- 해당 연도 데이터가 없으면 **추정하지 않고 결측**으로 답변
- caveats에 "공시 주기 미도래 또는 미공시 가능성" 안내 (welfare는 연 1회 공시)
- 어떤 연도 데이터가 존재하는지 대안 제시

이 "추정 대신 결측" 원칙은 공공데이터 활용에서 잘못된 수치 인용을 막는 핵심 설계입니다.
