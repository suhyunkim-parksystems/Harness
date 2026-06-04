# 01_plan - 03-project-chart-event

작성: Antigravity
일시: 2026-06-04

## 기능 목표
- 종목 차트에서 8개 기간(`1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`, `10Y`, `YTD`) 선택 기능을 지원하고 해당 데이터를 조회하여 렌더링합니다.
- 차트 확대/축소(마우스 휠/트랙패드), 확대 시 드래그(Pointer 이벤트)를 통한 보이는 구간 이동, 그리고 우하단 미니맵 표시를 제공하여 긴 차트 탐색 UX를 개선합니다.

## 구현 접근 방식
- **기존 SVG 확장**: 외부 차트 라이브러리 도입 대신 기존 `StockChart.tsx` 내의 순수 SVG 구조를 유지하고 확장합니다.
- **슬라이싱 기반 렌더링**: 데이터 인덱스를 이용해 줌 범위(`startIndex`, `endIndex`)를 관리하고, 보이는 영역(`visibleBars`)만 SVG 상에 렌더링하여 엘리먼트 개수를 조절하고 성능을 극대화합니다.
- **중심점 기반 줌 & 드래그 뷰포트 이동**: 휠 이벤트 시 포인터의 X축 상대 좌표를 기준으로 줌 센터를 계산하고, 포인터 드래그 시 pointer capture API를 사용해 부드럽고 끊김 없는 패닝(panning)을 구현합니다.
- **우하단 미니맵 구현**: 전체 데이터의 흐름을 표시하는 Area Path와 현재 뷰포트를 나타내는 반투명 오버레이를 포함한 컴팩트한 미니맵을 SVG 우하단 영역(Y축 레이아웃 및 볼륨 레이아웃 외부)에 줌인 상태에만 렌더링합니다.
- **동적 축 계산**: visible range의 가격/거래량 최댓값 및 최솟값을 기반으로 Y축 눈금과 캔들/볼륨 높이를 동적 재계산하여 확대 시 미세 변동도 명확히 드러나도록 구현합니다.

## 검토한 대안
- **대안 1: Recharts 또는 Chart.js 등 외부 라이브러리 도입**
  - 장점: 줌/팬/미니맵 기능이 내장되어 있어 구현이 수월할 수 있음.
  - 단점: 라이브러리 의존성 추가, 번들 크기 증가, 기존 프로젝트의 커스텀 스타일 및 한/미 마켓 상승/하락 색상 로직 등 호환성 통합 공수 큼.
  - 채택하지 않은 이유: 이미 순수 SVG로 간단하고 완결성 있게 차트가 작성되어 있어, 슬라이싱 연산과 React 상태값 제어만으로 줌/팬/미니맵을 직접 구현하는 것이 더 가볍고 결함 위험이 낮음.
- **대안 2: 서버 사이드 줌/팬 처리 (새로운 API 엔드포인트 또는 기간 세분화 요청)**
  - 장점: 프론트엔드 연산 및 메모리 부담이 적음.
  - 단점: 확대/축소나 드래그할 때마다 네트워크 요청이 발생하여 심각한 UX 버벅임 초래.
  - 채택하지 않은 이유: 10년 일봉 데이터를 전부 들고 있더라도 약 2500개 수준이므로 클라이언트 메모리에서 즉시 줌/팬을 연산하는 것이 즉각적이고 부드러운 반응성을 보여줄 수 있어 훨씬 우수함.

## 변경 파일 계획
- `src/backend/app/models/market.py` (수정): `ChartPeriod` Literal 정의에 `"3y", "5y", "10y", "ytd"` 추가.
- `src/backend/app/providers/yahoo_finance.py` (수정): `_PERIOD_PARAMS` 매핑 딕셔너리에 `3y`, `5y`, `10y`, `ytd`에 해당하는 yahoo finance 파라미터 매핑(`3y`, `5y`, `10y`, `ytd`) 추가.
- `src/frontend/src/types/market.ts` (수정): `ChartPeriod` 타입 정의에 `"3y" | "5y" | "10y" | "ytd"` 추가.
- `src/frontend/src/components/StockChart.tsx` (수정):
  - `PERIODS` 상수 배열에 신규 기간 추가.
  - `startIndex`, `endIndex` 상태 및 `isDragging`, `dragStartX`, `dragStartRange` 드래그 상태 추가.
  - `useEffect`로 `data` 및 `period` 변경 시 줌 상태 초기화.
  - SVG 휠 이벤트 리스너(imperative binding to use `{ passive: false }` for preventDefault)와 `onPointerDown`, `onPointerMove`, `onPointerUp` 이벤트 처리 핸들러 추가.
  - visible range를 기준으로 가격/거래량 스케일 동적 재계산.
  - 우하단 영역 미니맵(Area chart + 뷰포트 오버레이) SVG 컴포넌트 추가 및 줌인 상태 조건부 렌더링.
- `src/frontend/src/App.css` (수정):
  - `.chart-period-selector`에 `flex-wrap: wrap`을 추가하여 모바일/작은 화면 겹침 방지.
  - 드래그 동작 시 마우스 커서 스타일(`.stock-chart-svg`에 `user-select: none` 추가하여 텍스트 선택 방지) 추가.
  - 미니맵 스타일 및 기간 버튼 스타일 점검.
- `tests/backend/test_yahoo_finance_provider.py` (수정): 신규 기간 매핑 테스트 추가.
- `tests/backend/test_routes.py` (수정): 차트 API 신규 기간 쿼리 파라미터 유효성 검증 테스트 추가.
- `tests/frontend/StockChart.test.tsx` (신규):
  - 8개 기간 버튼 및 액티브 스타일 검증 (Unit)
  - 휠 이벤트 디스패치를 통한 줌인/줌아웃 시 `startIndex`/`endIndex` 상태 변화 검증 (Unit)
  - 드래그 동작(PointerDown -> PointerMove -> PointerUp)을 모사하여 뷰포트 이동과 경계값 클램핑 검증 (Unit)
  - 줌 상태에 따른 미니맵 표시 여부 및 뷰포트 사각형 위치 연산 검증 (Unit)

## 데이터 / 제어 흐름
- **API 호출 및 조회**:
  `StockChart` 기간 선택 버튼 클릭 -> `onPeriodChange(newPeriod)` -> `useStockDetail` 훅에서 감지 -> `fetchStockChart(symbol, category, newPeriod)` 비동기 호출 -> 백엔드 `/api/stocks/{symbol}/chart?period=...` -> Yahoo Finance API 호출 -> 파싱 후 `ChartResponse` 반환 -> 훅 상태 변경 -> `StockChart`에 새로운 `data` 전달.
- **줌/팬 로컬 상태 제어**:
  1. `data`/`period` 변경 시 `startIndex = 0`, `endIndex = data.bars.length - 1`로 초기화.
  2. 휠 스크롤 발생 -> `handleWheel` -> 마우스 위치 `t` 계산 -> 새로운 `numVisible` 결정 -> `startIndex`/`endIndex` 업데이트.
  3. 드래그 발생 -> Pointer Capture 실행 -> 드래그 거리 `diffX` 만큼 인덱스 오프셋 `shift` 계산 -> `startIndex`/`endIndex` 업데이트.
  4. 렌더링 -> `validBars.slice(startIndex, endIndex + 1)`로 `visibleBars` 추출 -> `visibleBars` 기준으로 가격축/거래량축 최대/최소 계산 -> 가격/거래량/날짜축 SVG 렌더링.
  5. 미니맵 -> 줌인(`visibleBars.length < validBars.length`) 상태인 경우에만 렌더링 -> `validBars`(전체) 기준 Area 차트 렌더링 + `[startIndex, endIndex]` 뷰포트 오버레이 박스 렌더링.

## 구현 단계 분할
1. **단계 1: 백엔드 기간 도메인 확장 및 테스트**
   - 파일: `src/backend/app/models/market.py`, `src/backend/app/providers/yahoo_finance.py`
   - 내용: `ChartPeriod` Literal에 `3y`, `5y`, `10y`, `ytd` 추가 및 Yahoo Finance 파라미터 매핑 등록.
   - 완료 기준: 백엔드 단위 테스트 `pytest tests/backend` 통과.
2. **단계 2: 프론트엔드 타입 확장 및 줌/팬 상태 제어 구현**
   - 파일: `src/frontend/src/types/market.ts`, `src/frontend/src/components/StockChart.tsx`
   - 내용: `ChartPeriod` 타입 확장, 기간 버튼 추가, `startIndex`/`endIndex` 상태 관리 및 이벤트 핸들러(Wheel, Pointer) 구현.
   - 완료 기준: 줌인/줌아웃 시 렌더링 캔들 개수가 변경되며, 드래그 시 좌우 이동이 가능하고 경계를 벗어나지 않음.
3. **단계 3: 줌 상태에 따른 축 동적 스케일링 및 날짜 포맷 적용**
   - 파일: `src/frontend/src/components/StockChart.tsx`
   - 내용: `visibleBars` 기준으로 가격/거래량 스케일 동적 갱신, 장기 기간 날짜 라벨 연도 표기 처리.
   - 완료 기준: 확대 시 봉들의 높이와 Y축 눈금이 보이는 구간 가격에 맞게 자동 리사이징됨.
4. **단계 4: 미니맵 컴포넌트 추가 및 줌 조건 연동**
   - 파일: `src/frontend/src/components/StockChart.tsx`, `src/frontend/src/App.css`
   - 내용: 우하단 고정 크기 미니맵(Area chart + viewport rect) 구현, CSS 스타일 보완 및 모바일 반응형 처리.
   - 완료 기준: 줌인 시 미니맵이 우하단에 자연스럽게 표시되며, 전체 흐름과 현재 위치 오버레이가 알맞게 보임.
5. **단계 5: 종합 테스트 작성 및 검증**
   - 파일: `tests/frontend/StockChart.test.tsx` 신규 생성 및 기존 관련 테스트 수정.
   - 완료 기준: `npm run build` 및 프론트/백엔드 테스트 모두 PASS.

## 위험 구간
- **위험 항목**: 10년치 일봉 데이터(약 2500개)가 있을 때 줌아웃 상태에서 SVG 캔들을 전부 렌더링하면 렌더링 성능이 저하될 우려가 있음.
- **완화 방안**: 확대된 상태에서는 보이는 캔들만 부분 렌더링하여 엘리먼트 개수를 크게 절약합니다. 또한, 미니맵은 개별 캔들을 모두 그리는 대신 단 하나의 SVG `<path>` 요소로 전체 추세를 채워진 영역(Area)으로 그려 연산량과 렌더링 비용을 최소화합니다.

## 호환성 검토
- **보존해야 할 기존 인터페이스**: 기존 API 경로 `/api/stocks/{symbol}/chart`, 응답 타입 `ChartResponse`, 기존 `StockChart` Props 시그니처.
- **영향받는 호출부/사용자 흐름**: 종목 상세 정보 조회 탭에서의 기간 선택 동작.
- **하위 호환성 위험**: 없음. 기간 문자열 추가는 하위 호환적인 확장입니다.
- **호환성 유지 전략**: 새로운 기간 파라미터를 추가하되 기본값은 `1m`로 설정하여 기존 클라이언트가 API를 호출할 때 오동작이 없도록 합니다.
- **breaking change 필요 여부**: 없음.

## 새 의존성
- 없음

## 테스트 전략
- **백엔드**:
  - `test_yahoo_finance_provider.py`: `3y`, `5y`, `10y`, `ytd` 매핑 확인 (Unit)
  - `test_routes.py`: 신규 기간들을 사용한 API 요청이 422 Validation Error 없이 정상 응답(Mock 데이터)하는지 확인 (Integration)
- **프론트엔드**:
  - `StockChart.test.tsx`:
    - 8개 기간 버튼 및 액티브 스타일 검증 (Unit)
    - 휠 이벤트 디스패치를 통한 줌인/줌아웃 시 `startIndex`/`endIndex` 상태 변화 검증 (Unit)
    - 드래그 동작(PointerDown -> PointerMove -> PointerUp)을 모사하여 뷰포트 이동과 경계값 클램핑 검증 (Unit)
    - 줌 상태에 따른 미니맵 표시 여부 및 뷰포트 사각형 위치 연산 검증 (Unit)

## 롤백 / 복구 방향
- Git Commit은 하네스가 관리하므로 변경이 오동작하는 경우 하네스의 롤백 절차 또는 이전 커밋 시점 `1d5509a13bb95bf6609e6225f222cc51ea2e2761`으로 되돌림.
- 로컬 DB 상태 변경 등 비가역적 스키마 변경이 없으므로 단순 파일 롤백으로 100% 원복 가능.

## 실행 승인
- risk_level: medium
- human_gate_required: true
- human_gate_reason: 사용자 경험 및 차트 인터랙션 UX(줌, 드래그, 미니맵)에 큰 변경이 있고, 다수의 소스코드 파일들이 연동되므로 PASS 상태에서 검증 게이트를 유지합니다.
- approval_required_before_develop: true

## 스펙 모호점 처리
- **줌 최소 봉 개수**: 확대 최대치를 명시적으로 제한하기 위해 최소 표시 봉 개수를 10개 (`MIN_BARS = 10`)로 결정하여 차트가 완전히 깨지거나 보이지 않는 현상을 방지함.
- **미니맵 인터랙션**: 미니맵 영역에서의 직접 드래그 이동 요구사항은 스펙에 없으므로, 메인 차트 드래그 이동 시 미니맵 오버레이가 연동되어 표시되는 수준으로 스펙 범위를 확정함.

## Git 기준점
- base_commit: 1d5509a13bb95bf6609e6225f222cc51ea2e2761
- diff_base_command: git diff 1d5509a13bb95bf6609e6225f222cc51ea2e2761

## 사용자 확인 사항
- 추가 질문 없음 (defaults_mode: true 및 interactive_mode: false에 따라 권장 기본 옵션으로 진행함)

## 단계 결과
- status: PASS
- next_stage: 02_develop
- human_gate_required: true
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/03-project-chart-event/01_plan.md
  - .ai/features/03-project-chart-event/01_plan.result.json
- changed_files:
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "plan: project chart zoom, pan and minimap support"
- model_mismatch: false
- actual_model: Antigravity
