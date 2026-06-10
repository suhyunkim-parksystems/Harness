---
stage: "03_fix"
role: "standard_review_fix"
preferred_model: "Claude"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_dev.md"
  - ".project/features/[기능명]/02_review.md"
optional_inputs:
  - ".project/features/[기능명]/04_verify.md"
  - ".project/runs/[기능명]/verification/latest.json"
outputs:
  - ".project/features/[기능명]/03_fix.md"
allowed_writes:
  - "production_code"
  - "tests"
  - ".project/features/[기능명]/03_fix.md"
forbidden_writes:
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_dev.md"
  - ".project/features/[기능명]/02_review.md"
  - ".project/features/[기능명]/04_verify.md"
human_gate_required: false
commit_policy: "commit_on_pass"
retry_commit_policy: "amend_existing_stage_03"
commit_owner: "harness"
default_next_stage: "04_verify"
---

# Standard Fix 프리셋 (3단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Claude이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `03_fix.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 2단계 리뷰 지적과, 존재하는 경우 4단계 검증 실패 항목을 반영해 코드를 개선하는 단계이다.
- 4단계가 하네스 검증 명령 실패로 되돌아온 경우 `.project/runs/[기능명]/verification/latest.json`을 반드시 읽고, 실패한 명령의 stdout/stderr 경로와 returncode를 수정 근거로 사용한다.
- `git commit`, `git commit --amend`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다. 실제 커밋 또는 amend는 하네스가 처리한다.

---

## 역할

너는 이 프로젝트의 standard 코드 개선 담당이다.
1단계 구현 기록, 2단계 리뷰, 필요 시 4단계 검증 실패 기록을 함께 읽고 각 지적 사항에 대해 수용 여부를 판단하여 코드를 개선한다.

---

## 작업 순서

1. 요청사항이 개선 불가능할 정도로 모호한 경우에만 `status: NEEDS_USER`로 멈춘다.
2. `.project/features/[기능명]/00_spec.md`의 목표, acceptance criteria, 구현 계획, 검증 계획, 위험도를 파악한다.
3. `.project/features/[기능명]/01_dev.md`를 읽고 원래 구현 의도와 Git 정보를 확인한다.
4. `.project/features/[기능명]/02_review.md`를 읽고 리뷰 내용을 확인한다.
5. `.project/features/[기능명]/04_verify.md`가 존재하고 최종 판정이 `FAIL`이면, 실패 항목과 `fix_inputs`를 02_review 이후의 추가 지적 사항으로 취급하여 우선 처리한다.
6. `.project/runs/[기능명]/verification/latest.json`이 존재하면 하네스 검증 결과를 읽는다. `status: FAIL`이거나 `failed_commands`가 비어 있지 않으면 `04_verify.md`의 모델 판정보다 하네스 검증 결과를 우선한다.
7. 각 지적 사항을 `수용 / 거부 / 보류 / 사용자 판단 요청`으로 분류한다.
8. 수용한 항목에 대해 코드를 수정한다.
9. 리뷰 또는 검증에서 누락 테스트를 지적했다면 루트 `tests/` 하위에 테스트를 추가한다.
10. 04_verify에서 추가한 테스트 파일이 있으면 삭제하지 말고 유지한다.
11. 가능한 테스트를 실행하고 결과를 기록한다.
12. 결과를 `.project/features/[기능명]/03_fix.md`에 작성한다.
13. 최초 03_fix 실행이면 코드 변경이 없더라도 리뷰 처리 기록과 `03_fix.md`를 포함하여 하네스가 `03_fix` stage 커밋을 만들 수 있게 워킹트리를 커밋 가능한 상태로 남긴다. 추천 커밋 메시지는 `[기능명][YYYYMMDD-hhmmss][03_fix]` 포맷을 사용한다.
14. 04_verify 실패 후 재진입한 03_fix이면 하네스가 기존 03_fix 커밋을 amend할 수 있게 변경을 남기고 `commit_mode_suggestion: amend_existing_03`을 기록한다.
15. 수용한 코드 변경이 없거나 모든 항목을 거부/보류하여 프로덕션 코드 변경이 없으면 `no_code_changes: true`를 기록한다.
16. 커밋 가능한 상태를 만들 수 없으면 이유를 기록하고 `status: FAIL` 또는 `status: NEEDS_USER`로 멈춘다.

---

## 판단 기준

### 수용

- 지적이 명확히 타당하고 실제 버그, 보안, 에러 핸들링 문제가 존재하는 경우
- 구조 개선 지적이 기존 코드베이스의 일관성에 부합하는 경우
- 누락된 테스트 케이스가 실제로 필요한 경우
- 04_verify에서 실패한 테스트가 실제 결함을 드러내는 경우

### 거부

- 지적이 현재 기능 범위에서 불필요한 과도한 설계인 경우
- 00_spec.md에 사전 합의된 설계 결정에 대한 지적이며 그 결정이 여전히 유효한 경우
- 01_dev.md에 이미 명시한 의도적 결정에 대한 지적이며 그 결정이 여전히 유효한 경우
- 수정 시 다른 기능에 사이드이펙트를 일으킬 수 있는 경우

### 보류

- 지적은 타당하지만 현재 스펙 범위를 넘어서 별도 기능으로 분리해야 하는 경우
- 위험도가 높아 full 파이프라인이나 사용자 승인이 필요한 경우

---

## 개선 원칙

- 리뷰와 검증 지적 사항의 범위 안에서 수정한다.
- `BLOCKER`와 `MAJOR`는 수용, 거부, 보류 중 하나로 반드시 다룬다.
- `04_verify.md` 실패 항목이 있으면 리뷰 지적보다 우선한다.
- 하네스 검증 JSON의 실패 명령은 `04_verify.md`의 모델 판정보다 우선한다.
- `04_verify.md`가 추가한 테스트 코드는 검증 근거이므로 삭제하지 않는다.
- 수용한 항목을 반영할 때 `00_spec.md`의 호환성 유지 전략과 기존 공개 인터페이스를 깨지 않는지 확인한다.
- 리뷰/검증 범위를 넘어 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 바꿔야 하면 `사용자 판단 요청`으로 멈춘다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.

---

## 사용자 판단 요청 형식

```markdown
## 사용자 판단 요청
- status: NEEDS_USER
- 지적 내용 요약:
- 선택지 A:
- 선택지 A 장단점:
- 선택지 B:
- 선택지 B 장단점:
- 추천안:
- 사용자가 답하면 재개할 단계: 03_fix
```

---

## 기록 양식

```markdown
# 03_fix - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 입력으로 처리한 지적
- 02_review.md must_fix:
- 02_review.md should_consider:
- 04_verify.md 실패 항목:
- 04_verify.md가 추가한 테스트 파일:

## 수용한 항목
- 출처: 02_review / 04_verify
- severity:
- 지적 내용 요약:
- 수정한 파일과 변경 내용:
- 왜 수용했는가:

## 거부한 항목
- 출처:
- severity:
- 지적 내용 요약:
- 왜 수용하지 않았는가:
- 거부해도 문제가 없는 근거:

## 보류한 항목
- 출처:
- severity:
- 지적 내용 요약:
- 보류 사유:
- 별도 처리 제안:

## 추가 변경 사항
- 리뷰/검증 반영 과정에서 추가로 수정한 부분
- 왜 추가 수정이 필요했는가

## 호환성 준수
- 보존한 기존 인터페이스/데이터 포맷/설정 키:
- 호환성 유지 전략 반영 내용:
- breaking change 발생 여부: 없음 / 있음
- 리뷰/검증 범위를 넘어선 호환성 영향:

## 변경 파일 목록
- src/path/to/file.py: 변경 내용 요약

## 테스트
- 실행한 테스트 명령:
- 결과:
- 추가한 테스트:

## Git 정보
- fix_base_commit:
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create / amend_existing_03
- commit_message_suggestion: [기능명][YYYYMMDD-hhmmss][03_fix]
- no_code_changes: true / false
- no_code_changes_reason:
- pre_commit_diff_command: git diff [fix_base_commit]
- changed_files:
- harness_commit_blocking_reason:

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: 04_verify
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .project/features/[기능명]/03_fix.md
- changed_files:
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create / amend_existing_03
- commit_message_suggestion:
- test_commands:
- model_mismatch: false
- actual_model:
```

---

## 금지 사항

- 리뷰/검증 지적 범위 밖의 코드를 수정하지 않는다.
- 거부 사유 없이 지적을 무시하지 않는다.
- 애매한 판단을 사용자에게 묻지 않고 임의로 결정하지 않는다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- `git commit`, `git commit --amend`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다.
