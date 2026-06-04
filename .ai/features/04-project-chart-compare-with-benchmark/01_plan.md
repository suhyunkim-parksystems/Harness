# 01_plan - 04-project-chart-compare-with-benchmark

작성: Antigravity
일시: 2026-06-05

## 기능 목표
- 종목 상세 `StockChart`에 Y축 가격 수평 grid 외에도 날짜 기준 세로 grid와 거래량 영역 기준선(baseline 및 보조선)을 추가해 차트 가독성을 높인다.
- 한국주식/ETF 검색 시 자동완성과 결과가 제대로 나오지 않는 문제를 디버깅하고 백엔드 검색/KRX 파서 영역을 복구한다. 한국 종목은 종목명뿐만 아니라 6자리 종목코드 검색도 지원한다.
- 종목 검색 직후에는 잘 동작하지만 기간을 `1M -> 3Y` 등으로 변경했을 때 휠 확대/축소, 드래그 이동(pan), 미니맵 등 차트 이벤트가 끊기는 현상을 디버깅하고 SVG 재마운트 시에도 리스너가 유지되도록 복구한다.

## 구현 접근 방식
기존 구현의 구조적 한계와 버그 원인을 정확히 분석하여 다음과 같이 접근한다.
1. **차트 이벤트 재연결**: `StockChart.tsx`에서 `isChartLoading=true` 상태일 때 SVG가 언마운트되고 로딩 메시지가 렌더링된다. 이후 로딩이 완료되면 새 SVG가 마운트되지만, 기존 wheel listener는 빈 의존성 배열(`[]`)을 가진 `useEffect`에서 최초 1회만 등록되어 누락된다. 이를 해결하기 위해 `svgRef` mutable ref와 함께 `svgNode` state를 관리하는 Callback Ref를 도입하여, SVG DOM 노드가 변경(마운트/재마운트/언마운트)될 때마다 이벤트를 유연하고 안전하게 재등록하도록 한다.
2. **차트 GRID 가독성 추가**: `StockChart` 내부에 하드코딩되어 있던 `sampleIndices` 함수를 `chartHelpers.ts`로 이관하여 날짜 라벨 출력 위치와 세로 grid line 위치가 일관되게 공유되도록 하고, 거래량 영역 하단 baseline 및 보조선을 캔들과 충돌하지 않는 저대비 stroke 색상으로 구현한다.
3. **한국 종목 및 코드 검색 디버깅**: 백엔드 `SearchService.search()`에서 한국 종목(category가 `kr_stock`, `kr_etf`인 경우)은 이름(`entry.name`)과 종목코드(`entry.symbol`)를 모두 비교 대상으로 처리한다. KRX CSV 파서(`_parse_master_csv`)에서는 CSV 헤더에 포함될 수 있는 BOM(`\ufeff`) 및 공백 문자를 정규화(trim & clean)하여 컬럼 매칭 실패를 근본적으로 차단한다.

## 검토한 대안
- **차트 이벤트 재연결 대안 1 (채택)**: `Callback Ref + svgNode state + [svgNode] effect` 구조를 사용한다. SVG DOM 노드의 생성 및 파괴 수명주기에 완벽히 동기화되어 wheel 리스너 누수나 오작동을 차단한다. 기존 `svgRef.current`를 사용하는 pointer grab logic과의 호환성도 보존할 수 있다.
- **차트 이벤트 재연결 대안 2 (기각)**: `useEffect` 의존성 배열에 `[data, period, isLoading]`을 추가하여 리스너를 재설정한다. 이 방식은 SVG 재마운트를 유발하는 모든 상태 변화를 프론트엔드 props 수준에서 수동으로 추적해야 하므로 복잡성이 올라가고 예기치 못한 누락이 생기기 쉬워 기각한다.
- **GRID 렌더링 대안 1 (채택)**: 기존 SVG 레이아웃 구조 내에 인라인 스타일로 저대비 보조 격자선(세로 grid 및 거래량 기준선)을 추가한다. 스타일 유지보수 및 기존 테마 색상과 충돌하지 않으면서도 가장 가볍고 안전하게 가독성을 향상시킬 수 있다.
- **GRID 렌더링 대안 2 (기각)**: D3 등 외부 차트 라이브러리를 도입하거나 grid 전용 외부 CSS 파일을 대대적으로 변경한다. 이는 스펙(기존 SVG 기반 구조 확장)을 벗어나고 불필요한 의존성 위험을 초래하므로 기각한다.
- **검색 디버깅 대안 1 (채택)**: KRX CSV 파서에서 첫 라인의 BOM 및 공백을 정규화하여 DictReader를 생성하고, `SearchService` 내에서 한글명과 종목코드를 모두 지원하도록 매칭 로직을 분기한다. 기존에 정의된 `SearchResponse` 인터페이스 계약을 깨뜨리지 않고 견고하게 디버깅한다.

## 변경 파일 계획
- [chartHelpers.ts](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/services/chartHelpers.ts) (수정):
  - `sampleIndices(total: number, count: number): number[]` 함수를 추가 export하여 테스트 가능하게 하고 `StockChart.tsx`에서 재사용하도록 한다.
  - 관련 단위 테스트를 작성하여 엣지 케이스(total 0, total <= count, 균등 분할)를 검증한다.
- [StockChart.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StockChart.tsx) (수정):
  - `setSvgRef` callback ref를 구현하여 `svgRef.current` 갱신과 `setSvgNode(node)`를 동시에 처리한다.
  - `useEffect` 의존성을 `[svgNode]`로 변경하여 새 SVG가 마운트될 때마다 `wheel` 이벤트 리스너를 바인딩하고 언마운트 시 안전하게 해제(cleanup)한다.
  - 세로 날짜 grid선을 추가 렌더링하고, 거래량 영역에 baseline 및 보조 격자선을 추가한다. 색상은 차트 요소를 방해하지 않는 저대비 보조선 색상(예: `#e4ebf1` 또는 그 이하의 대비 색상)을 적용한다.
- [krx_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/krx_provider.py) (수정):
  - `_parse_master_csv` 함수에서 CSV 텍스트의 첫 줄(헤더)을 파싱하기 전에 `\ufeff` BOM을 제거하고 컬럼명 앞뒤 공백을 strip하여 헤더를 정규화한다.
  - 컬럼 파싱 시 `BOM`이나 공백으로 인한 key mismatch가 발생하지 않도록 조치한다.
- [search_service.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/search_service.py) (수정):
  - `search` 함수에서 `category`가 한국 카테고리(`kr_stock`, `kr_etf`)일 때 한글 종목명과 6자리 종목코드를 모두 검색 키로 활용한다.
  - 중복 entry 수집을 차단하기 위해 `seen` set을 활용하여 동일 종목의 중복 후보 반환을 원천적으로 막는다.
  - `_ensure_master_loaded`에서 마스터 캐시 로딩 실패 시 로그를 남겨 실제 API 정상 0건 결과와 로딩 실패 상황을 격리하고 로그 수집을 보강한다.

## 데이터 / 제어 흐름
```
[검색 자동완성 흐름]
사용자 입력 (한글명/종목코드) -> SearchTab -> AutocompleteInput
  -> GET /api/search/autocomplete?q=...&category=...
  -> SearchService.search()
       -> _ensure_master_loaded() (KRXProvider 캐시 검사 및 마스터 로드)
          -> (캐시 미스 시) KRX CSV 다운로드 -> BOM/공백 정규화 파싱 -> MasterRecord 리스트 생성
          -> 로드 실패 시 warning 로그 출력
       -> 한국 카테고리인 경우: name.lower() 및 symbol.lower() 비교
          -> seen set로 중복 제거하며 prefix 및 substring 매칭 필터링 (최대 10개)
  -> SearchResponse 반환 -> Dropdown UI 갱신

[기간 변경 및 차트 이벤트 흐름]
차트 기간 변경 클릭 (1M -> 3Y) -> setPeriod()
  -> state.isChartLoading = true 상태 진입 -> 기존 SVG unmount -> callback ref 호출 (svgNode = null)
  -> useEffect cleanup 트리거 -> 이전 wheel 이벤트 리스너 안전하게 제거
  -> 차트 데이터 Fetch 완료 -> state.isChartLoading = false -> 새 SVG mount
  -> callback ref 호출 (svgNode = 신규 SVG 노드) -> useEffect([svgNode]) 실행
  -> 신규 SVG 노드에 wheel 리스너 바인딩 완료
  -> 사용자가 휠 조작 시 정상 작동 (zoom, pan, minimap 렌더링 유지)
```

## 구현 단계 분할
1. **1단계: chartHelpers 모듈 보강**
   - `sampleIndices` 함수를 `chartHelpers.ts`로 이관 및 export 추가.
   - 단위 테스트 작성 (`tests/frontend/StockChart.test.tsx` 내에 `chartHelpers` 테스트 케이스 보강).
2. **2단계: StockChart GRID선 추가 및 렌더링 보강**
   - `StockChart.tsx`에서 `sampleIndices`를 활용하여 가격 세로선 및 거래량 baseline/보조선 추가.
   - 데이터 로딩/오류 상태에서 GRID선이 오동작하거나 에러를 내지 않도록 방어 코드 추가.
3. **3단계: Callback Ref를 활용한 SVG wheel 리스너 라이프사이클 복구**
   - Callback ref `setSvgRef` 및 `svgNode` state 기반 wheel listener 등록 구현.
   - 로딩 완료 후 SVG 재마운트 시 휠 줌/드래그 팬/미니맵 이벤트가 끊김 없이 복구되는지 검증.
4. **4단계: 백엔드 KRX CSV 파서 헤더 정규화**
   - `krx_provider.py` 내 `_parse_master_csv`에 BOM 제거 및 공백 정규화 로직 적용.
   - 헤더에 예기치 못한 공백이나 BOM이 포함된 fixture 테스트 구현.
5. **5단계: 백엔드 SearchService 한국 종목코드 검색 디버깅**
   - `search_service.py` 내에서 한국 카테고리 대상 종목코드/종목명 동시 매칭 및 중복 방지 로직 적용.
   - 마스터 캐시 로딩 실패 시 로그 보강 및 unit test 작성.

## 위험 구간 및 완화 방안 (사전 부검 반영)
- **위험 1: unmount 시점 리스너 cleanup 실패 및 중복 리스너 등록으로 인한 메모리 누수/zoom 속도 폭주**
  - *완화 방안*: `useEffect` 내부에서 `svgNode`가 바뀔 때마다 리턴하는 cleanup 함수 `svgNode.removeEventListener("wheel", onWheel)`를 명확히 구현한다. 의존성 배열에 `[svgNode]`를 명시하여 노드가 null이 되거나 변경될 때 이전 노드의 리스너가 유실 없이 완전히 해제되도록 보장한다.
- **위험 2: 한글명과 종목코드를 동시 검색할 때 후보(candidate) 리스트 내 동일 종목 중복 유입**
  - *완화 방안*: `search` 로직 내에서 매칭된 entry의 중복 여부를 감지할 수 있도록 `seen_ids = set()`과 같은 중복 방지 셋을 사용하여 결과 리스트를 필터링한다. 또한 prefix 매치와 substring 매치의 수집 시점에 모두 이 중복 방지 필터를 통과하게 한다.
- **위험 3: KRX CSV 파싱 시 비정상 에러 응답(HTML/LOGOUT 등) 유입으로 인한 파서 크래시**
  - *완화 방안*: CSV 첫 라인 파싱 이전에 `text.strip().startswith("<")` 또는 `"LOGOUT" in text.upper()` 검사를 철저히 확인하고, `next(header_reader, None)`의 None 안전 체크 및 예외 발생 시 `Exception`을 캐치해 빈 리스트를 안전하게 리턴하고 로그를 찍는 방어적 로직을 파서 내부에 구현한다.

## 호환성 검토
- **보존해야 할 API 및 타입 시그니처**: `/api/search/autocomplete`, `/api/stocks/{symbol}/detail`, `/api/stocks/{symbol}/chart` 경로 및 반환 타입(SearchResponse 등), 8개 차트 기간 옵션.
- **하위 호환성 위험 여부**: 없음. 신규 helper export 및 UI GRID 라인, 이벤트 리바인딩, 검색 로직 개선은 모두 기존 명세를 침해하지 않고 기존 테스트를 깨뜨리지 않는 호환성 친화적인 변경이다.

## 새 의존성
- 없음.

## 테스트 전략
- **프론트엔드 테스트**:
  - `StockChart.test.tsx`:
    - `sampleIndices` 단위 테스트 (다양한 데이터 길이 및 나누기 케이스 검증).
    - `StockChart` 렌더링 시 세로 grid선 및 거래량 baseline 존재 여부 확인.
    - **이벤트 복구 검증**: `StockChart`를 `isLoading=true`로 렌더링한 후 `isLoading=false`와 mockChart 데이터로 리렌더링(re-render)했을 때, wheel 이벤트를 dispatch하여 미니맵이 다시 마운트 및 렌더링되는지 확인.
  - `SearchTab.test.tsx`:
    - 한국주식 카테고리에서 "삼성" 또는 "005930" 입력 시 디바운스 후 `/api/search/autocomplete`가 호출되고 후보 dropdown이 렌더링되는지 연동 테스트 보강.
- **백엔드 테스트**:
  - `test_krx_provider.py`:
    - BOM 및 공백이 포함된 CSV 헤더 fixture를 파싱했을 때 데이터가 온전히 복구되는지 검증.
    - 비정상/에러 응답 HTML이 파서에 인입되었을 때 크래시 없이 빈 리스트를 반환하는지 검증.
  - `test_search_service.py`:
    - 한국 카테고리에서 종목코드("005930")와 종목명("삼성전자") 검색 시 모두 올바른 검색 후보가 반환되는지 확인.
    - 동일 검색어에 대해 중복된 후보가 결과에 중복해서 삽입되지 않는지 검증.

## 롤백 / 복구 방향
- 데이터베이스 마이그레이션이나 영구 변경이 없으므로, 비상 시 git commit을 리버트하여 즉시 복구 가능하다.
- 검색 디버깅 로직과 차트 이벤트 복구 로직이 각각의 프론트엔드/백엔드 레이어로 깔끔히 분리되어 있어, 특정 부분에 이슈가 발견될 경우 개별 롤백이 용이하다.

## 실행 승인
- risk_level: medium
- human_gate_required: true
- human_gate_reason: 사용자에게 직접 노출되는 차트 렌더링 UX 및 한국 주식 검색 디버깅과 리바인딩 이벤트를 다루며 여러 프론트/백 파일의 변경을 요하므로 사람 승인이 필요하다.
- approval_required_before_develop: true

## 스펙 모호점 처리
- 없으며, `defaults_mode: true`에 근거해 차트 grid선 및 한글/종목코드 매칭의 세부 동작을 설계했다.

## Git 기준점
- base_commit: e0848aaa1f97a6913e79313c33836ee1ec8ac837
- diff_base_command: `git diff e0848aaa1f97a6913e79313c33836ee1ec8ac837 -- src tests`

## 단계 결과
- status: PASS
- next_stage: 02_develop
- human_gate_required: true
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/04-project-chart-compare-with-benchmark/01_plan.md
- changed_files:
  - .ai/features/04-project-chart-compare-with-benchmark/01_plan.md
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "plan: detail chart grid and recovery of event listeners after loading"
- model_mismatch: false
- actual_model: Antigravity
