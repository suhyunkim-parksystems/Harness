# 03_review - 03-project-chart-event

작성: Antigravity
일시: 2026-06-04

## 리뷰 대상
- `src/backend/app/models/market.py`
- `src/backend/app/providers/yahoo_finance.py`
- `src/frontend/src/types/market.ts`
- `src/frontend/src/services/chartHelpers.ts`
- `src/frontend/src/components/StockChart.tsx`
- `src/frontend/src/App.css`
- `tests/backend/test_yahoo_finance_provider.py`
- `tests/backend/test_routes.py`
- `tests/frontend/StockChart.test.tsx`
- base_commit: 801d18480eda78bb6b57ecc2a362abea887e48de
- review_target_commit: 2a00545bb85b0476cb6d79ba52647ab1ce92e4e9
- diff_command: `git diff 801d18480eda78bb6b57ecc2a362abea887e48de..2a00545bb85b0476cb6d79ba52647ab1ce92e4e9`
- diff_range: `801d18480eda78bb6b57ecc2a362abea887e48de..2a00545bb85b0476cb6d79ba52647ab1ce92e4e9`

## 지적 사항 요약
- BLOCKER: 0개
- MAJOR: 0개
- MINOR: 1개
- NIT: 1개

## 코드 품질
- severity: MINOR
- 지적 사항: `Math.max(...array)` 및 `Math.min(...array)` 사용 시 대규모 배열에 대한 Call Stack Overflow 위험
- 해당 코드 위치: 
  - [chartHelpers.ts#L62-L63](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/services/chartHelpers.ts#L62-L63)
  - [StockChart.tsx#L191-L192](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StockChart.tsx#L191-L192)
  - [StockChart.tsx#L204](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StockChart.tsx#L204)
- 왜 문제인지: 
  - `10Y`와 같은 장기 차트 조회 시 일봉 데이터 개수가 약 2500개 이상으로 증가합니다. JavaScript 스프레드 연산자(`...`)를 인수로 전달하면 JavaScript 엔진의 Call Stack 크기를 초과하여 브라우저나 테스트 환경에 따라 `Maximum call stack size exceeded` 오류를 유발할 위험이 있습니다.
- 어떻게 개선해야 하는지:
  - `Math.min(...closes)` 대신 일반적인 `reduce` 또는 단순 루프를 사용하여 최댓값/최솟값을 안전하게 구하도록 변경할 것을 권장합니다.
  - 예시: `const minC = closes.reduce((m, v) => v < m ? v : m, closes[0]);`

- severity: NIT
- 지적 사항: `computeZoomRange` 내 `deltaY === 0`일 때의 방어 로직 부재
- 해당 코드 위치:
  - [chartHelpers.ts#L26](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/services/chartHelpers.ts#L26)
- 왜 문제인지:
  - 브라우저 wheel 이벤트의 `deltaY`가 `0`인 경우에도 `factor = 1 / 1.15`로 판정되어 의도치 않은 줌인 동작이 발생하게 됩니다. 실제 환경에서는 `deltaY`가 `0`인 상태로 이벤트가 전달되는 경우가 극히 드물어 버그로 이어지지는 않으나 안전한 제어가 필요합니다.
- 어떻게 개선해야 하는지:
  - `deltaY === 0`일 경우 줌 연산을 생략하고 기존 범위를 그대로 반환하도록 방어 처리합니다.
  - 예시: `if (deltaY === 0) return { start, end };`

## 구조 및 가독성
- severity: NIT
- 지적 사항: 없음 (매우 우수)
- 해당 코드 위치: -
- 왜 문제인지: -
- 어떻게 개선해야 하는지:
  - 복잡한 줌/팬 수식과 문자열 포맷팅, 미니맵 패스 생성 로직을 `chartHelpers.ts` 서비스 레이어로 깔끔하게 분리하여 컴포넌트 내부 가독성이 크게 향상되었습니다.

## 계획 대비 구현 일치성
- severity: NIT
- 01_plan.md 대비 일치/불일치 항목: 일치
- 구체적 차이: 없음. 계획에 정의된 파일 변경 범위 및 테스트 전략을 충실히 준수하였습니다.
- 이 차이가 문제인지, 허용 가능한지: 문제 없음.

## 호환성 / 회귀 위험
- severity: NIT
- 지적 사항: 없음 (하위 호환성 완벽 유지)
- 깨질 수 있는 기존 인터페이스/호출부/테스트: 
  - API 엔드포인트 `/api/stocks/{symbol}/chart` 및 관련 타입이 깨지지 않고 확장되었습니다.
- 개선 제안: -

## 구현 의도 타당성
- severity: NIT
- 02_dev.md에 적힌 판단에 대한 동의 또는 반론: 
  - `view = null`을 전체 범위 센티널로 사용하는 설계와 wheel 이벤트의 imperative binding 등 브라우저 호환성과 성능을 확보하기 위한 최적의 판단이 이루어졌음에 동의합니다.
- 반론 시 근거: -

## 테스트
- severity: NIT
- 누락된 테스트 케이스: 없음
- 각 케이스가 왜 필요한지:
  - 프론트엔드 비즈니스 로직(Helpers)에 대한 유닛 테스트와 `StockChart.test.tsx` 컴포넌트 통합 테스트가 빈틈없이 작성되었습니다. 휠 줌, 포인터 드래그, 기간 전환 시 초기화, 에지 케이스(단일 봉, null 데이터 등)에 이르기까지 폭넓은 유효성 검증이 통과되었습니다.

## 04_fix 입력
- must_fix:
  - 없음 (BLOCKER 및 MAJOR 해당 사항 없음)
- should_consider:
  - `Math.min(...array)` 및 `Math.max(...array)` 사용 부분의 Call Stack Overflow 방어 조치 (MINOR)
- optional:
  - `computeZoomRange` 내 `deltaY === 0` 조건 방어 처리 (NIT)

## 총평
- 전체적인 구현 품질 요약:
  백엔드와 프론트엔드 전체에 걸쳐 차트 기간 확장 및 신규 상호작용 UX(줌, 드래그 팬, 미니맵) 요구사항이 안정적이고 고도로 최적화된 방식으로 구현되었습니다. 특히 서비스 모듈 분리를 통한 가독성 증대, Pydantic을 활용한 자연스러운 유효성 검증 확장, JSDOM 한계를 고려한 꼼꼼한 모의 테스트 작성이 돋보입니다. 지적된 Call Stack Overflow 방어 사항만 04_fix 단계에서 안전하게 개선된다면 프로덕션으로 배포하기에 완벽한 코드 품질을 자랑합니다.

## 단계 결과
- status: PASS
- next_stage: 04_fix
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/03-project-chart-event/03_review.md
- changed_files:
- harness_commit_required: false
- commit_created_by_model: false
- commit_message_suggestion:
- model_mismatch: false
- actual_model: Antigravity
