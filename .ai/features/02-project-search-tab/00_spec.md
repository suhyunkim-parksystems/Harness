# 00_spec - 02-project-search-tab

작성: Codex
일시: 2026-06-04

## 기능 목표
- 기존 시장 대시보드를 첫 번째 메인 탭으로 유지하고, 두 번째 탭에 한국/미국 주식 및 ETF 종목 검색, 자동완성, 상세 시세, 차트를 제공한다.
- 검색 가능한 종목 목록은 최신 상장 종목이 반영되도록 백엔드에서 갱신 및 캐시하며, 상세 조회는 외부 데이터 실패 시에도 가능한 범위의 부분 실패/캐시 상태를 명확히 표시한다.

## 기능명
- feature_name: 02-project-search-tab
- naming_reason: 하네스에서 잠긴 기능명이며, 기존 대시보드에 프로젝트/종목 검색 탭을 추가하는 범위를 안정적으로 표현한다.

## 구체적 요구사항
- 앱 최상위 화면에 탭 내비게이션을 추가한다.
- 첫 번째 탭은 기존 대시보드 화면을 그대로 표시하는 메인 탭이어야 한다.
- 두 번째 탭은 종목 검색 탭이어야 하며, 사용자가 한국주식, 한국ETF, 미국주식, 미국ETF 중 하나의 검색 범주를 선택할 수 있어야 한다.
- 검색 범주는 위 네 가지로 제한하며, 그 외 시장/상품은 이번 기능에서 검색 결과로 노출하지 않는다.
- 미국주식/미국ETF 검색은 티커를 기본 검색 키로 사용한다. 기본값은 티커 prefix 및 부분 문자열 매칭이며, 결과 표시에는 회사명/ETF명도 함께 보여준다.
- 한국주식/한국ETF 검색은 한글 종목명을 기본 검색 키로 사용한다. 기본값은 종목명 prefix 및 부분 문자열 매칭이며, 결과 표시에는 종목코드도 함께 보여준다.
- 검색 입력은 디바운스된 자동완성을 제공해야 한다. 기본값은 입력 2자 이상부터 요청하고, 응답은 최대 10개 후보로 제한한다.
- 자동완성 후보에는 시장 구분, 상품 유형, 티커 또는 종목코드, 종목명, 거래소 정보가 표시되어야 한다.
- 자동완성 후보 선택 또는 명확한 검색 제출 시 해당 종목의 상세 정보를 조회하고 표시해야 한다.
- 상세 정보에는 최소한 종목명, 티커/종목코드, 시장, 상품 유형, 거래소, 통화, 현재가 또는 종가, 시가, 고가, 저가, 전일 종가, 등락폭, 등락률, 거래량, 기준 시각, 데이터 출처, 데이터 상태가 포함되어야 한다.
- 외부 데이터가 일부만 제공되는 경우 누락 필드는 `null` 또는 `N/A`로 표시하고, 전체 상세 화면은 가능한 범위에서 계속 렌더링해야 한다.
- 차트는 필수 기능이다. 기본 범위는 일봉 가격 차트이며, 사용자가 최소 1개월, 3개월, 6개월, 1년 범위를 선택할 수 있어야 한다.
- 차트 데이터에는 날짜/시각, 시가, 고가, 저가, 종가, 거래량이 포함되어야 하며, UI는 가격 흐름과 거래량을 함께 해석할 수 있어야 한다.
- 차트 데이터가 부족하거나 provider가 실패하면 차트 영역에 명확한 오류/부분 실패 상태를 표시하고, 기본 상세 정보는 유지해야 한다.
- 백엔드는 종목 마스터 목록을 캐시해야 한다. 기본값은 프로세스 메모리 캐시이며, 한국/미국 및 주식/ETF 범주별 캐시 키를 분리한다.
- 종목 마스터 캐시는 최신 종목 반영을 우선한다. 기본 TTL은 상세 시세 캐시보다 길게 두되, 수동 또는 주기적 refresh 경로를 계획 단계에서 확정한다.
- 상세 시세/차트 캐시는 짧은 TTL을 사용하고, provider 실패 시 stale cache가 있으면 stale 상태로 반환해야 한다.
- 새 API 응답은 기존 백엔드 모델과 동일하게 camelCase JSON 필드를 사용해야 한다.
- 새 API는 검색 자동완성, 종목 상세, 차트 데이터를 분리된 엔드포인트 또는 단일 상세 엔드포인트의 명확한 하위 구조로 제공해야 한다.
- 프론트엔드는 API 호출 중 로딩, 입력 부족, 검색 결과 없음, 상세 조회 실패, 부분 실패, stale 데이터 상태를 구분해서 표시해야 한다.
- 기존 대시보드의 자동 새로고침/수동 새로고침 동작은 첫 번째 탭에서 계속 동작해야 한다.
- 검색 탭 구현 후 프론트엔드와 백엔드 테스트를 추가하거나 갱신해야 하며, 외부 HTTP 호출은 mock 또는 fixture로 격리해야 한다.

## 이번 범위에서 제외하는 것
- 한국주식/한국ETF/미국주식/미국ETF 외의 시장, 암호화폐, 선물, 옵션, 채권, 환율 검색은 제외한다.
- 실시간 체결 스트리밍, WebSocket, 호가창, 주문/매매 기능은 제외한다.
- 사용자별 관심종목 저장, 로그인, 포트폴리오, 알림 기능은 제외한다.
- 장중 초단위 실시간성 보장은 제외한다. 이번 기능은 최신 provider 응답과 짧은 TTL 캐시를 이용한 최신성 표시를 목표로 한다.
- 영구 DB 저장소 도입은 기본 범위에서 제외한다. 필요한 경우 다음 단계에서 명시적으로 의존성/저장소 변경을 검토한다.

## 입력과 출력
- 입력:
  - 탭 선택 값: `dashboard` 또는 `search`.
  - 검색 범주: `kr_stock`, `kr_etf`, `us_stock`, `us_etf`.
  - 검색어: 문자열. 기본값은 trim 후 2자 이상일 때 자동완성 요청.
  - 종목 선택 값: provider에서 조회 가능한 내부 식별자, 티커 또는 종목코드.
  - 차트 기간: `1m`, `3m`, `6m`, `1y`.
- 출력:
  - 자동완성 결과 배열: `id`, `market`, `assetType`, `symbol`, `name`, `exchange`, `currency`, `matchText`, `source`, `status`.
  - 상세 정보 객체: 기본 종목 메타데이터, OHLC, 거래량, 등락 정보, 기준 시각, 출처, 상태, 오류 메시지.
  - 차트 데이터 배열: `timestamp`, `open`, `high`, `low`, `close`, `volume`.
- 비정상 입력 처리:
  - 빈 검색어 또는 2자 미만 입력은 API 요청 없이 안내 상태를 표시한다.
  - 허용되지 않은 범주는 백엔드에서 400 계열 오류로 거부하고 프론트엔드에서 사용자 메시지를 표시한다.
  - 검색 결과가 없으면 빈 결과 상태를 표시한다.
  - provider 실패는 전체 앱 오류로 확산하지 않고 호출 단위 오류, stale, unavailable 상태로 격리한다.

## 기존 코드 영향
- 수정 예상 파일:
  - `src/frontend/src/App.tsx`: 탭 구조 추가 및 기존 대시보드를 첫 번째 탭 컨텐츠로 분리.
  - `src/frontend/src/App.css`: 탭, 검색 레이아웃, 자동완성, 상세 패널, 차트 영역 스타일 추가.
  - `src/frontend/src/api/markets.ts`: 검색/상세/차트 API 클라이언트 추가.
  - `src/frontend/src/types/market.ts`: 검색 후보, 종목 상세, 차트 데이터 타입 추가.
  - `src/frontend/src/hooks/`: 검색 자동완성 및 상세 조회 hook 추가 가능.
  - `src/frontend/src/components/`: 검색 탭, 자동완성, 상세 정보, 차트 컴포넌트 추가 가능.
  - `src/backend/app/api/routes.py`: 검색 및 상세 조회 라우트 추가.
  - `src/backend/app/models/market.py`: 검색/상세/차트 응답 모델 추가.
  - `src/backend/app/services/market_service.py` 또는 신규 서비스 파일: 기존 서비스 계층 패턴을 유지하며 종목 검색/상세 로직 추가.
  - `src/backend/app/providers/`: 종목 마스터 및 상세 시세 provider 추가 또는 기존 Stooq provider 확장.
  - `src/backend/app/config.py`: 캐시 TTL, provider URL, timeout 등 설정 추가 가능.
  - `tests/frontend/`, `tests/backend/`: 신규 UI/API/service/provider 테스트 추가.
- 사용할 기존 모듈/유틸:
  - 백엔드 `MemoryCache`를 재사용하거나 타입별 캐시로 확장한다.
  - 기존 `MarketStatus`, `SummaryStatus`, camelCase alias 패턴을 유지한다.
  - 프론트엔드의 fetch API 클라이언트, hook 기반 로딩/refresh 패턴, lucide-react 아이콘 사용 방식을 따른다.
- 충돌 가능성:
  - 현재 화면 텍스트 일부가 깨져 보이는 인코딩 문제가 있어, 새 UI 텍스트 작성 시 UTF-8 표시를 확인해야 한다.
  - 차트 라이브러리 또는 금융 데이터 provider가 새 외부 의존성을 요구할 수 있다.
  - 외부 무료 데이터 provider의 한국 ETF/미국 ETF 커버리지와 symbol 형식이 제한될 수 있다.

## 기술적 제약
- 프론트엔드는 기존 React 18, Vite, TypeScript 구조를 유지한다.
- 백엔드는 기존 FastAPI, Pydantic v2, httpx 구조를 유지한다.
- 새 코드는 서비스 레이어를 두어 provider/API/UI 책임을 분리한다.
- 테스트는 외부 네트워크에 의존하지 않으며 provider 응답은 mock 또는 fixture로 격리한다.
- 기존 공개 API와 테스트 기대값은 하위 호환을 우선한다. 기존 `/api/markets/summary`, `/api/markets/indices`, `/api/markets/exchange-rates` 응답 계약은 깨지지 않아야 한다.
- 차트 구현은 다음 단계에서 검토하되, 기본값은 새 런타임 의존성 없이 구현 가능한 SVG/HTML 기반 라인 또는 캔들 차트를 우선한다. 품질이나 유지보수상 라이브러리가 필요하면 계획 단계에서 의존성 추가 위험을 명시한다.
- 검색 자동완성은 입력 디바운스, 요청 취소 또는 최신 요청 우선 처리로 오래된 응답이 최신 입력을 덮어쓰지 않게 해야 한다.
- 종목 목록 최신성은 provider 호출 실패 시 stale cache 표시를 허용하되, 사용자가 최신성 상태를 알 수 있게 `status`, `asOf`, `source`를 노출해야 한다.

## 기본 결정 및 근거
- 별도 사용자 질문 없이 PASS로 확정한다. 하네스가 `defaults_mode: true`이고 `interactive_mode: false`이므로, 불가능하거나 안전상 차단되는 항목이 아닌 모호성은 권장 기본값으로 결정했다.
- 검색 범주는 사용자 요청 그대로 네 가지로 고정한다. 범위를 넓히면 provider/UX 복잡도가 커져 이번 목표를 흐린다.
- 미국 종목은 티커 기반, 한국 종목은 이름 기반 검색을 기본 계약으로 둔다. 사용자가 명시한 핵심 사용성 요구사항이다.
- 자동완성은 2자 이상, 최대 10개 후보, 디바운스 적용을 기본값으로 둔다. 네트워크 부하와 사용성을 균형 있게 맞추는 보수적 기본값이다.
- 차트는 필수 범위에 포함한다. 사용자가 특히 차트 기능을 강조했기 때문이다.
- 캐시는 프로세스 메모리 캐시를 기본값으로 둔다. 현재 코드에 이미 `MemoryCache`가 있고 영구 저장소 추가는 외부 의존성과 범위 확대를 유발한다.
- human gate는 유지한다. 금융 데이터 provider 선택, 캐시 최신성 정책, 차트 구현 방식은 사용자 경험과 외부 의존성에 직접 영향을 준다.

## 위험도 및 게이트
- risk_level: high
- human_gate_required: true
- human_gate_reason: 금융 데이터 외부 연동, 최신 종목 마스터 갱신, 차트 필수 구현, 새 provider 또는 차트 의존성 가능성이 있어 사용자 승인 게이트가 필요하다.

## 사용자 확인 사항
- 질문 없음. 기본 결정은 `## 기본 결정 및 근거`에 기록했다.

## 단계 결과
- status: PASS
- next_stage: 01_plan
- human_gate_required: true
- blocking_reason: 없음
- risk_level: high
- produced_files:
  - .ai/features/02-project-search-tab/00_spec.md
  - .ai/features/02-project-search-tab/00_spec.result.json
- changed_files:
  - .ai/features/02-project-search-tab/00_spec.md
  - .ai/features/02-project-search-tab/00_spec.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "spec: define project search tab"
- model_mismatch: false
- actual_model: Codex
