# Local Harness Prompt

## Harness Context
- feature_name: 03-project-chart-event
- pipeline_mode: full
- stage: 06_document
- preferred_model: Antigravity
- scheduled_provider: agy
- performance: medium
- output_file: .ai/features/03-project-chart-event/06_document.md
- result_json_file: .ai/features/03-project-chart-event/06_document.result.json
- run_state: .ai/runs/03-project-chart-event/run.json
- generated_at: 2026-06-04T23:54:56
- defaults_mode: true
- interactive_mode: false
- feature_name_locked: true

## Decision Policy
Use recommended defaults for ambiguous decisions. Do not return NEEDS_USER unless the task is impossible, unsafe, requires credentials/secrets that are not available, or would perform destructive/non-reversible actions. Record all default decisions and their rationale in the stage output.

## Manual Provider Instructions
1. The local harness is executing this prompt with the preferred model when possible.
2. Make the requested file changes directly in the repository.
3. Write the human-readable stage output file exactly at `.ai/features/03-project-chart-event/06_document.md`.
4. Also write the machine-readable stage result JSON exactly at `.ai/features/03-project-chart-event/06_document.result.json`.
5. Do not run `git commit`, `git reset`, `git checkout`, `git rebase`, or `git push`. The local harness owns Git history.
6. This Git ownership rule overrides any preset text that appears to ask the model to create, amend, or push commits.
7. For every successful stage, leave the working tree commit-ready and record commit intent in the stage output; the harness will create or amend the commit.
8. If `defaults_mode: true`, prefer recommended defaults over `NEEDS_USER` unless blocked by missing credentials, safety, destructive operations, or impossibility.
9. If the stage needs user input under the decision policy, write both outputs with `status: NEEDS_USER`.
10. If the stage fails, write both outputs with `status: FAIL` and a concrete blocking reason.
11. If `feature_name_locked: true`, keep the existing `feature_name` exactly as provided by the harness. Do not rename or invent a different feature slug.
12. End with a concise summary; the harness will inspect files, not your final message.

## Machine Result JSON Contract
The harness reads `.ai/features/03-project-chart-event/06_document.result.json` first. Keep the `## 단계 결과` section in `.ai/features/03-project-chart-event/06_document.md` for humans, but write this JSON file for the harness.

Required JSON keys:
- status: "PASS", "FAIL", "SKIPPED", or "NEEDS_USER"
- next_stage: next stage id or "done". This is the final pipeline stage; use "done" only when the run is complete.
- human_gate_required: true or false
- blocking_reason: string, use "" when there is no blocker

For NEEDS_USER in interactive_mode, also include `questions`: an array of question objects.
Each question object must include:
- id: stable snake_case identifier
- type: "choice", "yes_no", or "text"
- question: user-facing question text
- options: for "choice" only, either strings or objects with `id`, `label`, and optional `description`
- default: optional default option/value

Include any extra stage fields that the preset asks for, such as `risk_level`, `harness_commit_required`, `changed_files`, `verification_summary`, or `fix_inputs`.
For PASS or FAIL stages, also include `history_notes` with these arrays when known: `implemented`, `risks`, `future_improvements`, `decisions`, and `unresolved_items`. Use empty arrays for categories with nothing to record. Prefer Korean text for human-facing titles, descriptions, reasons, risks, and decisions when the project context is Korean.

## Project Contract
Source: .ai/project_contract.md

# Project Contract

## Hard Rules
- 모델은 Git commit, amend, reset, checkout, rebase, push를 직접 실행하지 않는다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 요청 범위를 벗어난 리팩터링, 의존성 추가, 파일 이동은 하지 않는다.
- 기존 코드와의 하위 호환성을 우선한다. 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 깨뜨리는 변경은 명시적으로 기록하고 사용자 승인을 받는다.

## Project Layout
- 프로덕션 코드는 루트 `src/` 하위에 둔다.
- 테스트 코드는 루트 `tests/` 하위에 둔다.
- 새 테스트 파일을 `src/` 하위에 만들지 않는다.

## Code Style
- 새 코드는 같은 디렉터리의 기존 패턴, 네이밍, 파일 구조를 우선 따른다.
- 프로젝트에 이미 명확한 네이밍 관례가 없으면 변수와 함수는 camelCase를 기본으로 한다.
- 함수 이름은 가능하면 동사 또는 동사구로 시작한다. 예: `loadConfig`, `validateInput`, `renderItem`.
- Boolean 값과 Boolean 반환 함수는 `is`, `has`, `can`, `should` 같은 의미 있는 접두사를 사용한다.
- 이벤트 핸들러는 `handle` 또는 기존 프로젝트의 이벤트 네이밍 패턴을 따른다.
- 값을 변환하는 함수는 `to`, `from`, `parse`, `format`, `normalize`처럼 변환 의도가 드러나는 이름을 사용한다.
- 데이터를 가져오는 함수는 `get`, `load`, `fetch`, `read` 중 실제 동작에 맞는 동사를 사용한다.
- 부수효과가 있는 함수는 `save`, `write`, `update`, `delete`, `send`, `create`처럼 변경 의도가 드러나는 동사를 사용한다.
- 구현이 30줄을 넘어가면 함수나 작은 단위로 분리한다.
- 서비스레이어를 두어서 유지보수를 좋게하라.

## Reliability
- 외부 입력, 파일, 네트워크, 프로세스 실행 결과는 실패 가능성을 명시적으로 처리한다.
- 외부 연동 실패는 호출 단위로 격리하고, 가능한 경우 부분 실패 상태로 응답해 전체 기능 중단을 피한다.
- 외부 데이터 조회는 캐시나 대체 경로를 활용해 일시적 실패에도 가능한 범위의 응답을 유지한다.
- 자동화 스크립트는 백그라운드 프로세스 종료 시 실행 시점에 기록한 PID를 우선 사용한다.

## Testing
- 테스트는 외부 네트워크에 의존하지 않으며, 외부 HTTP 호출은 Mock 또는 Fixture로 격리한다.


## Original User Request
차트는 기본적으로 1M,3M,6M,1Y,3Y,5Y,10Y,YTD 를 선택하면 그 기간만 보여줘야해. 기본은 1M로. 차트에서 확대 축소를 해서 더 자세하게 볼 수 있는 기능을 만들고싶어. 그리고 확대했을경우, 내가 전체 차트에 어디쯤인지 잘 모르니까, 마우스 클릭하고 마우스를 움직이면 이동하는 이벤트와 미니맵을 우하단에 표시하여 UX를 개선시켜줘.

## Previous Stage Outputs
- .ai/features/03-project-chart-event/00_spec.md
- .ai/features/03-project-chart-event/00_spec.result.json
- .ai/features/03-project-chart-event/01_plan.md
- .ai/features/03-project-chart-event/01_plan.result.json
- .ai/features/03-project-chart-event/02_dev.md
- .ai/features/03-project-chart-event/02_dev.result.json
- .ai/features/03-project-chart-event/03_review.md
- .ai/features/03-project-chart-event/03_review.result.json
- .ai/features/03-project-chart-event/04_fix.md
- .ai/features/03-project-chart-event/04_fix.result.json
- .ai/features/03-project-chart-event/05_verify.md
- .ai/features/03-project-chart-event/05_verify.result.json

## Additional Stage Inputs
- none

## Retry Context
- none

## Interactive Answer History
- none

## Current Git Hints
- current_head: d52fd4584c2b4a1c86a5ccd984bf1a51d90cd279
- changed_paths_excluding_runs: []
- latest_harness_verification: .ai/runs/03-project-chart-event/verification/latest.json

---

---
stage: "06_document"
role: "feature_documentation"
preferred_model: "Antigravity"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".ai/features/03-project-chart-event/00_spec.md"
  - ".ai/features/03-project-chart-event/01_plan.md"
  - ".ai/features/03-project-chart-event/02_dev.md"
  - ".ai/features/03-project-chart-event/03_review.md"
  - ".ai/features/03-project-chart-event/04_fix.md"
  - ".ai/features/03-project-chart-event/05_verify.md"
  - ".ai/templates/docx_helper.py"
outputs:
  - ".ai/docs/03-project-chart-event_명세서.docx"
  - ".ai/features/03-project-chart-event/06_document.md"
allowed_writes:
  - ".ai/docs/03-project-chart-event_명세서.docx"
  - ".ai/features/03-project-chart-event/06_document.md"
  - ".ai/runs/03-project-chart-event/document_build.py"
forbidden_writes:
  - "production_code"
  - "tests"
  - ".ai/templates/docx_helper.py"
  - ".ai/features/03-project-chart-event/00_spec.md"
  - ".ai/features/03-project-chart-event/01_plan.md"
  - ".ai/features/03-project-chart-event/02_dev.md"
  - ".ai/features/03-project-chart-event/03_review.md"
  - ".ai/features/03-project-chart-event/04_fix.md"
  - ".ai/features/03-project-chart-event/05_verify.md"
human_gate_required: false
commit_policy: "commit_on_pass"
commit_owner: "harness"
default_next_stage: "done"
---

# 문서 생성 프리셋 (6단계)

## 경로 원칙

- 프로덕션 코드는 루트 `src/` 하위 파일만 의미한다.
- 테스트 코드는 루트 `tests/` 하위 파일만 의미한다.
- 새 테스트 파일은 `tests/` 하위에만 만든다. `src/` 하위에 테스트 파일을 만들지 않는다.
- `requirements.txt`, `run.ps1`, 설정 파일, 의존성 파일, 실행 스크립트 같은 보조 파일도 루트에 만들지 않는다. 필요하면 반드시 `src/` 또는 `tests/` 하위에 둔다.
- `vendor/`, `packages/`, `dist/`, `build/` 등 외부/생성 산출물 디렉터리는 계획/수정/검증 대상에서 제외하고, 필요하면 생성물 또는 외부 산출물로만 기록한다.

## 실행 정책

- 권장 담당 모델은 Antigravity이다.
- 다른 모델이 이 단계를 실행하더라도 중지하지 않는다.
- 담당 모델이 권장 모델과 다르면 `06_document.md`의 `## 단계 결과`에 `model_mismatch: true`와 실제 실행 모델을 기록한다.
- 이 단계는 검증을 통과한 기능에 대한 개발자용 명세서를 생성하는 단계이다.
- 이 단계의 문서 산출물은 검증 성공 시 하네스가 stage 커밋에 포함한다.
- 05_verify.md의 최종 판정이 PASS인 경우에만 `.docx` 명세서를 작성한다.
- 05_verify.md가 FAIL이면 `.docx`를 만들지 않고 `06_document.md`에 `status: SKIPPED`를 기록한다.

---

## 역할

너는 이 프로젝트의 기능 명세서 작성 담당이다.
1~5단계의 모든 기록을 읽고, 완성된 기능에 대한 명세서를 `.docx` 형식으로 작성한다.

---

## 작업 순서

1. `.ai/features/03-project-chart-event/05_verify.md`의 최종 판정이 PASS인지 확인한다.
2. 최종 판정이 PASS가 아니면 `.ai/features/03-project-chart-event/06_document.md`에 `status: SKIPPED`를 기록하고 멈춘다.
3. `.ai/features/03-project-chart-event/00_spec.md`의 목표, 범위, 요구사항을 파악한다.
4. `.ai/features/03-project-chart-event/01_plan.md`를 읽고 구현 접근 방식, 검토된 대안, 위험 구간, 테스트 전략 등 설계 의사결정을 파악한다.
5. `.ai/features/03-project-chart-event/02_dev.md`를 읽고 구현 내용을 파악한다.
6. `.ai/features/03-project-chart-event/03_review.md`를 읽고 리뷰의 핵심 포인트를 파악한다.
7. `.ai/features/03-project-chart-event/04_fix.md`를 읽고 최종 설계 결정과 수용/거부/보류 항목을 파악한다.
8. `.ai/features/03-project-chart-event/05_verify.md`를 읽고 테스트 커버리지와 검증 결과를 파악한다.
9. `## 문서 생성 스크립트` 패턴을 참고하여 `.ai/runs/03-project-chart-event/document_build.py`를 작성하고 실행하여 `.ai/docs/03-project-chart-event_명세서.docx`를 생성한다.
10. 생성한 `.docx`가 유효한 Office Open XML 문서인지 아래 산출물 검증 절차로 확인한다.
11. 검증에 실패하면 가짜 `.docx`를 성공 산출물로 기록하지 말고 `.ai/features/03-project-chart-event/06_document.md`에 `status: FAIL`과 구체적인 실패 사유를 기록한다.
12. 검증에 성공한 경우에만 생성 결과를 `.ai/features/03-project-chart-event/06_document.md`에 기록한다.

---

## 명세서 구조

### 1. 개요

- 기능 이름
- 기능 목적 요약
- 최종 완성 일시

### 2. 사용 방법

- API 엔드포인트, 함수 인터페이스, 파라미터, 리턴값
- 호출 예시 코드
- 입력/출력 예시

### 3. 관련 파일

- 이 기능과 관련된 파일 목록
- 각 파일의 역할 한 줄 설명

### 4. 주요 설계 결정

- 선택한 구현 접근 방식과 근거
- 검토했지만 채택하지 않은 대안과 사유
- 식별된 위험 구간과 완화 방안
- 구현 단계에서의 추가 결정 사항
- 리뷰에서 논의된 핵심 포인트와 최종 결정
- 거부 또는 보류된 지적 사항과 그 이유

### 5. 의존성

- 이 기능이 사용하는 외부 라이브러리
- 각 라이브러리의 용도

### 6. 테스트 현황

- 테스트 파일 경로
- 커버하는 범위 요약
- 검증 시 추가된 테스트
- 최종 테스트 실행 결과

### 7. 알려진 한계 및 추후 개선

- 현재 구현의 제약사항
- 리뷰나 검증에서 보류된 항목
- 향후 개선 방향

---

## 문서 작성 원칙

- 반드시 `.docx` 확장자로 작성한다.
- `.docx`는 확장자만 `.docx`인 텍스트 파일이 아니라, Microsoft Word에서 열리는 유효한 Office Open XML 문서여야 한다.
- **반드시 `.ai/templates/docx_helper.py`를 사용하여 생성한다.** 아래 `## 문서 생성 스크립트` 패턴을 따른다.
- 문서 생성용 Python 스크립트는 `.ai/runs/03-project-chart-event/document_build.py`에만 작성한다.
- `.ai/templates/docx_helper.py`는 읽기 전용 템플릿으로 사용하고 수정하지 않는다.
- Markdown, HTML, plain text, JSON, XML 본문을 `.docx` 확장자로만 저장하는 것은 실패로 간주한다.
- `python-docx`를 사용할 수 없는 환경이면 `.docx`를 만들지 말고 `06_document.md`에 `status: FAIL`과 구체적인 사유를 기록한다.
- 파일 목록, 의존성 목록, 테스트 현황 중 최소 2개 이상은 반드시 `add_table`로 표로 정리한다.
- 코드 예시는 반드시 `add_code_block`으로 작성한다.
- 섹션 제목은 `add_h1`, 소항목은 `add_h2`, 본문은 `add_paragraph`, 목록은 `add_bullet`을 사용한다.
- 첫 섹션에는 기능명, 최종 판정, 최종 완성 일시를 한눈에 볼 수 있는 요약 문단 또는 요약 표를 둔다.
- 긴 파일 경로, 테스트 명령, API 예시는 표 셀이나 코드 블록 안에서 줄바꿈되어도 의미가 유지되도록 작성한다.
- 빈 섹션을 만들지 않는다. 해당 내용이 없으면 "없음"과 그 근거를 적는다.
- 문서는 개발자가 이 기능을 처음 접했을 때 이해할 수 있는 수준으로 작성한다.
- 1~5단계 md의 내용을 그대로 복붙하지 않고 핵심만 추출한다.
- md 파일에 없는 내용을 추측으로 채우지 않는다.

---

## 문서 생성 스크립트

아래 패턴으로 `.ai/runs/03-project-chart-event/document_build.py`를 작성하고 실행하여 `.docx`를 생성한다.
`03-project-chart-event`, `[내용]` 부분을 실제 내용으로 채운다.

```python
import sys, os
sys.path.insert(0, ".ai/templates")
from docx_helper import (
    create_doc, add_h1, add_h2, add_paragraph,
    add_bullet, add_code_block, add_table
)

doc = create_doc()

# ── 1. 개요 ──────────────────────────────────────────────────────────────────
add_h1(doc, "1. 개요")
add_table(doc,
    headers=["항목", "내용"],
    rows=[
        ["기능 이름", "03-project-chart-event"],
        ["기능 목적", "[한두 줄 요약]"],
        ["최종 판정", "PASS"],
        ["최종 완성 일시", "YYYY-MM-DD"],
    ]
)

# ── 2. 사용 방법 ──────────────────────────────────────────────────────────────
add_h1(doc, "2. 사용 방법")
add_h2(doc, "API / 인터페이스")
add_bullet(doc, "엔드포인트: GET /api/...")
add_bullet(doc, "파라미터: ...")
add_h2(doc, "호출 예시")
add_code_block(doc, "import requests\nresponse = requests.get(...)\nprint(response.json())")

# ── 3. 관련 파일 ──────────────────────────────────────────────────────────────
add_h1(doc, "3. 관련 파일")
add_table(doc,
    headers=["파일 경로", "역할"],
    rows=[
        ["src/path/to/file.py", "역할 설명"],
        ["src/path/to/another.py", "역할 설명"],
    ]
)

# ── 4. 주요 설계 결정 ─────────────────────────────────────────────────────────
add_h1(doc, "4. 주요 설계 결정")
add_h2(doc, "구현 접근 방식")
add_paragraph(doc, "[선택한 방식과 근거]")
add_h2(doc, "검토한 대안")
add_bullet(doc, "대안 A: [내용] — 채택하지 않은 이유: [이유]")
add_h2(doc, "리뷰 핵심 포인트")
add_bullet(doc, "[03_review.md 핵심 지적 및 최종 결정]")
add_h2(doc, "거부/보류 항목")
add_bullet(doc, "[04_fix.md 거부 항목 및 사유]")

# ── 5. 의존성 ─────────────────────────────────────────────────────────────────
add_h1(doc, "5. 의존성")
add_table(doc,
    headers=["라이브러리", "용도"],
    rows=[
        ["패키지명", "사용 목적"],
    ]
)

# ── 6. 테스트 현황 ────────────────────────────────────────────────────────────
add_h1(doc, "6. 테스트 현황")
add_table(doc,
    headers=["테스트 파일", "커버 범위", "결과"],
    rows=[
        ["tests/test_xxx.py", "정상 경로 / 에러 경로 / 엣지 케이스", "PASS"],
    ]
)

# ── 7. 알려진 한계 및 추후 개선 ──────────────────────────────────────────────
add_h1(doc, "7. 알려진 한계 및 추후 개선")
add_bullet(doc, "[현재 구현의 제약사항]")
add_bullet(doc, "[보류된 항목 및 향후 개선 방향]")

# ── 저장 ──────────────────────────────────────────────────────────────────────
os.makedirs(".ai/docs", exist_ok=True)
doc.save(".ai/docs/03-project-chart-event_명세서.docx")
print("생성 완료: .ai/docs/03-project-chart-event_명세서.docx")
```

---

## 산출물 검증

문서 생성 후 아래 검증을 반드시 수행한다.

1. `.ai/docs/03-project-chart-event_명세서.docx` 파일이 존재하는지 확인한다.
2. 파일 첫 바이트가 ZIP 시그니처 `PK`인지 확인한다.
3. ZIP 내부에 `[Content_Types].xml`과 `word/document.xml`이 있는지 확인한다.
4. Word 문서 본문이 비어 있지 않은지 확인한다.
5. `word/document.xml`에 표가 최소 2개 이상 있는지 확인한다.
6. Heading 1 섹션이 7개 이상 있는지 확인한다.
7. 코드 예시가 있으면 `add_code_block`으로 생성된 코드 블록 형태인지 확인한다.
8. `[내용]`, `03-project-chart-event`, `src/path/to/file.py`, `tests/test_xxx.py`, `패키지명` 같은 템플릿 placeholder가 남아 있으면 실패로 처리한다.
9. 위 검증 중 하나라도 실패하면 `status: FAIL`로 기록하고, `blocking_reason`에 실패한 검증 항목을 구체적으로 쓴다.

PowerShell 예시:

```powershell
Format-Hex -Path .ai\docs\03-project-chart-event_명세서.docx | Select-Object -First 1
```

Python 예시:

```python
from zipfile import ZipFile, is_zipfile

path = ".ai/docs/03-project-chart-event_명세서.docx"
assert is_zipfile(path)
with ZipFile(path) as zf:
    names = set(zf.namelist())
    assert "[Content_Types].xml" in names
    assert "word/document.xml" in names
    xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    assert xml.strip()
    assert xml.count("<w:tbl>") >= 2
    assert xml.count('w:val="Heading1"') >= 7
    forbidden_placeholders = [
        "[내용]", "03-project-chart-event", "src/path/to/file.py", "tests/test_xxx.py", "패키지명"
    ]
    assert not any(token in xml for token in forbidden_placeholders)
```

---

## 기록 양식

문서 생성 후 `.ai/features/03-project-chart-event/06_document.md`에 아래 형식으로 작성한다.

```markdown
# 06_document - 03-project-chart-event

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 실행 조건
- 05_verify 최종 판정: PASS / FAIL
- 문서 생성 여부: CREATED / SKIPPED
- SKIPPED 사유:

## 생성 문서
- docx_path: .ai/docs/03-project-chart-event_명세서.docx
- 포함한 주요 섹션:
- 표 개수:
- Heading 1 섹션 개수:
- placeholder 잔존 여부:
- 제외한 내용과 이유:

## 입력 문서
- 00_spec.md:
- 01_plan.md:
- 02_dev.md:
- 03_review.md:
- 04_fix.md:
- 05_verify.md:

## 단계 결과
- status: PASS / SKIPPED / NEEDS_USER / FAIL
- next_stage: done
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low / medium / high
- produced_files:
  - .ai/docs/03-project-chart-event_명세서.docx
  - .ai/features/03-project-chart-event/06_document.md
- changed_files:
- harness_commit_required: true / false
- commit_created_by_model: false
- commit_message_suggestion:
- model_mismatch: false
- actual_model:
```

---

## 금지 사항

- 05_verify.md가 FAIL인 기능의 `.docx` 명세서를 작성하지 않는다.
- `.ai/templates/docx_helper.py`를 사용하지 않고 raw XML로 직접 작성하지 않는다.
- `.ai/templates/docx_helper.py`를 수정하지 않는다.
- 문서 생성용 임시 스크립트를 `.ai/runs/03-project-chart-event/document_build.py` 외 경로에 작성하지 않는다.
- Markdown/HTML/plain text 파일을 `.docx` 확장자로 저장하지 않는다.
- 문서 산출물을 모델이 직접 커밋하지 않는다. 실제 커밋은 PASS 시 하네스가 처리한다.
- 프로덕션 코드를 수정하지 않는다.
- 테스트를 수정하지 않는다.
- 1~5단계 md 파일을 수정하지 않는다.
- 추측이나 가정으로 내용을 채우지 않는다.
