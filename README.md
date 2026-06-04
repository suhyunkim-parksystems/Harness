# Local AI Development Harness

이 저장소는 로컬 AI 에이전트들을 단계별로 오케스트레이션하는 개발 하네스입니다.

하네스의 목적은 단순히 프롬프트를 실행하는 것이 아니라, 기능 개발을 `스펙 -> 구현 -> 리뷰/수정 -> 검증 -> 기록` 흐름으로 고정하고, 각 단계의 산출물과 검증 결과를 프로젝트 안에 남기는 것입니다.

주 사용자는 Windows 환경에서 Python, Codex, Claude, Antigravity 계열 CLI를 로컬로 실행하는 개발자입니다.

---

## 빠른 시작

처음 보는 사람은 아래 순서만 따라가면 됩니다.

### 1. AI 하네스 상태 확인

빠른 파이프라인:

```powershell
python .ai\harness_fast.py doctor
```

표준 파이프라인:

```powershell
python .ai\harness_standard.py doctor
```

풀 파이프라인:

```powershell
python .ai\harness.py doctor
```

provider CLI까지 실제로 짧게 호출해 보고 싶으면:

```powershell
python .ai\harness_fast.py doctor --deep
python .ai\harness_standard.py doctor --deep
python .ai\harness.py doctor --deep
```

`doctor --deep`는 Codex, Claude, Antigravity CLI를 실제로 호출하므로 일반 `doctor`보다 오래 걸릴 수 있습니다.

### 2. 가장 흔한 실행 명령

작은 작업을 빠르게 끝내고 싶으면 보통 fast 파이프라인을 사용합니다.

```powershell
python .ai\harness_fast.py run "요청 내용을 여기에 작성" --feature feature-name --yes --defaults
```

리뷰/수정 단계를 포함한 일반 작업은 standard 파이프라인을 사용합니다.

```powershell
python .ai\harness_standard.py run "요청 내용을 여기에 작성" --feature feature-name --yes --defaults
```

계획, 리뷰, 수정, 검증, 문서 생성까지 모두 포함하려면 full 파이프라인을 사용합니다.

```powershell
python .ai\harness.py run "요청 내용을 여기에 작성" --feature feature-name --yes --defaults
```

`feature-name`은 소문자, 숫자, 하이픈만 쓰는 짧은 영문 slug를 권장합니다.

예:

```powershell
python .ai\harness_standard.py run "설정 항목에 도움말 툴팁을 추가해줘" --feature settings-tooltips --yes --defaults
```

---

## 저장소 구조

```text
presets/fast/
  3단계 빠른 파이프라인 프리셋

presets/standard/
  5단계 표준 파이프라인 프리셋

presets/full/
  7단계 풀 파이프라인 프리셋

.ai/
  하네스 본체, 설정, 템플릿, 실행 상태, 기능 산출물, 히스토리
```

주요 하네스 파일:

```text
.ai/harness_fast.py       fast 파이프라인 진입점
.ai/harness_standard.py   standard 파이프라인 진입점
.ai/harness.py            full 파이프라인 및 공통 하네스 구현
.ai/harness.config.json   하네스 검증 명령 설정
.ai/templates/            문서 생성 등 보조 템플릿
```

run을 실행하면 아래 폴더들이 생성될 수 있습니다.

```text
.ai/runs/<feature>/       run 상태, 프롬프트, 로그, handoff, 검증 결과
.ai/features/<feature>/   단계별 사람이 읽는 산출물과 result JSON
.ai/history/              완료된 run의 장기 히스토리
.ai/docs/                 full 파이프라인 문서 산출물
```

---

## 하네스가 해결하려는 문제

AI로 기능을 개발하면 다음 문제가 자주 생깁니다.

- 처음 요청이 모호한데 바로 코드를 고침
- 구현자는 통과했다고 말하지만 실제 빌드/테스트는 실패함
- 리뷰에서 나온 지적이 사라짐
- 검증 실패 원인이 다음 수정 단계로 잘 전달되지 않음
- 여러 모델이 만든 산출물이 흩어져 나중에 왜 그렇게 만들었는지 찾기 어려움
- 장기 프로젝트에서 리스크와 미래 개선점이 누적 관리되지 않음

이 하네스는 기능 단위를 하나의 run으로 다루고, 각 run을 단계별로 진행합니다.

각 단계는 다음 산출물을 남깁니다.

```text
.ai/features/<feature>/<stage>.md
.ai/features/<feature>/<stage>.result.json
```

하네스는 result JSON을 읽어 다음 단계로 진행할지, 사용자 확인이 필요한지, 실패했는지 판단합니다.

---

## 파이프라인 선택 기준

### fast

명령:

```powershell
python .ai\harness_fast.py ...
```

단계:

```text
00_specify -> 01_develop -> 02_verify
```

권장 용도:

- 작은 UI 수정
- 명확한 버그 수정
- 단일 기능 추가
- 빠른 프로토타입
- 리뷰 단계를 별도로 오래 돌릴 필요가 없는 작업

권장 모델:

```text
00_specify : Antigravity
01_develop : Claude
02_verify  : Codex
```

### standard

명령:

```powershell
python .ai\harness_standard.py ...
```

단계:

```text
00_specify -> 01_develop -> 02_review -> 03_fix -> 04_verify
```

권장 용도:

- 일반적인 기능 개발
- 리뷰와 수정 단계를 분리하고 싶은 작업
- 테스트 추가가 필요한 변경
- 여러 파일을 건드리는 변경
- 대부분의 일상 개발

권장 모델:

```text
00_specify : Codex
01_develop : Claude
02_review  : Antigravity
03_fix     : Claude
04_verify  : Codex
```

### full

명령:

```powershell
python .ai\harness.py ...
```

단계:

```text
00_specify -> 01_plan -> 02_develop -> 03_review -> 04_fix -> 05_verify -> 06_document
```

권장 용도:

- 위험도가 높은 작업
- 설계 판단이 중요한 작업
- 문서 산출물이 필요한 작업
- 장기 유지보수 관점에서 상세 기록이 필요한 기능
- API 계약, 데이터 흐름, 구조 변경이 포함된 작업

권장 모델:

```text
00_specify : Codex
01_plan    : Antigravity
02_develop : Claude
03_review  : Antigravity
04_fix     : Claude
05_verify  : Codex
06_document: Antigravity
```

---

## 자동 실행 기본 패턴

### fast 자동 실행

```powershell
python .ai\harness_fast.py run "요청 내용" --feature feature-name --yes --defaults
```

verify 실패 후 develop으로 되돌아가는 반복 횟수를 늘리려면:

```powershell
python .ai\harness_fast.py run "요청 내용" --feature feature-name --yes --defaults --max-verify-fix-retries 5
```

### standard 자동 실행

```powershell
python .ai\harness_standard.py run "요청 내용" --feature feature-name --yes --defaults
```

검증/수정 반복을 더 허용하려면:

```powershell
python .ai\harness_standard.py run "요청 내용" --feature feature-name --yes --defaults --max-verify-fix-retries 5
```

### full 자동 실행

```powershell
python .ai\harness.py run "요청 내용" --feature feature-name --yes --defaults
```

타임아웃, 자동 전환 최대 단계 수, verify/fix 반복 횟수를 직접 지정하려면:

```powershell
python .ai\harness.py run "요청 내용" --feature feature-name --yes --defaults --timeout 3600 --max-steps 30 --max-verify-fix-retries 5
```

---

## 명령어 전체 설명

아래 예시는 full 파이프라인 기준으로 `.ai\harness.py`를 사용합니다.

fast를 쓰려면 `.ai\harness_fast.py`로 바꾸면 됩니다.

standard를 쓰려면 `.ai\harness_standard.py`로 바꾸면 됩니다.

### run

새 run을 만들고 자동으로 끝까지 진행합니다.

```powershell
python .ai\harness.py run "요청 내용" --feature feature-name --yes --defaults
```

가장 자주 쓰는 명령입니다.

### resume

모델이 현재 단계 산출물을 작성한 뒤, 하네스가 그 결과를 읽고 다음 단계로 진행합니다.

```powershell
python .ai\harness.py resume feature-name
```

resume 후 계속 자동 진행하려면:

```powershell
python .ai\harness.py resume feature-name --auto --yes --defaults
```

### auto

이미 존재하는 run을 현재 멈춘 지점부터 자동으로 이어갑니다.

```powershell
python .ai\harness.py auto feature-name --yes --defaults
```

`auto`는 현재 단계 하나만 실행하는 명령이 아닙니다. 막히거나 완료될 때까지 다음 단계들을 계속 진행할 수 있습니다.

### step

현재 run의 현재 stage 하나만 실행하고 멈춥니다. stage 결과를 반영한 뒤 다음 stage prompt를 생성하는 곳까지만 진행하므로, 시연이나 수동 검토 흐름에 적합합니다.

```powershell
python .ai\harness.py step feature-name --defaults
```

현재 상태가 human gate에서 막혀 있고, 그 gate를 승인한 뒤 다음 stage 하나만 실행하려면:

```powershell
python .ai\harness.py step feature-name --yes --defaults
```

full 파이프라인을 한 단계씩 보여주는 예:

```powershell
python .ai\harness.py run "요청 내용" --feature feature-name --defaults --max-steps 1
python .ai\harness.py step feature-name --defaults
python .ai\harness.py step feature-name --yes --defaults
python .ai\harness.py step feature-name --yes --defaults
python .ai\harness.py step feature-name --yes --defaults
python .ai\harness.py step feature-name --yes --defaults
python .ai\harness.py step feature-name --yes --defaults
python .ai\harness.py step feature-name --yes --defaults
```

### approve

사용자 확인이 필요한 human gate에서 막힌 run을 승인합니다.

```powershell
python .ai\harness.py approve feature-name
```

승인 후 자동으로 계속 진행하려면:

```powershell
python .ai\harness.py approve feature-name --auto --yes --defaults
```

### retry

현재 막힌 단계를 재시도합니다.

```powershell
python .ai\harness.py retry feature-name
```

기본 retry는 실패 이유, handoff, 최근 로그, 검증 결과를 포함한 보강 프롬프트를 새로 생성합니다.

기존 프롬프트를 그대로 다시 쓰려면:

```powershell
python .ai\harness.py retry feature-name --same
```

프롬프트만 생성하고 provider 실행은 하지 않으려면:

```powershell
python .ai\harness.py retry feature-name --prompt-only
```

retry 성공 후 다음 단계까지 자동 진행하려면:

```powershell
python .ai\harness.py retry feature-name --auto --yes --defaults
```

retry 전에 기존 stage 산출물은 아래 위치로 보관됩니다.

```text
.ai/runs/<feature>/retry_archives/
```

이렇게 해야 오래된 실패 결과를 하네스가 다시 읽는 일을 막을 수 있습니다.

### todo

진행 중이거나 완료된 run 목록과 다음에 실행할 수 있는 명령을 봅니다. `next`는 추천 명령, `step`은 한 stage만 실행하는 명령, `auto`는 끝까지 이어가는 명령입니다.

```powershell
python .ai\harness.py todo
```

특정 run을 지정하면 상태, 현재 stage, provider, 산출물 경로, result JSON, handoff, 최근 이벤트, 다음 명령을 더 자세히 봅니다.

```powershell
python .ai\harness.py todo feature-name
```

### doctor

프리셋, provider CLI, 현재 변경 파일 등 하네스 환경을 점검합니다.

```powershell
python .ai\harness.py doctor
```

provider smoke test까지 하려면:

```powershell
python .ai\harness.py doctor --deep
```

### cleanup

run 상태를 삭제합니다.

```powershell
python .ai\harness.py cleanup feature-name
```

생성된 `.ai/features/<feature>` 산출물은 남기고 `.ai/runs/<feature>`만 삭제하려면:

```powershell
python .ai\harness.py cleanup feature-name --keep-feature
```

주의: cleanup은 로컬 하네스 기록을 지웁니다. 필요한 로그나 산출물이 있으면 먼저 확인하세요.

---

## 주요 옵션

### --feature

run의 기능 이름을 지정합니다.

```powershell
--feature metric-tooltips
```

권장 규칙:

- 소문자 영어
- 숫자 허용
- 단어 구분은 하이픈
- 공백, 한글, 특수문자 피하기

좋은 예:

```text
metric-tooltips
loading-state
simulation-frequency
```

### --yes

자동 실행 중 human gate가 나왔을 때 가능한 경우 승인하고 계속 진행합니다.

다만 모델이 `NEEDS_USER`를 반환하거나 실제로 사용자 판단이 필요한 경우에는 멈출 수 있습니다. `--interactive`를 함께 쓰면 구조화된 질문은 터미널에서 답하고 이어갈 수 있습니다.

### --defaults

모호한 판단이 있을 때 모델이 권장 기본값을 선택하게 합니다.

사용자에게 자주 물어보지 않고 진행하고 싶을 때 사용합니다.

`--interactive`와 함께 사용할 수 없습니다.

### --interactive

모델이 `NEEDS_USER`와 `questions`를 반환하면 하네스가 터미널에 질문을 보여주고 답변을 받은 뒤 같은 stage를 다시 실행합니다.

선택지는 `1`, `2`, `3`처럼 번호로 고르고, yes/no 질문은 `yes`, `y`, `no`, `n`으로 답할 수 있습니다. 대소문자는 구분하지 않습니다.

`--defaults`와 함께 사용할 수 없습니다. `--yes`와는 함께 사용할 수 있으며, 이 경우 질문은 interactive가 처리하고 human gate 승인은 `--yes`가 처리합니다.

예:

```powershell
python .ai\harness.py run "요청 내용" --feature feature-name --yes --interactive
```

이미 `NEEDS_USER`로 막힌 run도 같은 모드로 이어갈 수 있습니다.

```powershell
python .ai\harness.py resume feature-name --auto --yes --interactive
```

### --deep-thinking

full 파이프라인 전용 옵션입니다. 외부 stage는 그대로 두고 `01_plan` 내부에서만 여러 provider가 비공개 후보 계획을 만들게 한 뒤, 최종 결과만 공식 `01_plan.md`로 남깁니다.

중간 후보 계획은 공식 산출물이나 커밋으로 남지 않습니다. 사용자는 `.ai/features/<feature>/`에서 평소처럼 `01_plan.md` 한 개만 보게 되며, 일반 `01_plan`이 조금 더 오래 걸리는 것으로만 보면 됩니다.

```powershell
python .ai\harness.py run "요청 내용" --feature feature-name --yes --defaults --deep-thinking
```

이 옵션은 최소 2개의 사용 가능한 planning provider가 필요합니다. provider 선호 순서와 내부 지시문은 `.ai/harness.config.json`의 `deep_thinking` 설정에서 조정합니다. 기존 `--heavy-thinking`과 `heavy_thinking` 설정은 호환 alias로 계속 읽습니다.

### --strategy

`--deep-thinking`과 함께 쓰는 옵션으로, 01_plan 내부 계획 전략을 고릅니다.

```powershell
python .ai\harness.py run "요청 내용" --feature feature-name --yes --defaults --deep-thinking --strategy parallel
python .ai\harness.py run "요청 내용" --feature feature-name --yes --defaults --deep-thinking --strategy sequential
python .ai\harness.py run "요청 내용" --feature feature-name --yes --defaults --deep-thinking --strategy max
```

- `parallel` (기본값): 사용 가능한 planning provider들이 서로의 결과를 보지 않고(블라인드) **독립 초안을 병렬로** 작성한 뒤, 한 명이 그 초안들을 익명으로 받아 **방향 하나를 선택하고 좋은 디테일만 체리픽하여** 최종 `01_plan.md`로 종합합니다. 스펙이 비교적 자유롭고 구현 방향 자체를 넓게 탐색하고 싶을 때 적합합니다.
- `sequential`: 한 provider가 만든 초안을 다음 provider가 이어받아 보강하는 릴레이 방식입니다. 사람이 SPEC 단계에서 방향을 이미 충분히 구체화한 경우처럼, 한 줄기를 깊게 다듬는 것이 더 나은 상황에 적합합니다.
- `max`: `parallel`의 넓이(블라인드 독립 초안 → 방향 선택)에 **grounded 순차 릴레이로 깊이**를 더합니다. 방향을 고른 뒤 → 다른 provider가 계획이 언급한 파일·심볼을 **실제 코드로 대조·교정·심화**하고 → 마지막으로 owner가 **사전 부검(pre-mortem)** 후 최종 `01_plan.md`를 확정합니다. 비용이 가장 크며(3 agent 기준 약 6콜), 틀린 계획의 하류 비용이 큰 **가장 무겁고 신중해야 할 작업** 전용입니다. 자동 게이팅은 없고 사람이 직접 선택합니다.

`--strategy`는 `--deep-thinking`이 있을 때만 받습니다. `--deep-thinking` 없이 `--strategy`를 주면 오류로 거부됩니다. `--strategy`를 생략하면 `deep_thinking.strategy` 설정값(기본 `parallel`)을 따릅니다.

### --timeout

각 provider 실행의 최대 대기 시간을 초 단위로 지정합니다.

```powershell
--timeout 3600
```

### --max-steps

자동 실행 중 최대 단계 전환 횟수를 지정합니다.

```powershell
--max-steps 30
```

무한 루프를 막기 위한 안전장치입니다.

### --max-verify-fix-retries

verify 실패 후 fix/develop 단계로 되돌아가는 반복 횟수를 지정합니다.

```powershell
--max-verify-fix-retries 5
```

기본값은 3입니다.

### --performance

provider 모델 성능 프로필을 지정합니다.

```powershell
--performance lite
--performance medium
--performance high
```

기본값은 `medium`입니다.

---

## 단계 산출물 규칙

각 stage는 사람이 읽는 Markdown과 하네스가 읽는 JSON을 함께 남깁니다.

예:

```text
.ai/features/metric-tooltips/00_spec.md
.ai/features/metric-tooltips/00_spec.result.json
```

하네스는 `.result.json`을 먼저 읽습니다.

기존 호환성을 위해 `.result.json`이 없으면 Markdown의 `## 단계 결과` 섹션을 읽으려고 시도합니다.

result JSON의 최소 필드는 다음과 같습니다.

```json
{
  "status": "PASS",
  "next_stage": "01_develop",
  "human_gate_required": false,
  "blocking_reason": ""
}
```

사용 가능한 status:

```text
PASS        단계 성공
FAIL        단계 실패
SKIPPED     단계 스킵
NEEDS_USER  사용자 판단 필요
```

추가로 자주 쓰는 필드:

```json
{
  "risk_level": "low",
  "changed_files": [
    "path/to/file"
  ],
  "test_commands": [
    {
      "name": "project_tests",
      "command": ["python", "-m", "pytest", "tests"],
      "cwd": ".",
      "timeout_seconds": 600,
      "persist": true
    }
  ],
  "verification_summary": {
    "status": "PASS"
  },
  "fix_inputs": {
    "accepted": [],
    "rejected": [],
    "deferred": []
  },
  "history_notes": {
    "implemented": [],
    "risks": [],
    "future_improvements": [],
    "decisions": [],
    "unresolved_items": []
  }
}
```

`history_notes`는 장기 히스토리에 들어갈 사람이 읽는 요약입니다. 한국어로 작성하는 것을 권장합니다.

---

## 검증 정책

하네스 검증 명령은 `.ai/harness.config.json`에 있습니다.

검증 명령은 이 하네스를 적용하는 실제 프로젝트에 맞게 설정합니다.

예:

```json
{
  "verification": {
    "enabled": true,
    "required": true,
    "timeout_seconds": 600,
    "commands": [
      {
        "name": "project_tests",
        "command": [
          "your",
          "test",
          "command"
        ]
      },
      {
        "name": "git_diff_check",
        "command": [
          "git",
          "-c",
          "safe.directory={root}",
          "diff",
          "--check"
        ]
      }
    ]
  }
}
```

verify stage에서 모델이 `PASS`라고 해도, 하네스 검증 명령이 실패하면 하네스가 최종 판정을 `FAIL`로 바꾸고 fix/develop 단계로 되돌립니다.

검증 결과는 아래에 저장됩니다.

```text
.ai/runs/<feature>/verification/latest.json
```

각 명령의 stdout/stderr도 같은 폴더에 저장됩니다.

---

## Deep Thinking 설정

full 파이프라인의 `--deep-thinking`은 `.ai/harness.config.json`의 `deep_thinking` 설정을 사용합니다. 기존 `heavy_thinking` 설정은 `deep_thinking`이 없을 때만 fallback으로 읽습니다.

공통 필드:

- `strategy`: 기본 전략. `parallel`(기본), `sequential`, `max`. CLI `--strategy`가 이 값을 덮어씁니다.
- `plan_stage`: 내부 계획을 적용할 stage. 기본값은 `01_plan`.
- `provider_order`: planning provider 선호 순서.
- `min_available_providers`: 필요한 최소 provider 수. 기본값은 2.
- `persist_intermediate_outputs`: 중간 후보 계획을 보존할지 여부. 기본값은 false.
- `anonymize_candidates`: 후보를 종합/참조할 때 작성 provider 신원(`- provider:` 라벨, result JSON의 `actual_model` 등)을 제거할지 여부. 기본값은 true.
- `previous_candidate_max_chars`: 후보 본문을 prompt에 넣을 때의 최대 길이.
- `common_instruction_lines`: 두 전략이 공유하는 공통 내부 지시문.

`parallel` 전략 필드:

- `max_drafters`: 독립 초안을 만들 최대 provider 수. 기본값은 3.
- `min_drafters`: 종합을 진행하기 위한 최소 초안 수. 기본값은 2.
- `draft_instruction`: 블라인드 독립 초안 작성 지시문. `lines` 배열을 줄 단위로 합칩니다.
- `synthesis_instruction`: 종합 지시문. 방향 하나를 선택하고 나머지 안의 좋은 디테일만 체리픽하도록 안내합니다.

`parallel` 동작:

- 사용 가능한 planning provider(최대 `max_drafters`개)가 서로의 결과를 보지 않고 독립 초안을 **병렬로** 작성합니다.
- 초안 하나가 실패하면 경고만 남기고 나머지로 진행합니다. 성공 초안이 1개뿐이면 종합 없이 그 초안을 그대로 승격하고, 0개이면 blocked 됩니다.
- 종합은 single 모드였다면 `01_plan`을 맡았을 provider 1명이 수행하며, 최종 `01_plan.md`만 공식 산출물로 남깁니다.

`sequential` 전략 필드 (릴레이):

- `iterations`: 내부 계획 반복 횟수. 기본값은 3.
- `no_adjacent_same_provider`: 반복에서 같은 provider가 연속 실행되는 것을 막을지 여부.
- `instructions`: 회차별 릴레이 지시문 배열.

`max` 전략 필드:

- `max`는 `parallel`의 초안 필드(`max_drafters`, `min_drafters`, `draft_instruction`)를 그대로 재사용합니다.
- `select_instruction`: 후보 중 방향 하나를 선택하는 단계 지시문. `parallel`의 `synthesis_instruction`과 달리 이 단계 산출물은 *임시 중간 결과*이며 이후 검증·심화가 이어진다고 명시합니다.
- `ground_instruction`: 확정된 계획을 실제 코드에 대조·교정·심화하는 grounded 단계 지시문.
- `premortem_instruction`: 사전 부검 후 최종 계획을 확정하는 단계 지시문.

`max` 동작:

- 1단계는 `parallel`과 동일한 블라인드 병렬 초안(넓이)입니다.
- 2단계는 grounded 순차 릴레이(깊이)로, 각 단계가 **서로 다른 일**(방향 선택 → 코드 대조·심화 → 사전 부검+확정)을 수행합니다. 같은 작업을 반복하는 릴레이가 아닙니다.
- 릴레이는 **초안에 성공한 provider만** 재사용하며, 단계 수는 가용 agent 수에 맞춰 줄어듭니다(일을 버리지 않고 묶음). 마지막 단계는 항상 owner가 맡아 공식 `01_plan.md`를 작성합니다. 예: 3 agent → 초안 3 + 릴레이 3(약 6콜), 2 agent → 초안 2 + 릴레이 2(약 4콜).
- 성공 초안이 1개뿐이면 방향 선택은 생략하되 grounded 심화와 사전 부검은 그대로 수행합니다.

기본 의도는 `01_plan`을 더 깊게 만들되, 최종 `01_plan.md`와 `01_plan.result.json`만 공식 산출물로 인정하고, 사용자에게는 평소와 동일하게 plan 파일 1개만 보이게 하는 것입니다.

---

### Dynamic verify commands

Verify stages may discover project-specific tests or builds that should become mandatory for future runs. In that case, the verify result JSON can include `test_commands` or `recommended_verification_commands`.

The harness handles those commands as follows:

1. It always runs the static `.ai/harness.config.json` `verification.commands` first.
2. It parses `test_commands` from the verify result JSON.
3. It accepts only safe command arrays, not shell strings.
4. It skips commands that are already configured with the same `cwd + command`.
5. It reruns accepted non-duplicate commands in the same verify run.
6. If any accepted command fails, verify becomes `FAIL`.
7. If all verification commands pass, accepted non-duplicate commands with `persist: true` are appended to `.ai/harness.config.json`.

Example verify result field:

```json
{
  "test_commands": [
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
}
```

Dynamic command safety rules:

- Allowed commands: `python -m pytest ...`, `npm.cmd test`, `npm.cmd run build`, `dotnet test`, `dotnet build`.
- `command` must be a JSON array. Shell strings are rejected.
- `cwd` must stay inside the repository.
- Windows npm commands should use `npm.cmd`, not `npm`.
- Shell wrappers such as `powershell`, `cmd /c`, `bash -c`, and `sh -c` are rejected.
- Destructive, network, or Git-mutating commands such as `rm`, `del`, `curl`, `git push`, `git reset`, `git clean`, and `git checkout` are rejected.

---

## Git 정책

AI 모델은 직접 Git 명령을 실행하면 안 됩니다.

금지:

```text
git commit
git commit --amend
git reset
git checkout
git rebase
git push
```

하네스가 성공한 모든 stage의 commit을 관리합니다.

commit 메시지 형식:

```text
[feature][YYYYMMDD-hhmmss][stage        ]
```

stage 필드는 현재 pipeline에서 가장 긴 stage 이름에 맞춰 오른쪽 공백으로 정렬됩니다.

예:

```text
[settings-tab][20260519-232933][04_fix     ]
```

새 run을 시작하기 전에 하네스는 다음을 확인합니다.

- upstream에 push되지 않은 commit이 있는지
- 완료되지 않은 기존 run이 있는지

이 검사는 여러 기능 run이 섞여 Git 기록이 꼬이는 것을 막기 위한 안전장치입니다.

---

## Write Policy

각 preset의 frontmatter에는 단계별로 수정 가능한 파일 범위가 정의되어 있습니다.

예:

```yaml
allowed_writes:
  - "production_code"
  - "tests"
  - ".ai/features/[기능명]/01_dev.md"

forbidden_writes:
  - ".ai/features/[기능명]/00_spec.md"
```

하네스는 stage 실행 전 파일 snapshot을 만들고, stage 종료 후 변경된 파일이 allowed 범위를 벗어났는지 검사합니다.

위반 시 run은 blocked 상태가 됩니다.

---

## 실패와 복구

### provider 실행 실패

provider CLI가 실패하거나 타임아웃이 나면 run은 blocked 됩니다.

확인:

```powershell
python .ai\harness.py todo feature-name
```

재시도:

```powershell
python .ai\harness.py retry feature-name
```

### 산출물 누락

모델이 지정된 `.md` 또는 `.result.json`을 작성하지 않으면 하네스가 멈춥니다.

확인:

```powershell
python .ai\harness.py todo feature-name
```

대부분은 retry로 해결합니다.

```powershell
python .ai\harness.py retry feature-name
```

### human gate

스펙이 모호하거나 사용자 판단이 필요한 경우 `NEEDS_USER`로 멈춥니다.

상세 확인:

```powershell
python .ai\harness.py todo feature-name
```

승인:

```powershell
python .ai\harness.py approve feature-name --auto --yes --defaults
```

### verify 실패

verify stage가 실패하면 하네스는 fix/develop 단계로 되돌립니다.

fast:

```text
02_verify 실패 -> 01_develop
```

standard:

```text
04_verify 실패 -> 03_fix
```

full:

```text
05_verify 실패 -> 04_fix
```

실패 원인은 다음 파일에 정리됩니다.

```text
.ai/runs/<feature>/handoff.md
.ai/runs/<feature>/verification/latest.json
```

### verify/fix 반복 제한 도달

기본 반복 제한은 3회입니다.

더 허용하려면:

```powershell
python .ai\harness.py resume feature-name --auto --yes --max-verify-fix-retries 5
```

또는:

```powershell
python .ai\harness.py auto feature-name --yes --defaults --max-verify-fix-retries 5
```

---

## 하네스 히스토리

run이 완료되면 하네스는 프로젝트 장기 히스토리를 자동으로 갱신합니다.

위치:

```text
.ai/history/
```

주요 파일:

```text
.ai/history/events.json
.ai/history/features/<feature>.json
.ai/history/risks.json
.ai/history/unresolved_items.json
.ai/history/decisions.json
.ai/history/summary.md
```

### events.json

완료된 run 단위 기록입니다.

포함 내용:

- feature 이름
- pipeline 종류
- 요청 요약
- 구현한 내용
- 변경 파일
- 검증 결과
- 관련 commit
- source artifact
- 리스크
- 미래 개선점
- 미해결 항목

### features/<feature>.json

기능별 최신 요약입니다.

특정 기능이 언제 처음 만들어졌고, 마지막으로 어떤 상태였고, 어떤 파일을 건드렸는지 빠르게 확인할 수 있습니다.

### risks.json

프로젝트에 남아 있는 리스크와 미래 개선점을 추적합니다.

`risk_id`는 commit 번호가 아닙니다. 같은 리스크를 나중에 중복 없이 갱신하기 위한 내부 식별자입니다.

### unresolved_items.json

리뷰나 검증에서 나온 항목 중 바로 반영되지 않은 것들을 기록합니다.

예:

- rejected: 타당하지 않다고 판단해 수용하지 않은 항목
- deferred: 지금은 보류하고 나중에 처리할 항목
- warning_only: 통과는 했지만 주의가 필요한 항목
- pass_with_note: PASS지만 검증 note가 남은 항목

이 파일이 중요한 이유는, 장기 프로젝트에서 "그때 찜찜했지만 급하지 않아서 넘긴 것"을 잃어버리지 않기 위해서입니다.

### decisions.json

중요한 설계 결정 기록입니다.

예:

- 왜 이 파일 구조를 선택했는가
- 왜 특정 리뷰 지적을 거부했는가
- 왜 새 의존성을 추가하지 않았는가

### summary.md

사람이 빠르게 읽는 최신 히스토리 요약입니다.

---

## Project Contract

Project Contract(PC)는 여러 pipeline을 거치며 유지해야 하는 프로젝트 전체 규약입니다.

PC는 처음부터 크게 선언하는 문서가 아니라, standard/full pipeline 완료 후 실제 개발 과정에서 관찰된 규칙 후보를 누적하고, 사용자가 승인한 규칙만 모든 다음 프롬프트에 주입하는 방식으로 동작합니다.

### 파일 위치

```text
.ai/history/pc_candidates.json
  모든 PC 후보와 상태를 누적합니다.

.ai/project_contract.md
  승인된 규약과 기본 프로젝트 규칙을 담습니다. 모든 stage prompt에 자동 삽입됩니다.
  파일이 없으면 하네스가 기본 규칙 파일을 만든 뒤 그 내용을 prompt에 삽입합니다.

.ai/pc_review.py
  미정 PC 후보 전체를 선택한 agent로 한 번에 검토하고, 사용자 응답에 따라 후보 상태와 project_contract를 갱신합니다.
```

### 상태

PC 후보 상태는 세 가지만 사용합니다.

```text
미정
승인
기각
```

`미정` 후보가 있어도 새 pipeline은 시작할 수 있습니다. 하네스는 경고만 출력합니다.

### pipeline별 정책

```text
fast
  PC 후보 추출을 생략합니다.

standard
  pipeline 완료 후 PC 후보 추출을 필수로 수행합니다.

full
  pipeline 완료 후 PC 후보 추출을 필수로 수행합니다.
```

저장되는 후보는 `impact_scope: project_wide` 항목뿐입니다. 특정 스택 전용, 기능 한정, 구현 디테일 수준의 관찰은 버립니다.

fast가 PC 후보를 만들지는 않지만, 이미 미정 후보가 있으면 시작 시 경고만 표시합니다.

### 미정 후보 정산

미정 후보가 있으면 아래 명령을 실행합니다.

```powershell
python .ai\pc_review.py
```

기본 검토 agent는 `codex`입니다. 필요하면 아래처럼 바꿀 수 있습니다.

```powershell
python .ai\pc_review.py --agent claude
python .ai\pc_review.py --agent agy
```

실행하면 선택한 agent가 모든 미정 후보와 `.ai/project_contract.md`를 함께 읽고, 중복이 아니며 프로젝트 전체에 효과가 있는 규칙만 짧은 최종 문장으로 제안합니다.

사용자는 추가될 Project Contract 문장과 기각될 후보 요약을 한 번에 확인한 뒤 `Yes` 또는 `No`를 한 번만 입력합니다.

`Yes`를 입력하면 제안된 규칙을 `.ai/project_contract.md`에 반영하고, 규칙에 반영된 후보는 승인, 나머지 후보는 기각으로 기록합니다.

```text
.ai/history/pc_candidates.json
.ai/project_contract.md
```

`No`를 입력하면 `.ai/project_contract.md`는 수정하지 않고, 이번 미정 후보 전체를 기각으로 기록합니다.
따라서 정상 종료 후에는 미정 후보가 남지 않아야 합니다.

---

## 중요한 파일 위치

프롬프트:

```text
.ai/runs/<feature>/prompts/
```

provider stdout/stderr:

```text
.ai/runs/<feature>/logs/
```

하네스 이벤트 로그:

```text
.ai/runs/<feature>/harness.log
```

handoff:

```text
.ai/runs/<feature>/handoff.md
```

검증 결과:

```text
.ai/runs/<feature>/verification/
```

단계 산출물:

```text
.ai/features/<feature>/
```

장기 히스토리:

```text
.ai/history/
```

full 파이프라인 문서 산출물:

```text
.ai/docs/
```

---

## 자주 쓰는 작업 예시

### 작은 기능을 빠르게 개발

```powershell
python .ai\harness_fast.py run "처리 중 상태를 더 명확하게 표시해줘" --feature loading-state --yes --defaults
```

### 일반 기능을 리뷰 포함해서 개발

```powershell
python .ai\harness_standard.py run "설정 항목에 도움말 툴팁을 추가해줘" --feature settings-tooltips --yes --defaults
```

### 위험한 작업을 풀 파이프라인으로 개발

```powershell
python .ai\harness.py run "설정 저장 구조를 변경하고 문서까지 남겨줘" --feature settings-storage --yes --defaults
```

### 중간에 멈춘 run 이어가기

```powershell
python .ai\harness_standard.py auto settings-tooltips --yes --defaults
```

한 단계만 실행하며 보여주려면:

```powershell
python .ai\harness_standard.py step settings-tooltips --yes --defaults
```

### 왜 멈췄는지 확인

```powershell
python .ai\harness_standard.py todo settings-tooltips
```

### 실패 단계 재시도

```powershell
python .ai\harness_standard.py retry settings-tooltips --auto --yes --defaults
```

### 로그 파일 확인

```powershell
Get-Content .ai\runs\settings-tooltips\harness.log -Tail 120
```

### 히스토리 확인

```powershell
Get-Content .ai\history\summary.md
Get-Content .ai\history\risks.json
Get-Content .ai\history\unresolved_items.json
```

---

## 신규 사용자가 가장 많이 헷갈리는 점

### run과 feature의 차이

feature는 기능 이름입니다.

run은 그 feature를 개발하기 위한 하네스 실행 상태입니다.

보통 하나의 feature마다 하나의 run을 만듭니다.

### 모델이 직접 commit하면 안 되는 이유

하네스가 단계별 commit을 추적해야 verify 실패 시 어느 단계 commit을 amend할지 알 수 있습니다.

모델이 직접 commit하면 하네스의 Git 기준점이 깨질 수 있습니다.

### result JSON이 필요한 이유

Markdown은 사람이 읽기 좋지만, 하네스가 안정적으로 파싱하기 어렵습니다.

그래서 각 단계는 `.result.json`을 반드시 같이 남깁니다.

### verify가 PASS인데 다시 fix로 돌아가는 이유

모델의 PASS는 최종 판정이 아닙니다.

하네스 검증 명령이 실패하면 하네스가 최종 판정을 FAIL로 바꾸고 fix/develop 단계로 되돌립니다.

### history는 왜 필요한가

Git log만으로는 다음 질문에 답하기 어렵습니다.

- 무엇을 개발했는가
- 왜 그렇게 만들었는가
- 어떤 리스크를 알고도 남겼는가
- 어떤 리뷰 지적을 거부했는가
- 어떤 개선점을 나중으로 미뤘는가

하네스 history는 이 정보를 기능 단위로 누적합니다.

---

## 개발자가 지켜야 할 원칙

- 작업은 가능한 feature 단위로 작게 나눈다.
- feature 이름은 명확한 영문 slug로 둔다.
- 작은 작업은 fast, 일반 작업은 standard, 위험한 작업은 full을 사용한다.
- 모델이 직접 Git commit/push를 하지 않게 한다.
- verify 실패를 숨기지 않는다.
- `NEEDS_USER`가 나오면 억지로 진행하지 말고 판단을 남긴다.
- 리뷰에서 거부/보류한 항목은 `fix_inputs.rejected`, `fix_inputs.deferred`, `history_notes.unresolved_items`에 남긴다.
- 장기적으로 의미 있는 판단은 `history_notes.decisions`에 남긴다.
- 향후 개선점과 리스크는 `history_notes.risks`, `history_notes.future_improvements`에 남긴다.

---

## 권장 운영 흐름

평소에는 이 흐름을 권장합니다.

1. 작은 작업인지 일반 작업인지 위험한 작업인지 판단한다.
2. fast / standard / full 중 하나를 고른다.
3. `run ... --yes --defaults`로 자동 실행한다.
4. 멈추면 `todo <feature>`를 확인하고 필요하면 `.ai/runs/<feature>/harness.log`를 직접 본다.
5. 실패가 명확하면 `retry --auto --yes --defaults`를 사용한다.
6. 완료 후 `.ai/history/summary.md`와 `.ai/history/unresolved_items.json`을 확인한다.
7. 필요한 경우 남은 리스크나 보류 항목을 다음 feature로 분리한다.

---

## 배포 메모

다른 사람이 사용할 때는 다음을 먼저 확인하게 하세요.

- Python 설치 여부
- Codex CLI 설치 여부
- Claude CLI 설치 여부
- Antigravity/AGY CLI 설치 여부
- provider 인증 상태
- `python .ai\harness_*.py doctor` 결과
- 적용 대상 프로젝트에 맞춘 `.ai/harness.config.json` 검증 명령

하네스를 처음 쓰는 사람에게는 `fast`보다 `standard`를 먼저 권장하는 것이 좋습니다. 리뷰와 수정 단계가 분리되어 있어 결과를 이해하기 쉽습니다.
