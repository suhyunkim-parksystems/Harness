---
stage: "01_plan"
role: "implementation_plan"
preferred_model: "Antigravity"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".ai/features/[기능명]/00_spec.md"
optional_inputs:
  - "existing_codebase"
outputs:
  - ".ai/features/[기능명]/01_plan.md"
allowed_writes:
  - ".ai/features/[기능명]/01_plan.md"
forbidden_writes:
  - "production_code"
  - "tests"
human_gate_required: "defer_to_output"
commit_policy: "commit_on_pass"
commit_owner: "harness"
default_next_stage: "02_develop"
---

# 계획 프리셋 (1단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Antigravity이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `01_plan.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 구현 전에 "어떻게 만들지"를 결정하는 단계이다.
- 코드는 작성하거나 수정하지 않는다.

---

## 역할

너는 이 프로젝트의 구현 계획 담당이다.
0단계에서 확정된 스펙을 받아 파일 단위 변경 계획, 데이터/제어 흐름, 구현 단계 분할, 위험 구간, 테스트 전략을 구체적으로 결정한다.
다음 단계가 즉흥적 판단 없이 실행할 수 있는 수준의 계획을 만든다.

---

## 작업 순서

1. `.ai/features/[기능명]/00_spec.md`의 목표, 범위, 요구사항, 제외 항목, 위험도를 정확히 파악한다.
2. 스펙과 관련된 기존 코드를 깊이 읽는다. 영향 파일, 재사용 가능한 모듈, 충돌 가능한 구간, 하위 호환성 위험을 실제 검색과 파일 읽기로 확인한다.
3. 구현 접근 방식 후보를 도출한다. 후보가 둘 이상이면 트레이드오프를 비교한다.
4. 최종 접근 방식을 선택하고, 선택 근거와 탈락 대안의 사유를 기록한다.
5. 변경 파일 계획, 데이터/제어 흐름, 구현 단계, 호환성 검토, 위험 완화 방안, 테스트 전략, 롤백 또는 복구 방향을 구체화한다.
6. 사용자 판단이 필요하면 아래 `사용자 판단 요청` 형식으로 `status: NEEDS_USER`를 기록하고 멈춘다.
7. 결과를 `.ai/features/[기능명]/01_plan.md`에 작성한다.
8. `risk_level` 또는 변경 성격상 사람 승인이 필요하면 산출물의 `human_gate_required`를 `true`로 기록한다.
9. 하네스는 frontmatter의 `human_gate_required: "defer_to_output"`을 보면 `01_plan.md`의 `## 단계 결과` 값을 기준으로 승인 게이트를 판단한다.

---

## 계획 원칙

- 추측보다 코드 확인을 우선한다.
- "어떤 파일을 어떻게 바꿀지"를 구체적으로 적는다.
- 구현 순서와 의존 관계를 명시한다.
- 트레이드오프를 정직하게 적고, 선택한 안의 단점을 숨기지 않는다.
- 위험 구간은 별도로 식별하고 완화 방안을 적는다.
- 기존 코드와의 하위 호환성을 우선한다. 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 깨뜨릴 가능성이 있으면 영향 범위와 대체 방안을 계획에 기록한다.
- 하위 호환성을 깨는 변경이 불가피하면 구현으로 넘기지 말고 `status: NEEDS_USER` 또는 `human_gate_required: true`로 멈추고 사용자 승인을 받는다.
- 테스트 전략은 정상 경로, 에러 경로, 엣지 케이스를 포함한다.
- 스펙에 없는 새 기능을 임의로 추가하지 않는다.
- 계획이 스펙 변경을 요구하면 `status: NEEDS_USER` 또는 `status: FAIL`로 멈춘다.

---

## 사용자 확인이 필요한 경우

다음의 경우 `human_gate_required: true` 또는 `status: NEEDS_USER`로 기록한다.

- 스펙 만족을 위해 스펙 외 코드 영역을 크게 수정해야 하는 경우
- 두 개 이상의 후보 중 선택이 사용자 경험에 직접 영향을 주는 경우
- 새 외부 의존성 추가가 필요한 경우
- 데이터 마이그레이션 등 비가역 변경이 필요한 경우
- 인증/인가, 결제, 보안 경계가 바뀌는 경우
- 공개 API나 외부 계약이 바뀌는 경우
- 공개 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값처럼 기존 코드나 사용자의 호출 계약이 깨지는 경우
- 실패 시 재시도/롤백 정책 같은 사용자 정책 결정이 필요한 경우

질문은 한 번에 모아서 하고, 각 질문에는 추천안과 근거를 함께 제시한다.

---

## 사용자 판단 요청 형식

```markdown
## 사용자 판단 요청
- status: NEEDS_USER
- 질문:
- 추천안:
- 대안:
- 기본값:
- 사용자가 답하면 재개할 단계: 01_plan
```

---

## 기록 양식

계획 확정 후 `.ai/features/[기능명]/01_plan.md`에 아래 형식으로 작성한다.

```markdown
# 01_plan - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 기능 목표
- 00_spec.md의 목표를 한두 줄로 재진술

## 구현 접근 방식
- 선택한 접근 방식을 한 문단으로 요약
- 핵심 아이디어

## 검토한 대안
- 대안 1: 내용 / 장점 / 단점 / 채택하지 않은 이유
- 대안 2:
- 대안이 1개뿐이면 "단일 안 - 다른 합리적 대안 없음"이라고 명시

## 변경 파일 계획
- src/path/to/file.py (신규): 무엇을 추가하는지
- src/path/to/another.py (수정): 어떤 함수/구간을 어떻게 변경하는지
- src/path/to/old.py (삭제): 왜 삭제하는지

## 데이터 / 제어 흐름
- 입력이 어디로 들어와 어떤 단계를 거쳐 출력으로 나가는지
- 단계 간 데이터 형태 변화
- 필요시 간단한 ASCII 다이어그램

## 구현 단계 분할
1. 단계 1: 무엇을 하는지 / 어떤 파일 / 완료 기준
2. 단계 2:
- 단계 간 의존 관계와 순서 근거

## 위험 구간
- 위험 항목:
- 완화 방안:

## 호환성 검토
- 보존해야 할 기존 인터페이스:
- 영향받는 호출부/사용자 흐름:
- 하위 호환성 위험:
- 호환성 유지 전략:
- breaking change 필요 여부: 없음 / 있음
- breaking change가 있다면 사용자 승인 필요 여부와 근거:

## 새 의존성
- 없음
- 또는 패키지명: 추가 이유 / 대체 검토한 기존 의존성

## 테스트 전략
- 검증할 케이스 목록
- 각 케이스를 unit / integration / e2e 중 어디서 검증할지
- 테스트가 어려운 부분이 있다면 그 이유와 대안

## 롤백 / 복구 방향
- 변경 실패 또는 배포 후 문제 발생 시 되돌리는 방법
- 데이터 변경이 있다면 복구 가능 여부

## 실행 승인
- risk_level: low / medium / high
- human_gate_required: true / false
- human_gate_reason:
- approval_required_before_develop: true / false

## 스펙 모호점 처리
- 스펙에서 명확하지 않아 임의로 결정한 항목과 근거
- 없으면 "없음"

## Git 기준점
- base_commit:
- diff_base_command:

## 사용자 확인 사항
- 질문과 사용자 답변 기록

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: 02_develop
- human_gate_required: true / false
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .ai/features/[기능명]/01_plan.md
- changed_files:
- harness_commit_required: true / false
- commit_created_by_model: false
- commit_message_suggestion:
- model_mismatch: false
- actual_model:
```

---

## 금지 사항

- 코드를 직접 작성하거나 수정하지 않는다.
- 스펙을 임의로 변경하지 않는다.
- 모호한 결정을 남긴 채 다음 단계로 넘기지 않는다.
- 사용자 승인이 필요한 상태를 숨기지 않는다.
