# Local Harness Prompt

## Harness Context
- feature_name: 02-project-search-tab
- pipeline_mode: full
- stage: 00_specify
- preferred_model: Codex
- scheduled_provider: codex
- performance: medium
- output_file: .ai/features/02-project-search-tab/00_spec.md
- result_json_file: .ai/features/02-project-search-tab/00_spec.result.json
- run_state: .ai/runs/02-project-search-tab/run.json
- generated_at: 2026-06-04T22:12:56
- defaults_mode: true
- interactive_mode: false
- feature_name_locked: true

## Decision Policy
Use recommended defaults for ambiguous decisions. Do not return NEEDS_USER unless the task is impossible, unsafe, requires credentials/secrets that are not available, or would perform destructive/non-reversible actions. Record all default decisions and their rationale in the stage output.

## Manual Provider Instructions
1. The local harness is executing this prompt with the preferred model when possible.
2. Make the requested file changes directly in the repository.
3. Write the human-readable stage output file exactly at `.ai/features/02-project-search-tab/00_spec.md`.
4. Also write the machine-readable stage result JSON exactly at `.ai/features/02-project-search-tab/00_spec.result.json`.
5. Do not run `git commit`, `git reset`, `git checkout`, `git rebase`, or `git push`. The local harness owns Git history.
6. This Git ownership rule overrides any preset text that appears to ask the model to create, amend, or push commits.
7. For every successful stage, leave the working tree commit-ready and record commit intent in the stage output; the harness will create or amend the commit.
8. If `defaults_mode: true`, prefer recommended defaults over `NEEDS_USER` unless blocked by missing credentials, safety, destructive operations, or impossibility.
9. If the stage needs user input under the decision policy, write both outputs with `status: NEEDS_USER`.
10. If the stage fails, write both outputs with `status: FAIL` and a concrete blocking reason.
11. If `feature_name_locked: true`, keep the existing `feature_name` exactly as provided by the harness. Do not rename or invent a different feature slug.
12. End with a concise summary; the harness will inspect files, not your final message.

## Machine Result JSON Contract
The harness reads `.ai/features/02-project-search-tab/00_spec.result.json` first. Keep the `## 단계 결과` section in `.ai/features/02-project-search-tab/00_spec.md` for humans, but write this JSON file for the harness.

Required JSON keys:
- status: "PASS", "FAIL", "SKIPPED", or "NEEDS_USER"
- next_stage: next stage id. This is not the final pipeline stage; do not use "done". Use `01_plan` unless the preset explicitly routes to another valid stage.
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

## Reliability
- 외부 입력, 파일, 네트워크, 프로세스 실행 결과는 실패 가능성을 명시적으로 처리한다.
- 외부 연동 실패는 호출 단위로 격리하고, 가능한 경우 부분 실패 상태로 응답해 전체 기능 중단을 피한다.
- 외부 데이터 조회는 캐시나 대체 경로를 활용해 일시적 실패에도 가능한 범위의 응답을 유지한다.
- 자동화 스크립트는 백그라운드 프로세스 종료 시 실행 시점에 기록한 PID를 우선 사용한다.

## Testing
- 테스트는 외부 네트워크에 의존하지 않으며, 외부 HTTP 호출은 Mock 또는 Fixture로 격리한다.


## Original User Request
주식 종목을 검색해서 그 종목의 상세정보 (종가, 시가 등등 엄청 많은 정보들이 있을거야. 특히 차트기능은 꼭)를 보여주는 Tab을 만들어줘. 기존의 대시보드는 첫번째 메인탭으로 가져가고 지금 검색기능 이걸 두번째 탭으로 두면되. 여기서 중요한건, 가장 최신 종목이 항상 반영되어야하며, 미리 캐시해 둘 필요가 있다면 그렇게 하도록해. 또한 한국주식/한국ETF/미국주식/미국ETF 이 4개에 대해서만 검색을 할건데, 미국 종목의 경우 티커를 기반으로한 검색을 해야하고 한국주식의 경우 이름을 기반으로한 검색을 해야해. 또한 검색의 편의성을 위해 자동완성 기능은 매우 필수야.

## Previous Stage Outputs
- none

## Additional Stage Inputs
- none

## Retry Context
- none

## Interactive Answer History
- none

## Current Git Hints
- current_head: ca994453753ad7fdfd186f1eb43656cabd85657e
- changed_paths_excluding_runs: []
- latest_harness_verification: none

---

---
stage: "00_specify"
role: "specification"
preferred_model: "Codex"
model_policy: "preferred_not_hard_block"
required_inputs:
  - "user_request"
optional_inputs:
  - "existing_codebase"
outputs:
  - ".ai/features/02-project-search-tab/00_spec.md"
allowed_writes:
  - ".ai/features/02-project-search-tab/00_spec.md"
forbidden_writes:
  - "production_code"
  - "tests"
human_gate_required: true
commit_policy: "commit_on_pass"
commit_owner: "harness"
default_next_stage: "01_plan"
---

# 스펙 구체화 프리셋 (0단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Codex이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `00_spec.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계의 목적은 사용자의 요구사항을 개발 가능한 수준의 스펙으로 확정하는 것이다.
- 코드는 작성하거나 수정하지 않는다.

---

## 역할

너는 이 프로젝트의 기능 스펙 정리 담당이다.
사용자의 요구사항을 받아 개발에 바로 착수할 수 있는 수준의 구체적인 스펙으로 정리한다.
빠지거나 모호한 부분이 있으면 사용자에게 질문하여 확정한다.

---

## 작업 순서

1. 사용자의 요구사항을 읽고 기능의 목적과 범위를 파악한다.
2. 기존 코드베이스를 확인하여 관련 코드, 패턴, 제약사항을 파악한다.
3. 요구사항에서 빠지거나 모호한 부분을 찾는다.
4. 기능명이 명확하지 않으면 요구사항을 기준으로 짧고 안정적인 기능명을 직접 작명한다.
5. 기능명은 소문자 영문, 숫자, 하이픈만 쓰는 slug로 만든다. 예: `user-auth`, `invoice-export`.
6. 질문이 필요하면 아래 `사용자 판단 요청` 형식으로 `status: NEEDS_USER`를 기록하고 멈춘다.
7. 질문이 필요 없거나 사용자 답변이 있으면 스펙을 확정한다.
8. `.ai/features/02-project-search-tab/` 디렉토리가 없으면 생성한다.
9. 확정된 스펙을 `.ai/features/02-project-search-tab/00_spec.md`에 아래 양식으로 작성한다.
10. 이 단계는 기본적으로 사람 승인 게이트가 필요하다. 하네스는 `human_gate_required: true`이면 사용자 확인을 받은 뒤 다음 단계로 진행한다.

---

## 질문 기준

다음 항목이 요구사항에서 명확하지 않으면 사용자에게 질문한다.
코드베이스를 보면 답을 알 수 있는 것은 질문하지 않고 직접 파악한다.

### 기능 범위

- 이 기능이 정확히 어디서 시작하고 어디서 끝나는지
- 이번에 구현할 것과 다음에 할 것의 경계

### 입력과 출력

- 이 기능에 들어오는 입력의 형태와 범위
- 기대하는 출력의 형태
- 비정상 입력에 대한 처리 방식

### 기존 코드와의 관계

- 기존 코드에서 수정이 필요한 부분
- 기존 기능과 충돌 가능성이 있는 부분
- 사용해야 하는 기존 모듈이나 유틸

### 기술적 제약

- 사용하거나 피해야 할 라이브러리
- 성능 요구사항
- 호환성 요구사항

---

## 질문 원칙

- 질문은 한 번에 모아서 한다.
- 각 질문에는 추천안, 대안, 기본값을 제시한다.
- 요구사항이 이미 충분히 구체적이면 질문 없이 바로 스펙을 정리한다.
- 질문이 필요한 상태에서는 스펙을 확정하지 않는다.

---

## 위험도 판단 기준

`00_spec.md`에는 `risk_level`을 반드시 기록한다.

- `low`: 문구 수정, 작은 UI 조정, 단일 함수의 국소 버그 수정
- `medium`: 일반 기능 추가, 여러 파일 변경, 테스트 추가 필요
- `high`: 인증/인가, 결제, 보안, 데이터 마이그레이션, 데이터 삭제/변환, 공개 API 변경, 새 외부 의존성, 대규모 리팩토링

다음 중 하나라도 해당하면 `human_gate_required: true`로 둔다.

- `risk_level: high`
- 새 외부 의존성 가능성
- 비가역 변경 가능성
- 사용자 경험에 직접 영향을 주는 정책 결정
- 보안 경계 변경

---

## 사용자 판단 요청 형식

질문이 필요하면 `.ai/features/02-project-search-tab/00_spec.md`에 아래 블록만 작성하고 멈춘다.

```markdown
# 00_spec - 02-project-search-tab

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 사용자 판단 요청
- status: NEEDS_USER
- 질문:
- 추천안:
- 대안:
- 기본값:
- 사용자가 답하면 재개할 단계: 00_specify

## 단계 결과
- status: NEEDS_USER
- next_stage: 00_specify
- human_gate_required: true
- blocking_reason:
- risk_level:
- produced_files:
  - .ai/features/02-project-search-tab/00_spec.md
- changed_files:
- harness_commit_required: true / false
- commit_created_by_model: false
- commit_message_suggestion:
- model_mismatch: false
- actual_model:
```

---

## 기록 양식

스펙 확정 후 `.ai/features/02-project-search-tab/00_spec.md`에 아래 형식으로 작성한다.
기존 파일이 있으면 같은 파일을 갱신하되, 이전 사용자 답변 기록을 삭제하지 않는다.

```markdown
# 00_spec - 02-project-search-tab

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 기능 목표
- 이 기능이 무엇을 하는지 한두 줄로 요약

## 기능명
- feature_name: [기능명 slug]
- naming_reason: 이 이름을 선택한 이유

## 구체적 요구사항
- 되어야 하는 것 목록
- 각 항목은 검증 가능한 수준으로 구체적으로 작성

## 이번 범위에서 제외하는 것
- 관련은 있지만 이번에 구현하지 않는 것
- 제외 사유

## 입력과 출력
- 입력 형태, 타입, 범위
- 출력 형태, 타입
- 비정상 입력 처리 방식

## 기존 코드 영향
- 수정이 필요한 기존 파일
- 사용할 기존 모듈/유틸
- 충돌 가능성이 있는 부분

## 기술적 제약
- 사용할 라이브러리/프레임워크
- 성능/호환성 요구사항

## 위험도 및 게이트
- risk_level: low / medium / high
- human_gate_required: true / false
- human_gate_reason:

## 사용자 확인 사항
- 질문과 사용자 답변 기록

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: 01_plan
- human_gate_required: true
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .ai/features/02-project-search-tab/00_spec.md
- changed_files:
- harness_commit_required: true / false
- commit_created_by_model: false
- commit_message_suggestion:
- model_mismatch: false
- actual_model:
```

---

## 금지 사항

- 개발을 시작하지 않는다.
- 테스트 코드를 작성하지 않는다.
- 사용자의 최종 확인 없이 `human_gate_required: false`로 낮추지 않는다.
- 질문할 것이 있는데 추측으로 스펙을 확정하지 않는다.
- 질문을 여러 턴에 나눠서 하지 않는다.
