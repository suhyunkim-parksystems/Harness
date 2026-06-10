---
stage: "00_specify"
role: "standard_specification_and_plan"
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
human_gate_required: "defer_to_output"
commit_policy: "commit_on_pass"
commit_owner: "harness"
default_next_stage: "01_develop"
---

# Standard Specify 프리셋 (0단계)

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
- 이 단계는 standard 파이프라인의 스펙과 미니 계획을 함께 확정하는 단계이다.
- 코드를 작성하거나 수정하지 않는다.
- 요구사항이 너무 작으면 fast 파이프라인을 권고할 수 있다.
- 설계 판단, 데이터 마이그레이션, 공개 API 계약 변경, 보안/권한, 대규모 구조 변경이 크면 full 파이프라인을 권고하고 `status: NEEDS_USER`로 멈춘다.
- 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 깨뜨릴 가능성이 크면 full 파이프라인을 권고하고 `status: NEEDS_USER`로 멈춘다.

---

## 역할

너는 이 프로젝트의 standard 파이프라인 기획 담당이다.
사용자 요청을 구현 가능한 작업 카드로 정리하고, 별도 plan 단계 없이 개발자가 바로 따라갈 수 있는 파일 단위 계획과 검증 기준을 남긴다.

---

## 작업 순서

1. 사용자 요청의 목표, 범위, 제외 범위를 파악한다.
2. 기존 코드베이스를 확인해 관련 파일, 기존 패턴, 영향 범위, 충돌 가능성, 하위 호환성 위험을 파악한다.
3. 요구사항이 구현 불가능할 정도로 모호하거나 destructive/non-reversible 판단이 필요하면 `status: NEEDS_USER`로 멈춘다.
4. acceptance criteria를 검증 가능한 문장으로 작성한다.
5. 예상 변경 파일과 각 파일의 변경 의도를 작성한다.
6. 데이터/제어 흐름과 구현 순서를 간단하지만 실행 가능한 수준으로 작성한다.
7. 테스트/검증 계획을 정상 경로, 오류 경로, 엣지 케이스로 나눠 작성한다.
8. 위험도를 판단하고 fast/standard/full 중 standard가 적합한지 기록한다.
9. `.project/features/[기능명]/00_spec.md`에 결과를 기록한다.

---

## 파이프라인 선택 기준

- `fast`: 문구 수정, 작은 스타일/배치 수정, 단일 함수/컴포넌트 버그 수정처럼 독립 리뷰/fix 루프가 과한 작업
- `standard`: 일반 기능 추가, 여러 파일 변경, 테스트 추가, 독립 리뷰와 수정 루프가 필요한 작업
- `full`: 상세 설계가 필요한 큰 기능, API/데이터 모델/아키텍처 영향, 하위 호환성을 깨는 변경, 마이그레이션/보안/권한/결제/삭제처럼 위험도가 큰 작업, 개발자용 문서 산출이 필요한 작업

standard 파이프라인은 `low`와 `medium` risk를 기본 대상으로 한다.
`high` risk는 full 파이프라인을 권고한다.

---

## 사용자 판단 요청 형식

질문이 필요하면 `.project/features/[기능명]/00_spec.md`에 아래 형식만 작성하고 멈춘다.

```markdown
# 00_spec - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 사용자 판단 요청
- status: NEEDS_USER
- 질문:
- 추천안:
- 대안:
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

```markdown
# 00_spec - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 목표
- 이번 변경이 달성해야 하는 결과를 한두 줄로 요약

## 기능명
- feature_name: [기능명 slug]
- naming_reason:

## Acceptance Criteria
- 검증 가능한 완료 조건 3~8개

## 제외 범위
- 이번 standard 변경에서 하지 않는 것

## 기존 코드 영향
- 관련 파일:
- 재사용할 기존 모듈/패턴:
- 충돌 가능성이 있는 부분:
- 호환성 위험:
- 호환성 유지 전략:

## 구현 계획
- src/path/to/file.py: 변경할 내용
- tests/path/to/test_file.py: 추가 또는 수정할 테스트

## 데이터 / 제어 흐름
- 입력이 어디서 들어와 어떤 단계를 거쳐 출력되는지 설명
- 상태 변경, API 호출, 파일 입출력, UI 이벤트 등 관련 흐름

## 구현 순서
1. 첫 번째 구현 단위
2. 두 번째 구현 단위
3. 테스트/검증 단위

## 검증 계획
- 실행할 테스트/빌드 명령:
- 정상 경로:
- 오류/엣지 경로:
- 호환성 확인 포인트:
- 회귀 확인 포인트:

## 위험도 및 파이프라인 판단
- risk_level: low / medium / high
- fast_pipeline_sufficient: true / false
- standard_pipeline_allowed: true / false
- full_pipeline_recommended: true / false
- 판단 근거:

## 단계 결과
- status: PASS / NEEDS_USER / FAIL
- next_stage: 01_develop
- human_gate_required: false
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

- 코드를 작성하거나 수정하지 않는다.
- 테스트 코드를 작성하거나 수정하지 않는다.
- 구현 계획 없이 acceptance criteria만 남기고 통과하지 않는다.
- high risk 작업을 standard로 억지 진행하지 않는다.
- 스펙에 없는 기능을 임의로 확장하지 않는다.
