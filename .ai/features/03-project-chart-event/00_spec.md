# 00_spec - 03-project-chart-event

작성: Codex
일시: 2026-06-04

## 기능 목표
- 종목 상세 차트에서 `1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`, `10Y`, `YTD` 기간 선택을 지원하고, 선택한 기간 데이터만 보여준다.
- 차트 확대/축소, 확대 상태의 마우스 드래그 이동, 우하단 미니맵을 추가해 긴 기간 차트에서도 현재 위치를 쉽게 파악하고 세부 구간을 탐색할 수 있게 한다.

## 기능명
- feature_name: 03-project-chart-event
- naming_reason: 하네스에서 잠근 기능명이며, 프로젝트 종목 차트의 기간 선택과 마우스 이벤트 기반 탐색 UX를 다루는 범위를 안정적으로 표현한다.

## 구체적 요구사항
- 차트 기간 선택지는 UI 라벨 기준 `1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`, `10Y`, `YTD`를 모두 제공해야 한다.
- 프론트엔드와 백엔드의 기간 값은 기존 관례를 이어 `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `10y`, `ytd`를 사용한다.
- 초기 차트 기간과 API의 `period` 생략 시 기본값은 `1m`이다.
- 사용자가 기간을 선택하면 해당 기간의 차트 데이터만 조회하고 렌더링해야 한다. 이전 기간의 응답이 늦게 도착해도 현재 선택 기간 차트에 덮어쓰면 안 된다.
- 기간 변경은 차트 데이터만 다시 조회해야 하며, 이미 표시 중인 종목 상세 정보 전체를 불필요하게 다시 가져오지 않는다.
- 백엔드 `ChartPeriod` 검증과 Yahoo Finance range 매핑에 신규 기간을 추가해야 한다.
- 권장 Yahoo Finance 매핑은 `1m -> 1mo`, `3m -> 3mo`, `6m -> 6mo`, `1y -> 1y`, `3y -> 3y`, `5y -> 5y`, `10y -> 10y`, `ytd -> ytd`이며 interval은 확대 시 세부 확인을 위해 기본 `1d`를 사용한다.
- `YTD`는 런타임 기준 현재 연도 1월 1일부터 최신 가용 거래일까지의 기간으로 해석한다.
- 차트 데이터는 날짜 오름차순으로 렌더링해야 하며, provider 응답 순서가 불안정하면 렌더링 전 정렬 또는 정규화해야 한다.
- 차트 영역 위에서 마우스 wheel 또는 트랙패드 스크롤을 사용하면 확대/축소가 동작해야 한다.
- 확대/축소 중심점은 사용자의 포인터 X 좌표를 기준으로 한다. 포인터가 없는 환경에서는 현재 보이는 구간의 중앙을 기준으로 한다.
- 확대는 최소 표시 봉 개수까지 제한하고, 축소는 선택 기간 전체 범위를 넘지 않도록 제한한다.
- 확대된 상태에서 차트 본문을 마우스로 클릭한 뒤 좌우로 움직이면 보이는 구간이 이동해야 한다.
- 이동은 차트 데이터 범위 밖으로 넘어가지 않도록 좌우 경계를 클램프해야 한다.
- 확대되지 않은 전체 범위 상태에서는 드래그 이동이 레이아웃을 흔들거나 잘못된 상태를 만들지 않아야 한다.
- 기간이 변경되거나 종목 데이터가 바뀌면 확대/이동 상태는 새 기간의 전체 범위로 초기화한다.
- 확대된 상태에서는 차트 우하단에 미니맵을 표시해야 한다.
- 미니맵은 선택 기간 전체 데이터를 작게 보여주고, 현재 보이는 구간을 반투명 사각형 또는 명확한 오버레이로 표시해야 한다.
- 미니맵은 로딩, 데이터 없음, 오류 상태에서는 표시하지 않는다.
- 미니맵은 차트의 가격축, 날짜축, 주요 캔들 정보를 과도하게 가리지 않도록 고정 크기와 반응형 최대폭을 가져야 한다.
- 기존 차트의 한국 시장 상승/하락 색상 규칙과 미국 시장 상승/하락 색상 규칙은 유지한다.
- 가격축과 거래량축은 현재 보이는 구간 기준으로 다시 계산해 확대 시 세부 변화를 읽기 쉽게 한다.
- 미니맵의 스케일은 선택 기간 전체 데이터 기준으로 계산한다.
- 빈 데이터, `null` OHLCV 값, 모든 가격이 같은 데이터, 거래량이 모두 0인 데이터에서도 예외 없이 빈 상태 또는 안전한 차트를 보여줘야 한다.
- 화면 폭이 좁아져도 기간 버튼, 차트, 미니맵, 축 라벨 텍스트가 서로 겹치지 않아야 한다.
- 차트 계산 로직이 커지면 컴포넌트 내부에 모두 넣지 말고 별도 프론트엔드 서비스/헬퍼 모듈로 분리해 유지보수성을 확보한다.
- 외부 네트워크에 의존하지 않는 프론트엔드/백엔드 테스트를 추가하거나 갱신해야 한다.

## 이번 범위에서 제외하는 것
- 기술적 분석 지표, 보조지표, 이동평균선, 드로잉 도구는 제외한다. 이번 목표는 기간 선택과 탐색 이벤트 UX 개선이다.
- 사용자가 직접 시작일/종료일을 입력하는 커스텀 기간 조회는 제외한다. 요구된 고정 기간 선택지만 구현한다.
- 확대 상태를 종목별로 저장하거나 브라우저 저장소에 영구 보존하는 기능은 제외한다.
- WebSocket, 실시간 틱 데이터, 분봉 차트는 제외한다. 기존 일봉 OHLCV 차트의 탐색성을 개선한다.
- 새 외부 차트 라이브러리 도입은 기본 범위에서 제외한다. 기존 순수 SVG 구현을 우선 확장한다.
- 모바일 pinch zoom 고도화는 제외한다. 다만 pointer 이벤트로 자연스럽게 지원 가능한 범위는 구현에서 허용한다.

## 입력과 출력
- 입력:
  - 차트 API 쿼리: `category`는 기존 `kr_stock`, `kr_etf`, `us_stock`, `us_etf`, `period`는 `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `10y`, `ytd`.
  - UI 입력: 기간 버튼 클릭, 차트 영역 wheel 이벤트, 차트 영역 pointer down/move/up 이벤트.
  - 데이터 입력: `ChartResponse.bars[]`의 `timestamp`, `open`, `high`, `low`, `close`, `volume`.
- 출력:
  - 선택 기간에 해당하는 `ChartResponse`와 차트 렌더링 결과.
  - 확대 상태의 현재 visible range, 드래그 이동 후 갱신된 visible range, 우하단 미니맵의 전체 범위와 현재 범위 표시.
- 비정상 입력 처리:
  - 허용되지 않는 `period`는 FastAPI/Pydantic 검증으로 422 계열 응답을 유지한다.
  - provider가 신규 기간 데이터를 반환하지 못하면 기존 방식처럼 `status: unavailable`과 `errorMessage`를 반환하고 UI는 차트 영역에 실패 상태를 표시한다.
  - 표시 가능한 `close` 값이 없는 경우 차트와 미니맵을 렌더링하지 않고 빈 상태를 표시한다.
  - zoom/pan 계산 결과가 `NaN`, 음수 범위, 전체 데이터 범위 밖이 되지 않도록 방어한다.

## 기존 코드 영향
- 수정 예상 파일:
  - `src/backend/app/models/market.py`: `ChartPeriod` Literal에 `3y`, `5y`, `10y`, `ytd` 추가.
  - `src/backend/app/providers/yahoo_finance.py`: `_PERIOD_PARAMS` 신규 기간 매핑 추가 및 기간별 fetch 파라미터 검증.
  - `src/backend/app/api/routes.py`: 기본값은 유지하되 신규 기간이 API 문서와 검증에 반영되도록 확인.
  - `src/backend/app/services/search_service.py`: 기존 차트 캐시 키가 기간을 포함하므로 구조 변경은 크지 않지만 신규 기간 캐싱 동작을 확인.
  - `src/frontend/src/types/market.ts`: `ChartPeriod` 타입 확장.
  - `src/frontend/src/hooks/useStockDetail.ts`: 기간 타입 정리, stale 응답 방어, 기간/데이터 변경 시 zoom 상태 초기화와 충돌하지 않도록 연동.
  - `src/frontend/src/components/StockChart.tsx`: 기간 버튼 확장, zoom/pan 상태 또는 props 설계, visible range 렌더링, 미니맵 렌더링, 이벤트 처리 추가.
  - `src/frontend/src/App.css`: 기간 버튼 줄바꿈, 차트 이벤트 커서, 미니맵 오버레이, 반응형 스타일 추가.
  - `tests/backend/`: 기간 검증과 Yahoo range 매핑 테스트 갱신.
  - `tests/frontend/`: 기간 버튼, 기본값, zoom/pan 이벤트, 미니맵 표시 조건 테스트 갱신.
- 사용할 기존 모듈/유틸:
  - 기존 FastAPI 라우트, Pydantic alias/camelCase 응답 패턴, `MemoryCache`, `YahooFinanceProvider`.
  - 기존 React/Vite/TypeScript 구조, `fetchStockChart`, `useStockDetail`, 순수 SVG `StockChart` 패턴.
- 충돌 가능성:
  - 장기 기간에서 봉 개수가 크게 늘어 SVG 요소 수가 증가할 수 있다. 확대 상태에서는 보이는 구간만 상세 캔들로 렌더링하고, 미니맵은 단순화된 선 또는 샘플링으로 렌더링하는 방식이 필요할 수 있다.
  - 현재 일부 한글 UI 문자열이 깨져 보이는 파일이 있어 신규/수정 문자열은 UTF-8 인코딩을 유지하고 테스트 기대값을 신중히 갱신해야 한다.
  - 기존 테스트는 기간 선택지를 4개로 기대하므로 신규 8개 선택지에 맞게 갱신해야 한다.

## 기술적 제약
- 기존 React 18, Vite, TypeScript, FastAPI, Pydantic, httpx 구조를 유지한다.
- 새 외부 차트 라이브러리나 런타임 의존성은 기본적으로 추가하지 않는다.
- 차트 상호작용 계산은 순수 함수 또는 작은 헬퍼로 분리해 테스트 가능하게 만든다.
- 기존 공개 API 경로 `/api/stocks/{symbol}/chart`와 응답 필드 형식은 유지한다. 기간 값 추가는 하위 호환적인 확장으로 처리한다.
- 테스트는 외부 네트워크에 의존하지 않고 mock 또는 fixture로 격리한다.
- 장기 기간 데이터에서도 일반 브라우저에서 wheel, drag, period switch가 눈에 띄게 버벅이지 않도록 렌더링할 SVG 요소 수를 관리한다.
- 접근성 측면에서 기간 버튼의 `aria-pressed`, 차트의 `role="img"` 또는 적절한 레이블은 유지하고, 장식용 미니맵은 필요 시 `aria-hidden` 처리한다.

## 기본 결정 및 근거
- 신규 기간 값은 소문자 API 값과 대문자 UI 라벨을 분리한다. 기존 `1m`, `3m`, `6m`, `1y` 관례와 호환된다.
- 새 차트 라이브러리는 도입하지 않는다. 현재 `StockChart.tsx`가 이미 순수 SVG로 구현되어 있어 범위를 작게 유지할 수 있고, 외부 의존성 추가에 따른 검토 부담을 줄인다.
- 장기 기간도 기본 interval은 `1d`로 둔다. 사용자가 확대해서 더 자세히 보려는 요구가 있으므로 주봉으로 줄이면 확대 UX의 가치가 떨어진다.
- 미니맵은 확대된 상태에서만 표시한다. 전체 범위에서는 현재 위치 혼란이 적고, 차트 영역을 더 넓게 쓰는 편이 낫다.
- 확대/이동 상태는 클라이언트 UI 상태로만 둔다. 서버 API는 고정 기간 데이터를 제공하고, 세부 탐색은 이미 받아온 데이터 안에서 처리하는 편이 응답 지연과 API 복잡도를 줄인다.
- 기간 변경 시 zoom/pan은 초기화한다. 서로 다른 기간의 viewport 비율을 유지하면 사용자가 선택한 기간 전체를 즉시 보지 못할 수 있다.
- defaults_mode가 true이고 interactive_mode가 false이므로 사용자에게 추가 질문하지 않고 권장 기본값으로 스펙을 확정한다.

## 검증 기준
- `StockChart`가 `1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`, `10Y`, `YTD` 버튼을 모두 렌더링한다.
- 초기 렌더링과 API 기본값은 `1m`이다.
- 각 기간 버튼 클릭 시 `onPeriodChange` 또는 fetch 호출에 올바른 기간 값이 전달된다.
- 백엔드 차트 API는 신규 기간 값을 정상 수락하고 잘못된 기간 값은 거부한다.
- Yahoo provider는 신규 기간별 range/interval을 올바른 파라미터로 요청한다.
- wheel 이벤트 후 차트의 visible range가 전체보다 좁아지고 미니맵이 표시된다.
- 확대된 상태에서 drag 이벤트를 발생시키면 visible range가 좌우로 이동하되 데이터 범위를 벗어나지 않는다.
- 축소로 전체 범위에 도달하면 미니맵이 숨겨지거나 비확대 상태로 표시 정책이 일관된다.
- 빈 데이터, 단일 가격 데이터, 거래량 0 데이터에서 예외가 발생하지 않는다.

## 위험도 및 게이트
- risk_level: medium
- human_gate_required: true
- human_gate_reason: 사용자 경험에 직접 영향을 주는 차트 상호작용 정책과 여러 프론트엔드/백엔드 파일 변경이 포함되므로 사람 승인 게이트를 유지한다.

## 사용자 확인 사항
- 추가 질문 없음.
- 사용자 요청에 명시되지 않은 세부 동작은 `## 기본 결정 및 근거`의 기본값으로 확정했다.

## 단계 결과
- status: PASS
- next_stage: 01_plan
- human_gate_required: true
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/03-project-chart-event/00_spec.md
  - .ai/features/03-project-chart-event/00_spec.result.json
- changed_files:
  - .ai/features/03-project-chart-event/00_spec.md
  - .ai/features/03-project-chart-event/00_spec.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "spec: define project chart interactions"
- model_mismatch: false
- actual_model: Codex
