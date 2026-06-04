# 02_dev - 02-project-search-tab

작성: Claude Sonnet 4.6
일시: 2026-06-04

## 기능 목표
- 기존 시장 대시보드를 첫 번째 탭(대시보드)으로 보존하고, 두 번째 탭(종목검색)에 한국주식/한국ETF/미국주식/미국ETF 검색, 자동완성, 상세 시세, SVG 캔들스틱+거래량 차트를 제공한다.
- 백엔드에서 KRX/NASDAQ 종목 마스터를 24시간 인메모리 캐시로 관리하고, Yahoo Finance를 통해 상세 시세와 일봉 OHLCV 차트를 60초 TTL + Stale Fallback으로 제공한다.

## 변경 파일
- .ai/features/02-project-search-tab/00_spec.md (입력 / 변경 금지)
- .ai/features/02-project-search-tab/01_plan.md (입력 / 변경 금지)
- .ai/features/02-project-search-tab/02_dev.md (신규)
- src/backend/app/models/market.py (수정) — AssetCategory, ChartPeriod 타입과 SearchCandidate, SearchResponse, StockDetail, ChartBar, ChartResponse 모델 추가
- src/backend/app/config.py (수정) — symbol_master_ttl_seconds, quote_cache_ttl_seconds, stock_provider_timeout_seconds 설정 추가
- src/backend/app/providers/krx_provider.py (신규) — KRX Data Marketplace OTP+CSV 다운로드, EUC-KR 디코딩, LOGOUT 감지
- src/backend/app/providers/nasdaq_provider.py (신규) — NASDAQ Symbol Directory nasdaqlisted.txt + otherlisted.txt 파이프 파싱
- src/backend/app/providers/yahoo_finance.py (신규) — Yahoo Finance chart API 연동, 심볼 정규화(.KS/.KQ, BRK.B→BRK-B), Null-safe OHLCV 파싱
- src/backend/app/services/search_service.py (신규) — Prefix/Substring 랭킹 검색, 마스터 24h 캐시/Lazy Loading, 상세/차트 60s 캐시 + Stale Fallback
- src/backend/app/api/routes.py (수정) — /api/search/autocomplete, /api/stocks/{symbol}/detail, /api/stocks/{symbol}/chart 엔드포인트 추가
- src/backend/app/main.py (수정) — FastAPI lifespan을 추가하여 백그라운드에서 preload_all_masters() 실행
- src/frontend/src/types/market.ts (수정) — AssetCategory, ChartPeriod, SearchCandidate, SearchResponse, StockDetail, ChartBar, ChartResponse 타입 추가
- src/frontend/src/api/markets.ts (수정) — fetchAutocomplete, fetchStockDetail, fetchStockChart 함수 추가
- src/frontend/src/hooks/useStockSearch.ts (신규) — 300ms 디바운스, AbortController, ignore 플래그로 레이스 컨디션 방어
- src/frontend/src/hooks/useStockDetail.ts (신규) — 종목 변경 시 detail+chart 병렬 fetch, period 변경 시 chart만 재조회
- src/frontend/src/components/DashboardTab.tsx (신규) — 기존 App.tsx 대시보드 내용을 격리 이관
- src/frontend/src/components/AutocompleteInput.tsx (신규) — 키보드(ArrowUp/Down/Enter/Esc) 제어 접근성 포함 자동완성 드롭다운
- src/frontend/src/components/StockDetailPanel.tsx (신규) — OHLC, 거래량, 등락, 출처, 기준시각 상세 그리드
- src/frontend/src/components/StockChart.tsx (신규) — SVG 캔들스틱+거래량 차트, 0-divide 방어, 빈 데이터 오버레이
- src/frontend/src/components/SearchTab.tsx (신규) — 4개 범주 Segmented Control, AutocompleteInput, StockDetailPanel, StockChart 조합
- src/frontend/src/App.tsx (수정) — 두 탭 버튼 추가, DashboardTab/SearchTab 조건부 렌더링
- src/frontend/src/App.css (수정) — 탭 내비게이션, 검색 탭, 자동완성, 상세 패널, 차트 스타일 추가
- tests/backend/test_krx_provider.py (신규)
- tests/backend/test_nasdaq_provider.py (신규)
- tests/backend/test_yahoo_finance_provider.py (신규)
- tests/backend/test_search_service.py (신규)
- tests/backend/test_search_routes.py (신규)
- tests/frontend/SearchTab.test.tsx (신규)

## 구현 내용

### 백엔드

**모델 (market.py)**
- `AssetCategory` Literal 타입과 `ChartPeriod` Literal 타입 추가
- `SearchCandidate` (자동완성 후보), `SearchResponse` (배열 응답), `StockDetail` (상세 시세), `ChartBar` (단일 일봉), `ChartResponse` (차트 데이터) Pydantic 모델 추가
- 기존 `MarketItem`, `MarketSummary`, `MarketCollection` 모델 완전 보존

**설정 (config.py)**
- `symbol_master_ttl_seconds=86400` (24h), `quote_cache_ttl_seconds=60`, `stock_provider_timeout_seconds=5.0` 추가

**KRX Provider**
- OTP 발급(POST) → CSV 다운로드(POST) 2단계 플로우 구현
- EUC-KR 디코딩 + UTF-8 fallback
- LOGOUT 문자열 및 HTML 응답 감지 시 예외 발생, 상위에서 격리
- 종목명/코드 컬럼 다양한 명칭 패턴 허용 (한글 종목명 vs 한글 종목명 vs 종목명)

**NASDAQ Provider**
- `nasdaqlisted.txt` (NASDAQ 상장) + `otherlisted.txt` (NYSE/AMEX 등) 파이프 구분 파싱
- Test Issue="Y" 행, 파일 메타데이터 행 필터링
- ETF 컬럼 기반 주식/ETF 분리

**Yahoo Finance Provider**
- `/v8/finance/chart/{symbol}` 단일 엔드포인트로 시세 메타데이터 + OHLCV 배열 모두 파싱
- 한국 종목 `.KS`/`.KQ` 접미사 자동 부여, 미국 `.` → `-` 변환 (BRK.B→BRK-B)
- 누락 필드 `None` Null-safe 처리, 파싱 실패 시 `status="unavailable"` 반환

**SearchService**
- 범주별 `MemoryCache` (마스터 24h, 상세/차트 60s)
- `asyncio.Lock()`으로 동시 lazy loading 방지 (double-check 패턴)
- us_stock/us_etf 범주 요청 시 NASDAQ 파일을 한 번만 다운로드해 두 캐시 동시 적재
- 한국 범주는 이름(name) 기반, 미국 범주는 티커(symbol) 기반 매칭
- Prefix 매칭이 Substring 매칭보다 먼저 나오도록 정렬, 최대 10개로 잘라냄
- 상세/차트 provider 실패 시 stale 캐시 반환, 캐시도 없으면 예외 전파

**Routes + Main**
- `GET /api/search/autocomplete?q=<min2>&category=<AssetCategory>` — FastAPI Query min_length=2 검증
- `GET /api/stocks/{symbol}/detail?category=` — camelCase 응답
- `GET /api/stocks/{symbol}/chart?category=&period=` — 기본값 period="1m"
- `/api/health` 응답에 krx, nasdaq, yahoo_finance provider 상태 추가
- `lifespan` 이벤트로 백그라운드 preload 태스크 기동, 앱 종료 시 정리

### 프론트엔드

**타입/API 클라이언트**
- `AssetCategory`, `ChartPeriod`, `SearchCandidate`, `SearchResponse`, `StockDetail`, `ChartBar`, `ChartResponse` TypeScript 인터페이스 추가
- `fetchAutocomplete`, `fetchStockDetail`, `fetchStockChart` 함수 — AbortSignal 지원

**훅**
- `useStockSearch`: 300ms 디바운스 + AbortController + `ignore` 플래그로 2중 race condition 방어
- `useStockDetail`: symbol/category 변경 시 detail+chart 병렬 fetch, period 변경 시 chart만 재조회 (prevSymbolRef 패턴)

**컴포넌트**
- `DashboardTab`: 기존 App.tsx 대시보드를 격리 이관, 기존 훅/상태 그대로 보존
- `AutocompleteInput`: role=combobox, aria-expanded, listbox, ArrowUp/Down/Enter/Esc 키 제어
- `StockDetailPanel`: StatusBadge 포함, stale/unavailable 경고 배너, OHLC 그리드
- `StockChart`: viewBox 800×380 SVG, 캔들스틱 (몸통+꼬리) + 거래량 막대, 0-divide 완전 방어, 데이터 없음 오버레이, 5개 Y축 눈금, 날짜 레이블
- `SearchTab`: 4개 범주 버튼 → AutocompleteInput → 조건부 detail+chart 또는 empty state
- `App`: `activeTab` 상태로 DashboardTab/SearchTab 전환, 두 탭 버튼

## 왜 이렇게 구현했는가

- **단일 `_fetch_chart` 재사용**: Yahoo Finance detail과 chart 둘 다 같은 chart API 엔드포인트를 사용한다. detail은 `range=1d`로 현재가 메타 추출, chart는 적절한 range/interval 파라미터로 OHLCV 배열 추출.
- **us_stock+us_etf 공동 적재**: NASDAQ 파일을 2번 다운로드하는 비효율을 방지하기 위해 `_load_us_masters()`에서 한 번에 적재하고 두 캐시 키에 저장.
- **빈 마스터 미캐시 전략**: provider 실패로 빈 리스트가 반환되면 캐시에 저장하지 않아 다음 요청에서 재시도 가능하게 했다.
- **ignore 플래그 + AbortController 2중 방어**: AbortController는 HTTP 요청 취소, ignore 플래그는 React 상태 업데이트 방지 (cleanup 시 이미 unmount됐거나 검색어가 바뀐 경우).
- **단일 useEffect + prevRef 패턴**: `useStockDetail`에서 symbol/category/period 모두 동일 deps에 두되, prevRef로 변경 원인을 파악해 symbol 변경 시 full fetch, period만 변경 시 chart fetch만 수행.
- **순수 SVG 차트**: Recharts 등 외부 라이브러리 없이 viewBox 800×380에 좌표 계산만으로 캔들스틱+거래량 차트 구현. 번들 크기, 컴파일 위험 없음.
- **0-divide 방어**: `priceRange===0`일 때 `Math.max(maxPrice*0.05, 1)`을 padding으로 사용해 Y축 스케일링 계산 안전 보장. `maxVolume===0`일 때도 `Math.max(...vols, 1)` 패턴으로 보장.

## 호환성 준수
- 01_plan.md의 호환성 유지 전략 반영 내용:
  - `/api/health`, `/api/markets/summary`, `/api/markets/indices`, `/api/markets/exchange-rates` 응답 계약 완전 보존
  - `fetchMarketSummary`, `useMarketSummary`, 기존 컴포넌트 모두 미변경
  - 기존 App.tsx 대시보드 내용을 DashboardTab으로 1:1 이관, 기능 동일
- 보존한 기존 인터페이스/데이터 포맷/설정 키: MarketItem, MarketSummary, MarketCollection, SummaryStatus, MarketStatus, camelCase alias 전체
- breaking change 발생 여부: 없음
- 계획에 없던 호환성 영향: health 응답에 krx/nasdaq/yahoo_finance 필드 추가 — 기존 테스트는 stooq 필드만 검사하므로 영향 없음

## 새로 추가한 의존성
- 없음 (백엔드 csv, asyncio 표준 라이브러리 사용, 프론트엔드 SVG 직접 렌더링)

## 테스트

### 작성한 테스트 파일
- `tests/backend/test_krx_provider.py` (6개 테스트)
- `tests/backend/test_nasdaq_provider.py` (5개 테스트)
- `tests/backend/test_yahoo_finance_provider.py` (10개 테스트)
- `tests/backend/test_search_service.py` (6개 테스트)
- `tests/backend/test_search_routes.py` (7개 테스트)
- `tests/frontend/SearchTab.test.tsx` (12개 테스트)

### 커버 범위
- KRX: 정상 파싱, LOGOUT 감지, 예외 격리, EUC-KR 디코딩
- NASDAQ: 주식/ETF 분리, Test Issue 필터링, 교환소 코드 매핑, 파일 다운로드 실패 격리
- Yahoo Finance: 가격/변동 파싱, null 안전 처리, JSON 구조 오류 처리, 심볼 정규화, HTTP 오류 격리
- SearchService: Prefix 우선 정렬, 최대 10개 제한, 캐싱, stale fallback
- Routes: camelCase 직렬화, 2자 미만 400 검증, 잘못된 범주 422, 차트 기간 기본값
- SearchTab: 범주 버튼, 디바운스, 자동완성 드롭다운 표시, 종목 선택 후 detail 로딩
- StockChart: SVG 정상 렌더링, 0-divide 안전(단일 가격 종목), 빈 데이터 오버레이, 기간 버튼

### 실행한 테스트 명령
```
python -m pytest tests/backend/ -v       # 46 passed
npm test (src/frontend)                  # 18 passed
npm run build (src/frontend)             # TypeScript 컴파일 성공, 빌드 성공
```

### 테스트 실행 결과
- 백엔드: 46/46 통과 (기존 11개 + 신규 35개)
- 프론트엔드: 18/18 통과 (기존 6개 + 신규 12개)
- TypeScript 빌드: 0 에러

## 알려진 한계 / 추후 개선 사항
- KRX provider는 거래일 기준 날짜를 OTP 파라미터로 사용하므로 주말/공휴일에는 응답이 달라질 수 있다. 실패 시 빈 목록 반환 + lazy retry로 대응.
- NASDAQ symbol directory는 미국 주요 거래소만 포함한다. 일부 OTC, 소형주 누락 가능.
- Yahoo Finance 무료 API는 비공식 엔드포인트이며 언제든 구조가 바뀔 수 있다. 구조 변경 시 `_parse_detail`/`_parse_chart` 파서만 수정하면 된다.
- 차트 SVG는 반응형이나 마우스 오버 툴팁이 없다. 향후 외부 차트 라이브러리(Recharts 등) 도입 시 더 풍부한 인터랙션 가능.
- 종목 마스터 프리로드는 앱 시작 시 백그라운드로 수행되므로 서버 시작 직후 첫 검색은 lazy loading으로 약간 느릴 수 있다.

## Git 정보
- base_commit: c17873f811e427e4483a6781b1654452777fd372
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 02-project-search-tab[20260604-225800][02_develop]
- commit_scope:
  - .ai/features/02-project-search-tab/02_dev.md
  - src/backend/app/models/market.py
  - src/backend/app/config.py
  - src/backend/app/providers/krx_provider.py
  - src/backend/app/providers/nasdaq_provider.py
  - src/backend/app/providers/yahoo_finance.py
  - src/backend/app/services/search_service.py
  - src/backend/app/api/routes.py
  - src/backend/app/main.py
  - src/frontend/src/types/market.ts
  - src/frontend/src/api/markets.ts
  - src/frontend/src/hooks/useStockSearch.ts
  - src/frontend/src/hooks/useStockDetail.ts
  - src/frontend/src/components/DashboardTab.tsx
  - src/frontend/src/components/AutocompleteInput.tsx
  - src/frontend/src/components/StockDetailPanel.tsx
  - src/frontend/src/components/StockChart.tsx
  - src/frontend/src/components/SearchTab.tsx
  - src/frontend/src/App.tsx
  - src/frontend/src/App.css
  - tests/backend/test_krx_provider.py
  - tests/backend/test_nasdaq_provider.py
  - tests/backend/test_yahoo_finance_provider.py
  - tests/backend/test_search_service.py
  - tests/backend/test_search_routes.py
  - tests/frontend/SearchTab.test.tsx
- pre_commit_diff_command: git diff c17873f811e427e4483a6781b1654452777fd372
- changed_files: (위 commit_scope 파일 전체)
- harness_commit_blocking_reason: 없음

## 단계 결과
- status: PASS
- next_stage: 03_review
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/02-project-search-tab/02_dev.md
- changed_files:
  - src/backend/app/models/market.py
  - src/backend/app/config.py
  - src/backend/app/providers/krx_provider.py
  - src/backend/app/providers/nasdaq_provider.py
  - src/backend/app/providers/yahoo_finance.py
  - src/backend/app/services/search_service.py
  - src/backend/app/api/routes.py
  - src/backend/app/main.py
  - src/frontend/src/types/market.ts
  - src/frontend/src/api/markets.ts
  - src/frontend/src/hooks/useStockSearch.ts
  - src/frontend/src/hooks/useStockDetail.ts
  - src/frontend/src/components/DashboardTab.tsx
  - src/frontend/src/components/AutocompleteInput.tsx
  - src/frontend/src/components/StockDetailPanel.tsx
  - src/frontend/src/components/StockChart.tsx
  - src/frontend/src/components/SearchTab.tsx
  - src/frontend/src/App.tsx
  - src/frontend/src/App.css
  - tests/backend/test_krx_provider.py
  - tests/backend/test_nasdaq_provider.py
  - tests/backend/test_yahoo_finance_provider.py
  - tests/backend/test_search_service.py
  - tests/backend/test_search_routes.py
  - tests/frontend/SearchTab.test.tsx
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 02-project-search-tab[20260604-225800][02_develop]
- test_commands:
  - python -m pytest tests/backend/ -v
  - npm test (from src/frontend/)
  - npm run build (from src/frontend/)
- model_mismatch: false
- actual_model: Claude Sonnet 4.6
