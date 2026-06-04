# 04_fix - 02-project-search-tab

작성: Claude Sonnet 4.6
일시: 2026-06-04

## 입력으로 처리한 지적
- 03_review.md must_fix:
  1. SearchService에서 YahooFinanceProvider가 status="unavailable"을 리턴했을 때도 stale 데이터 제공
  2. 프론트엔드 useStockDetail 훅에서 Promise.all 해체 - 차트 조회 실패 시에도 상세 패널 정상 렌더링
- 03_review.md should_consider:
  1. StockDetailPanel 내 formatPrice가 KRW 통화일 때 소수점 생략
  2. StockChart에서 한국 종목 카테고리(kr_stock, kr_etf)일 때 상승(빨간색)/하락(파란색) 색상 분기
- 03_review.md optional:
  1. StockChart Y축 PAD_LEFT 값 조정 (가격 라벨 잘림 방지)
  2. SearchService _load_lock 카테고리별 분산 관리
- 05_verify.md 실패 항목: 없음 (05_verify 미실행)
- 05_verify.md가 추가한 테스트 파일: 없음

## 수용한 항목

### 항목 1 (must_fix)
- 출처: 03_review (MAJOR)
- severity: MAJOR
- 지적 내용 요약: YahooFinanceProvider가 예외를 삼키고 status="unavailable" 정상 객체를 반환하면 SearchService의 except 블록에 진입하지 못해 stale fallback이 무력화됨
- 수정한 파일과 변경 내용:
  - `src/backend/app/services/search_service.py`: `get_detail()`과 `get_chart()` 내부에 `detail.status == "unavailable"` / `chart.status == "unavailable"` 체크를 추가. 기존 stale 캐시가 있으면 stale 반환, 없으면 unavailable을 그대로 반환 (단, 캐시에 저장하지 않아 다음 요청에서 재시도 가능)
- 왜 수용했는가: 플랜 및 스펙의 "외부 연동 실패 시 stale 데이터 반환" 핵심 요구사항이 실질적으로 동작하지 않는 버그이므로 반드시 수정 필요

### 항목 2 (must_fix)
- 출처: 03_review (MAJOR)
- severity: MAJOR
- 지적 내용 요약: Promise.all 사용으로 인해 차트 조회 실패 시 상세 조회 성공 데이터도 렌더링되지 않음
- 수정한 파일과 변경 내용:
  - `src/frontend/src/hooks/useStockDetail.ts`: `Promise.all` → `Promise.allSettled`로 교체. detailResult.status === "fulfilled"일 때만 detail을 set, chartResult.status === "fulfilled"일 때만 chart를 set. detail 실패 시에만 error state 설정, chart 실패 시에는 chart가 null로 남아 StockChart의 empty state 표시
- 왜 수용했는가: "차트 실패 시에도 상세 패널 유지" 스펙 요구사항에 직접 위배되는 버그

### 항목 3 (should_consider)
- 출처: 03_review (MINOR)
- severity: MINOR
- 지적 내용 요약: KRW 통화 가격에 소수점 2자리가 붙어 표시됨 (예: ₩70,000.00 → ₩70,000)
- 수정한 파일과 변경 내용:
  - `src/frontend/src/components/StockDetailPanel.tsx`: `formatPrice()` 내 `decimals = currency === "KRW" ? 0 : 2` 분기 추가. minimumFractionDigits와 maximumFractionDigits 모두 0으로 설정
- 왜 수용했는가: 원화 특성상 소수점 표시가 없는 것이 자연스럽고 사용자 경험상 명확히 개선되는 사항

### 항목 4 (should_consider)
- 출처: 03_review (MINOR)
- severity: MINOR
- 지적 내용 요약: 한국 주식/ETF에서 상승 시 녹색, 하락 시 빨간색으로 표시되어 한국 주식시장 관례(상승=빨강, 하락=파랑)와 반대
- 수정한 파일과 변경 내용:
  - `src/frontend/src/components/StockChart.tsx`: `category?: string` prop 추가, `isKorean = category === "kr_stock" || category === "kr_etf"` 변수 산출. 캔들스틱 색상: 한국이면 up=#dc2626(빨강)/down=#1d4ed8(파랑), 미국이면 up=#16a34a(녹색)/down=#dc2626(빨강). 거래량 막대도 동일 분기
  - `src/frontend/src/components/SearchTab.tsx`: `<StockChart category={...} />` prop 전달 추가
- 왜 수용했는가: 한국 주식 사용자에게 직관적인 색상 표현을 제공하는 UX 개선이며 스펙 범위 내 수정

### 항목 5 (optional/NIT)
- 출처: 03_review (NIT)
- severity: NIT
- 지적 내용 요약: PAD_LEFT=56이 한국 원화 고가 종목(예: 150,000원)에서 Y축 가격 라벨이 잘릴 수 있음
- 수정한 파일과 변경 내용:
  - `src/frontend/src/components/StockChart.tsx`: `PAD_LEFT = 56` → `PAD_LEFT = 72`로 증가
- 왜 수용했는가: 한국 고가 종목 라벨 잘림을 방지하는 단순한 수치 변경이며, 항목 4 수정 시 함께 처리하는 것이 자연스럽고 부작용이 없음

## 거부한 항목

### 항목 1 (NIT)
- 출처: 03_review
- severity: NIT
- 지적 내용 요약: _load_lock을 카테고리별로 분산 관리하여 preload 병렬 성능 개선
- 왜 수용하지 않았는가: 현재 preload_all_masters()는 순차적으로 4개 카테고리를 로드하므로 lock 분리의 실질적 성능 이익이 미미함. 코드 복잡도 증가 대비 효과가 낮고 현재 스펙 범위를 벗어나는 최적화 변경
- 거부해도 문제가 없는 근거: preload는 앱 시작 시 백그라운드에서 실행되어 사용자 경험에 직접 영향이 없음. 실시간 검색 응답 경로에는 lock contention이 발생하지 않음

## 보류한 항목
- 없음

## 사용자 판단 요청 항목
- 없음

## 추가 변경 사항
- `tests/backend/test_search_service.py`: unavailable → stale fallback 시나리오 테스트 2개 추가
  - `test_get_detail_returns_stale_when_provider_returns_unavailable`
  - `test_get_chart_returns_stale_when_provider_returns_unavailable`
- `tests/frontend/SearchTab.test.tsx`: 누락 테스트 케이스 3개 추가
  - `StockDetailPanel - KRW formatting > renders KRW price without decimal places`
  - `StockDetailPanel - KRW formatting > does not show decimals for KRW open/high/low prices`
  - `SearchTab - partial failure isolation > renders detail panel even when chart fetch fails`

## 호환성 준수
- 보존한 기존 인터페이스/데이터 포맷/설정 키:
  - SearchService의 get_detail/get_chart 공개 시그니처 완전 보존
  - StockDetailState 인터페이스 필드 추가 없음 (chartError 미추가 - 필요 없음)
  - StockChart의 category prop은 optional로 추가하여 기존 호출부 영향 없음
- 호환성 유지 전략 반영 내용:
  - 기존 테스트 기대값 (test_get_detail_returns_stale_on_provider_failure 등) 모두 유지
  - StockChart 기존 props (data, period, onPeriodChange, isLoading) 변경 없음
- breaking change 발생 여부: 없음
- 리뷰/검증 범위를 넘어선 호환성 영향: 없음

## 변경 파일 목록
- `src/backend/app/services/search_service.py`: get_detail/get_chart에 unavailable → stale fallback 분기 추가
- `src/frontend/src/hooks/useStockDetail.ts`: Promise.all → Promise.allSettled 교체
- `src/frontend/src/components/StockDetailPanel.tsx`: KRW 가격 소수점 제거
- `src/frontend/src/components/StockChart.tsx`: category prop 추가, 한국/미국 색상 분기, PAD_LEFT=72
- `src/frontend/src/components/SearchTab.tsx`: StockChart에 category prop 전달
- `tests/backend/test_search_service.py`: unavailable stale fallback 테스트 2개 추가
- `tests/frontend/SearchTab.test.tsx`: KRW 포맷팅 테스트 2개 + 부분실패격리 테스트 1개 추가

## 테스트
- 실행한 테스트 명령:
  - `python -m pytest tests/backend/ -v`
  - `cd src/frontend && npm test -- --run`
  - `cd src/frontend && npm run build`
- 결과:
  - 백엔드: 48/48 통과 (기존 46개 + 신규 2개)
  - 프론트엔드: 21/21 통과 (기존 18개 + 신규 3개)
  - TypeScript 빌드: 0 에러
- 추가한 테스트:
  - `tests/backend/test_search_service.py::test_get_detail_returns_stale_when_provider_returns_unavailable`
  - `tests/backend/test_search_service.py::test_get_chart_returns_stale_when_provider_returns_unavailable`
  - `tests/frontend/SearchTab.test.tsx` StockDetailPanel KRW formatting 2개
  - `tests/frontend/SearchTab.test.tsx` SearchTab partial failure isolation 1개

## Git 정보
- fix_base_commit: 8a365deac2af346af29d1a2fb22283a4d3995aa5
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 02-project-search-tab[20260604-230200][04_fix]
- no_code_changes: false
- pre_commit_diff_command: git diff 8a365deac2af346af29d1a2fb22283a4d3995aa5
- changed_files:
  - src/backend/app/services/search_service.py
  - src/frontend/src/hooks/useStockDetail.ts
  - src/frontend/src/components/StockDetailPanel.tsx
  - src/frontend/src/components/StockChart.tsx
  - src/frontend/src/components/SearchTab.tsx
  - tests/backend/test_search_service.py
  - tests/frontend/SearchTab.test.tsx
- harness_commit_blocking_reason: 없음

## 단계 결과
- status: PASS
- next_stage: 05_verify
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low
- produced_files:
  - .ai/features/02-project-search-tab/04_fix.md
- changed_files:
  - src/backend/app/services/search_service.py
  - src/frontend/src/hooks/useStockDetail.ts
  - src/frontend/src/components/StockDetailPanel.tsx
  - src/frontend/src/components/StockChart.tsx
  - src/frontend/src/components/SearchTab.tsx
  - tests/backend/test_search_service.py
  - tests/frontend/SearchTab.test.tsx
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 02-project-search-tab[20260604-230200][04_fix]
- test_commands:
  - python -m pytest tests/backend/ -v
  - cd src/frontend && npm test -- --run
  - cd src/frontend && npm run build
- model_mismatch: false
- actual_model: Claude Sonnet 4.6
