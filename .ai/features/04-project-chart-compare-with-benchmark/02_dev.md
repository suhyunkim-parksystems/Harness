# 02_dev - 04-project-chart-compare-with-benchmark

작성: Claude (claude-opus-4-8)
일시: 2026-06-05

## 기능 목표
- 종목 상세 `StockChart`에 세로 날짜 grid선과 거래량 영역 기준선을 추가해 차트 가독성을 높인다.
- 한국주식/ETF 검색이 종목명뿐 아니라 6자리 종목코드로도 동작하도록 백엔드 검색을 고치고, KRX CSV 헤더의 BOM/공백 때문에 마스터가 통째로 비던 파싱 버그를 복구한다.
- 기간을 `1M -> 3Y` 등으로 바꾼 뒤 로딩 분기에서 SVG가 재마운트될 때 wheel 확대/축소·미니맵 이벤트가 끊기던 문제를 callback ref로 복구한다.

## 변경 파일
- .ai/features/04-project-chart-compare-with-benchmark/00_spec.md (입력 / 변경 금지)
- .ai/features/04-project-chart-compare-with-benchmark/01_plan.md (입력 / 변경 금지)
- .ai/features/04-project-chart-compare-with-benchmark/02_dev.md (신규)
- .ai/features/04-project-chart-compare-with-benchmark/02_dev.result.json (신규)
- src/frontend/src/services/chartHelpers.ts (수정): `sampleIndices` 순수 함수 추가 및 export.
- src/frontend/src/components/StockChart.tsx (수정): callback ref 기반 wheel listener 재연결, 세로 날짜 grid선·거래량 기준선 추가, `sampleIndices` 재사용.
- src/backend/app/providers/krx_provider.py (수정): CSV 헤더 BOM/공백 정규화, HTML/LOGOUT 방어 가드, 헤더/값 정규화 헬퍼 추가.
- src/backend/app/services/search_service.py (수정): 한국 카테고리 종목명+종목코드 동시 매칭, 중복 방지 `seen` set, 마스터 로딩 빈 결과 경고 로그.
- tests/frontend/StockChart.test.tsx (수정): `sampleIndices` 단위 테스트, grid 렌더링 테스트, 로딩 재마운트 후 wheel/미니맵 복구 회귀 테스트 추가.
- tests/frontend/SearchTab.test.tsx (수정): 한국주식 자동완성(종목명·종목코드) 호출/후보 표시 테스트 추가.
- tests/backend/test_krx_provider.py (수정): BOM/공백 헤더 fixture, HTML/LOGOUT 응답 방어 테스트 추가.
- tests/backend/test_search_service.py (수정): 종목코드 검색·부분 코드 prefix·중복 제거 테스트 추가.

## 구현 내용

### 1. 차트 GRID 가독성 (StockChart.tsx, chartHelpers.ts)
- `StockChart` 내부에 하드코딩되어 있던 `sampleIndices(total, count)`를 `chartHelpers.ts`로 이관하고 export했다. `total <= 0`이면 빈 배열, `count <= 1`이면 `[0]`을 반환하도록 엣지 케이스를 보강해 0으로 나누는 문제를 막았다.
- `StockChart`는 이제 `sampleIndices(visibleBars.length, 5)`를 한 번 계산(`labelIndices`)해 세로 grid선과 날짜 라벨이 정확히 같은 x 위치를 공유한다.
- 가격 영역에 세로 날짜 grid선(저대비 `#eef2f6`), 거래량 영역에 상단/중간/하단 기준선(`#eef2f6`, `#f1f5f9`, `#e4ebf1`)을 추가했다. 모두 캔들/거래량 막대보다 시선을 끌지 않는 저대비 보조선이며 캔들/미니맵보다 먼저(뒤쪽 레이어에) 렌더링된다.
- 로딩/빈 데이터/`unavailable` 상태에서는 기존처럼 SVG 자체가 렌더링되지 않으므로 grid도 그려지지 않는다(빈 상태 메시지 유지).

### 2. 기간 변경 후 차트 이벤트 복구 (StockChart.tsx)
- 원인: wheel listener를 빈 의존성 배열 `[]` effect에서 최초 1회만 등록했다. 기간 변경 시 `isChartLoading=true`로 SVG가 언마운트되고, 로딩 완료 후 새 SVG가 마운트되어도 effect가 다시 실행되지 않아 새 노드에 listener가 붙지 않았다.
- 해결: `svgRef`(명령형 포인터 계산용) 갱신과 `svgNode` state 갱신을 동시에 처리하는 callback ref `setSvgRef`를 도입했다. wheel listener effect의 의존성을 `[svgNode]`로 바꿔, SVG 노드가 바뀔 때마다 이전 노드의 listener를 cleanup하고 새 노드에 다시 바인딩한다.
- pointer down/move/up 로직은 `svgRef.current`를 계속 사용하므로 기존 drag pan 동작과 호환된다.
- 늦게 도착한 이전 period 응답이 최신 상태를 덮어쓰는 race는 기존 `useStockDetail`의 `ignore` 플래그 + `AbortController`로 이미 방어되어 있어 본 단계에서 hook은 수정하지 않았다.

### 3. 한국 종목 검색·KRX 파서 복구 (krx_provider.py, search_service.py)
- `_parse_master_csv`: 선두 BOM(`﻿`)을 `lstrip`으로 제거하고, 각 행의 컬럼 키/값에서 BOM·zero-width space·앞뒤 공백을 제거하는 `_normalize_row` 헬퍼를 추가했다. BOM/공백으로 컬럼 매칭이 모두 실패해 마스터가 통째로 비던 근본 원인을 차단한다.
- HTML 에러 페이지나 LOGOUT 리다이렉트가 파서에 직접 인입돼도 크래시 없이 빈 리스트를 반환하도록 가드와 경고 로그를 추가했다.
- `SearchService.search`: 한국 카테고리(`kr_stock`, `kr_etf`)는 `entry.name`과 `entry.symbol`(종목코드)을 모두 매칭 키로 사용한다. 미국 카테고리는 기존대로 ticker만 사용한다. `seen` set으로 동일 종목 중복 후보 유입을 차단하고, prefix 우선 → substring 보조 랭킹과 최대 10개 제한은 유지했다.
- `_ensure_master_loaded`: 한국 마스터가 비어 로드된 경우(KRX fetch/parse 실패) 경고 로그를 남겨, "마스터 로딩 실패로 인한 0건"과 "정상 검색 0건"을 운영 로그에서 구분할 수 있게 했다.

## 왜 이렇게 구현했는가
- callback ref + `svgNode` state(01_plan 대안 1 채택): SVG 노드 생명주기에 정확히 동기화돼 listener 누수/누락을 원천 차단한다. props 변화를 수동 추적하는 대안 2는 누락 위험이 커 기각했다.
- grid는 외부 라이브러리 없이 기존 SVG에 인라인 저대비 line으로 추가(01_plan 대안 1 채택)했다. 의존성 추가 없이 가장 가볍고 테마와 충돌하지 않는다.
- BOM/공백 정규화를 "텍스트 선두 lstrip + 행 단위 키 정규화" 두 겹으로 둔 이유: 선두 BOM은 첫 컬럼명만 깨뜨리지만, 공급원에 따라 개별 셀에도 공백/zero-width가 섞일 수 있어 행 단위 정규화로 견고성을 높였다.
- 종목코드 검색은 `(name, symbol)` 두 키에 대해 단일 분기에서 `any(...)`로 평가하므로 한 entry가 두 번 추가되지 않는다. `seen` set은 마스터 자체에 중복 레코드가 있을 때를 대비한 방어다.
- 작은 결정: 거래량 기준선을 3줄(상/중/하)로 두되 가운데 선만 더 옅은 `#f1f5f9`로 해 영역 구분은 주되 막대를 가리지 않도록 했다. 계획의 "baseline + 보조선" 의도에 맞춘 코드베이스 컨벤션 수준의 세부 결정이다.

## 호환성 준수
- 01_plan.md의 호환성 유지 전략 반영 내용: 공개 API 경로/응답 타입(`SearchResponse` 등), 8개 차트 기간, 한국/미국 상승·하락 색상 규칙, 기존 함수 시그니처를 모두 보존했다.
- 보존한 기존 인터페이스/데이터 포맷/설정 키: `_parse_master_csv(text, asset_type)` 시그니처, `SearchService.search(query, category)` 시그니처와 반환 타입, `StockChartProps`, `chartHelpers`의 기존 export.
- breaking change 발생 여부: 없음. `sampleIndices`는 신규 export, grid line/이벤트 리바인딩/검색 키 확장은 모두 가산적 변경이다. 기존 테스트는 삭제·비활성화 없이 전부 유지·통과한다.
- 계획에 없던 호환성 영향과 처리: 없음.

## 새로 추가한 의존성
- 없음.

## 테스트
- 작성/보강한 테스트 파일:
  - tests/frontend/StockChart.test.tsx: `sampleIndices` 단위 테스트(엣지 케이스 포함), 세로 grid선·거래량 baseline 렌더링 테스트, 빈 상태 grid 미렌더 테스트, 로딩 재마운트 후 wheel 확대 시 미니맵 복구 회귀 테스트.
  - tests/frontend/SearchTab.test.tsx: 한국주식 자동완성이 `category=kr_stock`로 호출되고 한글 후보가 표시되는 테스트, 6자리 종목코드(`005930`) 검색 테스트.
  - tests/backend/test_krx_provider.py: BOM+공백 헤더 fixture 정상 파싱, HTML 에러 페이지/LOGOUT 응답에서 빈 리스트 반환 테스트.
  - tests/backend/test_search_service.py: 종목코드 검색, 부분 코드 prefix 매칭, 종목명 검색 유지, 중복 마스터 dedup 테스트.
- 실행한 테스트 명령과 결과:
  - `python -m pytest tests/backend/ -q` → 61 passed, 1 warning.
  - `cd src/frontend && npm test` → 4 files / 63 passed.
  - `cd src/frontend && npx tsc -b` → 타입 에러 없음(exit 0).
- 외부 네트워크 의존: 없음. KRX/Yahoo/NASDAQ 호출은 mock 또는 fixture로 격리.
- 의도적으로 테스트하지 않은 부분: 실제 브라우저 수동 확인(검증 기준의 선택 항목)은 자동화 단위 테스트로 대체했다. drag pan 후 미니맵 유지·기간 변경 reset 등은 기존 테스트가 이미 커버한다.

## 알려진 한계 / 추후 개선 사항
- grid 색상/간격은 인라인 상수로, 추후 테마 토큰화 시 `App.css`/디자인 토큰으로 분리하면 일관성이 좋아진다(이번 범위 밖).
- 종목코드 검색은 단순 prefix/substring 매칭이다. 초성 검색·오타 교정·랭킹 고도화는 스펙상 제외 항목이다.
- KRX 컬럼명은 알려진 후보 집합으로만 매칭한다. 완전히 새로운 헤더 스키마가 오면 추가 후보 등록이 필요하다.

## Git 정보
- base_commit: e0848aaa1f97a6913e79313c33836ee1ec8ac837 (01_plan.md 기준점 우선; 현재 HEAD는 ed8d06bff8aa28d5f602dfa281925b54a79a79ec)
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 04-project-chart-compare-with-benchmark[20260605-010206][02_develop]
- commit_scope:
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.md
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.result.json
  - 구현 코드(src/frontend, src/backend)와 구현 테스트(tests/frontend, tests/backend)
- pre_commit_diff_command: git diff e0848aaa1f97a6913e79313c33836ee1ec8ac837 -- src tests
- changed_files:
  - src/frontend/src/services/chartHelpers.ts
  - src/frontend/src/components/StockChart.tsx
  - src/backend/app/providers/krx_provider.py
  - src/backend/app/services/search_service.py
  - tests/frontend/StockChart.test.tsx
  - tests/frontend/SearchTab.test.tsx
  - tests/backend/test_krx_provider.py
  - tests/backend/test_search_service.py
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.md
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.result.json
- harness_commit_blocking_reason: 없음

## 단계 결과
- status: PASS
- next_stage: 03_review
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.md
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.result.json
- changed_files:
  - src/frontend/src/services/chartHelpers.ts
  - src/frontend/src/components/StockChart.tsx
  - src/backend/app/providers/krx_provider.py
  - src/backend/app/services/search_service.py
  - tests/frontend/StockChart.test.tsx
  - tests/frontend/SearchTab.test.tsx
  - tests/backend/test_krx_provider.py
  - tests/backend/test_search_service.py
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.md
  - .ai/features/04-project-chart-compare-with-benchmark/02_dev.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 04-project-chart-compare-with-benchmark[20260605-010206][02_develop]
- test_commands:
  - python -m pytest tests/backend/ -q
  - cd src/frontend && npm test
  - cd src/frontend && npx tsc -b
- model_mismatch: false
- actual_model: claude-opus-4-8
