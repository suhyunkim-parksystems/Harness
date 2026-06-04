# 01_plan - 02-project-search-tab

작성: Antigravity
일시: 2026-06-04

## 기능 목표
- 기존의 주식/환율 대시보드 화면을 첫 번째 기본 탭(dashboard)으로 보존한다.
- 두 번째 탭(search)에 한국주식/한국ETF/미국주식/미국ETF 종목을 통합 검색, 자동완성, 상세 시세 및 일봉 가격/거래량 차트를 조회할 수 있는 신규 화면을 추가한다.
- 종목 마스터는 24시간 TTL 인메모리 캐시로 관리하고, 상세/차트 정보는 60초 짧은 캐시 TTL과 Stale Fallback을 적용하여 외부 API 실패 시에도 부분적 복구 및 장애 격리를 수행한다.

## 구현 접근 방식
백엔드와 프론트엔드 모두 기존 모듈의 호환성을 100% 보존하면서 확장하는 방식으로 구현한다.

- **백엔드**:
  - `SearchService`가 종목 검색 매칭, 캐싱, 상세 조회, 차트 파싱 로직을 총괄하며 기존 `MarketService`와 분리된다.
  - `KRXProvider`는 KRX Data Marketplace 공개 다운로드 경로를 사용해 OTP 발급 및 CSV 수집을 진행하며, EUC-KR 디코딩 및 로그아웃(`LOGOUT`) 에러 처리를 구현한다.
  - `NasdaqProvider`는 NASDAQ Symbol Directory (`nasdaqlisted.txt`, `otherlisted.txt`)를 다운로드하여 파이프라인으로 미국 주식 및 ETF 마스터 목록을 추출한다.
  - `YahooFinanceProvider`는 Yahoo Finance의 차트 API (`query1.finance.yahoo.com/v8/finance/chart/{symbol}`)를 사용하여 실시간 시세와 1개월/3개월/6개월/1년 단위 일봉(OHLCV) 데이터를 단일 엔드포인트로 파싱한다.
  - FastAPI의 `lifespan` 내 background task로 마스터 사전 적재(`preload_all_masters`)를 시도하되, 기동 실패를 방지하기 위해 예외를 격리하고 실패 시 첫 검색에서 lock 하에 lazy loading으로 재시도한다.
- **프론트엔드**:
  - `App.tsx`를 두 탭(dashboard, search)의 껍데기(Tab Container)로 리팩토링하고, 기존 대시보드 내용은 `DashboardTab.tsx`로 격리하여 기존의 새로고침 및 상태 변경 훅을 온전히 보존한다.
  - `SearchTab.tsx`에서 자동완성 입력 컴포넌트(`AutocompleteInput`), 상세 패널(`StockDetailPanel`), 그리고 캔들스틱과 거래량 바가 통합된 SVG 직접 렌더링 차트 컴포넌트(`StockChart`)를 조합한다.
  - 300ms 디바운스, `AbortController`를 통한 이전 요청 취소, 그리고 훅 내부의 `ignore` 플래그 처리를 통해 동시성/레이스 컨디션 문제를 프론트엔드단에서 원천 해결한다.

## 검토한 대안
- **대안 1: 정적 로컬 시드 파일 기반 종목 마스터**
  - *장점*: 외부 사이트 장애나 파싱 구조 변경 시에도 검색 목록이 100% 작동하여 안전하다.
  - *단점*: "가장 최신 종목이 항상 반영되어야 한다"는 요구사항에 어긋난다. 신규 상장 종목이 누락되므로 미채택.
- **대안 2: KRX OpenAPI 공식 인증키 연동**
  - *장점*: 데이터 정합성과 응답 안정성이 보장된다.
  - *단점*: API 사용 신청 및 승인 프로세스가 수반되어 비대화식 자동화 테스트 환경(`interactive_mode: false`)에서 자격 증명을 획득 및 검증할 수 없다. 미채택.
- **대안 3: 외부 차트 라이브러리(Recharts 등) 추가**
  - *장점*: 다양한 기능(줌, 마우스 오버 툴팁 등)이 기본 제공된다.
  - *단점*: 새 npm 패키지 설치로 인한 의존성 복잡도가 커지고, 프론트엔드 번들 크기가 증가하며, `npm run build` 단계의 컴파일 위험을 유발할 수 있다.
  - *결정*: 런타임 추가 의존성 없이 순수 HTML/CSS와 SVG 좌표 계산만으로 캔들 및 거래량 그래프를 가볍고 반응성이 뛰어나게 그리는 방향을 채택한다.

## 변경 파일 계획
- **`src/backend/app/models/market.py` (수정)**:
  - `AssetCategory` (`kr_stock`, `kr_etf`, `us_stock`, `us_etf`), `ChartPeriod` (`1m`, `3m`, `6m`, `1y`) Literal 추가.
  - `SearchCandidate` (자동완성 후보 모델), `SearchResponse` (배열 응답), `StockDetail` (상세 시세 및 상태), `ChartBar` (단일 일봉), `ChartResponse` (차트 데이터 일체) Pydantic 모델을 기존 모델 하단에 추가. 기존 모델 필드는 그대로 유지.
- **`src/backend/app/config.py` (수정)**:
  - `symbol_master_ttl_seconds: int = 86400` (종목 마스터 24시간 캐시)
  - `quote_cache_ttl_seconds: int = 60` (상세 시세 60초 캐시)
  - `stock_provider_timeout_seconds: float = 5.0` (타임아웃 임계치) 설정 필드 추가.
- **`src/backend/app/providers/krx_provider.py` (신규)**:
  - KRX Data Marketplace 공개 다운로드 HTTP 요청 구현.
  - CSV 내용 수집 및 `EUC-KR` 디코딩. `LOGOUT` 문자열 또는 HTML 응답 감지 시 예외 발생 및 격리.
- **`src/backend/app/providers/nasdaq_provider.py` (신규)**:
  - `nasdaqlisted.txt` 및 `otherlisted.txt` 파일 다운로드 및 파이프(`|`) 구분자 파싱.
  - `Test Issue` 여부가 `N`인 실제 종목만 필터링하고 `ETF` 컬럼 기반으로 주식/ETF 분리.
- **`src/backend/app/providers/yahoo_finance.py` (신규)**:
  - Yahoo Finance Chart API 연동. 미국 주식의 클래스 주식(예: BRK.B -> BRK-B)의 심볼 정규화 지원.
  - 한국 종목은 KRX 코드를 바탕으로 `.KS` 또는 `.KQ` 접미사(Suffix)를 붙여 시세 조회.
  - 반환되는 JSON에서 시세 메타데이터와 시/고/저/종/거래량 배열을 안전하게 추출하여 `StockDetail`과 `ChartBar` 형태로 정규화.
- **`src/backend/app/services/search_service.py` (신규)**:
  - `KRXProvider`, `NasdaqProvider`, `YahooFinanceProvider`를 의존성으로 가짐.
  - 마스터 검색 시 한국은 종목명, 미국은 티커 매칭을 구현하고 Prefix 매칭을 Substring 매칭보다 우선하여 10개로 정렬.
  - 상세 시세 및 차트 캐싱 및 Stale Fallback 구현. 외부 공급처 호출 실패 시 캐시에 보관된 Stale 데이터를 `status="stale"`로 리턴하여 전체 중단 방지.
- **`src/backend/app/api/routes.py` (수정)**:
  - `/api/search/autocomplete`, `/api/stocks/{symbol}/detail`, `/api/stocks/{symbol}/chart` GET 엔드포인트 신규 추가.
  - `/api/health` 응답에 신규 프로바이더 상태를 기재하되 기존 stooq, frankfurter 상태에 지장이 없도록 호환성 보장.
- **`src/backend/app/main.py` (수정)**:
  - FastAPI의 lifespan 이벤트를 추가하여 백그라운드 태스크로 `preload_all_masters()`를 기동하고, shutdown 시 태스크를 정리. 기존 `create_app()` 시그니처와 인수 형태 유지.
- **`src/frontend/src/types/market.ts` (수정)**:
  - 백엔드 응답 형태와 일치하도록 TypeScript `SearchCandidate`, `StockDetail`, `ChartBar`, `ChartResponse` 타입 인터페이스 선언 추가.
- **`src/frontend/src/api/markets.ts` (수정)**:
  - `fetchAutocomplete(query, category, signal)`, `fetchStockDetail(symbol, category, signal)`, `fetchStockChart(symbol, category, period, signal)` 클라이언트 함수 추가.
- **`src/frontend/src/hooks/useStockSearch.ts` (신규)**:
  - 입력값의 300ms 디바운스, 2글자 미만 API 요청 생략, `AbortController`를 통한 이전 요청 즉시 중단 기능 제공.
- **`src/frontend/src/hooks/useStockDetail.ts` (신규)**:
  - 선택한 종목의 상세 및 차트를 병렬 fetch하고 로딩/에러 상태 관리. 기간(`period`) 갱신 시 차트 데이터만 새로 고치는 기능 구현.
- **`src/frontend/src/components/DashboardTab.tsx` (신규)**:
  - 기존 `App.tsx` 내의 대시보드 그리드 및 마켓 섹션 렌더링을 그대로 이관하여 회귀 위험 제거.
- **`src/frontend/src/components/SearchTab.tsx` (신규)**:
  - 네 가지 범주 선택 단추(Segmented Control), 자동완성 입력 창, 상세/차트 패널 레이아웃 구성.
- **`src/frontend/src/components/AutocompleteInput.tsx` (신규)**:
  - 포커스 시/입력 시 활성화되는 리스트박스 팝오버. 방향키(ArrowUp, ArrowDown), 엔터(Enter), Esc(Escape) 키로 조작 가능한 접근성 마운트.
- **`src/frontend/src/components/StockDetailPanel.tsx` (신규)**:
  - 종목 정보(OHLC, 거래량, 전일비 등) 및 데이터 신뢰처, 기준 시각, Stale 경고문 표시.
- **`src/frontend/src/components/StockChart.tsx` (신규)**:
  - 캔들스틱 및 거래량 막대를 포함하는 SVG 차트 컴포넌트. 0으로 나누기 방어, 데이터 부족 시 우아한 에러 상태 렌더링 포함.
- **`src/frontend/src/App.tsx` (수정)**:
  - 상단에 두 개의 탭 버튼(대시보드 / 종목검색)을 두고 `activeTab` 상태에 따라 각 탭 컴포넌트를 분기 렌더링.
- **`src/frontend/src/App.css` (수정)**:
  - 탭 셸, 검색 창, 자동완성 드롭다운, 시세 그리드, SVG 차트 및 반응형 스타일링을 추가하며 기존 스타일을 보존.

## 데이터 / 제어 흐름
### 1. 백엔드 기동 및 사전 적재 (Preload) 흐름
```
[FastAPI Startup]
       │
       ▼
[Lifespan Background Task]
       │
       ├─────────────────────────────────────┐
       ▼                                     ▼
[KRX 마스터 Preload]                 [NASDAQ 마스터 Preload]
(KRX Data Marketplace)               (Nasdaq Trader Symbol Directory)
       │                                     │
       ▼                                     ▼
[인메모리 캐시 적재 (24h TTL)]       [인메모리 캐시 적재 (24h TTL)]
```
* ※ Preload 실패 시에도 예외는 완전히 내부 격리 처리되며, 첫 자동완성/검색 요청 시 Lock 제어 하에서 Lazy Loading을 수행합니다.

### 2. 검색 자동완성 제어 흐름
```
[사용자 입력 (>= 2자)] ──(300ms 디바운스)──► [useStockSearch Hook] (이전 AbortController 취소)
                                                     │
                                                     ▼
                                          [GET /api/search/autocomplete]
                                                     │
                                                     ▼
                                         [SearchService.search()]
                                                     │
                                     (인메모리 캐시조회 / Lazy 로딩)
                                                     │
                                                     ▼
                                         [Prefix & Substring 매칭]
                                                     │
                                                     ▼
                                            [최대 10개 결과 반환]
```

### 3. 종목 상세 및 차트 조회 흐름
```
[종목 선택] ──────────────────────────► [useStockDetail Hook]
                                               │
                       ┌───────────────────────┴───────────────────────┐
                       ▼ (병렬 요청)                                   ▼
          [GET /api/stocks/{symbol}/detail]               [GET /api/stocks/{symbol}/chart]
                       │                                               │
                       ▼                                               ▼
          [SearchService.get_detail()]                    [SearchService.get_chart()]
                       │                                               │
          (Yahoo Finance API 호출)                        (Yahoo Finance API 호출)
                       │                                               │
              (60s 캐시 set/get)                              (60s 캐시 set/get)
                       │                                               │
                       ▼                                               ▼
         [StockDetailPanel 렌더링]                       [StockChart (SVG) 렌더링]
         - 수치 누락 시 N/A 처리                          - 0으로 나누기 방지
         - Stale/Unavailable 뱃지 표시                    - 차트 데이터 부족/에러 오버레이
```

## 구현 단계 분할
1. **단계 1: 백엔드 스켈레톤 및 모델 구축**
   - `models/market.py`에 신규 Pydantic 모델을 정의하고 `config.py`에 TTL 및 타임아웃 설정을 추가한다.
   - `routes.py`에 3개 API의 빈 핸들러(스켈레톤)를 작성하여 기존 테스트 및 빌드 상태를 정상으로 유지한다.
2. **단계 2: 외부 공급자(Provider) 연동 모듈 및 단위 테스트 작성**
   - `krx_provider.py`, `nasdaq_provider.py`, `yahoo_finance.py`를 신규로 정의한다.
   - 외부 네트워크 의존성 배제를 위해 로컬의 가상 CSV/JSON 응답 Fixture 데이터를 이용하는 단위 테스트(`tests/backend/test_*_provider.py`)를 함께 작성한다.
3. **단계 3: `SearchService` 비즈니스 로직 및 캐시/에러 격리 구현**
   - Prefix/Substring 랭킹이 적용된 자동완성 기능, 짧은 캐시 TTL 및 Stale Fallback을 담당하는 `SearchService`를 구현한다.
   - FastAPI lifespan에 마스터 preload background task를 연결한다.
   - `tests/backend/test_search_service.py`와 `test_search_routes.py`를 작성하여 캐시 동작 및 예외 처리를 검증한다.
4. **단계 4: 프론트엔드 API 클라이언트 및 Custom Hooks 구현**
   - TypeScript 타입을 명세하고 `fetchAutocomplete`, `fetchStockDetail`, `fetchStockChart` 클라이언트를 작성한다.
   - AbortController 및 디바운스가 장착된 `useStockSearch` 훅과 상태 관리를 전담하는 `useStockDetail` 훅을 작성한다.
5. **단계 5: UI 컴포넌트 이관 및 신규 구현**
   - 기존 대시보드를 `DashboardTab.tsx`로 이관하여 격리한다.
   - `SearchTab.tsx`, `AutocompleteInput.tsx`, `StockDetailPanel.tsx`, `StockChart.tsx`를 구현하고 `App.css`에 스타일을 배치한다.
6. **단계 6: 종합 통합 테스트 및 빌드 검증**
   - 백엔드 pytest 및 프론트엔드 Vitest 통합 테스트(`App.test.tsx`, `SearchTab.test.tsx`)를 실행하고, `npm run build`를 수행하여 TypeScript 컴파일 에러가 없음을 확인한다.

## 위험 구간 및 완화 방안 (Pre-mortem 기반 보강)
- **위험 1: 외부 마스터 사이트의 다운로드 실패/인코딩 변경/로그아웃으로 인한 백엔드 기동 불능**
  - *현상*: 서버 시작(`lifespan`) 중 KRX 등의 연동 에러가 던져지면 FastAPI 기동 프로세스 전체가 비정상 종료되거나 긴 시간 행이 걸린다.
  - *완화*: Lifespan 내의 수집 동작은 완전한 try-except 블록으로 에러를 격리하며, 실패 시 로깅 후 프로세스는 정상 실행된다. 수집된 종목 마스터가 비어있다면 첫 자동완성 요청이 들어오는 시점에 Mutex Lock 하에서 lazy loading을 1회 재시도하도록 보강한다.
- **위험 2: Yahoo Finance API의 비정상적 JSON 구조 및 누락값 발생으로 인한 Pydantic 검증 오류**
  - *현상*: 특정 미국/한국 ETF 또는 신규 상장 주식의 경우, 시가/고가/저가 등이 `null`이거나 파라미터가 누락되어 백엔드에서 500 내부 에러가 반환된다.
  - *완화*: Pydantic 응답 모델의 가격, 등락폭, 거래량 등 대부분 필드를 `float | None`으로 지정하여 엄격한 검증 실패를 예방한다. 또한 프로바이더 파서 수준에서 구조 분해 시 `try-except`로 완전히 감싸서 파싱 실패 시 500 에러 대신 `status="unavailable"`, `errorMessage="일부 시세 정보 파싱 불가"`를 채운 유효한 객체를 반환하여 프론트엔드에 우아하게 부분 실패를 보여준다.
- **위험 3: 자동완성 동시 입력 시 늦게 응답된 이전 요청이 최신 결과를 덮어쓰는 화면 꼬임 (Race Condition)**
  - *현상*: 사용자가 "삼" 입력 후 "삼성"을 연이어 입력하였을 때, "삼"에 대한 자동완성 비동기 응답이 "삼성"보다 늦게 도착하여 목록이 이전 상태로 덮어씌워진다.
  - *완화*: `useStockSearch` 훅 내에 `AbortController`를 인스턴스화하고 새 API 요청 시점에 `controller.abort()`를 강제 실행한다. 이에 더해 React `useEffect` 클린업 패턴을 사용해 `ignore = true` 플래그를 설정함으로써, 이미 unmount 되었거나 검색어가 변경된 이전 비동기 resolution은 state에 반영되지 않도록 2중 가드로 방어한다.
- **위험 4: 가격 변동이 없거나 거래량이 없는 종목 조회 시 SVG 차트 Y좌표/볼륨 높이 계산 오류 (0으로 나누기)**
  - *현상*: 시세 변동이 전혀 없는 종목(예: 거래 정지 종목 또는 단일가 종목)은 최고가와 최저가가 동일하여 Y축 스케일링 계산 분모가 0이 되어 `NaN`이나 `Infinity` 값을 갖게 되고, 이로 인해 SVG 렌더링 스크립트 에러가 발생해 화면이 뻗는다.
  - *완화*: SVG 좌표 변환 계산식 직전에 `const priceRange = maxPrice - minPrice;`가 0일 경우 강제로 `1.0` 혹은 `maxPrice * 0.05`를 마진 범위로 지정하여 0으로 나누기 연산을 원천 배제한다. 거래량 그래프도 `maxVolume === 0`일 때 스케일링 비율을 0으로 강제 변환하여 차트가 깨지지 않고 깔끔한 평탄선(Flat Line)을 그리도록 보강한다. 데이터가 0건일 때도 "차트 데이터가 존재하지 않습니다" 오버레이를 씌운다.

## 호환성 검토
- **보존해야 할 API**: `/api/health`, `/api/markets/summary`, `/api/markets/indices`, `/api/markets/exchange-rates`와 관련 응답 Pydantic 스키마를 고스란히 유지한다.
- **프론트엔드 호환성**: `fetchMarketSummary` 및 `useMarketSummary`는 손대지 않고 대시보드 탭에 온전히 탑재한다.
- **CORS 및 의존성**: CORS 허용 메서드는 GET에 머무르므로 변경 불필요. 프론트엔드 빌드 도구 및 tsconfig 설정은 온전히 유지된다.
- **Breaking Change**: 전혀 존재하지 않는다.

## 새 의존성
- **없음**: 추가적인 NPM 패키지나 Python 패키지를 도입하지 않는다. 오직 React 내장 훅, standard SVG 엘리먼트, 백엔드는 표준 csv 및 httpx 클라이언트를 사용한다.

## 테스트 전략
- **백엔드 단위 테스트**:
  - `tests/backend/test_krx_provider.py`: 정상/빈 응답/`LOGOUT` 검출 및 한글 디코딩을 Mock HTTP 응답으로 격리하여 테스트.
  - `tests/backend/test_nasdaq_provider.py`: 미국 마스터 파일 내 `Test Issue` 필터링 및 footer 행 제외 파싱 검증.
  - `tests/backend/test_yahoo_finance_provider.py`: Yahoo 차트 API의 JSON 복합 구조 파싱 성공 및 일부 파라미터 `null`일 때의 Null-safe 처리 검증.
  - `tests/backend/test_search_service.py` & `test_search_routes.py`: 검색 자동완성 우선순위(Prefix > Substring), 2자 미만 400 반환, 상세 조회 Stale Fallback 동작 흐름 테스트.
- **프론트엔드 단위 테스트**:
  - `tests/frontend/App.test.tsx`: 탭 내비게이션 요소의 렌더링 및 기본 탭(`dashboard`)이 기존과 동일하게 표출되는지 테스트.
  - `tests/frontend/SearchTab.test.tsx`: 자동완성 타이핑 시 디바운스 대기 후 API 요청이 나가며, 팝오버를 누르면 상세 정보 및 SVG 차트 영역이 제대로 출력되는지 테스트. 0으로 나누기가 배제되어 평탄선 차트가 안정적으로 렌더링되는지도 Fixture 검증.
- **빌드 테스트**:
  - `npm run build --prefix src/frontend` 명령으로 컴파일 누락을 자동 검증한다.

## 롤백 / 복구 방향
- DB 마이그레이션이 없는 순수 메모리 캐시 기반 확장이므로, 비상 상황 시 Git Checkout 등을 통해 이전 파일로 원복 후 API 서버 및 프론트엔드 빌드를 재기동하는 것으로 즉각적인 완전 롤백이 가능하다.

## 실행 승인
- `risk_level`: medium
- `human_gate_required`: false
- `human_gate_reason`: 금융 연동 API의 오류 및 SVG 차트 수치적 edge case에 대해 pre-mortem 기반의 방어 설계(0 나누기 우회, null-safe 파싱, 2중 요청 취소)가 수립되어 있어 게이트가 불필요하다.
- `approval_required_before_develop`: false

## 스펙 모호점 처리
- **기본 탭 설정**: 기존 사용자 시나리오 및 리그레션 최소화를 위해 첫 진입 탭은 기존 대시보드로 둔다.
- **검색 매칭 규칙**: 한국 주식/ETF는 '한글 종목명'의 Prefix 우선 후 Substring 매칭으로 순서화하며, 미국 주식/ETF는 '티커(Ticker)'의 Prefix 우선 후 Substring 매칭으로 순서화한다.
- **미국 클래스 주식 심볼 변환**: Yahoo Finance에서 `BRK.B`와 같이 `.`이 있는 심볼은 백엔드에서 `BRK-B`로 자동 변환하여 연동한다.
- **한국 ETF의 Suffix 결정**: KRX 마스터의 시장 구분 정보가 유효하면 KOSPI/KOSDAQ 여부에 따라 `.KS` 또는 `.KQ`를 부여하고, 판단이 불분명할 경우 ETF 기본값인 `.KS`를 부여한다.

## Git 기준점
- **base_commit**: c17873f811e427e4483a6781b1654452777fd372
- **diff_base_command**: `git diff c17873f811e427e4483a6781b1654452777fd372`

## 사용자 확인 사항
- 없음. (Harness defaults_mode 활성화에 따라 추천 계획안으로 전격 확정)

## 단계 결과
- status: PASS
- next_stage: 02_develop
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/02-project-search-tab/01_plan.md
  - .ai/features/02-project-search-tab/01_plan.result.json
- changed_files:
  - .ai/features/02-project-search-tab/01_plan.md
  - .ai/features/02-project-search-tab/01_plan.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "plan: setup stock search tab implementation strategy with pre-mortem safeguards"
- model_mismatch: false
- actual_model: Antigravity
