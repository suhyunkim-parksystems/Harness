# 00_spec - 04-project-chart-compare-with-benchmark

작성: Codex
일시: 2026-06-05

## 기능 목표
- 종목 상세 차트에 가격/거래량을 읽기 쉬운 GRID 기준선을 추가해 차트만 단독으로 보이는 문제를 줄인다.
- 한국주식 종목 자동완성/검색 결과가 비는 문제를 디버깅하고, 검색 직후뿐 아니라 기간을 `1M`에서 `3Y` 등으로 바꾼 뒤에도 확대/축소/미니맵 이벤트가 정상 동작하게 한다.

## 기능명
- feature_name: 04-project-chart-compare-with-benchmark
- naming_reason: 하네스에서 잠근 기능명이다. 실제 사용자 요청은 벤치마크 비교 추가가 아니라 차트 가독성, 한국주식 검색, 기간 변경 후 차트 이벤트 복구이므로 기능명은 유지하되 구현 범위는 원 요청에 맞춘다.

## 구체적 요구사항
- `StockChart`는 유효한 차트 데이터가 있을 때 가격 영역에 Y축 가격 tick과 연결된 수평 grid line을 표시해야 한다.
- `StockChart`는 날짜 라벨 또는 샘플링된 X축 위치에 맞춘 세로 기준선을 제공해 캔들 위치를 읽기 쉽게 해야 한다.
- 거래량 영역은 가격 영역과 구분되는 baseline 또는 보조 grid를 가져야 하며, 가격 grid와 시각적으로 충돌하지 않아야 한다.
- Grid 색상과 두께는 기존 dashboard 스타일과 맞는 저대비 보조선이어야 하며, 캔들/거래량 막대/미니맵보다 우선 시선을 끌지 않아야 한다.
- Grid와 축 라벨은 데스크톱/모바일 폭에서 차트 요소, 기간 버튼, 미니맵, 날짜 라벨과 겹치지 않아야 한다.
- 로딩, 빈 데이터, `status: unavailable` 상태에서는 잘못된 grid를 렌더링하지 않고 기존 빈 상태 메시지를 유지해야 한다.
- 한국주식 카테고리(`kr_stock`)에서 한글 종목명 2자 이상 입력 시 `/api/search/autocomplete?q=...&category=kr_stock` 호출이 debounce 이후 발생해야 한다.
- 한국주식 자동완성은 한글 종목명 검색을 기본으로 하되, 권장 기본값으로 6자리 종목코드 검색도 지원해야 한다. 예: `삼성`, `삼성전자`, `005930`.
- 한국 ETF(`kr_etf`)도 같은 KRX 검색 경로를 사용하되 ETF 종목명과 종목코드를 기준으로 후보를 반환해야 한다.
- KRX CSV parser는 실제 KRX 응답의 EUC-KR/UTF-8 디코딩과 컬럼명 후보를 올바르게 처리해야 한다. 최소 컬럼 후보는 `단축코드`, `종목코드`, `표준코드`, `한글 종목명`, `한글종목명`, `종목명`, `시장구분`, `소속부`를 포함한다.
- KRX parser가 컬럼명 깨짐이나 응답 형식 변경 때문에 모든 행을 버리는 경우를 테스트로 재현하고, 정상 fixture에서는 후보가 비지 않도록 수정해야 한다.
- 검색 서비스는 KRX 마스터 로딩 실패와 정상적인 검색 결과 없음이 내부적으로 구분되도록 로그/상태 처리를 보강해야 한다. 공개 API 응답 포맷 변경은 이번 기본 범위에서 피한다.
- 현재 소스와 테스트에 깨진 한국어 문자열이 검색 UI, KRX 컬럼명, 테스트 기대값에 영향을 주고 있으므로 관련 파일의 사용자 노출 문자열과 fixture 문자열을 정상 UTF-8 한국어로 복구해야 한다.
- 종목을 선택한 직후에는 기존처럼 상세 정보와 차트가 표시되고, wheel 확대/축소 시 미니맵이 표시되어야 한다.
- 선택된 종목에서 기간을 `1M -> 3Y`, `3Y -> 1M`, `1M -> YTD`처럼 바꾼 뒤 새 차트가 로드되어도 wheel 확대/축소 이벤트가 다시 동작해야 한다.
- 기간 변경 후 첫 wheel 확대에서 visible range가 전체 범위보다 좁아지고 미니맵이 표시되어야 한다.
- 기간 변경 후 확대 상태에서 pointer drag pan이 동작해야 하며, visible range가 데이터 범위를 벗어나지 않아야 한다.
- 기간 변경 중 늦게 도착한 이전 chart 응답이 최신 period의 chart 상태를 덮어쓰지 않아야 한다.
- 기간 변경 시 zoom/pan 상태는 권장 기본값으로 전체 범위에 초기화한다. 이후 사용자의 wheel/drag 입력부터 새 period 데이터 기준으로 다시 동작한다.
- `StockChart`가 로딩 분기에서 SVG를 잠시 언마운트하더라도 새 SVG에 wheel listener가 다시 연결되어야 한다. 또는 SVG를 유지하는 방식으로 구현하더라도 같은 사용자 관찰 결과를 만족해야 한다.
- 기존 8개 기간(`1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `10y`, `ytd`)과 API 응답 포맷은 유지한다.
- 한국 시장 상승/하락 색상 규칙과 미국 시장 상승/하락 색상 규칙은 기존 동작을 유지한다.
- 변경 사항은 프론트엔드/백엔드 단위 테스트로 검증하고, 외부 네트워크 호출은 mock 또는 fixture로 격리한다.

## 이번 범위에서 제외하는 것
- 벤치마크 지수 또는 비교 종목과의 상대 수익률 비교 차트는 제외한다. 현재 원 요청에 포함되지 않았고 feature slug만으로 범위를 넓히지 않는다.
- 새 차트 라이브러리 도입은 제외한다. 기존 SVG 기반 `StockChart` 구조를 우선 확장한다.
- 실시간 시세, WebSocket, 분봉 차트, 사용자 지정 시작일/종료일 입력은 제외한다.
- 검색 랭킹 고도화, 초성 검색, 오타 교정, 서버 측 전문 검색 엔진 도입은 제외한다.
- 공개 API 경로, 응답 필드 이름, 기존 period 값의 하위 호환성을 깨는 변경은 제외한다.

## 입력과 출력
- 입력:
  - 검색어: 문자열, trim 후 2자 이상일 때 자동완성 요청. 한국 종목은 한글명 또는 6자리 숫자 코드, 미국 종목은 ticker 중심.
  - 검색 카테고리: `kr_stock`, `kr_etf`, `us_stock`, `us_etf`.
  - 차트 기간: `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `10y`, `ytd`.
  - 차트 데이터: `ChartResponse.bars[]`의 `timestamp`, `open`, `high`, `low`, `close`, `volume`.
  - UI 이벤트: 기간 버튼 click, SVG wheel, pointer down/move/up.
- 출력:
  - 자동완성 응답: 기존 `SearchResponse` 형태로 최대 10개 후보, `status`, `asOf`.
  - 차트 렌더링: 캔들/거래량/축 라벨/grid/minimap이 포함된 SVG.
  - 기간 변경 후 chart fetch 결과: 선택된 최신 period에 해당하는 `ChartResponse`.
- 비정상 입력 처리:
  - 2자 미만 검색어는 API를 호출하지 않고 후보를 비운다.
  - 잘못된 카테고리나 period는 기존 FastAPI/Pydantic 검증 흐름을 유지한다.
  - KRX 응답이 비정상 HTML/LOGOUT/컬럼 누락이면 전체 앱을 중단하지 않고 검색 후보 없음 또는 내부 실패 로그로 격리하되, 정상 fixture에서는 후보를 반환해야 한다.
  - 차트에 `close`가 없거나 bars가 비어 있으면 grid/minimap 계산을 하지 않고 기존 빈 상태를 표시한다.
  - wheel/pan 계산 결과는 `NaN`, 음수 범위, 전체 bars 범위 초과가 되지 않도록 clamp한다.

## 기존 코드 영향
- 수정 예상 파일:
  - `src/frontend/src/components/StockChart.tsx`: grid 렌더링, period 변경 후 wheel listener 재연결, minimap/zoom/pan 상태 동작 보강.
  - `src/frontend/src/services/chartHelpers.ts`: grid tick 또는 range 계산 보조 함수가 필요하면 기존 순수 함수 패턴으로 확장.
  - `src/frontend/src/components/SearchTab.tsx`: 깨진 한국어 UI 문자열 복구, category/query/selection 흐름 확인.
  - `src/frontend/src/components/AutocompleteInput.tsx`: 후보 표시와 입력 이벤트가 한국어 검색에서 정상인지 확인.
  - `src/frontend/src/hooks/useStockSearch.ts`: 한국어 query debounce, abort, 오류 상태 처리 확인.
  - `src/frontend/src/hooks/useStockDetail.ts`: period 변경 시 chart 요청 취소/최신성 보장, loading 중 SVG 이벤트 이슈와의 연동 확인.
  - `src/frontend/src/api/markets.ts`: query/category/period 인코딩 유지 확인.
  - `src/frontend/src/App.css`: grid, axis, minimap, 한국어 UI 텍스트 주변 반응형 스타일 보강.
  - `src/backend/app/providers/krx_provider.py`: KRX CSV 컬럼명/인코딩 파싱 복구.
  - `src/backend/app/services/search_service.py`: 한국 종목명과 종목코드 검색, 마스터 로딩 실패 구분, 캐시 동작 확인.
  - `src/backend/app/api/routes.py`: autocomplete 오류 처리 문구/상태 확인. 공개 API shape 변경은 피한다.
  - `tests/frontend/StockChart.test.tsx`: grid 렌더링, period 변경 후 로딩 분기 재마운트 뒤 wheel/minimap 동작 테스트 추가.
  - `tests/frontend/SearchTab.test.tsx`: 한국주식 자동완성 호출과 후보 표시 테스트 추가, 깨진 한국어 기대값 복구.
  - `tests/backend/test_krx_provider.py`: 실제 한글 컬럼명 fixture와 EUC-KR 디코딩 테스트 복구.
  - `tests/backend/test_search_service.py`: 한국 종목명/종목코드 검색, 빈 결과와 provider 실패 격리 테스트 보강.
- 사용할 기존 모듈/유틸:
  - `MemoryCache`, `SearchService`, `KRXProvider`, `YahooFinanceProvider`.
  - 기존 React hook 패턴, `AbortController`, `chartHelpers` 순수 함수.
- 충돌 가능성:
  - 현재 `StockChart` wheel listener가 imperative `addEventListener(..., { passive: false })` 방식이라 SVG 언마운트/리마운트 시 재연결 누락이 생길 수 있다.
  - period 변경 중 `isChartLoading` 분기가 SVG를 제거하면 이벤트 listener 생명주기와 충돌한다.
  - KRX provider가 실패를 빈 목록으로 반환하는 기존 동작은 검색 결과 없음처럼 보일 수 있다. 공개 API 호환성을 지키면서 내부 진단과 테스트를 보강해야 한다.
  - 깨진 한국어 문자열은 UI뿐 아니라 parser 컬럼 키와 테스트 fixture에 직접 영향을 주므로 함께 복구해야 한다.

## 기술적 제약
- 기존 React 18, Vite, TypeScript, FastAPI, Pydantic, httpx 구조를 유지한다.
- 새 외부 의존성은 기본적으로 추가하지 않는다.
- 기존 API 경로 `/api/search/autocomplete`, `/api/stocks/{symbol}/detail`, `/api/stocks/{symbol}/chart`와 JSON field alias는 유지한다.
- 외부 네트워크 의존 테스트는 금지한다. KRX/Yahoo/NASDAQ 호출은 mock 또는 fixture로 격리한다.
- 차트 이벤트 계산은 가능하면 `chartHelpers` 같은 순수 함수로 분리해 테스트 가능하게 유지한다.
- 프론트엔드 텍스트는 UTF-8 한국어로 저장하고, 테스트 기대값도 실제 사용자 표시 문구와 맞춘다.
- 비동기 요청은 늦게 도착한 이전 응답이 현재 선택 종목/period 상태를 덮어쓰지 않도록 abort 또는 request id로 방어한다.

## 기본 결정 및 근거
- 질문 없이 PASS로 확정한다. `defaults_mode: true`, `interactive_mode: false`이고 요구사항이 코드베이스 확인으로 충분히 구체화 가능하다.
- Grid는 수평 가격선만이 아니라 세로 날짜 기준선과 거래량 보조선을 포함하는 것으로 기본 결정한다. 사용자가 "GRID"를 요청했고 차트 해석성을 높이는 최소 UI 보강이다.
- 한국 종목 검색은 한글명과 6자리 종목코드 모두 지원하는 것으로 기본 결정한다. 사용자가 "한국주식 종목 검색"을 요청했고 국내 주식 검색에서 두 입력 방식 모두 자연스럽다.
- 기간 변경 시 zoom/pan 상태는 전체 범위로 초기화한다. 이전 단계 스펙과 기존 테스트가 period/data 변경 시 reset을 전제로 하고, 다른 길이의 기간에 이전 viewport 비율을 유지하면 혼란이 커질 수 있다.
- 새 차트 라이브러리는 도입하지 않는다. 현재 차트가 이미 SVG로 구현되어 있고 요청은 버그 수정과 가독성 보강이므로 의존성 추가 위험이 불필요하다.
- 벤치마크 비교 차트는 제외한다. feature slug와 달리 원 요청에는 포함되지 않았으며 이번 단계에서 범위를 넓히면 핵심 버그 수정이 흐려진다.

## 검증 기준
- 한국주식 탭에서 `삼성`, `삼성전자`, `005930` 입력 시 mock/fixture 기준 자동완성 후보가 표시된다.
- KRX parser가 한글 컬럼명 fixture에서 `005930 삼성전자 KOSPI`, `035720 카카오 KOSDAQ`을 올바르게 파싱한다.
- 검색어 2자 미만에서는 autocomplete API가 호출되지 않는다.
- `StockChart`가 유효한 데이터에서 가격 grid, 날짜 기준선, 거래량 기준선을 렌더링한다.
- 초기 검색 직후 wheel 확대 시 미니맵이 표시된다.
- 기간을 `1M -> 3Y`로 바꾸고 새 chart loading 분기를 거친 뒤 wheel 확대 시 미니맵이 다시 표시된다.
- 기간 변경 후 확대 상태에서 drag pan이 가능하고 minimap viewport가 전체 minimap 영역 밖으로 나가지 않는다.
- 이전 period chart 응답이 늦게 도착해도 최신 period의 chart를 덮어쓰지 않는다.
- 프론트엔드 테스트와 백엔드 테스트가 외부 네트워크 없이 통과한다.
- 가능하면 로컬 브라우저에서 한국주식 검색, 기간 변경, 확대/축소, 미니맵 동작을 수동 확인한다.

## 위험도 및 게이트
- risk_level: medium
- human_gate_required: true
- human_gate_reason: 사용자에게 직접 보이는 차트 UX와 검색 흐름을 수정하고, 프론트엔드와 백엔드 여러 파일 및 테스트 변경이 필요하다. 0단계 프리셋도 사람 승인 게이트를 요구한다.

## 사용자 확인 사항
- 추가 질문 없음.
- 사용자 요청과 코드베이스 확인으로 구현 가능한 수준의 스펙을 확정했다.
- 사용자에게 확인받지 않은 기본 결정은 `## 기본 결정 및 근거`에 기록했다.

## 단계 결과
- status: PASS
- next_stage: 01_plan
- human_gate_required: true
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/04-project-chart-compare-with-benchmark/00_spec.md
  - .ai/features/04-project-chart-compare-with-benchmark/00_spec.result.json
- changed_files:
  - .ai/features/04-project-chart-compare-with-benchmark/00_spec.md
  - .ai/features/04-project-chart-compare-with-benchmark/00_spec.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "spec: define chart grid and korean search fixes"
- model_mismatch: false
- actual_model: Codex
