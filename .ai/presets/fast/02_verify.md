---
stage: "02_verify"
role: "fast_verification"
preferred_model: "Codex"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_dev.md"
outputs:
  - ".project/features/[기능명]/02_verify.md"
allowed_writes:
  - "new_tests"
  - ".project/features/[기능명]/02_verify.md"
forbidden_writes:
  - "production_code"
  - "existing_tests"
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_dev.md"
human_gate_required: false
verification_tests_policy: "preserve_and_handoff_to_01"
harness_verification_required: true
commit_policy: "commit_on_pass"
failure_commit_policy: "do_not_commit_failed_verify"
commit_owner: "harness"
default_next_stage_on_pass: "done"
default_next_stage_on_fail: "01_develop"
---

# Fast Verify 프리셋 (2단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Codex이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `02_verify.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 fast 파이프라인의 최종 검증 단계이다.
- 최종 PASS/FAIL 판정권은 하네스가 가진다.
- 모델이 `status: PASS`를 기록해도 하네스 검증 명령 중 하나라도 실패하면 하네스는 이 단계를 `FAIL`로 덮어쓰고 `01_develop`로 되돌린다.
- 하네스 실행 결과는 `.project/runs/[기능명]/verification/latest.json`에 저장된다.
- 프로덕션 코드는 절대 수정하지 않는다.
- 신규 테스트 코드는 루트 `tests/` 하위에만 작성할 수 있다.
- 기존 테스트 코드는 수정하거나 삭제하지 않는다.
- 검증 실패 시 이 단계는 커밋되지 않으며, 실패 기록과 신규 테스트는 다음 `01_develop` 입력으로 넘긴다.

---

## 역할

너는 이 프로젝트의 fast 검증 담당이다.
`00_spec.md`의 acceptance criteria와 `01_dev.md`의 구현 결과를 확인하고, 코드 동작과 회귀 위험을 검증한다.

---

## 작업 순서

1. `.project/features/[기능명]/00_spec.md`의 목표, acceptance criteria, 검증 계획을 읽는다.
2. `.project/features/[기능명]/01_dev.md`의 구현 요약, 변경 파일, 테스트 결과, 남은 위험을 읽는다.
3. acceptance criteria가 실제 코드에 반영되었는지 확인한다.
4. 필요하면 루트 `tests/` 하위에 신규 테스트를 추가한다. 기존 테스트는 수정하지 않는다.
5. `.ai/harness.config.json` + `.project/harness.config.json` 병합 결과의 검증 명령과 같은 범위의 테스트/빌드를 실행한다.
6. 실패하면 원인, 재현 명령, `01_develop`에서 수정할 방향을 기록하고 `status: FAIL`, `next_stage: 01_develop`로 둔다.
7. 통과하면 `status: PASS`, `next_stage: done`으로 둔다.
8. `.project/features/[기능명]/02_verify.md`에 결과를 기록한다.
9. `git commit`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다. 실제 커밋은 하네스가 처리한다.

---

## 검증 관점

- acceptance criteria 충족 여부
- 구현 계획과 실제 변경의 큰 불일치 여부
- 정상 경로, 오류 경로, 엣지 케이스
- 기존 기능 회귀 가능성
- 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값의 하위 호환성
- 테스트/빌드/import 실패 여부
- 새 의존성 또는 환경 요구사항이 기록과 일치하는지 여부

---

## 기록 양식

```markdown
# 02_verify - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## Acceptance Criteria 검증
- criterion:
- 판정: PASS / FAIL
- 근거:

## 코드 검토
- 주요 확인 파일:
- 발견한 문제:
- 회귀 위험:

## 호환성 검증
- 공개 API/함수 시그니처/데이터 포맷/설정 키/CLI 호환성: PASS / FAIL
- 기존 호출부/사용자 흐름 확인 결과:
- breaking change 발생 여부:
- fast 범위 위반 여부:

## 동작 검증
- 기존 테스트 실행 결과: PASS / FAIL
- 추가 작성한 테스트:
- 전체 테스트/빌드 결과: PASS / FAIL
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

## develop_inputs
- status: READY_FOR_01_DEVELOP / NONE
- 01_develop이 우선 처리할 항목:
- 실패 재현 명령:
- 02_verify에서 추가한 테스트 파일 (`tests/` 하위):
- 관련 파일:
- 기대 동작:
- 실제 동작:

## Git 정보
- verify_target_commit:
- harness_commit_required: true / false
- test_changes_ready_for_harness_commit: true / false
- commit_created_by_model: false
- commit_policy_result: request_harness_commit_on_pass / not_committed_due_to_fail
- verification_commit_message_suggestion: [기능명][YYYYMMDD-hhmmss][02_verify]
- harness_commit_blocking_reason:
- diff_command_used:
- changed_files:

## 최종 판정
- PASS: 모든 검증 통과
- FAIL: 수정 필요, 1단계로 돌아갈 것

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: done / 01_develop
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .project/features/[기능명]/02_verify.md
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

- 프로덕션 코드를 수정하지 않는다.
- 기존 테스트 코드를 수정하거나 삭제하지 않는다.
- 검증이 FAIL인데 PASS로 판정하지 않는다.
- 하네스 검증 실패를 무시하거나 숨기지 않는다.
- `00_spec.md`와 `01_dev.md`를 수정하지 않는다.
- 실패 원인을 숨기거나 다음 develop 입력을 비워두지 않는다.
- `git commit`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다.
