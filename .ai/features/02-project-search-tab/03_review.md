# 03_review - 02-project-search-tab

작성: Antigravity
일시: 2026-06-04

## 리뷰 대상
- 검토한 파일 목록:
  - [src/backend/app/models/market.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/models/market.py)
  - [src/backend/app/config.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/config.py)
  - [src/backend/app/providers/krx_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/krx_provider.py)
  - [src/backend/app/providers/nasdaq_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/nasdaq_provider.py)
  - [src/backend/app/providers/yahoo_finance.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/yahoo_finance.py)
  - [src/backend/app/services/search_service.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/search_service.py)
  - [src/backend/app/api/routes.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/api/routes.py)
  - [src/backend/app/main.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/main.py)
  - [src/frontend/src/types/market.ts](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/types/market.ts)
  - [src/frontend/src/api/markets.ts](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/api/markets.ts)
  - [src/frontend/src/hooks/useStockSearch.ts](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/hooks/useStockSearch.ts)
  - [src/frontend/src/hooks/useStockDetail.ts](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/hooks/useStockDetail.ts)
  - [src/frontend/src/components/DashboardTab.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/DashboardTab.tsx)
  - [src/frontend/src/components/AutocompleteInput.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/AutocompleteInput.tsx)
  - [src/frontend/src/components/StockDetailPanel.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StockDetailPanel.tsx)
  - [src/frontend/src/components/StockChart.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StockChart.tsx)
  - [src/frontend/src/components/SearchTab.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/SearchTab.tsx)
  - [src/frontend/src/App.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/App.tsx)
  - [src/frontend/src/App.css](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/App.css)
  - [tests/backend/test_krx_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_krx_provider.py)
  - [tests/backend/test_nasdaq_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_nasdaq_provider.py)
  - [tests/backend/test_yahoo_finance_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_yahoo_finance_provider.py)
  - [tests/backend/test_search_service.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_search_service.py)
  - [tests/backend/test_search_routes.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_search_routes.py)
  - [tests/frontend/SearchTab.test.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/frontend/SearchTab.test.tsx)
- base_commit: `c17873f811e427e4483a6781b1654452777fd372`
- review_target_commit: `59d4965224dec75df8bde4aaf01b502b782e3b0f`
- diff_command: `git diff c17873f811e427e4483a6781b1654452777fd372..59d4965224dec75df8bde4aaf01b502b782e3b0f`
- diff_range: `c17873f811e427e4483a6781b1654452777fd372..59d4965224dec75df8bde4aaf01b502b782e3b0f`

## 지적 사항 요약
- BLOCKER: 0개
- MAJOR: 2개
- MINOR: 2개
- NIT: 2개

## 코드 품질
### 1. 외부 연동 실패 시 Stale Fallback 동작 불능 버그 (MAJOR)
- **severity**: MAJOR
- **지적 사항**: 외부 시세 API 통신 또는 파싱 실패 시 `SearchService`에 구현된 Stale Fallback이 동작하지 않음.
- **해결 방안 및 관련 코드**:
  - 관련 코드 위치: [yahoo_finance.py#L45-L73](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/yahoo_finance.py#L45-L73), [search_service.py#L96-L138](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/search_service.py#L96-L138)
  - **왜 문제인지**: `YahooFinanceProvider`의 `fetch_detail`과 `fetch_chart`는 외부 연동/파싱 에러 시 내부 `try-except` 블록에서 예외를 처리하고 `status="unavailable"`를 마킹한 정상 `StockDetail` / `ChartResponse` 모델을 반환합니다. 이로 인해 `SearchService` 내부의 `try-except` 블록에 진입하지 못하며, 결과적으로 이전에 저장해 둔 캐시 데이터가 있어도 이를 복구하는 stale fallback 로직이 실행되지 않습니다. 오히려 `unavailable` 상태의 새 데이터가 캐시에 덮어씌워지게 됩니다.
  - **어떻게 개선해야 하는지**:
    - `YahooFinanceProvider`가 외부 연동 실패 시 `_make_unavailable_detail` 등을 바로 리턴하지 않고 예외를 발생시키도록(또는 예외를 다시 raise하도록) 변경하여 `SearchService`의 `except Exception` 분기로 빠지게 유도하고, `SearchService`에서 stale 캐시가 없을 때 비로소 `unavailable` 응답을 처리하도록 변경합니다.
    - 또는 `SearchService`가 `yahoo_provider` 응답을 검사하여 `detail.status == "unavailable"` 인 경우, `stale` 데이터가 캐시에 있는지 먼저 확인하고 있으면 stale 데이터를 반환하도록 처리합니다.

### 2. 프론트엔드 `useStockDetail` 내 `Promise.all` 사용으로 인한 부분 실패 격리 누락 (MAJOR)
- **severity**: MAJOR
- **지적 사항**: 상세 조회 API와 차트 API 호출 중 하나가 실패했을 때 전체 렌더링이 실패함.
- **해결 방안 및 관련 코드**:
  - 관련 코드 위치: [useStockDetail.ts#L48-L68](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/hooks/useStockDetail.ts#L48-L68)
  - **왜 문제인지**: `useStockDetail` 훅에서 종목 상세와 차트 조회를 `Promise.all`로 처리하고 있습니다. 이로 인해 두 요청 중 차트 데이터 조회(또는 상세 조회) 중 단 하나라도 503 등의 에러(reject)를 반환하면, 성공한 다른 하나의 응답이 있어도 전체가 `catch` 블록으로 넘어가고 에러 상태가 표시됩니다. 이는 "차트 데이터가 부족하거나 provider가 실패하면 차트 영역에 명확한 오류/부분 실패 상태를 표시하고, 기본 상세 정보는 유지해야 한다."는 스펙 요구사항에 어긋납니다.
  - **어떻게 개선해야 하는지**: `Promise.all` 대신 `Promise.allSettled`를 사용하거나, `fetchStockDetail`과 `fetchStockChart`를 분리하여 개별 에러 핸들링 및 상태 할당을 진행해야 합니다.

## 구조 및 가독성
### 1. `StockChart.tsx` 내 Y축 가격 라벨 잘림 가능성 (NIT)
- **severity**: NIT
- **지적 사항**: Y축 눈금 라벨이 위치한 공간(`PAD_LEFT=56`)이 큰 단위의 원화 가격을 표시하기에 부족할 수 있음.
- **해결 방안 및 관련 코드**:
  - 관련 코드 위치: [StockChart.tsx#L13](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StockChart.tsx#L13), [StockChart.tsx#L121-L125](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StockChart.tsx#L121-L125)
  - **왜 문제인지**: `PAD_LEFT`가 `56` 픽셀로 고정되어 있습니다. 10만 원이 넘는 원화 종목의 경우 Y축 가격 라벨(예: `150,000` 등)이 우측 정렬(`textAnchor="end"`)되면서 왼쪽 SVG 프레임 바깥으로 삐져나가 일부 잘려 보일 가능성이 있습니다.
  - **어떻게 개선해야 하는지**: `PAD_LEFT`를 약간 늘리거나(예: 64~72), 가격이 큰 경우 단위 변환(K 등) 혹은 가격 포맷팅 자릿수를 유연하게 제어하는 것을 권장합니다.

### 2. `SearchService` 내 `_load_lock` 단일화로 인한 병렬 preload 비효율 (NIT)
- **severity**: NIT
- **지적 사항**: 비즈니스 레이어에서 모든 카테고리의 로드 락을 하나의 lock 멤버 변수로 공유함.
- **해결 방안 및 관련 코드**:
  - 관련 코드 위치: [search_service.py#L61](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/search_service.py#L61), [search_service.py#L145](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/search_service.py#L145)
  - **왜 문제인지**: `preload_all_masters`에서 4가지 카테고리를 순차적으로 로드할 때, 하나의 `self._load_lock`을 사용하기 때문에 사실상 카테고리 간에도 대기가 발생합니다. 이는 병렬 사전 로딩 시 성능 비효율을 가져올 수 있습니다.
  - **어떻게 개선해야 하는지**: 카테고리별로 Lock 객체를 분리하여 관리(예: 딕셔너리 구조)하면 카테고리 간 간섭 없이 독립적인 락 제어가 가능합니다.

## 계획 대비 구현 일치성
- **severity**: MINOR
- **01_plan.md 대비 일치/불일치 항목**: Stale Fallback 전략 및 에러 격리
- **구체적 차이**: 플랜에서는 "외부 공급처 호출 실패 시 캐시에 보관된 Stale 데이터를 리턴하여 전체 중단을 방지한다"고 하였으나, 실제 구현에서는 `YahooFinanceProvider`가 예외를 삼키고 정상 형태의 `unavailable` 응답 객체를 던지도록 설계되었습니다. 이로 인해 `SearchService`에서 Stale 데이터를 반환하는 동작이 무력화되었습니다.
- **이 차이가 문제인지, 허용 가능한지**: 외부 연동 실패 시 stale 데이터 노출이라는 핵심 스펙 요구사항이 어긋나는 지점이므로, 허용하기 어렵고 반드시 다음 `04_fix` 단계에서 수정되어야 합니다.

## 호환성 / 회귀 위험
- **severity**: NIT
- **지적 사항**: `/api/health` 응답에 `providers` 항목 추가
- **깨질 수 있는 기존 인터페이스/호출부/테스트**:
  - 기존 테스트([test_routes.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_routes.py))는 헬스 체크 응답 시 `stooq` 및 `frankfurter` 항목의 존재 여부만 검사하므로 영향은 전혀 없습니다.
  - 외부 API 포맷과의 역호환성은 100% 만족하며 기존 대시보드 화면 및 훅 구조도 `DashboardTab`으로 잘 격리 이관되었습니다.
- **개선 제안**: 특이 사항 없으며 기존 호환성은 매우 잘 유지되었습니다.

## 구현 의도 타당성
- **severity**: NIT
- **02_dev.md에 적힌 판단에 대한 동의 또는 반론**:
  - `02_dev.md`에 기재된 "us_stock + us_etf 공동 적재", "AbortController + ignore 플래그 2중 방어", "순수 SVG 차트 구현" 의사결정에 전적으로 동의합니다.
  - 런타임에 불필요한 서드파티 차트 라이브러리(Recharts 등)나 외부 패키지 의존성을 가져오지 않고 순수 SVG로 캔들스틱과 거래량 스케일링을 정확하게 계산하여 구현한 점은 가볍고 컴파일 에러가 없어 높은 점수를 줍니다.
- **반론 시 근거**: 없음.

## 테스트
- **severity**: MAJOR
- **누락된 테스트 케이스**:
  - `fetchStockDetail`은 성공하고 `fetchStockChart`가 실패하는 상황에 대한 부분 실패 테스트 케이스.
  - 한국 원화(KRW) 금액 렌더링에 대한 포맷팅 단위 테스트.
- **각 케이스가 왜 필요한지**:
  - 프론트엔드의 `Promise.all` 구조로 인해 한쪽 API가 터졌을 때 상세 스펙(부분 실패 노출)을 만족하지 못하므로, 이를 검증하는 테스트가 누락되어 있습니다.
  - 포맷팅 유틸리티에서 한국 통화에 소수점이 붙어 나오는 엣지 케이스를 테스트하여 올바르게 렌더링되는지 보장할 필요가 있습니다.

## 04_fix 입력
- **must_fix**:
  - `SearchService`에서 `YahooFinanceProvider`가 `status="unavailable"`을 리턴했을 때도 캐시에 기존 stale 데이터가 있다면 stale 데이터를 꺼내와 `"stale"` 상태로 제공할 수 있도록 보강. (또는 예외를 상위로 전파하여 `except`의 `stale` 반환 로직이 수행되도록 수정)
  - 프론트엔드 `useStockDetail` 훅에서 `Promise.all`을 해체하거나 개별 catch 처리를 더해, 차트 조회가 실패하더라도 상세 시세 패널은 정상 렌더링되도록 수정.
- **should_consider**:
  - `StockDetailPanel` 내 `formatPrice`가 `KRW` 통화일 때 소수점을 생략하도록 수정.
  - `StockChart`에서 한국 주식/ETF 카테고리(`kr_stock`, `kr_etf`)일 때 상승(빨간색), 하락(파란색)으로 렌더링되도록 캔들스틱 및 거래량 색상 분기 처리.
- **optional**:
  - `StockChart` Y축의 가격 눈금 라벨이 SVG 경계에 가려 잘리지 않도록 `PAD_LEFT` 값 및 포맷팅 자릿수 조정.
  - `SearchService` 내 `_load_lock`을 카테고리별로 분산 관리하도록 개선.

## 총평
- 02_dev 개발자가 구현한 코드의 베이스라인은 상당히 정교하고 테스트 통과율도 100%로 훌륭합니다.
- 다만, 외부 연동 실패를 대비한 **Stale Fallback 기능**이 `yahoo_provider` 내부의 과도한 예외 포착으로 인해 무력화된 상태이며, 프론트엔드 단에서도 `Promise.all`을 이용해 두 API를 일괄 fetch하고 있어 **차트 조회 실패 시 상세 조회 데이터까지 렌더링이 깨지는 병목**이 존재합니다.
- 다음 단계인 `04_fix` 단계에서 이 두 가지 MAJOR 결함을 핵심적으로 수정하고, MINOR UX 피드백(원화 소수점 제거, 상승/하락 캔들 색상 분기)을 보완한다면 완벽한 검색/차트 탭 스펙을 달성할 수 있습니다.

## 단계 결과
- status: PASS
- next_stage: 04_fix
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/02-project-search-tab/03_review.md
- changed_files:
- harness_commit_required: false
- commit_created_by_model: false
- commit_message_suggestion:
- model_mismatch: false
- actual_model: Antigravity
