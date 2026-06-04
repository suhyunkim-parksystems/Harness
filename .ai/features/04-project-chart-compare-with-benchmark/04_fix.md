# 04_fix - 04-project-chart-compare-with-benchmark

작성: Claude (claude-opus-4-8)
일시: 2026-06-05

## 입력으로 처리한 지적
- 03_review.md must_fix:
  - 없음. (BLOCKER 0 / MAJOR 0)
- 03_review.md should_consider:
  - 없음. (MINOR 0)
- 03_review.md optional:
  - NIT: `StockChart.tsx`의 하드코딩된 그리드/거래량 보조선 색상(`#eef2f6`, `#f1f5f9`, `#e4ebf1`)을 다크 모드/테마 대응을 위해 CSS 변수(예: `var(--chart-grid-line)`)로 토큰화하는 방안 검토.
- 05_verify.md 실패 항목:
  - 해당 없음. 05_verify 단계는 아직 실행되지 않았고 `.ai/features/04-project-chart-compare-with-benchmark/05_verify.md`가 존재하지 않는다.
- 05_verify.md가 추가한 테스트 파일:
  - 해당 없음.
- 하네스 검증 결과(`.ai/runs/04-project-chart-compare-with-benchmark/verification/latest.json`):
  - 파일 없음. 처리 대상 없음.

## 수용한 항목
- 없음. (수용해 코드를 수정한 항목 없음)

## 거부한 항목
- 없음.

## 보류한 항목
- 출처: 03_review (optional)
- severity: NIT
- 지적 내용 요약: `StockChart.tsx`의 그리드 및 거래량 보조선 색상(`#eef2f6`, `#f1f5f9`, `#e4ebf1`)을 인라인 stroke 대신 CSS 변수로 토큰화하여 추후 테마/다크 모드 대응력을 높이자는 제안.
- 보류 사유:
  1. 테마/다크 모드는 00_spec.md의 "이번 범위에서 제외하는 것"에 직접 포함되지는 않았으나, CSS 변수 토큰화는 오직 다크 모드/테마라는 미도입 기능을 위한 선제적 추상화이다. 현재 스펙(차트 가독성 GRID 추가, 한국주식 검색 복구, 기간 변경 후 차트 이벤트 복구)의 검증 기준 어디에도 테마 토큰화 요구가 없다.
  2. 02_dev.md에서 "grid 색상/간격은 인라인 상수로, 추후 테마 토큰화 시 `App.css`/디자인 토큰으로 분리"하는 것을 이번 범위 밖의 의도적 결정으로 명시했고, 03_review도 이를 `optional`(must_fix/should_consider 아님)로 분류해 현 결정이 여전히 유효하다.
  3. 프로젝트 계약의 "요청 범위를 벗어난 리팩터링은 하지 않는다" 원칙에 부합한다. 실제 소비자(테마 스위처)가 없는 상태에서의 토큰화는 불필요한 간접화를 더한다.
- 별도 처리 제안: 추후 다크 모드/테마 기능을 별도 feature로 착수할 때, 그리드 색상뿐 아니라 캔들 상승/하락 색상, 거래량 막대 색상, 축 라벨 색상까지 일괄적으로 `App.css`의 디자인 토큰(CSS 변수)으로 추출하고, 관련 테스트 기대값도 함께 토큰 기반으로 갱신한다.

## 사용자 판단 요청 항목
- 없음. `defaults_mode: true`, `interactive_mode: false`에 따라 권장 기본값으로 보류 판단을 확정했다. (NEEDS_USER 사유인 자격증명/안전/파괴적 작업/불가능에 해당하지 않음)

## 추가 변경 사항
- 없음. 리뷰가 BLOCKER/MAJOR/MINOR 0건 PASS이고 유일한 optional NIT을 보류했으므로 프로덕션 코드/테스트 변경이 발생하지 않았다.

## 보류 항목을 코드 변경 없이 처리한 추가 근거 (회귀 위험)
- 기존 테스트 `tests/frontend/StockChart.test.tsx:400`이 그리드선을 `l.getAttribute("stroke") === "#eef2f6"`로 직접 단언한다. NIT을 수용해 색상을 `var(--chart-grid-line)`로 토큰화하면 이 기존 테스트 기대값이 깨진다.
- 프로젝트 계약상 "기존 테스트 기대값을 깨뜨리는 변경은 명시적으로 기록하고 사용자 승인을 받는다"이며, 본 단계 프리셋도 "리뷰/검증 범위를 넘어 기존 테스트 기대값을 바꿔야 하면 사용자 판단 요청으로 멈춘다"고 규정한다. optional NIT 하나를 위해 기존 테스트를 변경하면서까지 진행할 근거가 약하므로 보류가 타당하다.

## 호환성 준수
- 보존한 기존 인터페이스/데이터 포맷/설정 키: 코드 변경이 없으므로 02_dev에서 보존한 모든 인터페이스가 그대로 유지된다. (`_parse_master_csv(text, asset_type)`, `SearchService.search(query, category)`, `StockChartProps`, `chartHelpers` 기존 export, `/api/search/autocomplete`·`/api/stocks/{symbol}/detail`·`/api/stocks/{symbol}/chart` 경로, 8개 차트 기간, 한/미 상승·하락 색상 규칙)
- 호환성 유지 전략 반영 내용: 추가 변경이 없어 01_plan.md의 호환성 친화적(가산적) 변경 상태가 그대로 보존된다.
- breaking change 발생 여부: 없음
- 리뷰/검증 범위를 넘어선 호환성 영향: 없음

## 변경 파일 목록
- 없음. (프로덕션 코드 및 테스트 변경 없음. 본 단계 산출물 `04_fix.md`, `04_fix.result.json`만 신규 작성)

## 테스트
- 실행한 테스트 명령:
  - `python -m pytest tests/backend/ -q`
  - `cd src/frontend && npm test` (vitest run)
  - `cd src/frontend && npx tsc -b`
- 결과:
  - 백엔드 pytest: 61 passed, 1 warning (starlette PendingDeprecationWarning, 기능 무관).
  - 프론트엔드 vitest: 4 files / 63 passed (StockChart 40, SearchTab 17, App 3, useMarketSummary 3).
  - TypeScript 빌드: exit 0 (타입 에러 없음).
- 추가한 테스트: 없음. (리뷰/검증에서 누락 테스트 지적이 없었고, 코드 변경도 없음)
- 외부 네트워크 의존: 없음. 기존 테스트가 KRX/Yahoo/NASDAQ 호출을 mock/fixture로 격리하고 있다.

## Git 정보
- fix_base_commit: 67a34b8dab9bd6e53f2efea5bb039c5eb7652661 (현재 HEAD = 03_review stage 커밋)
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 04-project-chart-compare-with-benchmark[20260605-010551][04_fix]
- no_code_changes: true
- no_code_changes_reason: 03_review가 BLOCKER/MAJOR/MINOR 0건 PASS이며 유일한 optional NIT(그리드 색상 CSS 토큰화)을 보류했고, 05_verify 실패/하네스 검증 실패 입력이 존재하지 않아 수정할 코드가 없다.
- pre_commit_diff_command: git diff 67a34b8dab9bd6e53f2efea5bb039c5eb7652661 -- src tests
- changed_files:
  - .ai/features/04-project-chart-compare-with-benchmark/04_fix.md
  - .ai/features/04-project-chart-compare-with-benchmark/04_fix.result.json
- harness_commit_blocking_reason: 없음

## 단계 결과
- status: PASS
- next_stage: 05_verify
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low
- produced_files:
  - .ai/features/04-project-chart-compare-with-benchmark/04_fix.md
  - .ai/features/04-project-chart-compare-with-benchmark/04_fix.result.json
- changed_files:
  - .ai/features/04-project-chart-compare-with-benchmark/04_fix.md
  - .ai/features/04-project-chart-compare-with-benchmark/04_fix.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 04-project-chart-compare-with-benchmark[20260605-010551][04_fix]
- test_commands:
  - python -m pytest tests/backend/ -q
  - cd src/frontend && npm test
  - cd src/frontend && npx tsc -b
- model_mismatch: false
- actual_model: claude-opus-4-8
