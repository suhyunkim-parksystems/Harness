# 00_spec - 05-debug-krx

작성: Codex
일시: 2026-06-05

## 기능 목표
- KRX 한국 주식/ETF 마스터 로딩 실패 원인을 provider 단계에서 드러내고, SearchService가 마스터 로딩 실패와 정상 검색 0건을 구분해 응답하도록 수정한다.
- 검색 UI는 한국주식/한국ETF/미국주식/미국ETF 선택 버튼을 제거하고, 네 범주를 한 번에 조회하는 통합 자동완성으로 바꾼다.

## 기능명
- feature_name: 05-debug-krx
- naming_reason: 하네스가 잠근 기능명이며, KRX 자동완성 디버깅과 통합검색 UI 변경을 함께 나타낸다.

## 구체적 요구사항
- `src/backend/app/providers/krx_provider.py`의 KRX OTP 요청은 현재 실서버에서 `url=...` 파라미터가 `LOGOUT`을 유발하므로 `bld=dbms/MDC/STAT/standard/...` 기반 payload로 변경한다.
- KRX stock master 요청은 `bld=dbms/MDC/STAT/standard/MDCSTAT01901`, `locale=ko_KR`, `mktId=ALL`, `trdDd=YYYYMMDD`, `share=1`, `money=1`, `csvxls_isNo=false`, `name=fileDown`을 명시한다.
- KRX ETF master 요청은 기존 ETF 화면 ID인 `dbms/MDC/STAT/standard/MDCSTAT04001`을 `bld`로 보내고, CSV 다운로드에 필요한 공통 form field와 헤더를 유지한다.
- KRX OTP/CSV 요청은 `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`, KRX Data Marketplace `Referer`, `User-Agent`, 필요 시 `X-Requested-With: XMLHttpRequest`를 명시한다.
- KRX provider는 네트워크 오류, HTTP 오류, `LOGOUT`, HTML/redirect, OTP 없음, CSV 본문 없음, CSV 파싱 결과가 비정상적으로 빈 경우를 정상 `[]`로 숨기지 말고 오류로 전달한다.
- CSV 파서는 정상 CSV에서 실제 레코드가 0건인 경우와 오류 페이지/빈 본문을 구분할 수 있어야 한다.
- `src/backend/app/services/search_service.py`는 마스터 로딩 실패를 SearchResponse에 `status`와 오류 메시지로 반영하고, 정상적으로 마스터가 로드된 뒤 매칭 결과가 없는 경우는 `status=ok`, `candidates=[]`로 응답한다.
- 통합 자동완성은 한국주식, 한국ETF, 미국주식, 미국ETF 마스터를 모두 조회해 최대 10개 후보를 반환한다.
- 통합 자동완성에서 일부 마스터만 실패하면 가능한 후보는 반환하고 `status=partial` 및 실패 설명을 함께 제공한다. 모든 마스터가 실패하면 `status=unavailable`, `candidates=[]`로 응답한다.
- 기존 클라이언트 호환성을 위해 `/api/search/autocomplete`의 `category` 쿼리는 선택값으로 유지한다. `category`가 있으면 기존 범주 단일 검색을 지원하고, 없으면 통합검색을 수행한다.
- 프론트엔드 `SearchTab`은 네 개 카테고리 선택 버튼과 관련 상태 초기화 로직을 제거한다.
- 프론트엔드 자동완성 API 호출은 더 이상 `category`를 보내지 않는다.
- 후보 선택 후 상세/차트 요청은 선택 후보의 `assetType`을 사용해 기존 detail/chart API와 Yahoo suffix 결정 로직을 유지한다.
- 기존 debounce, abort, 늦은 응답 무시 동작은 유지한다.
- 백엔드 테스트는 외부 네트워크에 의존하지 않고 KRX/NASDAQ/Yahoo 호출을 mock 또는 fixture로 격리한다.
- 프론트엔드 테스트는 카테고리 버튼 제거, 통합 autocomplete URL, 후보 `assetType` 기반 상세/차트 호출을 검증하도록 갱신한다.

## 이번 범위에서 제외하는 것
- KRX 로그인, 인증 우회, 계정/쿠키 기반 수집 기능은 구현하지 않는다. 현재 요구는 공개 CSV/OTP 계약 보정이다.
- 새로운 외부 의존성 추가는 하지 않는다. 기존 `httpx`, FastAPI, React/Vitest 패턴을 사용한다.
- 상세/차트 API의 `category` 파라미터 제거는 하지 않는다. 선택 후보의 `assetType`으로 계속 호출해 하위 호환성을 지킨다.
- 검색 결과 UI의 대규모 리디자인은 하지 않는다. 버튼 제거와 통합검색에 필요한 문구/상태 표시만 조정한다.
- Git commit, reset, checkout, rebase, push는 수행하지 않는다. 커밋은 하네스가 담당한다.

## 입력과 출력
- 입력: `/api/search/autocomplete?q=<검색어>` 또는 하위 호환용 `/api/search/autocomplete?q=<검색어>&category=<kr_stock|kr_etf|us_stock|us_etf>`.
- 입력 검색어는 기존처럼 최소 2자 이상을 요구한다.
- 통합검색 출력: `SearchResponse` JSON. `candidates`는 `SearchCandidate[]`, 각 후보는 `assetType`, `symbol`, `name`, `market`, `exchange`, `currency`, `source`, `status`를 포함한다.
- 정상 0건 출력: `status=ok`, `candidates=[]`, `errorMessage=null` 또는 미설정.
- 일부 마스터 실패 출력: `status=partial`, 가능한 `candidates`, 실패 설명 `errorMessage`.
- 전체 마스터 실패 출력: `status=unavailable`, `candidates=[]`, 실패 설명 `errorMessage`.
- 후보 선택 후 입력: `/api/stocks/{symbol}/detail?category=<candidate.assetType>`, `/api/stocks/{symbol}/chart?category=<candidate.assetType>&period=<period>`.
- 비정상 입력: 유효하지 않은 `category`가 명시되면 기존 FastAPI validation 실패를 유지한다. `category`가 생략되면 통합검색으로 처리한다.

## 기존 코드 영향
- 수정 예상 파일:
  - `src/backend/app/providers/krx_provider.py`
  - `src/backend/app/services/search_service.py`
  - `src/backend/app/models/market.py`
  - `src/backend/app/api/routes.py`
  - `src/frontend/src/api/markets.ts`
  - `src/frontend/src/hooks/useStockSearch.ts`
  - `src/frontend/src/components/SearchTab.tsx`
  - `src/frontend/src/types/market.ts`
- 테스트 수정 예상 파일:
  - `tests/backend/test_krx_provider.py`
  - `tests/backend/test_search_service.py`
  - `tests/backend/test_search_routes.py`
  - `tests/frontend/SearchTab.test.tsx`
- 기존 충돌 가능성:
  - 기존 테스트는 카테고리 버튼 렌더링과 `category=kr_stock` autocomplete 호출을 기대하므로 변경해야 한다.
  - 기존 `SearchService.search(query, category)` 호출부와 테스트는 optional category 또는 통합검색 메서드 도입에 맞춰 갱신해야 한다.
  - `SearchResponse`에 `errorMessage`를 추가하면 API 확장이므로 프론트 타입과 백엔드 모델을 함께 맞춰야 한다.

## 기술적 제약
- 새 라이브러리는 추가하지 않는다.
- 외부 데이터 조회 실패는 provider에서 삼키지 않고 서비스 레이어가 fallback, partial, unavailable 상태를 결정한다.
- KRX/NASDAQ/Yahoo 외부 호출 테스트는 mock/fixture로 격리한다.
- 통합검색은 현재 마스터 캐시 TTL과 stale detail/chart cache 패턴을 유지한다.
- 통합검색 로딩은 한 공급자 실패가 전체 검색을 중단하지 않도록 호출 단위로 격리한다.
- 한국 종목은 종목명과 6자리 코드로 검색하고, 미국 종목/ETF는 기존처럼 티커 중심 검색을 유지한다.

## KRX 실서버 확인 메모
- 2026-06-05 기준 `https://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd`에 `url=dbms/MDC/STAT/standard/MDCSTAT01901`를 form field로 보내면 `LOGOUT`이 반환됨을 확인했다.
- 같은 endpoint에 `bld=dbms/MDC/STAT/standard/MDCSTAT01901`, `mktId=ALL`, `trdDd=20260605`, form-urlencoded Content-Type, KRX Referer/User-Agent를 보내면 OTP 문자열이 반환됨을 확인했다.
- ETF도 `url=dbms/MDC/STAT/standard/MDCSTAT04001`은 `LOGOUT`, `bld=dbms/MDC/STAT/standard/MDCSTAT04001`은 OTP 문자열을 반환함을 확인했다.
- CSV 다운로드 본문 검증은 구현 단계에서 같은 세션, mock, fixture를 함께 사용해 검증한다. 빈 CSV 본문은 마스터 로딩 실패로 취급한다.

## 기본 결정 기록
- `feature_name`은 `feature_name_locked: true`이므로 `05-debug-krx`를 유지한다.
- `risk_level`은 여러 백엔드/프론트 파일과 API 응답 상태, 테스트 갱신이 필요한 변경이므로 `medium`으로 둔다.
- `category` 쿼리는 제거하지 않고 optional로 유지한다. 공개 API 하위 호환성을 지키면서 UI 요구사항인 통합검색을 만족하기 위한 기본 결정이다.
- 정상 0건과 실패 구분은 `SearchResponse.status`와 `errorMessage` 확장으로 처리한다. 기존 `candidates` 구조를 유지해 클라이언트 영향 범위를 줄이기 위한 기본 결정이다.
- 새 의존성은 추가하지 않는다. 기존 `httpx`, cache, service layer 패턴으로 해결 가능하기 때문이다.

## 위험도 및 게이트
- risk_level: medium
- human_gate_required: true
- human_gate_reason: 프리셋상 00_spec 단계는 사람 승인 게이트가 필요하며, 검색 UX와 API 응답 상태 정책이 사용자 경험에 직접 영향을 준다.

## 사용자 확인 사항
- 추가 질문 없음.
- defaults_mode에 따라 하위 호환성 유지, 통합검색 기본값, 부분 실패 상태 응답 정책을 권장 기본값으로 확정했다.

## 단계 결과
- status: PASS
- next_stage: 01_plan
- human_gate_required: true
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/05-debug-krx/00_spec.md
  - .ai/features/05-debug-krx/00_spec.result.json
- changed_files:
  - .ai/features/05-debug-krx/00_spec.md
  - .ai/features/05-debug-krx/00_spec.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "spec: define krx autocomplete recovery"
- model_mismatch: false
- actual_model: Codex
