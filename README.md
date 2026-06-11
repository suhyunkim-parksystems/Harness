# Local AI Development Harness

로컬 저장소에서 Codex/Claude/AGY 같은 AI 에이전트 CLI를 단계별 파이프라인으로 실행하고, 산출물 검증·커밋·이력 관리를 하네스가 책임지는 개발 하네스입니다.

- 모델이 코드를 쓰고, **하네스가 검증하고 커밋합니다.** 최종 PASS/FAIL 판정권은 모델이 아니라 하네스에 있습니다.
- 단계마다 서로 다른 프로바이더를 배정하는 **모델 독립성 정책**(코드 작성자와 리뷰어 분리, 인접 단계 동일 모델 금지)을 강제합니다.
- 새 작업은 보통 `standard` 파이프라인으로 시작하면 충분합니다.

## Quick Start

```powershell
python .ai\harness_standard.py doctor
python .ai\harness_standard.py run "구현할 내용을 적습니다" --feature my-feature --yes --defaults
python .ai\harness_standard.py todo my-feature
python .ai\harness_standard.py retry my-feature --auto --yes --defaults
```

`doctor`로 환경을 확인하고, `run`으로 기능 작업을 시작합니다. 실패하거나 남은 일이 있으면 `todo`로 상태와 다음 명령을 확인한 뒤 `retry`로 이어서 처리합니다.

## Pipelines

| Wrapper | Stages | Use Case |
| --- | --- | --- |
| `.ai\harness_fast.py` | specify -> develop -> verify | 작은 수정, 빠른 프로토타입 |
| `.ai\harness_standard.py` | specify -> develop -> review -> fix -> verify | 일반 기능 작업 기본값 |
| `.ai\harness.py` | specify -> plan -> develop -> review -> fix -> verify -> document | 큰 변경, 고위험 작업, 문서화가 필요한 작업 |

`full` 파이프라인에서만 `--deep-thinking`, `--strategy`, `--cross-validation` 같은 고비용 옵션을 사용할 수 있습니다. 기본 작업에는 `standard`를 권장합니다.
각 파이프라인의 stage 프리셋은 `.ai\presets\<mode>\*.md`에 있으며, 프리셋 frontmatter의 `allowed_writes`/`forbidden_writes`를 하네스가 스냅샷 비교로 실제 강제합니다.

## Main Commands

| Command | Description |
| --- | --- |
| `run "요청"` | 새 feature run을 생성하고 파이프라인을 실행합니다. |
| `resume <feature>` | 중단된 run을 이어서 실행합니다. |
| `auto <feature>` | 남은 단계를 자동으로 진행합니다. |
| `step <feature>` | 다음 단계 하나만 실행합니다. |
| `todo [feature]` | 현재 상태, 실패 지점, 다음 실행할 명령을 요약합니다. 생략하면 전체 run 목록. |
| `retry <feature>` | 실패한 단계를 재시도합니다. 기본은 실패 컨텍스트를 프롬프트에 추가하고, `--same`이면 동일 프롬프트로 재시도합니다. |
| `approve <feature>` | human gate로 멈춘 run을 승인합니다. |
| `doctor [--deep]` | 설정, provider, 경로를 점검합니다. `--deep`은 provider 스모크 테스트까지 실행합니다. |
| `selftest` | 하네스 자체 테스트(531개)를 실행합니다. |
| `cleanup <feature>` | run 디렉터리를 삭제합니다. `--keep-feature`로 feature 산출물은 보존할 수 있습니다. |

## Common Options

| Option | Meaning |
| --- | --- |
| `--feature <name>` | run과 산출물을 묶을 feature slug입니다. 생략하면 모델이 spec 단계에서 정합니다. |
| `--yes` | human gate를 자동 승인합니다. |
| `--defaults` | 모호한 결정을 모델 권장 기본값으로 진행합니다. |
| `--interactive` | NEEDS_USER 질문을 터미널에서 받아 같은 단계를 재시도합니다. |
| `--performance lite\|medium\|high` | provider 모델/추론 강도 프로필입니다. 기본 `medium`. |
| `--timeout <seconds>` | provider 실행 제한 시간입니다. 기본 3600. |
| `--max-steps <n>` | 자동 진행할 최대 단계 전환 수입니다. 기본 30. |
| `--max-verify-fix-retries <n>` | verify 실패 -> fix 재시도 사이클 상한입니다. 기본 3. |
| `--deep-thinking` | (full 전용) plan 단계를 멀티 프로바이더 내부 기획으로 실행합니다. `--strategy parallel\|sequential\|max`로 전략을 고릅니다. |
| `--cross-validation` | (full 전용) 구현을 보지 않는 블라인드 수용테스트 트랙을 병렬로 돌리고, 두 트랙이 CLEAN으로 합류할 때만 자동 통과시킵니다. 3개 provider 전원 가용 필요. |

## Planning & Batch Tools

단일 run 위에 얹어 쓰는 상위 도구들입니다.

| Tool | Purpose |
| --- | --- |
| `.ai\deep_interview.py "대략적 요청"` | 모호한 요청을 다회 인터뷰로 다듬어 완성된 `harness run` 명령 한 줄을 출력합니다. |
| `.ai\project_planning.py --plan-file 기획서.docx` | 기획서(docx/md/txt/pdf)를 feature 단위로 분해해 의존성 순서가 잡힌 `plan.txt`/`batch.json`/`decomposition.json`을 `.project\projects\<slug>\`에 생성합니다. |
| `.ai\orchestrate.py run [batch.json]` | batch.json의 run 큐를 순차 실행하는 배치 슈퍼바이저입니다. 재시도/승인/merge까지 처리합니다. |
| `.ai\pc_review.py [--yes]` | 누적된 Project Contract 후보를 에이전트 리뷰로 승인/기각합니다. orchestrate가 run 사이마다 `--yes`로 자동 호출합니다. |

### Orchestrate

```powershell
python .ai\project_planning.py --plan-file 기획서.docx --project my-project
python .ai\orchestrate.py run .project\projects\my-project\batch.json
```

진행 상황은 별도 터미널에서 확인합니다.

```powershell
while ($true) {
  Clear-Host
  Get-Date
  python .ai\orchestrate.py status .project\projects\my-project\batch.json
  Start-Sleep -Seconds 5
}
```

batch.json은 run마다 `feature`와 `request`만 필수이고 나머지는 기본값이 채워집니다
(`pipeline: standard`, `performance: medium`, `decision_mode: defaults`, `timeout: 3600`, `max_attempts: 3` 등).

```json
{
  "runs": [
    { "feature": "item-model", "request": "아이템 도메인 모델을 만든다" },
    { "feature": "item-api", "request": "아이템 CRUD API를 만든다", "pipeline": "full" }
  ]
}
```

실패는 자동 분류되어 정책대로 처리됩니다: 일시 오류는 횟수 제한 재시도, rate limit은 최대 24시간까지 5분 간격 대기, 인증 실패·human gate·수동 개입 필요는 즉시 멈추고 사람에게 넘깁니다. run 상태는 batch.json에 orchestrate가 기록하므로 `state` 필드는 직접 수정하지 않습니다. 중단해도 같은 명령으로 재개됩니다.

## Outputs

| Path | Purpose |
| --- | --- |
| `.project\runs\<feature>\run.json` | run 상태, 단계 결과, provider 스케줄 |
| `.project\runs\<feature>\handoff.md` | 다음 에이전트/사람이 읽을 인수인계 요약 |
| `.project\runs\<feature>\prompts\`, `logs\`, `verification\` | 단계별 프롬프트, provider stdout/stderr 로그, 하네스 검증 결과 |
| `.project\features\<feature>\` | 단계 산출물(`00_spec.md` 등)과 `*.result.json` |
| `.project\projects\<project>\` | project_planning이 만든 plan.txt / batch.json / decomposition.json |
| `.project\docs\` | document stage가 생성한 문서 |
| `.project\history\` | run 이력 index/summary, PC 후보(pc_candidates.json) |
| `.project\project_contract.md` | 프로젝트 공통 제약과 운영 규칙 (append-only) |

## Layout

| Path | Purpose |
| --- | --- |
| `.ai\harness.py`, `.ai\harness_fast.py`, `.ai\harness_standard.py` | 파이프라인 실행 엔트리포인트 |
| `.ai\harness_core\` | 프로젝트와 무관한 하네스 코어 (스케줄링, 검증, 정책, 이력 등) |
| `.ai\presets\` | 파이프라인 stage 프리셋 |
| `.ai\orchestrate.py`, `.ai\pc_review.py` | 배치 슈퍼바이저, PC 후보 리뷰어 |
| `.ai\deep_interview.py`, `.ai\project_planning.py` | 요청 다듬기, 기획서 분해 |
| `.ai\selftests\` | 하네스 자체 테스트 (가짜 provider 기반 E2E 포함) |
| `.ai\harness.config.json` | provider, model policy, generic verification 설정 |
| `.project\harness.config.json` | 현재 프로젝트 종속적인 verification 명령 |

## Verification

검증 설정은 `.ai\harness.config.json`과 `.project\harness.config.json`을 병합해서 읽습니다. `.ai`에는 provider, model policy, generic verification 명령을 두고, 현재 프로젝트에 종속적인 검증 명령은 `.project\harness.config.json`에 둡니다.

단계 결과가 `test_commands` 또는 `recommended_verification_commands`를 제공하면 하네스가 허용 목록(pytest, npm test, dotnet 등)에 맞는 명령만 골라 동적 검증으로 실행합니다. 셸 래퍼·파이프·저장소 밖 경로는 거부됩니다. 통과했고 `persist: true`인 동적 검증 명령은 `.project\harness.config.json`에 추가됩니다.

모델이 `status: PASS`를 기록해도 하네스 검증 명령이 하나라도 실패하면 해당 단계는 FAIL로 덮어쓰고 fix 단계로 되돌립니다. 검증이 실패하면 `todo`에서 실패 사유와 다음 행동을 확인한 뒤 `retry <feature> --auto`로 이어갑니다.

## Recovery Notes

- provider가 빈 결과를 내거나 중단되면 `todo <feature>`로 상태를 먼저 확인합니다. 다음 실행할 명령을 그대로 알려줍니다.
- `run.json`과 `handoff.md`를 보면 어떤 단계가 완료됐고 무엇을 다시 해야 하는지 빠르게 알 수 있습니다.
- 하네스는 JSON 파일을 읽을 때 UTF-8 BOM을 허용합니다. 쓰기는 UTF-8 without BOM이 기본입니다.
- Git commit은 하네스가 관리합니다. 에이전트 단계 안에서 직접 commit/reset/push하지 않는 것을 원칙으로 둡니다.
- 완료된 run의 브랜치는 base에 merge(또는 삭제)해야 다음 파이프라인을 시작할 수 있습니다.

## Maintenance

```powershell
python .ai\harness.py selftest --failfast
python .ai\pc_review.py
```

`selftest`는 하네스 변경 뒤 기본 회귀 확인용입니다(pyright 타입체크 게이트 포함, 전체 약 7~8분). `pc_review.py`는 쌓인 Project Contract 후보를 정리할 때 사용합니다.
