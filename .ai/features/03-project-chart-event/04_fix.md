# 04_fix - 03-project-chart-event

작성: Claude Sonnet 4.6
일시: 2026-06-04

## 입력으로 처리한 지적
- 03_review.md must_fix: 없음 (BLOCKER 및 MAJOR 해당 사항 없음)
- 03_review.md should_consider:
  - `Math.min(...array)` 및 `Math.max(...array)` 사용 부분의 Call Stack Overflow 방어 조치 (MINOR)
- 03_review.md optional:
  - `computeZoomRange` 내 `deltaY === 0` 조건 방어 처리 (NIT)
- 05_verify.md 실패 항목: 없음 (05_verify.md 미존재)
- 05_verify.md가 추가한 테스트 파일: 없음

---

## 수용한 항목

### 항목 1
- 출처: 03_review
- severity: MINOR
- 지적 내용 요약: `Math.max(...array)` / `Math.min(...array)` 스프레드 방식은 배열 크기가 2500개 이상(10Y 일봉)일 때 Call Stack Overflow를 유발할 위험이 있음
- 수정한 파일과 변경 내용:
  - `src/frontend/src/services/chartHelpers.ts` (buildMinimapPath 함수)
    - `Math.min(...closes)` → `closes.reduce((m, v) => (v < m ? v : m), closes[0])`
    - `Math.max(...closes)` → `closes.reduce((m, v) => (v > m ? v : m), closes[0])`
  - `src/frontend/src/components/StockChart.tsx` (Price scale / Volume scale 섹션)
    - `Math.max(...highs)` → `highs.reduce((m, v) => (v > m ? v : m), highs[0])`
    - `Math.min(...lows)` → `lows.reduce((m, v) => (v < m ? v : m), lows[0])`
    - `Math.max(...vols, 1)` → `Math.max(vols.reduce((m, v) => (v > m ? v : m), 0), 1)`
- 왜 수용했는가: 10Y 구간 일봉 데이터는 ~2500개로 JavaScript 엔진의 스택 한도를 초과할 수 있는 실제 위험이다. `reduce` 방식은 O(n) 루프로 동일한 결과를 안전하게 계산하며 기존 동작을 유지한다.

### 항목 2
- 출처: 03_review
- severity: NIT
- 지적 내용 요약: `computeZoomRange`에서 `deltaY === 0`일 때 `factor = 1 / 1.15`로 판정되어 의도치 않은 줌인 발생 가능
- 수정한 파일과 변경 내용:
  - `src/frontend/src/services/chartHelpers.ts` (computeZoomRange 함수 초반)
    - `if (total === 0) return ...` 직후에 `if (deltaY === 0) return { start, end };` 추가
- 왜 수용했는가: 단 한 줄의 방어 코드로 엣지 케이스를 안전하게 처리할 수 있고, 기존 동작에 영향이 없다. NIT이지만 실제 wheel 이벤트 환경에서 deltaY=0인 경우가 생길 수 있으므로 선제적으로 수용한다.

---

## 거부한 항목
- 없음

## 보류한 항목
- 없음

## 사용자 판단 요청 항목
- 없음

---

## 추가 변경 사항
- 없음 (리뷰 지적 범위 내에서만 수정)

---

## 호환성 준수
- 보존한 기존 인터페이스/데이터 포맷/설정 키:
  - `buildMinimapPath`, `computeZoomRange` 함수 시그니처 불변
  - `StockChart` 컴포넌트 props 인터페이스 불변
  - 기존 렌더링 출력값 동일 (동일 입력 → 동일 min/max 결과)
- 호환성 유지 전략 반영 내용: 순수 함수 내부 구현만 변경, 외부 인터페이스 불변
- breaking change 발생 여부: 없음
- 리뷰/검증 범위를 넘어선 호환성 영향: 없음

---

## 변경 파일 목록
- `src/frontend/src/services/chartHelpers.ts`: computeZoomRange에 deltaY===0 early return 추가; buildMinimapPath의 Math.min/max(...spread) → reduce 방식으로 교체
- `src/frontend/src/components/StockChart.tsx`: Price scale의 Math.max/min(...spread) → reduce; Volume scale의 Math.max(...vols, 1) → reduce+Math.max 방식으로 교체

---

## 테스트
- 실행한 테스트 명령:
  - `python -m pytest tests/backend/ -x -q`
  - `npx --prefix src/frontend vitest run --config src/frontend/vite.config.ts tests/frontend/`
- 결과:
  - Backend: 54 passed (0 failed)
  - Frontend: 53 passed (0 failed)
- 추가한 테스트: 없음 (기존 테스트가 변경된 함수를 충분히 커버함)

---

## Git 정보
- fix_base_commit: ce2d7595c1c540841251883a7dbc4f16254fd672
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 03-project-chart-event[20260604-234953][04_fix]
- no_code_changes: false
- no_code_changes_reason:
- pre_commit_diff_command: git diff ce2d7595c1c540841251883a7dbc4f16254fd672
- changed_files:
  - src/frontend/src/services/chartHelpers.ts
  - src/frontend/src/components/StockChart.tsx
- harness_commit_blocking_reason: 없음

---

## 단계 결과
- status: PASS
- next_stage: 05_verify
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low
- produced_files:
  - .ai/features/03-project-chart-event/04_fix.md
- changed_files:
  - src/frontend/src/services/chartHelpers.ts
  - src/frontend/src/components/StockChart.tsx
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 03-project-chart-event[20260604-234953][04_fix]
- test_commands:
  - python -m pytest tests/backend/ -x -q
  - npx --prefix src/frontend vitest run --config src/frontend/vite.config.ts tests/frontend/
- model_mismatch: false
- actual_model: Claude Sonnet 4.6
