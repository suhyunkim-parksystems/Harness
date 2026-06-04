# Local Harness Prompt

## Harness Context
- feature_name: 04-project-chart-compare-with-benchmark
- pipeline_mode: full
- stage: 05_verify
- preferred_model: Codex
- scheduled_provider: codex
- performance: high
- output_file: .ai/features/04-project-chart-compare-with-benchmark/05_verify.md
- result_json_file: .ai/features/04-project-chart-compare-with-benchmark/05_verify.result.json
- run_state: .ai/runs/04-project-chart-compare-with-benchmark/run.json
- generated_at: 2026-06-05T01:09:30
- defaults_mode: true
- interactive_mode: false
- feature_name_locked: true

## Decision Policy
Use recommended defaults for ambiguous decisions. Do not return NEEDS_USER unless the task is impossible, unsafe, requires credentials/secrets that are not available, or would perform destructive/non-reversible actions. Record all default decisions and their rationale in the stage output.

## Manual Provider Instructions
1. The local harness is executing this prompt with the preferred model when possible.
2. Make the requested file changes directly in the repository.
3. Write the human-readable stage output file exactly at `.ai/features/04-project-chart-compare-with-benchmark/05_verify.md`.
4. Also write the machine-readable stage result JSON exactly at `.ai/features/04-project-chart-compare-with-benchmark/05_verify.result.json`.
5. Do not run `git commit`, `git reset`, `git checkout`, `git rebase`, or `git push`. The local harness owns Git history.
6. This Git ownership rule overrides any preset text that appears to ask the model to create, amend, or push commits.
7. For every successful stage, leave the working tree commit-ready and record commit intent in the stage output; the harness will create or amend the commit.
8. If `defaults_mode: true`, prefer recommended defaults over `NEEDS_USER` unless blocked by missing credentials, safety, destructive operations, or impossibility.
9. If the stage needs user input under the decision policy, write both outputs with `status: NEEDS_USER`.
10. If the stage fails, write both outputs with `status: FAIL` and a concrete blocking reason.
11. If `feature_name_locked: true`, keep the existing `feature_name` exactly as provided by the harness. Do not rename or invent a different feature slug.
12. End with a concise summary; the harness will inspect files, not your final message.

## Machine Result JSON Contract
The harness reads `.ai/features/04-project-chart-compare-with-benchmark/05_verify.result.json` first. Keep the `## 단계 결과` section in `.ai/features/04-project-chart-compare-with-benchmark/05_verify.md` for humans, but write this JSON file for the harness.

Required JSON keys:
- status: "PASS", "FAIL", "SKIPPED", or "NEEDS_USER"
- next_stage: next stage id. This is not the final pipeline stage; do not use "done". Use `06_document` unless the preset explicitly routes to another valid stage.
- human_gate_required: true or false
- blocking_reason: string, use "" when there is no blocker

For NEEDS_USER in interactive_mode, also include `questions`: an array of question objects.
Each question object must include:
- id: stable snake_case identifier
- type: "choice", "yes_no", or "text"
- question: user-facing question text
- options: for "choice" only, either strings or objects with `id`, `label`, and optional `description`
- default: optional default option/value

Include any extra stage fields that the preset asks for, such as `risk_level`, `harness_commit_required`, `changed_files`, `verification_summary`, or `fix_inputs`.
For PASS or FAIL stages, also include `history_notes` with these arrays when known: `implemented`, `risks`, `future_improvements`, `decisions`, and `unresolved_items`. Use empty arrays for categories with nothing to record. Prefer Korean text for human-facing titles, descriptions, reasons, risks, and decisions when the project context is Korean.

## Project Contract
Source: .ai/project_contract.md

# Project Contract

## Hard Rules
- 모델은 Git commit, amend, reset, checkout, rebase, push를 직접 실행하지 않는다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 요청 범위를 벗어난 리팩터링, 의존성 추가, 파일 이동은 하지 않는다.
- 기존 코드와의 하위 호환성을 우선한다. 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 깨뜨리는 변경은 명시적으로 기록하고 사용자 승인을 받는다.

## Project Layout
- 프로덕션 코드는 루트 `src/` 하위에 둔다.
- 테스트 코드는 루트 `tests/` 하위에 둔다.
- 새 테스트 파일을 `src/` 하위에 만들지 않는다.

## Architecture
- 외부 연동 어댑터는 실패를 정상 응답으로 숨기지 말고, 서비스 레이어가 fallback과 최종 상태를 결정하도록 오류를 전달한다.
- 연속 비동기 요청은 늦게 도착한 이전 응답이 현재 상태를 덮어쓰지 않도록 요청 식별자나 취소 처리로 검증한다.

## Code Style
- 새 코드는 같은 디렉터리의 기존 패턴, 네이밍, 파일 구조를 우선 따른다.
- 프로젝트에 이미 명확한 네이밍 관례가 없으면 변수와 함수는 camelCase를 기본으로 한다.
- 함수 이름은 가능하면 동사 또는 동사구로 시작한다. 예: `loadConfig`, `validateInput`, `renderItem`.
- Boolean 값과 Boolean 반환 함수는 `is`, `has`, `can`, `should` 같은 의미 있는 접두사를 사용한다.
- 이벤트 핸들러는 `handle` 또는 기존 프로젝트의 이벤트 네이밍 패턴을 따른다.
- 값을 변환하는 함수는 `to`, `from`, `parse`, `format`, `normalize`처럼 변환 의도가 드러나는 이름을 사용한다.
- 데이터를 가져오는 함수는 `get`, `load`, `fetch`, `read` 중 실제 동작에 맞는 동사를 사용한다.
- 부수효과가 있는 함수는 `save`, `write`, `update`, `delete`, `send`, `create`처럼 변경 의도가 드러나는 동사를 사용한다.
- 구현이 30줄을 넘어가면 함수나 작은 단위로 분리한다.
- 서비스레이어를 두어서 유지보수를 좋게하라.

## Data
- 외부 데이터는 내부 로직이나 UI에 전달하기 전에 수신 경계에서 정렬, 형식 변환, null·빈 값 방어를 수행한다.

## Reliability
- 외부 입력, 파일, 네트워크, 프로세스 실행 결과는 실패 가능성을 명시적으로 처리한다.
- 외부 연동 실패는 호출 단위로 격리하고, 가능한 경우 부분 실패 상태로 응답해 전체 기능 중단을 피한다.
- 외부 데이터 조회는 캐시나 대체 경로를 활용해 일시적 실패에도 가능한 범위의 응답을 유지한다.
- 자동화 스크립트는 백그라운드 프로세스 종료 시 실행 시점에 기록한 PID를 우선 사용한다.

## Testing
- 테스트는 외부 네트워크에 의존하지 않으며, 외부 HTTP 호출은 Mock 또는 Fixture로 격리한다.


## Original User Request
차트만 덩그러니 있어서 뭐가 뭔지 잘 모르겠네. GRID를 추가해줘. 그리고 한국주식 종목 검색에 뭔가 문제가있는거같아. 자동완성이 안되고 검색 결과도 안나와 그거 같이 디버깅하고, 현재 종목 검색해서 검새 하자마자는 미니맵/확대/축소 다 잘 나오는데, 현재뷰를 예를들어 1M ->3Y이렇게 바꾸면 그건 확대/축소/미니맵 이벤트가 안생겨. 이것도 디버깅해줘

## Previous Stage Outputs
- .ai/features/04-project-chart-compare-with-benchmark/00_spec.md
- .ai/features/04-project-chart-compare-with-benchmark/00_spec.result.json
- .ai/features/04-project-chart-compare-with-benchmark/01_plan.md
- .ai/features/04-project-chart-compare-with-benchmark/01_plan.result.json
- .ai/features/04-project-chart-compare-with-benchmark/02_dev.md
- .ai/features/04-project-chart-compare-with-benchmark/02_dev.result.json
- .ai/features/04-project-chart-compare-with-benchmark/03_review.md
- .ai/features/04-project-chart-compare-with-benchmark/03_review.result.json
- .ai/features/04-project-chart-compare-with-benchmark/04_fix.md
- .ai/features/04-project-chart-compare-with-benchmark/04_fix.result.json

## Additional Stage Inputs
- none

## Retry Context
- none

## Interactive Answer History
- none

## Current Git Hints
- current_head: ab506f23fcad3b3b771a2ee9e6e8002686a8731a
- changed_paths_excluding_runs: []
- latest_harness_verification: none

---

---
stage: "05_verify"
role: "verification"
preferred_model: "Codex"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".ai/features/04-project-chart-compare-with-benchmark/00_spec.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/01_plan.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/02_dev.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/03_review.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/04_fix.md"
outputs:
  - ".ai/features/04-project-chart-compare-with-benchmark/05_verify.md"
allowed_writes:
  - "new_tests"
  - ".ai/features/04-project-chart-compare-with-benchmark/05_verify.md"
forbidden_writes:
  - "production_code"
  - "existing_tests"
  - ".ai/features/04-project-chart-compare-with-benchmark/00_spec.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/01_plan.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/02_dev.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/03_review.md"
  - ".ai/features/04-project-chart-compare-with-benchmark/04_fix.md"
human_gate_required: false
verification_tests_policy: "preserve_and_handoff_to_04"
harness_verification_required: true
commit_policy: "commit_on_pass"
failure_commit_policy: "do_not_commit_failed_verify"
commit_owner: "harness"
default_next_stage_on_pass: "06_document"
default_next_stage_on_fail: "04_fix"
---

# 검증 프리셋 (5단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Codex이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `05_verify.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 의사결정의 일관성과 코드 동작을 검증하는 단계이다.
- 최종 PASS/FAIL 판정권은 하네스가 가진다. 모델의 `05_verify.md` 판정은 검증 분석과 권고이며, 하네스가 설정된 검증 명령을 직접 실행한 결과가 우선한다.
- 모델이 `status: PASS`를 기록해도 하네스 검증 명령 중 하나라도 실패하면 하네스는 이 단계를 `FAIL`로 덮어쓰고 `04_fix`로 되돌린다.
- 하네스 실행 결과는 `.ai/runs/04-project-chart-compare-with-benchmark/verification/latest.json`에 저장된다.
- 프로덕션 코드는 절대 수정하지 않는다.
- 신규 테스트 코드는 루트 `tests/` 하위에만 작성할 수 있다.
- 기존 테스트 코드는 수정하거나 삭제하지 않는다.

---

## 역할

너는 이 프로젝트의 최종 검증 담당이다.
1~4단계 기록과 코드를 확인하여 의사결정의 일관성과 코드의 동작을 검증한다.

---

## 작업 순서

1. 요청사항이 검증 불가능할 정도로 모호한 경우에만 `status: NEEDS_USER`로 멈춘다.
2. `.ai/features/04-project-chart-compare-with-benchmark/00_spec.md`의 목표, 범위, 요구사항, 위험도를 파악한다.
3. `.ai/features/04-project-chart-compare-with-benchmark/01_plan.md`의 구현 접근 방식, 변경 파일 계획, 위험 구간, 의존성, 테스트 전략을 파악한다.
4. `.ai/features/04-project-chart-compare-with-benchmark/02_dev.md`를 읽고 기능 목표, 구현 의도, Git 정보를 파악한다.
5. `.ai/features/04-project-chart-compare-with-benchmark/03_review.md`를 읽고 리뷰 지적 사항을 파악한다.
6. `.ai/features/04-project-chart-compare-with-benchmark/04_fix.md`를 읽고 수용/거부/보류 판단과 실제 수정 내용을 파악한다.
7. 의사결정 검증을 수행한다.
8. 동작 검증을 수행한다. 직접 실행한 명령은 기록하되, 최종 자동화 판정은 하네스가 실행하는 검증 명령 결과에 위임한다.
9. 검증 결과를 `.ai/features/04-project-chart-compare-with-benchmark/05_verify.md`에 작성한다.
10. 검증 시작 시점의 현재 `HEAD`를 `verify_target_commit`으로 기록한다.
11. 모델 기준 판정이 `PASS`이면 `05_verify.md`와 검증 관련 변경을 하네스가 `05_verify` stage 커밋에 포함할 수 있게 워킹트리를 커밋 가능한 상태로 남긴다. 추천 커밋 메시지는 `04-project-chart-compare-with-benchmark[YYYYMMDD-hhmmss][05_verify]` 포맷을 사용한다.
12. 모델 기준 판정이 `FAIL`이면 `harness_commit_required: false`로 기록한다. 실패 기록, 재현 명령, 추가 테스트 파일은 워킹트리에 남겨 04_fix가 읽고 처리하게 한다.
13. 모델 기준 판정이 `PASS`이면 `next_stage: 06_document`로 기록한다. 단, 하네스 검증 실패 시 하네스가 `next_stage: 04_fix`로 덮어쓴다.
14. 모델 기준 판정이 `FAIL`이면 `next_stage: 04_fix`로 기록하고 `fix_inputs` 블록에 4단계가 처리해야 할 항목을 작성한다.
15. 하네스는 `--max-verify-fix-retries` 값으로 `05_verify` 실패 후 `04_fix`로 되돌아가는 최대 횟수를 제한한다. 기본값은 3이며, 무거운 작업은 사용자가 더 큰 값을 줄 수 있다.
16. `git commit`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다. 실제 커밋은 하네스가 처리한다.
17. 이 단계 산출물 안에 커밋 SHA를 기록하려고 하지 않는다. 커밋 SHA는 하네스가 커밋한 뒤에 생기므로 이 단계 산출물에는 정확히 적을 수 없다.

---

## 의사결정 검증

### 계획 정합성 (spec -> plan -> dev)

- 00_spec.md의 요구사항이 01_plan.md에 빠짐없이 반영되었는지 확인한다.
- 01_plan.md의 변경 파일 계획과 실제 변경 파일이 일치하는지 확인한다.
- 01_plan.md의 구현 접근 방식과 실제 구현이 일치하는지 확인한다.
- 차이가 있으면 02_dev.md에 사유가 기록되어 있는지 확인한다.
- 01_plan.md의 위험 구간 완화 방안이 실제 코드에 반영되었는지 확인한다.
- 01_plan.md의 호환성 유지 전략이 실제 코드와 테스트에 반영되었는지 확인한다.
- 01_plan.md의 새 의존성과 실제 추가 의존성이 일치하는지 확인한다.

### 일관성 확인 (dev -> review -> fix)

- 02_dev.md의 기능 목표와 실제 코드가 일치하는지 확인한다.
- 03_review.md의 `must_fix` 항목이 04_fix.md에서 빠짐없이 다뤄졌는지 확인한다.
- 04_fix.md에서 수용한 항목이 실제 코드에 반영되었는지 확인한다.
- 04_fix.md에서 거부한 항목의 근거가 타당한지 검토한다.
- 보류 항목이 별도 처리 가능한 형태로 남아 있는지 확인한다.

### 문서 정합성

- 02_dev.md와 04_fix.md의 변경 파일 목록이 실제 변경 파일과 일치하는지 확인한다.
- 새 의존성이 기록되어 있는지 확인한다.
- Git 정보의 `diff_range` 또는 `diff_command`로 실제 변경을 재현할 수 있는지 확인한다.

---

## 동작 검증

### 수정 가능 범위

- 신규 테스트 코드는 루트 `tests/` 하위에 작성 가능하다.
- 기존 테스트 코드는 수정하거나 삭제하지 않는다.
- 프로덕션 코드는 수정하지 않는다.
- 이 단계는 `05_verify` stage 커밋을 하네스가 만들 수 있게 준비하는 단계이다.
- 하네스는 검증 PASS일 때만 `05_verify` stage 커밋을 만든다.
- 검증 FAIL 상태의 05_verify 커밋은 모델도 하네스도 만들지 않는다.
- 이 단계에서 쓸 수 있는 파일은 신규 테스트 파일과 `05_verify.md`뿐이다.
- 05_verify에서 작성한 테스트 코드는 삭제하지 않는다.
- 검증이 FAIL이면 05_verify에서 작성한 테스트 코드를 04_fix의 입력으로 넘기고, 04_fix는 해당 테스트를 유지한 채 수정 대상으로 포함한다.
- 검증이 PASS이면 05_verify에서 작성한 테스트 코드는 하네스가 만드는 최종 변경 세트에 포함되어야 한다.

### 테스트 실행

- 기존 테스트를 전부 실행하여 통과 여부를 확인한다.
- 1~4단계에서 언급된 엣지 케이스 테스트가 존재하는지 확인한다.
- 누락된 중요 테스트가 있으면 루트 `tests/` 하위에 테스트 코드를 작성하여 실행한다.
- 에러 발생 경로 테스트가 없으면 루트 `tests/` 하위에 테스트 코드를 작성하여 실행한다.
- 하네스가 별도로 실행할 고정 검증 명령은 `.ai/harness.config.json`의 `verification.commands`에 정의되어 있다. 모델은 이 명령 목록을 최종 판정의 권위 있는 출처로 취급한다.
- 모델이 직접 실행한 명령과 하네스 검증 명령이 다르면, 그 차이를 `05_verify.md`에 기록한다.

### 통합 확인

- 새 기능이 기존 기능을 깨뜨리지 않는지 전체 테스트를 실행한다.
- 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값이 사용자 승인 없이 깨지지 않았는지 확인한다.
- 기존 호출부와 사용자 흐름이 새 구현 후에도 동작하는지 확인한다.
- import 오류, 타입 오류, 런타임 에러가 없는지 확인한다.

### 테스트 실패 시

- 실패한 테스트의 원인을 분석하여 `05_verify.md`에 기록한다.
- 프로덕션 코드는 직접 수정하지 않는다.
- 실패 원인과 수정 방향만 기록한다.

---

## 검증 기록 양식

검증 완료 후 `.ai/features/04-project-chart-compare-with-benchmark/05_verify.md`에 아래 형식으로 작성한다.

```markdown
# 05_verify - 04-project-chart-compare-with-benchmark

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 의사결정 검증
- 계획 정합성 (spec -> plan -> dev) 판정: PASS / FAIL
- 일관성 (dev -> review -> fix) 판정: PASS / FAIL
- 문서 정합성 판정: PASS / FAIL
- 호환성 계획 반영 판정: PASS / FAIL
- 불일치 항목:
- 04_fix.md에서 거부한 항목에 대한 타당성 판정:

## 호환성 검증
- 공개 API/함수 시그니처/데이터 포맷/설정 키/CLI 호환성: PASS / FAIL
- 기존 호출부/사용자 흐름 확인 결과:
- breaking change 발생 여부와 승인 여부:
- 회귀 위험:

## 동작 검증
- 기존 테스트 실행 결과: PASS / FAIL (통과 N개 / 실패 N개)
- 추가 작성한 테스트 목록과 실행 결과:
- 전체 테스트 실행 결과: PASS / FAIL
- 실행한 테스트 명령:

## 하네스 검증
- 최종 자동 판정 주체: harness
- 하네스 검증 결과 파일: .ai/runs/04-project-chart-compare-with-benchmark/verification/latest.json
- 하네스 검증 명령은 `.ai/harness.config.json`을 기준으로 실행됨
- 모델 판정과 하네스 판정이 다를 경우 하네스 판정이 우선함

## 실패 항목
- 실패한 테스트명:
- 실패 원인 분석:
- 수정 방향 제안:

## fix_inputs
- status: READY_FOR_04_FIX / NONE
- 04_fix가 우선 처리할 항목:
- 실패 재현 명령:
- 05_verify에서 추가한 테스트 파일 (`tests/` 하위):
- 관련 파일:
- 기대 동작:
- 실제 동작:

## Git 정보
- verify_target_commit:
- harness_commit_required: true / false
- test_changes_ready_for_harness_commit: true / false
- commit_created_by_model: false
- commit_policy_result: request_harness_commit_on_pass / not_committed_due_to_fail
- verification_commit_message_suggestion: 04-project-chart-compare-with-benchmark[YYYYMMDD-hhmmss][05_verify]
- harness_commit_blocking_reason:
- diff_command_used:
- changed_files:

## 최종 판정
- PASS: 모든 검증 통과
- FAIL: 수정 필요, 4단계로 돌아갈 것

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: 06_document / 04_fix
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .ai/features/04-project-chart-compare-with-benchmark/05_verify.md
- changed_files:
- harness_commit_required: true / false
- commit_created_by_model: false
- commit_message_suggestion:
- test_commands:
  - name: safe_command_name
    command: ["python", "-m", "pytest", "tests"]
    cwd: "."
    timeout_seconds: 600
    persist: true
- model_mismatch: false
- actual_model:
- harness_final_authority: true
```

---

## Dynamic Harness Verification Commands

If this verify stage runs project-specific tests or builds beyond the static commands in `.ai/harness.config.json`, record every command that should become mandatory in the stage result JSON field `test_commands`.

`test_commands` must be a JSON array of objects:

```json
[
  {
    "name": "backend_tests",
    "command": ["python", "-m", "pytest", "tests\\backend"],
    "cwd": ".",
    "timeout_seconds": 600,
    "persist": true
  },
  {
    "name": "frontend_tests",
    "command": ["npm.cmd", "test"],
    "cwd": "src\\frontend",
    "timeout_seconds": 600,
    "persist": true
  }
]
```

Rules:

- `command` must be an argument array. Do not write a shell string.
- Use only safe verification/build commands: `python -m pytest ...`, `npm.cmd test`, `npm.cmd run build`, `dotnet test`, or `dotnet build`.
- On Windows, use `npm.cmd`, not `npm`.
- `cwd` must be omitted or point inside this repository.
- Do not use shell wrappers such as `powershell`, `cmd /c`, `bash -c`, or `sh -c`.
- Do not include destructive, network, or Git-mutating commands such as `rm`, `del`, `curl`, `git push`, `git reset`, `git clean`, or `git checkout`.
- Set `persist: true` for commands that should be added to `.ai/harness.config.json` after they pass. Set `persist: false` only for one-off diagnostics.
- The harness reruns safe non-duplicate `test_commands` after the configured verification commands. Rejected commands or failed commands make verify fail. Passed non-duplicate commands with `persist: true` are appended to `.ai/harness.config.json`.

---

## 금지 사항

- 프로덕션 코드를 직접 수정하지 않는다.
- 기존 테스트 코드를 수정하거나 삭제하지 않는다.
- 검증이 FAIL인데 PASS로 판정하지 않는다.
- 하네스 검증 실패를 무시하거나 숨기지 않는다.
- 1~4단계 md 파일을 수정하지 않는다.
- 실패 원인을 숨기거나 다음 단계 입력을 비워두지 않는다.
- `git commit`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다.
