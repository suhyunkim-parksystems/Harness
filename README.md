# Local AI Development Harness

로컬 저장소에서 Codex/Claude/AGY 같은 AI 에이전트를 단계별로 실행하고, 산출물 검증과 이력 관리를 묶어서 처리하는 개발 하네스입니다.  
새 작업은 보통 `standard` 파이프라인으로 시작하면 충분합니다.

## Quick Start

```powershell
python .ai\harness_standard.py doctor
python .ai\harness_standard.py run "구현할 내용을 적습니다" --feature my-feature --yes --defaults
python .ai\harness_standard.py todo my-feature
python .ai\harness_standard.py retry my-feature --auto --yes --defaults
```

`doctor`로 환경을 확인하고, `run`으로 기능 작업을 시작합니다. 실패하거나 남은 일이 있으면 `todo`로 상태를 확인한 뒤 `retry`로 이어서 처리합니다.

## Pipelines

| Wrapper | Stages | Use Case |
| --- | --- | --- |
| `.ai\harness_fast.py` | specify -> develop -> verify | 작은 수정, 빠른 프로토타입 |
| `.ai\harness_standard.py` | specify -> develop -> review -> fix -> verify | 일반 기능 작업 기본값 |
| `.ai\harness.py` | specify -> plan -> develop -> review -> fix -> verify -> document | 큰 변경, 고위험 작업, 문서화가 필요한 작업 |

`full` 파이프라인에서는 `--deep-thinking`, `--strategy max` 같은 고비용 옵션을 사용할 수 있습니다. 기본 작업에는 `standard`를 권장합니다.
각 파이프라인의 stage 프리셋은 `.ai\presets\<mode>\*.md`에 있습니다.

## Main Commands

| Command | Description |
| --- | --- |
| `run "요청"` | 새 feature run을 생성하고 파이프라인을 실행합니다. |
| `resume <feature>` | 중단된 run을 이어서 실행합니다. |
| `auto <feature>` | 남은 단계를 자동으로 진행합니다. |
| `step <feature>` | 다음 단계 하나만 실행합니다. |
| `todo <feature>` | 현재 상태, 실패 지점, 다음 행동을 요약합니다. |
| `retry <feature>` | 실패한 단계 또는 남은 단계를 재시도합니다. |
| `approve <feature>` | 승인 대기 중인 단계를 승인합니다. |
| `doctor` | 설정, provider, 경로, 검증 명령을 점검합니다. |
| `selftest` | 하네스 자체 테스트를 실행합니다. |
| `cleanup <feature>` | run 산출물 정리를 수행합니다. |

## Common Options

| Option | Meaning |
| --- | --- |
| `--feature <name>` | run과 산출물을 묶을 feature 이름입니다. |
| `--yes` | 확인 프롬프트를 자동 승인합니다. |
| `--defaults` | 권장 기본값으로 실행합니다. |
| `--interactive` | 단계별 입력과 확인을 활성화합니다. |
| `--performance low|medium|high` | provider 예산과 실행 강도를 조절합니다. |
| `--max-verify-fix-retries <n>` | verify 실패 시 fix 재시도 횟수를 지정합니다. |
| `--timeout <seconds>` | provider 실행 제한 시간을 지정합니다. |

## Outputs

| Path | Purpose |
| --- | --- |
| `.project\runs\<feature>\run.json` | run 상태, 단계 결과, 스케줄 정보 |
| `.project\runs\<feature>\handoff.md` | 다음 에이전트가 읽을 요약과 인수인계 |
| `.project\runs\<feature>\artifacts\` | 단계별 결과 JSON, 로그, 검증 요약 |
| `.project\features\<feature>\` | feature 단위 산출물 |
| `.project\docs\` | 문서화 stage가 생성한 문서 산출물 |
| `.project\history\` | 후보, 평가, 실행 이력 |
| `.project\project_contract.md` | 프로젝트 공통 제약과 운영 규칙 |

## Layout

| Path | Purpose |
| --- | --- |
| `.ai\harness.py`, `.ai\harness_fast.py`, `.ai\harness_standard.py` | 하네스 실행 엔트리포인트 |
| `.ai\harness_core\` | 프로젝트와 무관한 하네스 코어 코드 |
| `.ai\presets\` | 프로젝트와 무관한 파이프라인 stage 프리셋 |
| `.ai\harness.config.json` | provider, model policy, generic verification 설정 |
| `.project\harness.config.json` | 현재 프로젝트에 종속적인 verification 명령 |

## Verification

검증 설정은 `.ai\harness.config.json`과 `.project\harness.config.json`을 병합해서 읽습니다. `.ai`에는 provider, model policy, generic verification 명령을 두고, 현재 프로젝트에 종속적인 검증 명령은 `.project\harness.config.json`에 둡니다.

단계 결과가 `test_commands` 또는 `recommended_verification_commands`를 제공하면 하네스가 허용 목록에 맞는 명령만 골라 동적 검증으로 실행할 수 있습니다. 통과했고 `persist: true`인 동적 검증 명령은 `.project\harness.config.json`에 추가됩니다.

검증이 실패하면 `todo`에서 실패 사유와 다음 행동을 확인합니다. 이후 `retry <feature> --auto`로 fix/verify 흐름을 이어갈 수 있습니다.

## Recovery Notes

- provider가 빈 결과를 내거나 중단되면 `todo <feature>`로 상태를 먼저 확인합니다.
- `run.json`과 `handoff.md`를 보면 어떤 단계가 완료됐고 무엇을 다시 해야 하는지 빠르게 알 수 있습니다.
- 하네스는 JSON 파일을 읽을 때 UTF-8 BOM을 허용합니다. 쓰기는 UTF-8 without BOM을 기본으로 합니다.
- Git commit은 하네스가 관리합니다. 에이전트 단계 안에서 직접 commit/reset/push하지 않는 것을 원칙으로 둡니다.

## Maintenance

```powershell
python .ai\harness.py selftest --failfast
python .ai\pc_review.py
```

`selftest`는 하네스 변경 뒤 기본 회귀 확인용입니다. `pc_review.py`는 provider 후보와 실행 품질을 점검할 때 사용합니다.
