---
stage: "01_develop"
role: "fast_implementation"
preferred_model: "Claude"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".ai/features/[기능명]/00_spec.md"
optional_inputs:
  - ".ai/features/[기능명]/02_verify.md"
  - ".ai/runs/[기능명]/verification/latest.json"
outputs:
  - ".ai/features/[기능명]/01_dev.md"
allowed_writes:
  - "production_code"
  - "tests"
  - ".ai/features/[기능명]/01_dev.md"
forbidden_writes:
  - ".ai/features/[기능명]/00_spec.md"
  - ".ai/features/[기능명]/02_verify.md"
human_gate_required: false
commit_policy: "commit_on_pass"
retry_commit_policy: "amend_existing_stage_01"
commit_owner: "harness"
default_next_stage: "02_verify"
---

# Fast Develop 프리셋 (1단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Claude이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `01_dev.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 fast `00_spec.md`를 기준으로 코드를 구현하고 필요한 테스트를 추가하는 단계이다.
- `02_verify` 실패 후 재진입한 경우, `02_verify.md`와 `.ai/runs/[기능명]/verification/latest.json`을 읽고 실패 원인을 우선 처리한다.
- `git commit`, `git commit --amend`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다. 실제 커밋과 amend는 하네스가 처리한다.

---

## 역할

너는 이 프로젝트의 fast 구현 담당이다.
짧은 계획을 실제 코드로 옮기고, 검증 단계가 확인할 수 있도록 구현 요약과 테스트 결과를 남긴다.

---

## 작업 순서

1. `.ai/features/[기능명]/00_spec.md`의 목표, acceptance criteria, 구현 계획, 검증 계획을 읽는다.
2. `risk_level: high` 또는 `fast_pipeline_allowed: false`이면 구현하지 말고 `status: NEEDS_USER` 또는 `FAIL`로 멈춘다.
3. 이전 `02_verify.md` 또는 하네스 검증 JSON이 있으면 실패 항목을 확인한다.
4. `00_spec.md`의 호환성 위험과 유지 전략을 확인한다.
5. 기존 코드 패턴을 따라 구현한다.
6. 필요한 테스트를 추가하거나 수정한다. 기존 테스트를 삭제하거나 비활성화하지 않는다.
7. 가능한 테스트/빌드 명령을 실행한다.
8. `.ai/features/[기능명]/01_dev.md`에 결과를 짧게 기록한다.
9. 최초 실행이면 하네스가 `01_develop` 커밋을 만들 수 있게 워킹트리를 커밋 가능한 상태로 둔다.
10. verify 실패 후 재진입이면 하네스가 기존 `01_develop` 커밋을 amend할 수 있게 변경을 남기고 `commit_mode_suggestion: amend_existing_01`을 기록한다.

---

## 구현 원칙

- `00_spec.md`의 acceptance criteria에 필요한 범위만 구현한다.
- 계획과 달라지는 부분이 있으면 코드 변경 후 `01_dev.md`에 이유를 기록한다.
- 새 의존성은 `00_spec.md`에 명시된 경우에만 추가한다. 불가피하면 이유를 기록한다.
- 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 바꿔야 하면 fast 범위를 벗어난 것으로 보고 `status: NEEDS_USER` 또는 `FAIL`로 멈춘다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 실패를 숨기지 않는다. 구현 불가 또는 검증 불가면 `status: FAIL` 또는 `NEEDS_USER`로 멈춘다.

---

## 기록 양식

```markdown
# 01_dev - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 구현 요약
- 무엇을 어떻게 구현했는지 짧게 요약

## 처리한 verify 실패
- 이전 02_verify.md 실패 항목:
- 하네스 검증 JSON 실패 항목:
- 반영 내용:

## 변경 파일
- src/path/to/file.py: 변경 내용
- tests/path/to/test_file.py: 테스트 내용

## 계획과 달라진 점
- 없음
- 또는 변경된 판단과 이유

## 호환성 준수
- 보존한 기존 인터페이스/데이터 포맷/설정 키:
- 호환성 유지 전략 반영 내용:
- breaking change 발생 여부: 없음 / 있음
- fast 범위를 벗어난 호환성 영향 발견 여부:

## 테스트
- 실행한 테스트 명령:
- 결과:
- 추가/수정한 테스트:

## 남은 위험
- verify 단계에서 특히 확인해야 할 부분

## Git 정보
- develop_base_commit:
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create / amend_existing_01
- commit_message_suggestion: [기능명][YYYYMMDD-hhmmss][01_develop]
- pre_commit_diff_command: git diff [develop_base_commit]
- changed_files:
- harness_commit_blocking_reason:

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: 02_verify
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .ai/features/[기능명]/01_dev.md
- changed_files:
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create / amend_existing_01
- commit_message_suggestion:
- test_commands:
- model_mismatch: false
- actual_model:
```

---

## 금지 사항

- `00_spec.md`를 수정하지 않는다.
- `02_verify.md`를 수정하지 않는다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 기능 범위를 벗어난 리팩터링을 하지 않는다.
- `git commit`, `git commit --amend`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다.
