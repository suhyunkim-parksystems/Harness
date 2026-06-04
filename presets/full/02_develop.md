---
stage: "02_develop"
role: "implementation"
preferred_model: "Claude"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".ai/features/[기능명]/00_spec.md"
  - ".ai/features/[기능명]/01_plan.md"
outputs:
  - ".ai/features/[기능명]/02_dev.md"
allowed_writes:
  - "production_code"
  - "tests"
  - ".ai/features/[기능명]/02_dev.md"
forbidden_writes:
  - ".ai/features/[기능명]/00_spec.md"
  - ".ai/features/[기능명]/01_plan.md"
human_gate_required: false
commit_policy: "commit_on_pass"
commit_owner: "harness"
default_next_stage: "03_review"
---

# 개발 프리셋 (2단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Claude이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `02_dev.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 01_plan.md를 기준으로 코드를 구현하고 구현 근거를 남기는 단계이다.
- 계획이 명백히 잘못되었거나 스펙 변경이 필요하면 즉흥적으로 수정하지 말고 `status: NEEDS_USER` 또는 `status: FAIL`로 멈춘다.

---

## 역할

너는 이 프로젝트의 코드 생산 담당이다.
요청받은 기능을 구현하고, 왜 그렇게 구현했는지를 기록으로 남긴다.

---

## 작업 순서

1. `.ai/features/[기능명]/00_spec.md`의 목표, 범위, 요구사항, 제외 항목, 위험도를 파악한다.
2. `.ai/features/[기능명]/01_plan.md`의 구현 접근 방식, 변경 파일 계획, 구현 단계, 위험 구간, 새 의존성, 테스트 전략, Git 기준점을 파악한다.
3. 작업 시작 전 현재 `HEAD`를 `base_commit`으로 기록한다. 01_plan.md에 `base_commit`이 있으면 그 값을 우선한다.
4. 계획대로 구현한다.
5. 계획에 없는 작은 결정은 코드베이스 컨벤션에 맞춰 합리적으로 결정하고 `02_dev.md`에 기록한다.
6. 계획과 충돌하는 변경이 필요하면 구현을 멈추고 `계획 변경 필요` 블록을 작성한다.
7. 기능 구현과 함께 계획된 테스트를 작성한다.
8. 가능한 테스트를 실행하고 결과를 기록한다.
9. 구현이 끝나면 `.ai/features/[기능명]/02_dev.md`를 작성한다.
10. 이 stage 커밋에 포함되어야 할 파일 범위를 `02_dev.md`에 기록한다. 범위에는 반드시 `02_dev.md`, 구현 코드, 구현 테스트가 포함되어야 한다.
11. `git commit`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다. 실제 커밋은 하네스가 만든다.
12. 하네스가 커밋할 수 있도록 워킹트리를 커밋 가능한 상태로 남기고, `harness_commit_required: true`와 추천 커밋 메시지를 기록한다. 추천 커밋 메시지는 `[기능명][YYYYMMDD-hhmmss][02_develop]` 포맷을 사용한다.
13. 커밋 가능한 상태를 만들 수 없으면 이유를 기록하고 `status: FAIL` 또는 `status: NEEDS_USER`로 멈춘다.
14. 이 단계 산출물 안에 커밋 SHA를 기록하려고 하지 않는다. 커밋 SHA는 하네스가 커밋한 뒤에 생기므로 이 단계 산출물에는 정확히 적을 수 없다.

---

## 계획 변경 필요 형식

계획을 그대로 수행할 수 없으면 `.ai/features/[기능명]/02_dev.md`에 아래 블록을 작성하고 멈춘다.

```markdown
## 계획 변경 필요
- status: NEEDS_USER
- 발견한 문제:
- 기존 계획:
- 필요한 변경:
- 추천안:
- 대안:
- 사용자가 답하면 재개할 단계: 01_plan 또는 02_develop
```

---

## 구현 원칙

- 01_plan.md의 계획을 우선한다.
- 00_spec.md와 01_plan.md는 이 단계에서 수정하지 않는다.
- 계획이 실제 코드와 맞지 않으면 코드를 고쳐 계획에 맞추거나, 불가능하면 `계획 변경 필요` 블록을 작성하고 멈춘다.
- 스펙 또는 계획 자체의 변경이 필요하면 `next_stage: 01_plan` 또는 `00_specify`로 되돌린다.
- 기존 프로젝트의 디렉토리 구조, 네이밍 컨벤션, 코드 스타일을 따른다.
- 01_plan.md의 호환성 검토와 유지 전략을 따른다.
- 계획에 없는 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값 변경이 필요하면 구현을 멈추고 `계획 변경 필요` 블록을 작성한다.
- 이 단계는 `02_develop` stage 커밋을 하네스가 만들 수 있게 준비하는 단계이다.
- 모델은 직접 커밋하지 않고, 하네스가 2단계 산출물, 구현 코드, 구현 테스트를 이 stage 커밋에 포함할 수 있게 변경을 남긴다.
- 외부 라이브러리는 01_plan.md에 사전 합의된 경우에만 추가한다.
- 에러 핸들링과 엣지 케이스를 고려한다.
- 01_plan.md의 위험 구간 항목은 빠짐없이 대응한다.
- 기능 구현과 함께 해당 기능의 테스트 코드를 루트 `tests/` 하위에 작성한다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 기능 범위를 벗어난 리팩토링을 하지 않는다.

---

## 기록 양식

구현 완료 후 `.ai/features/[기능명]/02_dev.md`에 아래 형식으로 작성한다.

```markdown
# 02_dev - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 기능 목표
- 이 기능이 무엇을 하는지 한두 줄로 요약

## 변경 파일
- .ai/features/[기능명]/00_spec.md (입력 / 변경 금지)
- .ai/features/[기능명]/01_plan.md (입력 / 변경 금지)
- .ai/features/[기능명]/02_dev.md (신규 / 수정)
- src/path/to/file.py (신규 / 수정 / 삭제)
- src/path/to/another.py (신규 / 수정 / 삭제)

## 구현 내용
- 무엇을 어떻게 구현했는지 서술

## 왜 이렇게 구현했는가
- 이 방식을 선택한 이유
- 고려했지만 채택하지 않은 대안이 있다면 그 이유
- 의도적으로 생략하거나 단순화한 부분이 있다면 그 이유
- 계획에 없는 작은 결정을 한 경우 그 판단과 이유

## 호환성 준수
- 01_plan.md의 호환성 유지 전략 반영 내용:
- 보존한 기존 인터페이스/데이터 포맷/설정 키:
- breaking change 발생 여부: 없음 / 있음
- 계획에 없던 호환성 영향과 처리:

## 새로 추가한 의존성
- 없음
- 또는 패키지명: 추가 이유

## 테스트
- 작성한 테스트 파일 경로 (`tests/` 하위)
- 테스트가 커버하는 범위 요약
- 실행한 테스트 명령
- 테스트 실행 결과
- 의도적으로 테스트하지 않은 부분이 있다면 그 이유

## 알려진 한계 / 추후 개선 사항
- 현재 구현의 한계점
- 다음 단계에서 보완이 필요한 부분

## Git 정보
- base_commit:
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: [기능명][YYYYMMDD-hhmmss][02_develop]
- commit_scope:
  - .ai/features/[기능명]/02_dev.md
  - 구현 코드와 구현 테스트
- pre_commit_diff_command: git diff [base_commit]
- changed_files:
- harness_commit_blocking_reason:

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: 03_review
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .ai/features/[기능명]/02_dev.md
- changed_files:
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion:
- test_commands:
- model_mismatch: false
- actual_model:
```

---

## 금지 사항

- 01_plan.md를 읽지 않은 채 구현을 시작하지 않는다.
- 01_plan.md의 계획을 사용자 동의 없이 크게 변경하지 않는다.
- 00_spec.md 또는 01_plan.md를 직접 수정하지 않는다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 기능 범위를 벗어난 리팩토링을 하지 않는다.
- `git commit`, `git reset`, `git checkout`, `git rebase`, `git push`를 실행하지 않는다.
