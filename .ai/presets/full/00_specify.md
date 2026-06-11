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
  - ".project/features/[기능명]/00_spec.md"
allowed_writes:
  - ".project/features/[기능명]/00_spec.md"
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
8. `.project/features/[기능명]/` 디렉토리가 없으면 생성한다.
9. 확정된 스펙을 `.project/features/[기능명]/00_spec.md`에 아래 양식으로 작성한다.
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

full 파이프라인의 이 단계는 항상 사람 승인 게이트를 거친다(`human_gate_required: true` 고정).
아래 항목은 `risk_level` 판단과 이후 plan 단계의 게이트 판단 근거로 기록한다.

- `risk_level: high`
- 새 외부 의존성 가능성
- 비가역 변경 가능성
- 사용자 경험에 직접 영향을 주는 정책 결정
- 보안 경계 변경

---

## 사용자 판단 요청 형식

질문이 필요하면 `.project/features/[기능명]/00_spec.md`에 아래 블록만 작성하고 멈춘다.

```markdown
# 00_spec - [기능명]

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
  - .project/features/[기능명]/00_spec.md
- changed_files:
- harness_commit_required: true / false
- commit_created_by_model: false
- commit_message_suggestion:
- model_mismatch: false
- actual_model:
```

---

## 기록 양식

스펙 확정 후 `.project/features/[기능명]/00_spec.md`에 아래 형식으로 작성한다.
기존 파일이 있으면 같은 파일을 갱신하되, 이전 사용자 답변 기록을 삭제하지 않는다.

```markdown
# 00_spec - [기능명]

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
  - .project/features/[기능명]/00_spec.md
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
