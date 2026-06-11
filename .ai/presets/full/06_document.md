---
stage: "06_document"
role: "feature_documentation"
preferred_model: "Antigravity"
model_policy: "preferred_not_hard_block"
required_inputs:
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_plan.md"
  - ".project/features/[기능명]/02_dev.md"
  - ".project/features/[기능명]/03_review.md"
  - ".project/features/[기능명]/04_fix.md"
  - ".project/features/[기능명]/05_verify.md"
  - ".ai/templates/docx_helper.py"
outputs:
  - ".project/docs/[기능명]_명세서.docx"
  - ".project/features/[기능명]/06_document.md"
allowed_writes:
  - ".project/docs/[기능명]_명세서.docx"
  - ".project/features/[기능명]/06_document.md"
  - ".project/runs/[기능명]/document_build.py"
forbidden_writes:
  - "production_code"
  - "tests"
  - ".ai/templates/docx_helper.py"
  - ".project/features/[기능명]/00_spec.md"
  - ".project/features/[기능명]/01_plan.md"
  - ".project/features/[기능명]/02_dev.md"
  - ".project/features/[기능명]/03_review.md"
  - ".project/features/[기능명]/04_fix.md"
  - ".project/features/[기능명]/05_verify.md"
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

1. `.project/features/[기능명]/05_verify.md`의 최종 판정이 PASS인지 확인한다.
2. 최종 판정이 PASS가 아니면 `.project/features/[기능명]/06_document.md`에 `status: SKIPPED`를 기록하고 멈춘다.
3. `.project/features/[기능명]/00_spec.md`의 목표, 범위, 요구사항을 파악한다.
4. `.project/features/[기능명]/01_plan.md`를 읽고 구현 접근 방식, 검토된 대안, 위험 구간, 테스트 전략 등 설계 의사결정을 파악한다.
5. `.project/features/[기능명]/02_dev.md`를 읽고 구현 내용을 파악한다.
6. `.project/features/[기능명]/03_review.md`를 읽고 리뷰의 핵심 포인트를 파악한다.
7. `.project/features/[기능명]/04_fix.md`를 읽고 최종 설계 결정과 수용/거부/보류 항목을 파악한다.
8. `.project/features/[기능명]/05_verify.md`를 읽고 테스트 커버리지와 검증 결과를 파악한다.
9. `## 문서 생성 스크립트` 패턴을 참고하여 `.project/runs/[기능명]/document_build.py`를 작성하고 실행하여 `.project/docs/[기능명]_명세서.docx`를 생성한다.
10. 생성한 `.docx`가 유효한 Office Open XML 문서인지 아래 산출물 검증 절차로 확인한다.
11. 검증에 실패하면 가짜 `.docx`를 성공 산출물로 기록하지 말고 `.project/features/[기능명]/06_document.md`에 `status: FAIL`과 구체적인 실패 사유를 기록한다.
12. 검증에 성공한 경우에만 생성 결과를 `.project/features/[기능명]/06_document.md`에 기록한다.

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
- 문서 생성용 Python 스크립트는 `.project/runs/[기능명]/document_build.py`에만 작성한다.
- `.ai/templates/docx_helper.py`는 읽기 전용 템플릿으로 사용하고 수정하지 않는다.
- Markdown, HTML, plain text, JSON, XML 본문을 `.docx` 확장자로만 저장하는 것은 실패로 간주한다.
- `python-docx`를 사용할 수 없는 환경이면 `.docx`를 만들지 말고 `06_document.md`에 `status: FAIL`과 구체적인 사유를 기록한다.
- 파일 목록, 의존성 목록, 테스트 현황 중 최소 2개 이상은 반드시 `add_table`로 표로 정리한다.
- 코드 예시는 반드시 `add_code_block`으로 작성한다.
- 문서 전체 형식은 `.ai/templates/docx_helper.py`의 helper가 제공하는 기본 형식 토큰을 따른다. 임의의 직접 서식으로 폰트, 여백, 색상, 표 테두리, 셀 여백을 덮어쓰지 않는다.
- 섹션 제목은 `add_h1`, 소항목은 `add_h2`, 본문은 `add_paragraph`, 목록은 `add_bullet`을 사용한다.
- 상단 보조 문구가 필요하면 `add_document_kicker`, 문서 제목은 `add_document_title`, 출처/각주는 `add_source_note`, 표 단위 표기는 `add_unit_label`을 사용한다.
- 첫 섹션에는 기능명, 최종 판정, 최종 완성 일시를 한눈에 볼 수 있는 요약 문단 또는 요약 표를 둔다.
- 긴 파일 경로, 테스트 명령, API 예시는 표 셀이나 코드 블록 안에서 줄바꿈되어도 의미가 유지되도록 작성한다.
- 빈 섹션을 만들지 않는다. 해당 내용이 없으면 "없음"과 그 근거를 적는다.
- 문서는 개발자가 이 기능을 처음 접했을 때 이해할 수 있는 수준으로 작성한다.
- 1~5단계 md의 내용을 그대로 복붙하지 않고 핵심만 추출한다.
- md 파일에 없는 내용을 추측으로 채우지 않는다.

## 문서 형식 규칙

- 페이지는 A4 세로이며 여백은 위 3.00cm, 좌/우/아래 2.54cm, header 1.50cm, footer 1.75cm를 사용한다.
- 영문/숫자/기호 글꼴은 Arial, 한글 글꼴은 맑은 고딕을 사용한다. `ascii`, `hAnsi`, `cs`는 Arial, `eastAsia`는 맑은 고딕으로 지정되어야 한다.
- 기본 본문은 12pt, 줄간격 1.5줄, 검정색을 사용한다.
- 상단 보조 문구와 출처/각주는 10pt를 사용한다. 상단 보조 문구는 회색 `#808080`을 사용한다.
- 문서 제목은 16pt bold를 사용한다. 기본 제목 색상은 `#002060`이며, 강조가 필요한 일부 단어만 `#00B0F0`을 사용할 수 있다.
- 섹션 제목은 16pt bold 검정, 소항목 제목은 12pt bold 검정을 사용한다.
- 표는 전체 폭 약 15.99cm, 얇은 단일선 그리드(`single`, `sz=4`), 셀 좌/우 여백 약 0.19cm, 셀 위/아래 여백 0, 세로 가운데 정렬을 사용한다.
- 표 헤더는 배경색을 넣지 않고 bold로만 구분한다. 데이터 성격에 따라 `add_table(..., column_widths_cm=[...], alignments=[...])`로 열 폭과 정렬을 명시한다.
- 표 행 높이는 약 20pt를 기본으로 하되, 긴 텍스트가 잘리면 행이 늘어날 수 있도록 내용 축약 또는 열 폭 조정으로 해결한다.
- 코드 블록은 `add_code_block`을 사용하며 회색 배경과 고정폭 글꼴을 유지한다.

---

## 문서 생성 스크립트

아래 패턴으로 `.project/runs/[기능명]/document_build.py`를 작성하고 실행하여 `.docx`를 생성한다.
`[기능명]`, `[내용]` 부분을 실제 내용으로 채운다.

```python
import sys, os
sys.path.insert(0, ".ai/templates")
from docx_helper import (
    create_doc, add_document_kicker, add_document_title,
    add_h1, add_h2, add_paragraph, add_bullet,
    add_code_block, add_table, add_source_note
)

doc = create_doc()
add_document_kicker(doc, "Feature Specification")
add_document_title(doc, "[기능명] 명세서")

# ── 1. 개요 ──────────────────────────────────────────────────────────────────
add_h1(doc, "1. 개요")
add_table(doc,
    headers=["항목", "내용"],
    rows=[
        ["기능 이름", "[기능명]"],
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
add_source_note(doc, "작성 기준: 00_spec~05_verify 단계 산출물")

# ── 저장 ──────────────────────────────────────────────────────────────────────
os.makedirs(".project/docs", exist_ok=True)
doc.save(".project/docs/[기능명]_명세서.docx")
print("생성 완료: .project/docs/[기능명]_명세서.docx")
```

---

## 산출물 검증

문서 생성 후 아래 검증을 반드시 수행한다.

1. `.project/docs/[기능명]_명세서.docx` 파일이 존재하는지 확인한다.
2. 파일 첫 바이트가 ZIP 시그니처 `PK`인지 확인한다.
3. ZIP 내부에 `[Content_Types].xml`과 `word/document.xml`이 있는지 확인한다.
4. Word 문서 본문이 비어 있지 않은지 확인한다.
5. `word/document.xml`에 표가 최소 2개 이상 있는지 확인한다.
6. Heading 1 섹션이 7개 이상 있는지 확인한다.
7. 코드 예시가 있으면 `add_code_block`으로 생성된 코드 블록 형태인지 확인한다.
8. `[내용]`, `src/path/to/file.py`, `tests/test_xxx.py`, `패키지명` 같은 템플릿 placeholder가 남아 있으면 실패로 처리한다.
9. 위 검증 중 하나라도 실패하면 `status: FAIL`로 기록하고, `blocking_reason`에 실패한 검증 항목을 구체적으로 쓴다.

PowerShell 예시:

```powershell
Format-Hex -Path .project\docs\[기능명]_명세서.docx | Select-Object -First 1
```

Python 예시:

```python
from zipfile import ZipFile, is_zipfile

path = ".project/docs/[기능명]_명세서.docx"
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
        "[내용]", "src/path/to/file.py", "tests/test_xxx.py", "패키지명"
    ]
    assert not any(token in xml for token in forbidden_placeholders)
```

---

## 기록 양식

문서 생성 후 `.project/features/[기능명]/06_document.md`에 아래 형식으로 작성한다.

```markdown
# 06_document - [기능명]

작성: [실제 실행 모델]
일시: YYYY-MM-DD

## 실행 조건
- 05_verify 최종 판정: PASS / FAIL
- 문서 생성 여부: CREATED / SKIPPED
- SKIPPED 사유:

## 생성 문서
- docx_path: .project/docs/[기능명]_명세서.docx
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
  - .project/docs/[기능명]_명세서.docx
  - .project/features/[기능명]/06_document.md
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
- 문서 생성용 임시 스크립트를 `.project/runs/[기능명]/document_build.py` 외 경로에 작성하지 않는다.
- Markdown/HTML/plain text 파일을 `.docx` 확장자로 저장하지 않는다.
- 문서 산출물을 모델이 직접 커밋하지 않는다. 실제 커밋은 PASS 시 하네스가 처리한다.
- 프로덕션 코드를 수정하지 않는다.
- 테스트를 수정하지 않는다.
- 1~5단계 md 파일을 수정하지 않는다.
- 추측이나 가정으로 내용을 채우지 않는다.
