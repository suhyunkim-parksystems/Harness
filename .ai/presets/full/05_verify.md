---
stage: "05_verify"
role: "verification"
preferred_model: "Codex"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_plan.md"
  - ".project/features/[기능명]/schemas.json"
  - ".project/features/[기능명]/02_dev.md"
  - ".project/features/[기능명]/03_review.md"
  - ".project/features/[기능명]/04_fix.md"
outputs:
  - ".project/features/[기능명]/05_verify.md"
allowed_writes:
  - "new_tests"
  - ".project/features/[기능명]/05_verify.md"
forbidden_writes:
  - "production_code"
  - "existing_tests"
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_plan.md"
  - ".project/features/[기능명]/schemas.json"
  - ".project/features/[기능명]/02_dev.md"
  - ".project/features/[기능명]/03_review.md"
  - ".project/features/[기능명]/04_fix.md"
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
- `tests/acceptance/`는 블라인드 수용테스트 트랙의 예약 경로다. 이 단계에서 그 하위에 파일을 만들거나 수정하지 않는다. 새 테스트는 `tests/` 하위의 다른 경로(예: `tests/unit/`)에 둔다.

## 실행 정책

- 권장 담당 모델은 Codex이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `05_verify.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 의사결정의 일관성과 코드 동작을 검증하는 단계이다.
- 최종 PASS/FAIL 판정권은 하네스가 가진다. 모델의 `05_verify.md` 판정은 검증 분석과 권고이며, 하네스가 설정된 검증 명령을 직접 실행한 결과가 우선한다.
- 모델이 `status: PASS`를 기록해도 하네스 검증 명령 중 하나라도 실패하면 하네스는 이 단계를 `FAIL`로 덮어쓰고 `04_fix`로 되돌린다.
- 하네스 실행 결과는 `.project/runs/[기능명]/verification/latest.json`에 저장된다.
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
2. `.project/features/[기능명]/00_spec.md`의 목표, 범위, 요구사항, 위험도를 파악한다.
3. `.project/features/[기능명]/01_plan.md`의 구현 접근 방식, 변경 파일 계획, 위험 구간, 의존성, 테스트 전략을 파악한다.
3-1. `.project/features/[기능명]/schemas.json`의 인터페이스 스키마를 파악한다(읽기 전용, 수정 금지).
4. `.project/features/[기능명]/02_dev.md`를 읽고 기능 목표, 구현 의도, Git 정보를 파악한다.
5. `.project/features/[기능명]/03_review.md`를 읽고 리뷰 지적 사항을 파악한다.
6. `.project/features/[기능명]/04_fix.md`를 읽고 수용/거부/보류 판단과 실제 수정 내용을 파악한다.
7. 의사결정 검증을 수행한다.
8. 동작 검증을 수행한다. 직접 실행한 명령은 기록하되, 최종 자동화 판정은 하네스가 실행하는 검증 명령 결과에 위임한다.
9. 검증 결과를 `.project/features/[기능명]/05_verify.md`에 작성한다.
10. 검증 시작 시점의 현재 `HEAD`를 `verify_target_commit`으로 기록한다.
11. 모델 기준 판정이 `PASS`이면 `05_verify.md`와 검증 관련 변경을 하네스가 `05_verify` stage 커밋에 포함할 수 있게 워킹트리를 커밋 가능한 상태로 남긴다. 추천 커밋 메시지는 `[기능명][YYYYMMDD-hhmmss][05_verify]` 포맷을 사용한다.
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

### 스키마 적합성 (schemas.json -> 구현)

- schemas.json의 모든 `change: new`/`modify` 심볼이 코드에 실제로 존재하는지 확인한다.
- 구현 시그니처(파라미터 이름/순서, 반환 구조)가 스키마 선언과 일치하는지 확인한다.
- 선언된 에러 규약(`errors[].raises`)이 해당 조건에서 실제로 발생하는지, 가능하면 동적으로(테스트 실행) 확인한다.
- 파라미터/반환의 `constraints`(범위, 포맷, enum)가 구현에서 강제되는지 확인한다. 가능하면 경계값을 동적으로 확인한다.
- 선언된 `invariants`가 유지되는지 확인한다.
- 참고: 모델 판정과 별개로, 하네스가 PASS 직후 심볼 존재/파라미터 이름·순서를 기계 검증한다. 불일치 시 하네스가 verify를 FAIL로 덮어쓰고 `next_stage: 04_fix`로 보낸다.

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
- 하네스가 별도로 실행할 고정 검증 명령은 `.ai/harness.config.json`과 `.project/harness.config.json`의 병합된 `verification.commands`에 정의되어 있다. 모델은 이 명령 목록을 최종 판정의 권위 있는 출처로 취급한다.
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

검증 완료 후 `.project/features/[기능명]/05_verify.md`에 아래 형식으로 작성한다.

```markdown
# 05_verify - [기능명]

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
- 하네스 검증 결과 파일: .project/runs/[기능명]/verification/latest.json
- 하네스 검증 명령은 `.ai/harness.config.json` + `.project/harness.config.json` 병합 결과를 기준으로 실행됨
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
- verification_commit_message_suggestion: [기능명][YYYYMMDD-hhmmss][05_verify]
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
  - .project/features/[기능명]/05_verify.md
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

If this verify stage runs project-specific tests or builds beyond the static commands in the merged harness config, record every command that should become mandatory in the stage result JSON field `test_commands`.

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
- Set `persist: true` for commands that should be added to `.project/harness.config.json` after they pass. Set `persist: false` only for one-off diagnostics.
- The harness reruns safe non-duplicate `test_commands` after the configured verification commands. Rejected commands or failed commands make verify fail. Passed non-duplicate commands with `persist: true` are appended to `.project/harness.config.json`.

---

## 금지 사항

- 프로덕션 코드를 직접 수정하지 않는다.
- 기존 테스트 코드를 수정하거나 삭제하지 않는다.
- `tests/acceptance/` 하위에 파일을 만들거나 수정하지 않는다.
- 검증이 FAIL인데 PASS로 판정하지 않는다.
- 하네스 검증 실패를 무시하거나 숨기지 않는다.
- 1~4단계 md 파일을 수정하지 않는다.
- 실패 원인을 숨기거나 다음 단계 입력을 비워두지 않는다.
- `git commit`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다.
