# 02_dev - 03-project-chart-event

작성: Claude Sonnet 4.6
일시: 2026-06-04

## 기능 목표
- 종목 차트에서 `1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`, `10Y`, `YTD` 8개 기간 선택을 지원하고, 선택 기간 데이터만 조회·렌더링한다.
- 마우스 휠 확대/축소, Pointer 드래그 패닝, 우하단 미니맵을 추가해 긴 기간 차트에서 현재 위치를 파악하고 세부 구간을 탐색할 수 있게 한다.

## 변경 파일
- `.ai/features/03-project-chart-event/00_spec.md` (입력 / 변경 금지)
- `.ai/features/03-project-chart-event/01_plan.md` (입력 / 변경 금지)
- `.ai/features/03-project-chart-event/02_dev.md` (신규)
- `src/backend/app/models/market.py` (수정)
- `src/backend/app/providers/yahoo_finance.py` (수정)
- `src/frontend/src/types/market.ts` (수정)
- `src/frontend/src/services/chartHelpers.ts` (신규)
- `src/frontend/src/components/StockChart.tsx` (수정)
- `src/frontend/src/App.css` (수정)
- `tests/backend/test_yahoo_finance_provider.py` (수정)
- `tests/backend/test_routes.py` (수정)
- `tests/frontend/StockChart.test.tsx` (신규)

## 구현 내용

### 단계 1: 백엔드 기간 도메인 확장
- `ChartPeriod` Literal에 `"3y" | "5y" | "10y" | "ytd"` 추가 (`models/market.py`)
- `_PERIOD_PARAMS`에 신규 기간→Yahoo Finance range/interval 매핑 추가 (`yahoo_finance.py`): `3y→("3y","1d")`, `5y→("5y","1d")`, `10y→("10y","1d")`, `ytd→("ytd","1d")`

### 단계 2: 프론트엔드 타입 및 서비스 분리
- `ChartPeriod` 타입에 `"3y" | "5y" | "10y" | "ytd"` 추가 (`types/market.ts`)
- `src/frontend/src/services/chartHelpers.ts` 신규 생성: `clampRange`, `computeZoomRange`, `computePanRange`, `formatDateLabel`, `buildMinimapPath` 순수 함수 포함

### 단계 3: StockChart 컴포넌트 확장
- `PERIODS` 배열을 8개 항목으로 확장
- `view: null | {start,end}` 상태 도입 (`null`=전체 범위 sentinel)
- `data`/`period` 변경 시 `useEffect`로 `view = null` 초기화
- `useEffect` + `addEventListener("wheel", ..., {passive:false})`로 휠 줌 구현; `viewRef`/`totalBarsRef` mutable ref로 stale closure 방지
- `onPointerDown/Move/Up/Cancel` 핸들러로 드래그 패닝; `setPointerCapture` try-catch 방어
- `visibleBars = validBars.slice(safeStart, safeEnd+1)` 슬라이싱으로 렌더링 요소 수 제한
- 가격축·거래량축 스케일을 `visibleBars` 기준으로 동적 재계산
- 날짜 라벨: `formatDateLabel`로 기간별 포맷 (3M↓=MM-DD, 1Y/YTD=YYYY-MM, 3Y+= YYYY)
- `isZoomed` 조건부 미니맵 SVG 렌더링 (전체 데이터 Area path + 뷰포트 오버레이 rect)

### 단계 4: CSS 보완
- `.chart-period-selector`에 `flex-wrap: wrap` 추가 (8버튼 소형화면 줄바꿈)
- `.stock-chart-svg`에 `user-select: none` 추가; `--grab`, `--grabbing` 커서 클래스 추가

## 왜 이렇게 구현했는가

- **null sentinel 패턴**: `view = null`이 "전체 범위"를 의미하도록 해서, 초기 렌더링과 data/period 변경 시 즉시 올바른 범위를 계산할 수 있고, useEffect 비동기 타이밍 문제로 인한 1-frame 미니맵 깜빡임을 방지했다.
- **ref + 빈 deps useEffect**: 휠 핸들러를 한 번만 등록하되 `viewRef.current`와 `totalBarsRef.current`로 항상 최신 값을 참조한다. deps에 `validBars.length`를 넣으면 데이터 변경 시마다 핸들러를 재등록하는 비용이 생기므로 제외했다.
- **단일 act() 내 다중 휠 이벤트 주의**: 테스트에서 단일 `act()` 안에 여러 wheel event를 발생시키면 중간 re-render가 일어나지 않아 `viewRef`가 갱신되지 않는다. 테스트는 각 zoom 이벤트를 개별 `act()` + `dispatchWheel` 헬퍼로 발생시켜 이를 회피했다.
- **서비스 레이어 분리**: `chartHelpers.ts` 순수 함수로 분리해 단위 테스트 가능성을 높이고 컴포넌트를 30줄 이하 단위로 분할했다.
- **미니맵 SVG-only**: CSS clipPath 대신 수학적으로 정확한 좌표를 계산해 path를 미니맵 rect 내에 자연스럽게 배치함으로써 외부 의존성 없이 구현했다.

## 호환성 준수
- 01_plan.md의 호환성 유지 전략 반영 내용: `ChartPeriod` Literal 확장은 하위 호환적; 기존 `1m` 기본값 유지
- 보존한 기존 인터페이스/데이터 포맷/설정 키:
  - `/api/stocks/{symbol}/chart` 경로 불변
  - `ChartResponse`, `StockChartProps` 시그니처 불변
  - 기존 상승/하락 색상 규칙(한국: 빨/파, 미국: 녹/빨) 유지
- breaking change 발생 여부: 없음
- 계획에 없던 호환성 영향: 없음

## 새로 추가한 의존성
- 없음

## 테스트

### 백엔드 테스트
- `tests/backend/test_yahoo_finance_provider.py` 수정
  - `test_period_params_include_all_required_periods`: 신규 4개 기간의 `_PERIOD_PARAMS` 매핑 검증
  - `test_parse_chart_uses_correct_period_string`: 파싱 시 period 문자열 보존 검증
  - `test_yahoo_provider_fetch_chart_maps_new_periods`: `fetch_chart` 가 올바른 range/interval을 전달하는지 검증
- `tests/backend/test_routes.py` 수정
  - `test_chart_api_rejects_invalid_period`: 잘못된 period → 422
  - `test_chart_api_accepts_extended_periods`: 신규 3y/5y/10y/ytd → 200
  - `test_chart_api_default_period_is_1m`: period 생략 시 기본값 1m

### 프론트엔드 테스트
- `tests/frontend/StockChart.test.tsx` 신규 생성
  - `chartHelpers` 순수 함수 단위 테스트 (clampRange, computeZoomRange, computePanRange, formatDateLabel, buildMinimapPath)
  - 8개 기간 버튼 렌더링 및 aria-pressed 검증
  - 신규 기간 id(3y/5y/10y/ytd) onPeriodChange 콜백 검증
  - 휠 줌인 → 미니맵 표시 검증
  - 개별 act()로 줌아웃 → 전체 범위 복귀 → 미니맵 숨김 검증
  - 드래그 패닝 (미니맵 유지) 검증
  - 기간/데이터 변경 시 줌 초기화 검증
  - 엣지케이스: 단일 봉, null OHLCV, 동일 가격, 빈 데이터

### 테스트 실행 결과
```
Backend:  54 passed (0 failed)
Frontend: 53 passed (0 failed)
```

### 의도적으로 테스트하지 않은 부분
- 미니맵 내 실제 `<path>` 좌표값의 수치 정확도: jsdom에서 SVG 좌표 렌더링 검증이 불가하고, `buildMinimapPath` 순수 함수 단위 테스트로 커버됨
- `setPointerCapture` 동작: jsdom 미지원이므로 try-catch 방어로 처리하고 기능 동작을 대신 검증

## 알려진 한계 / 추후 개선 사항
- 10Y 일봉 데이터(~2500봉) 전체 가시 시 SVG 요소가 2500개 생성됨. 확대 상태에서는 visibleBars 슬라이싱으로 완화되나, 전체 범위 표시 시 성능 이슈 가능성 있음. 추후 캔버스 기반 렌더링 또는 가상 스크롤 적용 고려.
- 미니맵에서 직접 클릭하여 뷰포트 이동하는 기능은 스펙 범위 밖으로 미구현.

## Git 정보
- base_commit: 801d18480eda78bb6b57ecc2a362abea887e48de
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 03-project-chart-event[20260604-234529][02_develop]
- commit_scope:
  - .ai/features/03-project-chart-event/02_dev.md
  - src/backend/app/models/market.py
  - src/backend/app/providers/yahoo_finance.py
  - src/frontend/src/types/market.ts
  - src/frontend/src/services/chartHelpers.ts
  - src/frontend/src/components/StockChart.tsx
  - src/frontend/src/App.css
  - tests/backend/test_yahoo_finance_provider.py
  - tests/backend/test_routes.py
  - tests/frontend/StockChart.test.tsx
- pre_commit_diff_command: git diff 801d18480eda78bb6b57ecc2a362abea887e48de
- changed_files:
  - src/backend/app/models/market.py
  - src/backend/app/providers/yahoo_finance.py
  - src/frontend/src/types/market.ts
  - src/frontend/src/services/chartHelpers.ts (신규)
  - src/frontend/src/components/StockChart.tsx
  - src/frontend/src/App.css
  - tests/backend/test_yahoo_finance_provider.py
  - tests/backend/test_routes.py
  - tests/frontend/StockChart.test.tsx (신규)
- harness_commit_blocking_reason: 없음

## 단계 결과
- status: PASS
- next_stage: 03_review
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/03-project-chart-event/02_dev.md
- changed_files:
  - src/backend/app/models/market.py
  - src/backend/app/providers/yahoo_finance.py
  - src/frontend/src/types/market.ts
  - src/frontend/src/services/chartHelpers.ts
  - src/frontend/src/components/StockChart.tsx
  - src/frontend/src/App.css
  - tests/backend/test_yahoo_finance_provider.py
  - tests/backend/test_routes.py
  - tests/frontend/StockChart.test.tsx
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 03-project-chart-event[20260604-234529][02_develop]
- test_commands:
  - python -m pytest tests/backend/ -x -q
  - npx --prefix src/frontend vitest run --config src/frontend/vite.config.ts tests/frontend/
- model_mismatch: false
- actual_model: Claude Sonnet 4.6
