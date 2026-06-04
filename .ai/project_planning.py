#!/usr/bin/env python
"""project_planning: 프로젝트 전체 기획을 feature 단위 harness run 명령 시퀀스로 분해한다.

deep_interview가 "러프한 요청 1개 -> 정제된 run 명령 1개"라면,
project_planning은 그 상위 레벨이다: "프로젝트 기획서 -> 의존성 순서로 정렬된 feature N개 + 각 run 명령".

설계 원칙:
- 기존 코드를 건드리지 않는다. deep_interview의 provider/JSON 배관만 import해서 재사용한다.
- 실행하지 않는다. 추천 명령 모음(plan.txt)만 만든다. 실제 실행은 사용자가 한다.
- 입력 파일(docx/md/txt/pdf)은 에이전트가 자기 파일 도구로 직접 읽는다. ppt는 받지 않고 PDF 변환을 안내한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AI_DIR = ROOT / ".ai"
PROJECTS_DIR = AI_DIR / "projects"

# deep_interview는 같은 .ai 디렉터리에 있다. 그 안의 provider 호출 / JSON 파싱 / spinner를 재사용한다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_core.requirements import HarnessRequirementsError, ensure_requirements_installed  # noqa: E402
import deep_interview as di  # noqa: E402

REJECTED_INPUT_SUFFIXES = {".ppt", ".pptx"}
READABLE_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf", ".docx"}
INLINE_TEXT_MAX_CHARS = 20000
MAX_SAFETY_ROUNDS = 50

# --reference-folder 전용. 레퍼런스는 "명세"가 아니라 "참고 코드베이스"다.
# 본문을 통째로 인라인하지 않고(너무 큼), 경로 "맵"만 주고 에이전트가 필요한 파일만 직접 연다.
# 단, 레퍼런스 최상위의 오리엔테이션 문서는 작아서 소량 인라인한다.
REFERENCE_ORIENTATION_NAMES = ("readme.md", "agents.md", "claude.md")
REFERENCE_MAP_SKIP_SUFFIXES = {
    # 이미지/바이너리: LLM이 직접 못 읽으므로 파일 맵에서 제외한다.
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".ico", ".emf", ".wmf", ".svg",
    ".pdb", ".dll", ".exe", ".so", ".dylib", ".a", ".lib", ".bin", ".cache", ".baml",
    ".resources", ".vsidx", ".suo", ".user", ".nupkg",
}
# 빌드 산출물/패키지/IDE 디렉터리: 소스가 아니라 맵만 폭주시키므로 통째로 제외한다.
REFERENCE_MAP_SKIP_DIRS = {
    "obj", "bin", "testresults", "packages", "node_modules", ".vs", ".git", ".idea",
}
REFERENCE_MAP_MAX_FILES = 6000  # 맵 폭주 방지 안전장치(플랫폼 SDK는 파일이 많아 넉넉히)

# 티어 사다리(약 -> 강). 사용자가 정의한 순서:
# fast -> standard -> full -> full(parallel|sequential) -> full(max)
TIER_LADDER = ["fast", "standard", "full", "full-parallel", "full-sequential", "full-max"]
TIER_SET = set(TIER_LADDER)

# 성능(작업량) 축. tier(중요도/위험)와 직교한다: feature가 실제로 짜야 하는 코드의 양/복잡도로 정한다.
# tier x performance 조합으로 사다리가 더 세분화된다(예: full+lite vs full+high).
PERFORMANCE_LEVELS = ["lite", "medium", "high"]
PERFORMANCE_SET = set(PERFORMANCE_LEVELS)
# 모델이 performance를 비우거나 잘못 주면 tier에서 합리적 기본값을 끌어온다(= 작업량에 따라 알아서).
DEFAULT_PERFORMANCE_BY_TIER = {
    "fast": "lite",
    "standard": "medium",
    "full": "medium",
    "full-parallel": "high",
    "full-sequential": "high",
    "full-max": "high",
}


class PlanningError(RuntimeError):
    pass


PLANNING_PRESET = """
너는 프로젝트 전체 기획을 하네스로 개발 가능한 feature 단위로 쪼개는 분해 담당자다.

핵심 철학:
- 한 번에 프로젝트 전체를 만들지 않는다. 작은 feature를 하나씩 붙여 만든다.
- feature 1개 = `harness.py run` 1회 = 파이프라인 1단위다. 독립적으로 출하 가능한 가장 작은 의미 단위로 잡는다.
- 예) 쇼핑몰이면 "와이어프레임", "아이템 모델 정의", "장바구니", "주문 API"처럼 한 번의 파이프라인으로 만들 만한 크기로 나눈다.
- 너무 굵게(메가 feature 2~3개) 잡지 말고, 너무 잘게(의미 없는 수십 개) 쪼개지도 마라. 개수는 기획서를 읽고 네가 판단한다.

의존성:
- 한 프로젝트 안에서는 선행되어야 하는 feature가 흔하다(데이터 모델이 API보다 먼저 등).
- 각 feature의 depends_on에 반드시 먼저 개발되어야 하는 feature slug를 적는다.
- 순환 의존이 생기지 않게 한다.
- 후행 feature의 refined_prompt는 선행 feature를 slug 이름으로 참조할 수 있다(예: "item-model feature에서 정의한 모델을 사용한다").

티어 추천(약 -> 강, 추천일 뿐 강제가 아니다):
- fast: 작고 위험이 낮은 작업.
- standard: 일반적인 기능.
- full: 핵심/중요 기능.
- full-parallel / full-sequential: 더 중요해서 다중 에이전트 심층 계획이 필요한 기능(병렬 초안 합성 / 순차 릴레이 정제).
- full-max: 가장 중요하고 위험한 기능(인증/결제/마이그레이션/공개 API 등). 가장 비싸다.

성능 프로파일 추천(작업량 축, tier와 별개로 각 feature마다 반드시 하나 정한다):
- 기준은 그 feature에서 실제로 작성/수정할 코드의 "양과 복잡도"다. 중요도/위험(tier)과는 다른 축이다.
- lite: 손이 적게 가는 작은 feature(설정/상수 추가, 단순 CRUD 한두 개, 와이어프레임 스텁, 얇은 래퍼 등).
- medium: 보통 규모의 feature(여러 파일에 걸친 일반 기능, 표준적인 API/화면 한 벌).
- high: 코드량이 많거나 알고리즘·상태기계·동시성·복잡한 데이터 변환처럼 까다로운 feature.
- tier와 performance는 자유롭게 조합한다: 작지만 중요한 인증 패치는 tier=full + performance=lite처럼 둘 수 있다.

금지:
- 코드를 작성하거나 파일을 수정하지 않는다.
- shell 명령을 실행하지 않는다.
- 기획서에 없는 큰 기능을 임의로 추가하지 않는다.
- 가짜로 확인한 척하지 않는다. 입력 파일을 실제로 읽고 근거를 둔다.
""".strip()


PLANNING_QUESTION_SCHEMA = """
반드시 JSON 객체 하나만 출력한다.

분해를 더 정확히 하기 위해 질문이 필요하면:
{
  "action": "ask",
  "question": "사용자에게 물을 한국어 질문 하나",
  "why": "이 질문이 분해에 왜 필요한지 짧은 이유",
  "options": [
    {"label": "선택지", "value": "short_value", "description": "선택 시 의미"}
  ],
  "state_summary": "현재까지 이해한 프로젝트 구조 한두 문장"
}

feature 경계/의존성/우선순위가 충분히 분명해서 분해를 시작해도 되면:
{
  "action": "final",
  "state_summary": "분해를 시작할 수 있는 상태 요약"
}

규칙:
- 한 번에 질문 하나만 한다.
- 이미 답한 내용은 다시 묻지 않는다.
- options는 자연스러운 경우에만 2~4개 제공한다. 있어도 사용자는 자유 입력할 수 있다.
- 질문은 feature 분해 결과를 실제로 바꿀 때만 한다. 아니면 final을 반환한다.
- JSON 밖에 설명 문장을 쓰지 않는다.
""".strip()


DECOMPOSE_SCHEMA = """
반드시 JSON 객체 하나만 출력한다.

{
  "project_slug": "ascii-kebab-case-project-name",
  "summary": "프로젝트 한 줄 요약",
  "features": [
    {
      "slug": "ascii-kebab-case-feature",
      "title": "사람이 읽는 짧은 제목",
      "description": "이 feature가 무엇을 만드는지 1~2문장",
      "refined_prompt": "harness run 명령에 넣을 한국어 정제 요청문",
      "tier": "fast | standard | full | full-parallel | full-sequential | full-max",
      "tier_reason": "이 티어를 고른 짧은 이유",
      "performance": "lite | medium | high",
      "performance_reason": "이 성능 프로파일을 고른 짧은 이유(코드 작성량/복잡도 기준)",
      "depends_on": ["먼저 개발되어야 하는 다른 feature slug", "..."]
    }
  ]
}

규칙:
- features는 의미 있는 순서로 1개 이상 제공한다(최종 순서는 도구가 의존성으로 다시 정렬한다).
- slug는 영어 소문자, 숫자, 하이픈만 사용한다.
- tier는 정확히 다음 중 하나만 사용: fast | standard | full | full-parallel | full-sequential | full-max
- performance는 정확히 다음 중 하나만 사용: lite | medium | high
- performance는 그 feature에서 실제로 작성/수정할 코드의 양과 복잡도로 정한다(많고 복잡할수록 high, 적고 단순하면 lite). tier(중요도/위험)와는 별개의 축이다.
- depends_on은 반드시 먼저 개발되어야 하는 feature의 slug 목록이다. 없으면 빈 배열 [].
- 순환 의존(A->B->A)을 만들지 않는다.
- refined_prompt는 한국어로 5~12문장, 한 번의 run 요청으로 쓰기 좋게 구체적으로 작성한다.
- refined_prompt는 선행 feature가 있으면 그 slug를 이름으로 참조한다.
- refined_prompt에 "분해", "project-planning" 같은 내부 과정 표현을 넣지 않는다.
- 기획서에 없는 큰 기능을 임의로 추가하지 않는다.
- JSON 밖에 설명 문장을 쓰지 않는다.
""".strip()


# --strategy parallel 전용. deep_thinking의 parallel(블라인드 독립 초안 -> 종합)을 벤치마킹한다.
DRAFT_INSTRUCTION = """
## 전략: 독립 초안 (블라인드)
지금 너는 여러 에이전트 중 한 명으로서, 다른 에이전트의 결과를 보지 않고 너 혼자 독립적으로 이 프로젝트를 분해한다.
- 다른 초안을 의식하거나 미리 합의하려 하지 마라. 네가 최선이라 보는 분해를 그대로 제시하라.
- 이 초안은 이후 한 에이전트가 여러 독립 초안을 받아 한 방향으로 종합하는 데 쓰인다.
- 최종 출력은 위 '## 출력 계약'의 JSON 객체 하나여야 한다. 그 외 텍스트를 쓰지 마라.
""".strip()

SYNTHESIS_INSTRUCTION = """
## 전략: 종합 (여러 독립 초안 -> 하나)
위 '## 독립 분해 초안들'은 여러 에이전트가 서로를 보지 않고 만든 익명 초안이다.
- 초안들을 기계적으로 합치거나 feature를 단순 합집합하지 마라.
- 가장 타당한 분해 방향 하나를 고르고, 나머지 초안에서 명백히 더 나은 디테일(누락된 의존성, 더 적절한 feature 경계/티어/성능)만 골라 반영하라.
- 초안들이 충돌하면 기획서/레퍼런스 근거로 판단하라. 어느 초안을 누가 썼는지는 중요하지 않다.
- 최종 출력은 위 '## 출력 계약'의 JSON 객체 하나여야 한다. 그 외 텍스트를 쓰지 마라.
""".strip()

# 종합 프롬프트에 넣는 초안 1개당 최대 길이(과대 프롬프트 방지). deep_thinking previous_candidate_max_chars 대응.
CANDIDATE_MAX_CHARS = 12000


# --strategy max 전용. parallel의 블라인드 초안(넓이) 위에 grounded 순차 릴레이(깊이)를 더한다.
# 릴레이 3단계는 서로 다른 일을 한다: 방향 선택 -> 레퍼런스 코드 대조·심화 -> 사전 부검·확정.
SELECT_INSTRUCTION = """
## 전략(max) 1단계: 방향 선택 (중간 결과)
위 '## 독립 분해 초안들'은 익명 초안이다. 여기서 가장 타당한 분해 방향 하나를 고른다.
- 이 단계 결과는 최종이 아니다. 이후 레퍼런스 코드 대조와 사전 부검이 이어진다.
- 기계적 합집합 금지. 한 방향을 고르되 다른 초안의 명백히 더 나은 디테일만 흡수하라.
- 최종 출력은 위 '## 출력 계약'의 JSON 객체 하나여야 한다. 그 외 텍스트를 쓰지 마라.
""".strip()

GROUND_INSTRUCTION = """
## 전략(max) 2단계: 플랫폼/레퍼런스 코드 대조·교정·심화 (grounded)
위 '## 지금까지의 모든 산출물'에는 원본 블라인드 초안 전부와 직전까지의 릴레이 결과가 들어 있다. 그중 '현재 최신본'은 아직 검증되지 않은 중간 결과다. 지금 임무는 그것을 실제 코드로 검증·심화하는 것이다.
- '## 재사용 플랫폼 / 내부 SDK'가 있으면, 그 파일 맵에서 기반 클래스·모듈(*Module.cs)·템플릿을 직접 열어 '플랫폼이 이미 무엇을 제공하는지' 확인하라. 플랫폼이 주는 것을 새로 만드는 feature가 있으면 '재사용/등록'으로 바꿔라.
- '## 참고 레퍼런스'가 있으면, 형제 앱이 그 플랫폼을 '어떻게 조합'해 앱을 완성했는지(모듈 등록·Region 조립·의존성 순서)를 직접 열어 보고 우리 분해의 경계·depends_on·순서를 교정하라.
- 그 근거로 feature 경계, depends_on, tier/performance를 교정하고, 누락된 선행 feature(플랫폼 셋업/추상화 계층 등)를 보강하라.
- 최신본을 기준으로 삼되, 드롭된 초안에 더 나은 아이디어가 있으면 되살려라.
- 플랫폼 자산은 최대한 재사용하되, 형제 앱의 고유 코드를 통째로 베끼지 마라. 우리 기획서(명세)에 맞춰라.
- 추측하지 말고 실제로 연 파일에 근거하라. (대조할 코드가 없으면 기획서 근거로 심화하라.)
- 최종 출력은 위 '## 출력 계약'의 JSON 객체 하나여야 한다. 그 외 텍스트를 쓰지 마라.
""".strip()

PREMORTEM_INSTRUCTION = """
## 전략(max) 마지막 단계: 사전 부검(pre-mortem) 후 확정
위 '## 지금까지의 모든 산출물'(원본 초안 + 모든 중간 결과)을 모두 참고해, 그중 '현재 최신본'을 최종 확정하기 전에 사전 부검을 수행한다.
- "이 분해/순서/티어대로 진행하면 무엇이 가장 먼저 깨질까?"를 스스로 묻고, 그 약점을 분해에 반영해 교정하라.
- 흔한 실패: 잘못된 의존성 순서, 너무 크거나 작은 feature, 누락된 선행 작업, 비현실적인 tier.
- 초안이나 중간 결과 중 더 나은 선택지가 있었다면 지금 반영하라.
- 교정된 최종 분해를 확정하라. 최종 출력은 위 '## 출력 계약'의 JSON 객체 하나여야 한다. 그 외 텍스트를 쓰지 마라.
""".strip()


# agy(Antigravity)는 --print에서도 Cascade 에이전트로 동작해, 도구로 파일을 읽고/쓰는 건 자연스럽지만
# 최종 답을 stdout으로는 잘 못 내보낸다(텍스트를 TTY로 drip -> 우리가 잡는 PIPE엔 0 bytes -> 초안 탈락).
# 그래서 빌드 하네스가 stage 산출물을 'provider가 쓴 파일'로 받는 것과 같은 원리로, agy 호출은 결과
# JSON을 stdout이 아니라 '파일'에 쓰게 하고 그 파일을 읽는다(_run_agy_via_file). 이러면 agy가 입력
# 파일(PDF/소스)을 자유롭게 다 읽으면서(=codex/claude와 동등) 출력은 파일 쓰기라 안정적이다.
#
# 실측으로 밝혀진 함정 2가지(2026-06-02, agy cli.log 분석):
#  (1) agy를 '산출물(deliverable) 제작'으로 프레이밍하거나 파일쓰기 지시를 거대 프롬프트 '말미'에만 두면,
#      agy가 자기 brain 폴더(~/.gemini/.../brain/<conv-id>/*.md)에 프로즈 마크다운 기획서를 만들어 버린다
#      (내 경로엔 안 씀). -> 파일쓰기 지시를 프롬프트 '최상단'에 둬 지배적 프레이밍으로 삼고, 말미에 짧게
#      재강조한다(AGY_FILE_OUTPUT_TAIL_REMINDER). 'JSON only'를 강제하고 deliverable 트리거 단어를 뺀다.
#  (2) agy는 dot-디렉터리(.ai/...)를 hidden으로 보고 워크스페이스에서 무시한다
#      (cli.log "failed to add ... is hidden: ignore uri"). -> 출력 파일은 .ai/ 밖, 비숨김 경로
#      (repo 루트 AGY_OUTPUT_DIR=cache/agy_out)에 둔다.
# {rel_path}/{abs_path}에 실제 출력 경로(워크스페이스 상대/절대)가 채워진다.
# 성공하면 캐시를 지우고, 실패(파일 없음/파싱 실패)하면 진단용으로 남겨 둔다.
AGY_OUTPUT_DIR = ROOT / "cache" / "agy_out"

AGY_FILE_OUTPUT_INSTRUCTION = """
## Manual Provider Instructions (가장 우선 — 아래 모든 내용에 우선한다)
이것은 로컬 하네스가 실행하는 저장소(repo) 데이터 추출 작업이다. 너는 이 저장소(--add-dir 워크스페이스)를 직접 다루는 에이전트다. 아래에는 분석 맥락과 '## 출력 계약'(원하는 JSON 구조)이 이어진다. 네 임무는 그 JSON 데이터를 '저장소 안 파일 하나'로 써넣는 것뿐이다 — 사람에게 보여줄 문서를 작성하는 게 아니다.
1. 기획서·설계서·계획서·분해 결과를 .md 문서나 산출물(artifact)로 '작성'하지 마라. 너의 brain/대화 폴더에 어떤 파일도 만들지 마라. 오직 아래 한 파일에만 JSON을 '직접' 써라(write this one file directly in the repository):
   - output_file (repo 루트 기준 상대경로): {rel_path}
   - (절대경로: {abs_path})
2. output_file 내용은 JSON 객체 '하나'뿐이다: 파일은 '{{' 로 시작해 '}}' 로 끝나야 하고, 코드펜스(```)·제목·설명·마크다운을 넣지 마라. 이 파일 외에 다른 파일을 만들거나 수정하지 마라.
3. 분석 입력(기획서 PDF/MD, 재사용 플랫폼·레퍼런스 소스)은 자유롭게 읽어라. 추측하지 말고 실제 파일에 근거하라.
4. 끝에는 한 줄 요약만 말하라. 하네스는 너의 최종 메시지나 대화 산출물이 아니라 오직 위 output_file만 검사한다(the harness inspects only that file).
""".strip()

# 거대 프롬프트(~340KB) 말미 recency 보강용 짧은 재강조. {rel_path}만 채운다.
AGY_FILE_OUTPUT_TAIL_REMINDER = (
    "## 출력 재강조 (가장 마지막 지시)\n"
    "위 맥락의 결론을 사람에게 설명하거나 .md 문서·기획서로 만들지 마라. "
    "JSON 객체 하나만 repo 파일 `{rel_path}` 에 직접 써라. 그 파일 하나만 검사된다. "
    "brain/대화 폴더를 포함해 다른 어떤 파일도 만들지 마라."
)


def slugify(value: Any, fallback: str = "project") -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:64].strip("-") or fallback


def derive_project_slug(
    args: argparse.Namespace,
    request: str,
    plan_files: list[Path],
    plan_folders: list[Path] | None = None,
) -> str:
    if args.project:
        return slugify(args.project)
    if request:
        return slugify(" ".join(request.split()[:6]))
    if plan_folders:
        return slugify(plan_folders[0].name)
    if plan_files:
        return slugify(plan_files[0].stem)
    return "project"


def resolve_plan_files(raw_paths: list[str] | None) -> list[Path]:
    files: list[Path] = []
    for raw in raw_paths or []:
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        suffix = path.suffix.lower()
        if suffix in REJECTED_INPUT_SUFFIXES:
            raise PlanningError(
                f"PPT는 직접 입력받지 않습니다: {path.name}\n"
                "PowerPoint는 와이어프레임이 이미지라 텍스트 추출이 불안정합니다.\n"
                "PDF로 내보낸 뒤 --plan-file 로 다시 전달하세요."
            )
        if not path.exists():
            raise PlanningError(f"기획서 파일을 찾을 수 없습니다: {path}")
        if suffix not in SUPPORTED_SUFFIXES:
            raise PlanningError(
                f"지원하지 않는 입력 형식입니다: {path.name} ({suffix or '확장자 없음'})\n"
                f"지원 형식: {', '.join(sorted(SUPPORTED_SUFFIXES))} (ppt는 pdf로 변환)"
            )
        files.append(path)
    return files


def resolve_plan_folders(raw_folders: list[str] | None) -> tuple[list[Path], list[Path]]:
    """--plan-folder로 받은 디렉터리들을 재귀 스캔해 지원 형식 파일만 모은다.

    반환: (수집한 파일 경로, 입력 폴더 경로).
    단일 파일(--plan-file)과 달리 폴더에는 이미지/ppt 같은 잡파일이 섞여 있는 게
    정상이므로, 비지원 파일은 에러 없이 건너뛴다. ppt만 따로 안내 메시지를 남긴다.
    숨김 디렉터리(.git 등)는 탐색에서 제외한다.
    """
    collected: list[Path] = []
    folders: list[Path] = []
    for raw in raw_folders or []:
        folder = Path(raw)
        if not folder.is_absolute():
            folder = Path.cwd() / folder
        folder = folder.resolve()
        if not folder.exists():
            raise PlanningError(f"기획서 폴더를 찾을 수 없습니다: {folder}")
        if not folder.is_dir():
            raise PlanningError(
                f"--plan-folder 는 디렉터리여야 합니다(파일 하나면 --plan-file 을 쓰세요): {folder}"
            )
        folders.append(folder)
        matched: list[Path] = []
        skipped_ppt: list[str] = []
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.relative_to(folder).parts):
                continue
            suffix = path.suffix.lower()
            if suffix in SUPPORTED_SUFFIXES:
                matched.append(path.resolve())
            elif suffix in REJECTED_INPUT_SUFFIXES:
                skipped_ppt.append(path.name)
        if skipped_ppt:
            print(
                f"참고: '{folder.name}' 안의 PPT {len(skipped_ppt)}개는 건너뜁니다"
                f"(PDF로 변환하면 포함됩니다): {', '.join(skipped_ppt)}",
                file=sys.stderr,
            )
        if not matched:
            raise PlanningError(
                f"폴더에서 지원하는 기획서 파일을 찾지 못했습니다: {folder}\n"
                f"지원 형식: {', '.join(sorted(SUPPORTED_SUFFIXES))} (ppt는 pdf로 변환)"
            )
        collected.extend(matched)
    return collected, folders


def merge_plan_files(plan_files: list[Path], folder_files: list[Path]) -> list[Path]:
    """--plan-file 파일 뒤에 폴더 수집 파일을 같은 경로 중복 없이 이어 붙인다."""
    merged = list(plan_files)
    seen = set(merged)
    for path in folder_files:
        if path not in seen:
            merged.append(path)
            seen.add(path)
    return merged


def _extract_pdf_text(path: Path, *, max_chars: int = INLINE_TEXT_MAX_CHARS) -> str | None:
    """PDF에서 텍스트만 추출한다(PyMuPDF/fitz). 미설치·추출 실패면 None(경로만 노출).

    도구로 파일을 못 여는(=프롬프트에 인라인된 것만 보는) provider(특히 agy)도 PDF 명세
    '본문'을 보게 하려는 용도. 이미지·와이어프레임·도식은 추출되지 않는다(텍스트 한정).
    """
    try:
        import fitz  # PyMuPDF
    except Exception:  # noqa: BLE001 - 라이브러리 없으면 조용히 경로 표시로 폴백
        return None
    try:
        parts: list[str] = []
        total = 0
        with fitz.open(path) as doc:
            for page in doc:
                chunk = page.get_text("text")
                parts.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    break
        text = "\n".join(parts).strip()
        return text or None
    except Exception:  # noqa: BLE001 - 추출 실패도 경로 표시로 폴백
        return None


def build_inputs_section(plan_files: list[Path]) -> str:
    if not plan_files:
        return "## 입력 기획서 파일\n(첨부 파일 없음 - 아래 요청 텍스트만으로 분해한다.)\n"
    lines = [
        "## 입력 기획서 파일",
        "아래 파일들을 너의 파일 읽기 도구로 직접 열어서 전체 내용을 읽어라.",
        "PDF/Word는 표와 다이어그램, 와이어프레임 이미지까지 최대한 해석하라.",
        "(텍스트·PDF 본문은 아래에 인라인해 두었으니, 파일을 못 여는 환경이면 인라인본만으로도 분해하라.)",
        "",
    ]
    lines.extend(f"- {path}" for path in plan_files)
    inline_blocks: list[str] = []
    for path in plan_files:
        suffix = path.suffix.lower()
        if suffix in READABLE_TEXT_SUFFIXES:
            try:
                content: str | None = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = None
        elif suffix == ".pdf":
            content = _extract_pdf_text(path)
        else:
            content = None  # .docx 등은 인라인 미지원 -> 경로만 노출
        if not content:
            continue
        truncated = len(content) > INLINE_TEXT_MAX_CHARS
        content = content[:INLINE_TEXT_MAX_CHARS]
        note = " · 앞부분만" if truncated else ""
        kind = "PDF 텍스트 추출" if suffix == ".pdf" else "파일 내용"
        inline_blocks.append(
            f"\n### {kind}(참고용 인라인{note}): {path.name}\n```\n{content}\n```"
        )
    body = "\n".join(lines)
    if inline_blocks:
        body += "\n" + "\n".join(inline_blocks)
    return body + "\n"


def _display_path(path: Path) -> str:
    """에이전트가 cwd(repo 루트)에서 바로 열 수 있도록 ROOT-상대 posix 경로로 표시한다."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_dirs(raw_folders: list[str] | None, *, kind: str, flag: str) -> list[Path]:
    """디렉터리 인자들을 존재/유형만 검증한다(스캔은 프롬프트 빌드 시점에)."""
    folders: list[Path] = []
    for raw in raw_folders or []:
        folder = Path(raw)
        if not folder.is_absolute():
            folder = Path.cwd() / folder
        folder = folder.resolve()
        if not folder.exists():
            raise PlanningError(f"{kind} 폴더를 찾을 수 없습니다: {folder}")
        if not folder.is_dir():
            raise PlanningError(
                f"{flag} 는 디렉터리여야 합니다(문서 파일이면 --plan-file 을 쓰세요): {folder}"
            )
        folders.append(folder)
    return folders


def resolve_reference_folders(raw_folders: list[str] | None) -> list[Path]:
    """--reference-folder 디렉터리들을 검증한다."""
    return _resolve_dirs(raw_folders, kind="레퍼런스", flag="--reference-folder")


def resolve_reuse_folders(raw_folders: list[str] | None) -> list[Path]:
    """--reuse-folder(재사용 플랫폼/SDK) 디렉터리들을 검증한다."""
    return _resolve_dirs(raw_folders, kind="재사용 플랫폼", flag="--reuse-folder")


def _scan_reference_folder(folder: Path) -> tuple[list[Path], list[Path]]:
    """레퍼런스를 재귀 스캔해 (맵에 넣을 파일, 최상위 오리엔테이션 문서)를 돌려준다.

    - 숨김 디렉터리(.git 등)는 제외한다.
    - 빌드 산출물/패키지 디렉터리(obj/bin/TestResults 등, REFERENCE_MAP_SKIP_DIRS)도 제외한다.
    - 이미지/바이너리(REFERENCE_MAP_SKIP_SUFFIXES)는 맵에서 제외한다(LLM이 못 읽음).
    - 오리엔테이션(README/AGENTS/CLAUDE)은 레퍼런스 최상위에 있을 때만 인라인 대상으로 모으고,
      맵에서는 뺀다(본문을 인라인하므로 중복 표시할 필요 없음).
    """
    map_files: list[Path] = []
    orientation: list[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(folder).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if any(part.lower() in REFERENCE_MAP_SKIP_DIRS for part in rel_parts[:-1]):
            continue
        if len(rel_parts) == 1 and path.name.lower() in REFERENCE_ORIENTATION_NAMES:
            orientation.append(path)
            continue
        if path.suffix.lower() in REFERENCE_MAP_SKIP_SUFFIXES:
            continue
        map_files.append(path)
    return map_files, orientation


def _render_folder_maps(folders: list[Path], *, root_label: str) -> list[str]:
    """폴더들을 스캔해 (오리엔테이션 인라인 + 파일 맵) 블록 라인들을 만든다.

    참고 레퍼런스와 재사용 플랫폼 섹션이 공유한다(헤더 문구만 다르고 맵 렌더링은 동일).
    """
    out: list[str] = []
    for folder in folders:
        map_files, orientation = _scan_reference_folder(folder)
        out.append(f"### {root_label}: {_display_path(folder)}")
        out.append(f"(절대경로: {folder})")
        out.append("")
        for doc in orientation:
            try:
                content = doc.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            out.append(
                f"#### 오리엔테이션: {_display_path(doc)}\n```\n"
                + content[:INLINE_TEXT_MAX_CHARS]
                + "\n```\n"
            )
        truncated = len(map_files) > REFERENCE_MAP_MAX_FILES
        shown = map_files[:REFERENCE_MAP_MAX_FILES]
        header = f"#### 파일 맵 (총 {len(map_files)}개, 이미지/바이너리·빌드산출물 제외"
        header += ", 일부만 표시)" if truncated else ")"
        out.append(header)
        out.append("필요할 때 아래 경로(repo 루트 기준 상대경로)를 직접 열어 참고하라:")
        out.append("```")
        out.extend(_display_path(path) for path in shown)
        if truncated:
            out.append(f"... (그 외 {len(map_files) - len(shown)}개 생략)")
        out.append("```")
        out.append("")
    return out


def build_reuse_section(reuse_folders: list[Path]) -> str:
    """재사용 플랫폼/내부 SDK 섹션. 레퍼런스와 '반대로' 최대 재사용·의존을 못박는다."""
    if not reuse_folders:
        return ""
    out: list[str] = [
        "## 재사용 플랫폼 / 내부 SDK (최대한 재사용 — 재구현 금지)",
        "아래는 우리 회사가 이미 개발해 둔 내부 플랫폼/SDK 코드베이스다. 우리 프로젝트는 이 플랫폼 '위에' 올린다.",
        "원칙: 여기 있는 기반 클래스·모듈·서비스를 새로 만들지 말고 그대로 가져다 쓴다(의존/상속/등록).",
        "- 플랫폼이 이미 제공하는 것을 '재구현하는 feature'로 만들지 마라. 대신 '플랫폼 모듈 X를 가져와 등록/설정/상속'하는 식으로 feature를 잡아라.",
        "- refined_prompt에는 재사용할 구체적 플랫폼 자산(모듈/기반 클래스/인터페이스 이름)을 직접 지목하라.",
        "- 공개 API와 등록 방식을 모르면 추측하지 말고, 아래 파일 맵에서 해당 파일(특히 *Module.cs, 오리엔테이션 문서, 템플릿 프로젝트)을 직접 열어 확인하라.",
        "맵은 경로만 준다. 본문은 붙이지 않는다. 필요한 파일만 너의 파일 읽기 도구로 직접 열어라.",
        "",
    ]
    out.extend(_render_folder_maps(reuse_folders, root_label="재사용 플랫폼 루트"))
    return "\n".join(out).rstrip() + "\n"


def build_references_section(reference_folders: list[Path]) -> str:
    """참고 레퍼런스 섹션. 명세가 아니라 '플랫폼을 조합한 형제 앱 예시'임을 못박고 파일 맵을 준다."""
    if not reference_folders:
        return ""
    out: list[str] = [
        "## 참고 레퍼런스 (명세 아님 — 통째로 베끼지 말 것)",
        "아래는 우리가 만들 프로젝트가 아니라, 같은 플랫폼 위에 이미 만들어진 '형제 앱/예시' 코드베이스다.",
        "이것을 요구사항이나 구현 대상으로 착각하지 마라. 앱 고유 기능을 그대로 끌어오거나 통째로 복제하지 마라.",
        "용도: 플랫폼을 '어떻게 조합해' 하나의 앱으로 완성했는지(레이어 구조·모듈 조립·네이밍·의존성 패턴)를 보고 우리 분해에 참고하는 것이다.",
        "맵은 경로만 준다. 본문은 붙이지 않는다. 필요한 파일만 너의 파일 읽기 도구로 직접 열어 확인하라.",
        "",
    ]
    out.extend(_render_folder_maps(reference_folders, root_label="레퍼런스 루트"))
    return "\n".join(out).rstrip() + "\n"


def build_planning_question_prompt(
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path] | None = None,
    reuse_folders: list[Path] | None = None,
    transcript: list[dict[str, Any]],
    round_no: int,
) -> str:
    sections = [PLANNING_PRESET, "", build_inputs_section(plan_files)]
    reuse = build_reuse_section(reuse_folders or [])
    if reuse:
        sections.append(reuse)
    references = build_references_section(reference_folders or [])
    if references:
        sections.append(references)
    if request:
        sections.append("## 원본 요청/지시\n" + request + "\n")
    sections.append(
        "## 지금까지의 질의응답\n```json\n"
        + json.dumps(transcript, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    sections.append(
        f"## 현재 임무 (라운드 {round_no})\n"
        "프로젝트를 feature로 정확히 분해하기 위해 가장 모호한 점 하나를 사용자에게 질문하라.\n"
        "feature 경계, 선후 의존성, 우선순위/티어, 제외 범위가 충분히 분명해지면 action=final로 분해를 시작하라.\n"
    )
    sections.append("## 출력 계약\n" + PLANNING_QUESTION_SCHEMA)
    return "\n".join(sections)


def build_decompose_prompt(
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path] | None = None,
    reuse_folders: list[Path] | None = None,
    transcript: list[dict[str, Any]],
) -> str:
    sections = [PLANNING_PRESET, "", build_inputs_section(plan_files)]
    reuse = build_reuse_section(reuse_folders or [])
    if reuse:
        sections.append(reuse)
    references = build_references_section(reference_folders or [])
    if references:
        sections.append(references)
    if request:
        sections.append("## 원본 요청/지시\n" + request + "\n")
    if transcript:
        sections.append(
            "## 사전 질의응답 기록\n```json\n"
            + json.dumps(transcript, ensure_ascii=False, indent=2)
            + "\n```\n"
        )
    sections.append(
        "## 현재 임무\n"
        "프로젝트 기획을 독립적으로 출하 가능한 feature 단위로 분해하고,\n"
        "각 feature의 의존성(depends_on)과 추천 티어(tier)를 정한다.\n"
    )
    sections.append("## 출력 계약\n" + DECOMPOSE_SCHEMA)
    return "\n".join(sections)


def build_draft_decompose_prompt(
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path] | None,
    reuse_folders: list[Path] | None,
    transcript: list[dict[str, Any]],
) -> str:
    """블라인드 독립 초안용 프롬프트: 일반 분해 프롬프트 + 독립 초안 지시."""
    base = build_decompose_prompt(
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        transcript=transcript,
    )
    return base + "\n\n" + DRAFT_INSTRUCTION


def _candidates_block(candidates: list[dict[str, Any]]) -> str:
    """익명 초안들을 '초안 A/B/C' 블록으로 만든다(작성 provider 신원 제거)."""
    blocks: list[str] = []
    for index, candidate in enumerate(candidates):
        label = chr(ord("A") + index) if index < 26 else str(index + 1)
        body = json.dumps(candidate, ensure_ascii=False, indent=2)[:CANDIDATE_MAX_CHARS]
        blocks.append(f"### 초안 {label}\n```json\n{body}\n```")
    return "## 독립 분해 초안들 (익명)\n" + "\n\n".join(blocks) + "\n"


def build_candidates_decompose_prompt(
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path] | None,
    reuse_folders: list[Path] | None,
    transcript: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    instruction: str,
) -> str:
    """익명 초안들 + 지시(종합/방향선택)를 붙인 프롬프트. parallel 종합과 max 선택이 공유."""
    base = build_decompose_prompt(
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        transcript=transcript,
    )
    return base + "\n\n" + _candidates_block(candidates) + "\n" + instruction


def build_max_stage_prompt(
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path] | None,
    reuse_folders: list[Path] | None,
    transcript: list[dict[str, Any]],
    history: list[tuple[str, dict[str, Any]]],
    instruction: str,
) -> str:
    """max 릴레이(ground/premortem)용: 지금까지의 '모든' 산출물을 한 번에 보여준다.

    원본 블라인드 초안 전부 + 완료된 릴레이 단계 결과를 누적해서 넣고, 마지막 항목을 '현재 최신본'으로
    표시한다. 각 단계가 직전 결과만이 아니라 드롭된 초안과 모든 중간 결과를 보도록 한다(deep_thinking과 동일).
    """
    base = build_decompose_prompt(
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        transcript=transcript,
    )
    blocks: list[str] = []
    last = len(history) - 1
    for index, (label, decomp) in enumerate(history):
        body = json.dumps(decomp, ensure_ascii=False, indent=2)[:CANDIDATE_MAX_CHARS]
        marker = (
            "  <- 현재 최신본: 이걸 기준으로 작업하되, 위 산출물(드롭된 초안 포함)도 모두 참고하라."
            if index == last
            else ""
        )
        blocks.append(f"### {label}{marker}\n```json\n{body}\n```")
    section = "## 지금까지의 모든 산출물 (전부 참고하라)\n" + "\n\n".join(blocks) + "\n"
    return base + "\n\n" + section + "\n" + instruction


def available_plan_providers(harness: Any) -> list[str]:
    """plan 능력이 있고 실제 사용 가능한 provider를 harness 기준 순서로 돌려준다."""
    result: list[str] = []
    for provider in harness.known_provider_names():
        try:
            if harness.provider_available(provider) and "plan" in harness.provider_capabilities(provider):
                result.append(provider)
        except Exception:  # noqa: BLE001 - 탐색 실패한 provider는 조용히 건너뛴다.
            continue
    return result


def _collect_blind_drafts(
    harness: Any,
    args: argparse.Namespace,
    *,
    draft_prompt: str,
    drafters: list[str],
    logs_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    """drafter들을 순차로(서로 안 보게) 돌려 (유효 초안, 성공한 provider)를 모은다.

    parallel·max가 공유한다. 실패/무효 초안은 경고만 남기고 건너뛴다.
    """
    candidates: list[dict[str, Any]] = []
    succeeded: list[str] = []
    total = len(drafters)
    for index, drafter in enumerate(drafters, start=1):
        try:
            candidate = plan_model_json(
                harness,
                args,
                provider=drafter,
                prompt=draft_prompt,
                logs_dir=logs_dir,
                log_prefix=f"draft_{drafter}",
                repair_schema=DECOMPOSE_SCHEMA,
                status_message=f"독립 초안 작성 중 ({drafter}, {index}/{total})",
            )
        except di.InterviewError as exc:
            print(f"  초안 실패({drafter}): {exc} - 건너뜀", file=sys.stderr)
            continue
        features = candidate.get("features")
        if isinstance(features, list) and features:
            candidates.append(candidate)
            succeeded.append(drafter)
        else:
            print(f"  초안 무효({drafter}): features 배열 없음 - 건너뜀", file=sys.stderr)
    return candidates, succeeded


def _rotated(seq: list[str], start: int) -> list[str]:
    if not seq:
        return []
    offset = start % len(seq)
    return list(seq[offset:]) + list(seq[:offset])


def _assign_relay_providers(phase_count: int, pool: list[str], owner: str) -> list[str]:
    """릴레이 각 단계에 provider를 배정한다. 마지막은 항상 owner, 인접 단계는 가능하면 다른 provider."""
    pool = list(dict.fromkeys(pool)) or [owner]
    assigned = [owner] * phase_count
    for i in range(phase_count - 2, -1, -1):
        nxt = assigned[i + 1]
        used = set(assigned[i + 1:])
        assigned[i] = (
            next((p for p in _rotated(pool, i) if p != nxt and p not in used), None)
            or next((p for p in _rotated(pool, i) if p != nxt), pool[0])
        )
    return assigned


def run_parallel_decompose(
    harness: Any,
    args: argparse.Namespace,
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path],
    reuse_folders: list[Path],
    transcript: list[dict[str, Any]],
    logs_dir: Path,
) -> dict[str, Any]:
    """parallel 전략: 가용 provider들이 블라인드 독립 초안 -> --model이 종합.

    품질은 '블라인드 독립성'에서 나오므로 초안은 순차로(서로 안 보게) 돌린다.
    초안이 0개면 실패, 1개면 종합 없이 승격, 2개 이상이면 owner(--model)가 종합한다.
    """
    owner = args.model
    drafters = available_plan_providers(harness)

    def _single(status: str) -> dict[str, Any]:
        prompt = build_decompose_prompt(
            request=request,
            plan_files=plan_files,
            reference_folders=reference_folders,
            reuse_folders=reuse_folders,
            transcript=transcript,
        )
        return plan_model_json(
            harness,
            args,
            prompt=prompt,
            logs_dir=logs_dir,
            log_prefix="decompose",
            repair_schema=DECOMPOSE_SCHEMA,
            status_message=status,
        )

    if len(drafters) < 2:
        print(
            f"warning: 사용 가능한 planning provider가 {len(drafters)}개뿐이라 "
            "parallel 대신 단일 분석으로 진행합니다.",
            file=sys.stderr,
        )
        return _single("프로젝트를 feature로 분해하는 중")

    print(f"parallel 분해: 블라인드 초안 {len(drafters)}개({', '.join(drafters)}) -> 종합({owner})")
    draft_prompt = build_draft_decompose_prompt(
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        transcript=transcript,
    )
    candidates, _succeeded = _collect_blind_drafts(
        harness, args, draft_prompt=draft_prompt, drafters=drafters, logs_dir=logs_dir
    )

    if not candidates:
        raise PlanningError("모든 분해 초안이 실패했습니다. logs를 확인하세요.")
    if len(candidates) == 1:
        print("  유효 초안이 1개라 종합 없이 그대로 사용합니다.")
        return candidates[0]

    synthesis_prompt = build_candidates_decompose_prompt(
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        transcript=transcript,
        candidates=candidates,
        instruction=SYNTHESIS_INSTRUCTION,
    )
    return plan_model_json(
        harness,
        args,
        provider=owner,
        prompt=synthesis_prompt,
        logs_dir=logs_dir,
        log_prefix="synthesis",
        repair_schema=DECOMPOSE_SCHEMA,
        status_message=f"초안 {len(candidates)}개를 종합하는 중 ({owner})",
    )


def run_max_decompose(
    harness: Any,
    args: argparse.Namespace,
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path],
    reuse_folders: list[Path],
    transcript: list[dict[str, Any]],
    logs_dir: Path,
) -> dict[str, Any]:
    """max 전략: 블라인드 초안(넓이) -> grounded 순차 릴레이(깊이).

    릴레이 단계는 서로 다른 일을 한다: 방향 선택 -> 레퍼런스 코드 대조·심화 -> 사전 부검·확정.
    단계마다 다른 provider(no-adjacent)를 쓰고 마지막은 항상 owner(--model). 초안이 1개면 방향 선택은
    생략하고 grounded 심화와 사전 부검은 그대로 수행한다. 각 단계가 무효/실패하면 직전 결과를 유지한다.
    """
    owner = args.model
    drafters = available_plan_providers(harness) or [owner]
    if not reference_folders and not reuse_folders:
        print(
            "warning: --reference-folder/--reuse-folder 없이 max를 쓰면 grounding 단계가 약해집니다(코드 대조 대상 없음).",
            file=sys.stderr,
        )

    print(
        f"max 분해: 블라인드 초안 {len(drafters)}개({', '.join(drafters)}) "
        f"-> grounded 릴레이 -> 확정({owner})"
    )
    draft_prompt = build_draft_decompose_prompt(
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        transcript=transcript,
    )
    candidates, succeeded = _collect_blind_drafts(
        harness, args, draft_prompt=draft_prompt, drafters=drafters, logs_dir=logs_dir
    )
    if not candidates:
        raise PlanningError("모든 분해 초안이 실패했습니다. logs를 확인하세요.")

    phases = (["select"] if len(candidates) >= 2 else []) + ["ground", "premortem"]
    providers = _assign_relay_providers(len(phases), succeeded or [owner], owner)
    print("  릴레이: " + " -> ".join(f"{ph}({pr})" for ph, pr in zip(phases, providers)))

    # 모든 릴레이 단계가 '전부' 보는 산출물 히스토리: 원본 블라인드 초안부터 시작해 완료된 단계를 누적한다.
    history: list[tuple[str, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        label = chr(ord("A") + index) if index < 26 else str(index + 1)
        history.append((f"블라인드 초안 {label}", candidate))

    working = candidates[0]
    for phase, provider in zip(phases, providers):
        if phase == "select":
            # 방향 선택은 익명 초안들 중에서 고르는 단계(아직 '최신본' 개념 없음).
            prompt = build_candidates_decompose_prompt(
                request=request,
                plan_files=plan_files,
                reference_folders=reference_folders,
                reuse_folders=reuse_folders,
                transcript=transcript,
                candidates=candidates,
                instruction=SELECT_INSTRUCTION,
            )
            log_prefix, status = "max_select", f"방향 선택 중 ({provider})"
        else:
            instruction = GROUND_INSTRUCTION if phase == "ground" else PREMORTEM_INSTRUCTION
            prompt = build_max_stage_prompt(
                request=request,
                plan_files=plan_files,
                reference_folders=reference_folders,
                reuse_folders=reuse_folders,
                transcript=transcript,
                history=history,
                instruction=instruction,
            )
            log_prefix = f"max_{phase}"
            status = (
                f"레퍼런스 대조·심화 중 ({provider})"
                if phase == "ground"
                else f"사전 부검·확정 중 ({provider})"
            )
        try:
            result = plan_model_json(
                harness,
                args,
                provider=provider,
                prompt=prompt,
                logs_dir=logs_dir,
                log_prefix=log_prefix,
                repair_schema=DECOMPOSE_SCHEMA,
                status_message=status,
            )
        except di.InterviewError as exc:
            print(f"  {phase} 실패({provider}): {exc} - 직전 결과 유지", file=sys.stderr)
            result = None
        if isinstance((result or {}).get("features"), list) and result["features"]:
            working = result
            history.append((f"[{phase}] 결과", result))
        elif result is not None:
            print(f"  {phase} 결과 무효({provider}) - 직전 결과 유지", file=sys.stderr)
    return working


def _run_agy_via_file(
    harness: Any,
    args: argparse.Namespace,
    *,
    prompt: str,
    logs_dir: Path,
    log_prefix: str,
    status_message: str,
) -> dict[str, Any]:
    """agy 전용 실행: 결과 JSON을 stdout이 아니라 '파일'로 받는다.

    agy는 --print에서도 Cascade 에이전트라 파일 읽기/쓰기는 자연스럽지만 최종 답을 stdout으로는
    잘 못 낸다(planner 단계로 끝나며 빈 출력). 그래서 빌드 하네스가 stage 산출물을 'provider가 쓴
    파일'로 받는 것과 같은 원리로, 프롬프트로 결과를 캐시 파일에 쓰게 하고 그 파일을 읽어 파싱한다.
    이러면 agy가 입력(PDF/소스)을 자유롭게 다 읽으면서(=codex/claude와 동등) 출력은 안정적이다.
    캐시는 읽은 뒤 삭제한다. 실패(파일 없음/깨짐 + stdout 폴백도 실패)하면 di.InterviewError를 올려
    호출부(_collect_blind_drafts / max 릴레이)가 초안을 드롭하게 한다.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    AGY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # .ai/ 밖 비숨김 경로(agy가 .ai를 hidden으로 무시함)
    stamp = harness.now_stamp() if hasattr(harness, "now_stamp") else time.strftime("%Y%m%d-%H%M%S")
    cache_path = AGY_OUTPUT_DIR / f"{log_prefix}_agy_out_{stamp}.json"
    cache_abs = cache_path.resolve()
    try:  # 상대경로는 워크스페이스(ROOT=--add-dir) 기준
        cache_rel = cache_abs.relative_to(ROOT).as_posix()
    except ValueError:
        cache_rel = cache_abs.as_posix()
    instruction = AGY_FILE_OUTPUT_INSTRUCTION.format(
        rel_path=cache_rel, abs_path=cache_abs.as_posix()
    )
    # 파일쓰기 지시를 '최상단'에 둬 deliverable 해석을 누르고, 말미에 짧게 재강조한다(거대 프롬프트 recency 보강).
    file_prompt = (
        instruction
        + "\n\n"
        + prompt.rstrip()
        + "\n\n"
        + AGY_FILE_OUTPUT_TAIL_REMINDER.format(rel_path=cache_rel)
        + "\n"
    )
    try:  # 이전 잔여 캐시 제거(있으면)
        cache_path.unlink()
    except OSError:
        pass

    try:
        with di.Spinner(status_message):
            result = di.run_deep_interview_provider_prompt(
                harness,
                "agy",
                file_prompt,
                logs_dir=logs_dir,
                log_prefix=log_prefix,
                timeout_seconds=args.timeout,
                performance=args.performance,
            )
    except Exception as exc:  # noqa: BLE001 - provider 배관이 여러 예외를 올린다.
        raise di.InterviewError(f"Provider call failed for agy: {exc}") from exc

    if result.get("timed_out"):
        raise di.InterviewError(f"agy timed out after {args.timeout} seconds.")
    returncode = result.get("returncode")
    if returncode not in {0, None}:
        raise di.InterviewError(
            f"agy exited with code {returncode}. "
            f"stdout={result.get('stdout')} stderr={result.get('stderr')}"
        )

    raw = ""
    if cache_path.exists():
        try:
            raw = cache_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
    if not raw.strip():  # 파일이 비었으면 혹시 stdout으로 냈는지 폴백
        raw = di.provider_text(result)
    try:
        parsed = di.extract_json_object(raw)
    except di.InterviewError as exc:
        # 실패 시 캐시를 '남겨' 둔다(진단용): agy가 무엇을 썼는지/안 썼는지 직접 확인 가능.
        diag = f"출력 파일 남겨둠: {cache_rel}" if cache_path.exists() else "agy가 출력 파일을 쓰지 않음(brain 폴더 확인)"
        raise di.InterviewError(
            f"agy가 유효한 JSON을 파일({cache_rel})에도 stdout에도 내지 않았습니다. (진단: {diag})"
        ) from exc
    try:  # 성공 시에만 캐시 정리
        cache_path.unlink()
    except OSError:
        pass
    return parsed


def plan_model_json(
    harness: Any,
    args: argparse.Namespace,
    *,
    prompt: str,
    logs_dir: Path,
    log_prefix: str,
    repair_schema: str,
    status_message: str,
    provider: str | None = None,
) -> dict[str, Any]:
    resolved_provider = provider or args.model
    if resolved_provider == "agy":  # agy는 stdout이 비므로 파일 인터페이스로 받는다.
        return _run_agy_via_file(
            harness,
            args,
            prompt=prompt,
            logs_dir=logs_dir,
            log_prefix=log_prefix,
            status_message=status_message,
        )
    return di.model_json(
        harness,
        provider=resolved_provider,
        prompt=prompt,
        logs_dir=logs_dir,
        log_prefix=log_prefix,
        timeout_seconds=args.timeout,
        performance=args.performance,
        repair_schema=repair_schema,
        status_message=status_message,
    )


def print_planning_question(data: dict[str, Any], round_no: int) -> None:
    print()
    print(f"[질문 {round_no}] {di.compact_text(data.get('question'))}")
    why = di.compact_text(data.get("why"))
    if why:
        print(f"이유: {why}")
    options = data.get("options")
    if isinstance(options, list):
        for index, option in enumerate(options, start=1):
            if isinstance(option, dict):
                label = str(option.get("label") or option.get("value") or f"선택 {index}")
                description = di.compact_text(option.get("description"))
                suffix = f" - {description}" if description else ""
                print(f"  {index}. {label}{suffix}")
            else:
                print(f"  {index}. {option}")


def run_interactive(
    harness: Any,
    args: argparse.Namespace,
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path],
    reuse_folders: list[Path],
    logs_dir: Path,
) -> list[dict[str, Any]] | None:
    """질문 라운드(무제한, /done으로 종료)를 돌려 transcript를 모은다. /cancel이면 None."""
    transcript: list[dict[str, Any]] = []
    print("project planning (interactive): `/done` 분해 시작, `/cancel` 취소")
    for round_no in range(1, MAX_SAFETY_ROUNDS + 1):
        prompt = build_planning_question_prompt(
            request=request,
            plan_files=plan_files,
            reference_folders=reference_folders,
            reuse_folders=reuse_folders,
            transcript=transcript,
            round_no=round_no,
        )
        data = plan_model_json(
            harness,
            args,
            prompt=prompt,
            logs_dir=logs_dir,
            log_prefix=f"q{round_no}",
            repair_schema=PLANNING_QUESTION_SCHEMA,
            status_message=f"질문을 고르는 중 (라운드 {round_no})",
        )
        if str(data.get("action") or "").lower() == "final":
            break
        question = str(data.get("question") or "").strip()
        if not question:
            break
        print_planning_question(data, round_no)
        raw_answer = input("답변> ").strip()
        lowered = raw_answer.lower()
        if lowered in {"/cancel", "cancel", "quit", "exit"}:
            print("취소되었습니다.")
            return None
        if lowered in {"/done", "done", "final", "finish"}:
            transcript.append({"round": round_no, "question": question, "answer": "(사용자가 분해 시작 요청)"})
            break
        transcript.append(
            {
                "round": round_no,
                "question": question,
                "why": str(data.get("why") or ""),
                "answer": raw_answer,
            }
        )
    else:
        print(f"최대 라운드({MAX_SAFETY_ROUNDS}) 도달 - 현재까지 내용으로 분해합니다.")
    return transcript


def topological_order(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """feature를 의존성 위상정렬한다. 각 feature에 _slug/_deps/_id를 채운다. 순환이면 PlanningError."""
    by_slug: dict[str, dict[str, Any]] = {}
    order_index: dict[str, int] = {}
    for index, feature in enumerate(features):
        base = slugify(feature.get("slug") or feature.get("title"), fallback=f"feature-{index + 1}")
        slug = base
        suffix = 2
        while slug in by_slug:
            slug = f"{base}-{suffix}"
            suffix += 1
        feature["_slug"] = slug
        by_slug[slug] = feature
        order_index[slug] = index

    for feature in features:
        deps: list[str] = []
        for raw_dep in feature.get("depends_on") or []:
            dep_slug = slugify(raw_dep, fallback="")
            if dep_slug and dep_slug in by_slug and dep_slug != feature["_slug"] and dep_slug not in deps:
                deps.append(dep_slug)
        feature["_deps"] = deps

    indegree = {slug: len(by_slug[slug]["_deps"]) for slug in by_slug}
    dependents: dict[str, list[str]] = {slug: [] for slug in by_slug}
    for slug in by_slug:
        for dep in by_slug[slug]["_deps"]:
            dependents[dep].append(slug)

    queue: deque[str] = deque(
        sorted((slug for slug in by_slug if indegree[slug] == 0), key=lambda s: order_index[s])
    )
    ordered: list[dict[str, Any]] = []
    while queue:
        slug = queue.popleft()
        ordered.append(by_slug[slug])
        freed = []
        for dependent in dependents[slug]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                freed.append(dependent)
        for dependent in sorted(freed, key=lambda s: order_index[s]):
            queue.append(dependent)

    if len(ordered) != len(by_slug):
        done = {feature["_slug"] for feature in ordered}
        remaining = sorted((slug for slug in by_slug if slug not in done), key=lambda s: order_index[s])
        raise PlanningError(
            "순환 의존성이 감지되어 순서를 정할 수 없습니다(분해 그래프에 사이클).\n"
            f"관련 feature: {', '.join(remaining)}"
        )

    for position, feature in enumerate(ordered, start=1):
        feature["_id"] = f"{position:02d}-{feature['_slug']}"
    return ordered


def tier_to_invocation(tier: Any) -> tuple[str, list[str]]:
    normalized = str(tier or "full").strip().lower()
    mapping = {
        "fast": (".ai/harness_fast.py", []),
        "standard": (".ai/harness_standard.py", []),
        "full": (".ai/harness.py", []),
        "full-parallel": (".ai/harness.py", ["--deep-thinking", "--strategy", "parallel"]),
        "full-sequential": (".ai/harness.py", ["--deep-thinking", "--strategy", "sequential"]),
        "full-max": (".ai/harness.py", ["--deep-thinking", "--strategy", "max"]),
    }
    return mapping.get(normalized, (".ai/harness.py", []))


def normalize_performance(value: Any, tier: Any) -> str:
    """feature의 performance를 lite/medium/high로 정규화한다.

    모델이 직접 준 값이 유효하면 그대로 쓰고, 비었거나 이상하면 tier 기반 기본값으로 떨어뜨린다
    (= 사용자가 따로 지정 안 해도 작업량/티어에 따라 알아서 정해지도록).
    """
    text = str(value or "").strip().lower()
    if text in PERFORMANCE_SET:
        return text
    return DEFAULT_PERFORMANCE_BY_TIER.get(str(tier or "").strip().lower(), "medium")


def feature_performance(feature: dict[str, Any]) -> str:
    cached = feature.get("_performance")
    if cached in PERFORMANCE_SET:
        return cached
    return normalize_performance(feature.get("performance"), feature.get("tier"))


def quote_arg(value: Any) -> str:
    # cmd/PowerShell 양쪽에서 안전하도록 한 줄로 만들고 내부 큰따옴표는 작은따옴표로 치환한다.
    text = di.compact_text(value).replace('"', "'")
    return '"' + text + '"'


def feature_command(feature: dict[str, Any]) -> str:
    script, extra = tier_to_invocation(feature.get("tier"))
    prompt = feature.get("refined_prompt") or feature.get("description") or feature.get("title") or feature["_slug"]
    parts = [
        "python",
        script,
        "run",
        quote_arg(prompt),
        "--feature",
        feature["_id"],
        "--performance",
        feature_performance(feature),
        "--yes",
        "--defaults",
        *extra,
    ]
    return " ".join(parts)


def render_plan_text(
    *,
    project_slug: str,
    summary: str,
    model: str,
    mode: str,
    plan_files: list[Path],
    ordered: list[dict[str, Any]],
    reference_folders: list[Path] | None = None,
    reuse_folders: list[Path] | None = None,
    strategy: str = "single",
) -> str:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"프로젝트 계획: {summary or project_slug}")
    lines.append("=" * 78)
    lines.append(f"project_slug : {project_slug}")
    lines.append(f"생성         : {timestamp}")
    lines.append(f"모델         : {model}")
    lines.append(f"모드         : {mode}")
    lines.append(f"전략         : {strategy}")
    lines.append(f"feature 수   : {len(ordered)}")
    if plan_files:
        lines.append("입력 기획서  :")
        lines.extend(f"  - {path}" for path in plan_files)
    else:
        lines.append("입력 기획서  : (없음, 요청 텍스트 기반)")
    if reuse_folders:
        lines.append("재사용 플랫폼:")
        lines.extend(f"  - {path}" for path in reuse_folders)
    if reference_folders:
        lines.append("참고 레퍼런스:")
        lines.extend(f"  - {path}" for path in reference_folders)
    lines.append("")

    lines.append("-" * 78)
    lines.append("실행 순서 (의존성 위상정렬)")
    lines.append("-" * 78)
    for feature in ordered:
        deps = feature.get("_deps") or []
        dep_ids = []
        id_by_slug = {f["_slug"]: f["_id"] for f in ordered}
        for dep in deps:
            dep_ids.append(id_by_slug.get(dep, dep))
        lines.append(
            f"[{feature['_id']}]  tier={feature.get('tier') or 'full'}  perf={feature_performance(feature)}"
        )
        title = di.compact_text(feature.get("title"))
        if title:
            lines.append(f"  제목   : {title}")
        description = di.compact_text(feature.get("description"))
        if description:
            lines.append(f"  설명   : {description}")
        lines.append(f"  선행   : {', '.join(dep_ids) if dep_ids else '없음'}")
        tier_reason = di.compact_text(feature.get("tier_reason"))
        if tier_reason:
            lines.append(f"  티어이유: {tier_reason}")
        perf_reason = di.compact_text(feature.get("performance_reason"))
        if perf_reason:
            lines.append(f"  성능이유: {perf_reason}")
        lines.append("")

    lines.append("-" * 78)
    lines.append("연속 실행 명령어 모음")
    lines.append("위에서부터 의존성 순서대로 차례로 실행하세요.")
    lines.append("한 줄(feature)이 실패하면 멈추고 원인을 해결한 뒤 다음 줄로 진행하길 권장합니다.")
    lines.append("필요하면 아래 줄들을 그대로 .bat / .sh 파일에 붙여 쓰세요. (추천일 뿐, 그대로 돌릴 의무는 없습니다.)")
    lines.append("-" * 78)
    for feature in ordered:
        lines.append(
            f"# {feature['_id']}  (tier={feature.get('tier') or 'full'}, perf={feature_performance(feature)})"
        )
        lines.append(feature_command(feature))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --update-contract 전용. 분해가 '완전히 끝난 뒤' 별도 에이전트(분해 owner와 동일 모델)를 한 번 더
# 호출해, 현재 project_contract.md에 이 프로젝트 전역 규칙을 '추가'만 한다(삭제·수정 없음).
# 입력은 분해가 썼던 근거(기획서 + reuse/reference 코드 맵) + 분해 최종 결과 요약 + 현재 계약이다.
# 중간 심의 과정(드래프트/select/ground/premortem)은 주지 않는다(신호 대비 잡음이 낮고 보존되지 않음).
CONTRACT_UPDATE_RULE_MAX_CHARS = 220

CONTRACT_UPDATE_PRESET = """
너는 방금 분해한 프로젝트의 전체 시야를 바탕으로, 이 프로젝트의 Project Contract(프로젝트 전역 규약)에 '추가'할 새 규칙만 제안하는 담당자다.

핵심 원칙:
- 기존 규칙은 절대 삭제하거나 수정하지 않는다. 너는 오직 '추가할 새 규칙'만 제안한다.
- 추가 규칙은 이 프로젝트의 실제 스택/아키텍처/도메인에 근거해야 한다. 특히 '재사용 플랫폼/내부 SDK'와 '참고 레퍼런스' 코드, 그리고 기획서에서 드러난 프로젝트 전역 규칙을 찾는다.
- project_wide 규칙만 제안한다: 많은 미래 feature에 걸쳐 적용되고, 오래 가며, 특정 feature나 일회성 구현 디테일이 아니다.
- 이미 현재 계약이 다루는 내용은 다시 제안하지 않는다.
- 추측하지 말고 실제로 연 파일/기획서에 근거한다. 근거가 없으면 제안하지 않는다.

좋은 추가 예:
- "이 프로젝트는 Python이므로 함수와 변수는 snake_case를 따른다" (스택이 기존 기본값과 다를 때 그 프로젝트의 관례를 못박아, 기존의 일반적 기본값 규칙이 이에 양보하게 함)
- "모든 화면/모듈은 재사용 플랫폼의 기반 모듈을 상속해 등록한다"
- "외부 시세/시장 데이터는 단일 어댑터 인터페이스에서만 받는다"

금지:
- 기존 규칙 삭제·수정 제안
- feature 한정·구현 디테일·일회성 관찰
- 파일 수정, shell 실행
""".strip()


CONTRACT_UPDATE_SCHEMA = """
반드시 JSON 객체 하나만 출력한다.

{
  "summary": "이번에 추가 제안하는 내용을 한국어 한두 문장으로",
  "added_rules": [
    {
      "target_section": "Hard Rules | Project Layout | Architecture | Code Style | Data | Reliability | Testing | Dependencies | Other (기존 섹션 우선, 적절한 게 없으면 새 섹션 이름)",
      "rule_text": "추가할 최종 규칙 한 문장(한국어, 간결)",
      "reason": "왜 이 프로젝트의 전역 규칙으로 가치가 있는지 짧게(스택/레퍼런스/기획서 근거)"
    }
  ]
}

규칙:
- 추가할 규칙이 없으면 added_rules를 빈 배열 []로 둔다.
- rule_text는 한 문장, 160자 이내를 권장한다(최대 220자).
- 기존 계약에 이미 있는 규칙은 넣지 않는다.
- JSON 밖에 설명 문장을 쓰지 않는다.
""".strip()


def _contract_feature_summary(ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """계약 에이전트용 분해 결과 요약(구조 프레이밍). 구현 디테일은 빼고 id/제목/티어만 준다."""
    return [
        {"id": feature.get("_id"), "title": di.compact_text(feature.get("title")), "tier": feature.get("tier")}
        for feature in ordered
    ]


def build_contract_update_prompt(
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path] | None,
    reuse_folders: list[Path] | None,
    ordered: list[dict[str, Any]],
    summary: str,
    current_contract: str,
) -> str:
    """추가-전용 계약 갱신 프롬프트: 분해 근거 입력 + 최종 결과 요약 + 현재 계약."""
    sections = [CONTRACT_UPDATE_PRESET, "", build_inputs_section(plan_files)]
    reuse = build_reuse_section(reuse_folders or [])
    if reuse:
        sections.append(reuse)
    references = build_references_section(reference_folders or [])
    if references:
        sections.append(references)
    if request:
        sections.append("## 원본 요청/지시\n" + request + "\n")
    sections.append(
        "## 방금 확정된 분해 결과 (이 프로젝트가 만들 것들)\n"
        + f"프로젝트 요약: {summary}\n"
        + "```json\n"
        + json.dumps(_contract_feature_summary(ordered), ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    sections.append(
        "## 현재 Project Contract (절대 삭제·수정 금지, 추가만)\n"
        + "```markdown\n"
        + current_contract.strip()
        + "\n```\n"
    )
    sections.append(
        "## 현재 임무\n"
        "위 프로젝트의 실제 스택/아키텍처/도메인 근거로, 현재 계약에 '추가'할 프로젝트 전역 규칙만 제안한다.\n"
        "기존 규칙은 한 줄도 건드리지 않는다. 추가할 게 없으면 added_rules를 빈 배열로 둔다.\n"
    )
    sections.append("## 출력 계약\n" + CONTRACT_UPDATE_SCHEMA)
    return "\n".join(sections)


def run_contract_update(
    harness: Any,
    args: argparse.Namespace,
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path],
    reuse_folders: list[Path],
    ordered: list[dict[str, Any]],
    summary: str,
    current_contract: str,
    logs_dir: Path,
) -> dict[str, Any]:
    """분해 owner와 동일 모델로 추가-전용 계약 갱신 제안을 받는다(별도 1회 호출)."""
    prompt = build_contract_update_prompt(
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        ordered=ordered,
        summary=summary,
        current_contract=current_contract,
    )
    return plan_model_json(
        harness,
        args,
        prompt=prompt,
        logs_dir=logs_dir,
        log_prefix="contract_update",
        repair_schema=CONTRACT_UPDATE_SCHEMA,
        status_message=f"Project Contract 추가 규칙을 추출하는 중 ({args.model})",
    )


def normalize_added_rules(
    proposal: dict[str, Any],
    current_contract: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """제안된 added_rules를 (적용, 건너뜀)으로 가른다.

    - 이미 현재 계약에 있는 문장(부분 문자열 일치) -> already_covered
    - 이번 배치 내 중복 -> duplicate
    - 220자 초과 -> too_long
    """
    raw_rules = proposal.get("added_rules")
    if not isinstance(raw_rules, list):
        return [], []
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        rule_text = di.compact_text(raw.get("rule_text"))
        if not rule_text:
            continue
        section = di.compact_text(raw.get("target_section")) or "Other"
        reason = di.compact_text(raw.get("reason"))
        entry = {"section": section, "rule_text": rule_text, "reason": reason}
        if len(rule_text) > CONTRACT_UPDATE_RULE_MAX_CHARS:
            skipped.append({**entry, "skip_reason": "too_long"})
            continue
        if rule_text in current_contract:
            skipped.append({**entry, "skip_reason": "already_covered"})
            continue
        if rule_text in seen:
            skipped.append({**entry, "skip_reason": "duplicate"})
            continue
        seen.add(rule_text)
        applied.append(entry)
    return applied, skipped


def insert_rule_into_contract(contract_text: str, section: str, rule_text: str) -> str:
    """기존 계약을 보존한 채 `- rule_text` 한 줄만 해당 섹션 끝에 삽입한다.

    섹션이 있으면 그 섹션 마지막 항목 뒤에, 없으면 새 `## section`을 파일 끝에 만든다.
    삭제·수정은 하지 않는다(순수 삽입).
    """
    bullet = f"- {rule_text}"
    target = section.strip().lower()
    lines = contract_text.splitlines()

    header_idx: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and stripped[3:].strip().lower() == target:
            header_idx = index
            break

    if header_idx is None:
        out = list(lines)
        if out and out[-1].strip() != "":
            out.append("")
        out.append(f"## {section}")
        out.append(bullet)
        return "\n".join(out) + "\n"

    section_end = len(lines)
    for index in range(header_idx + 1, len(lines)):
        if lines[index].strip().startswith("## "):
            section_end = index
            break
    insert_at = header_idx + 1
    for index in range(header_idx + 1, section_end):
        if lines[index].strip() != "":
            insert_at = index + 1
    out = lines[:insert_at] + [bullet] + lines[insert_at:]
    return "\n".join(out) + "\n"


def apply_contract_additions(current_contract: str, applied: list[dict[str, Any]]) -> str:
    text = current_contract
    for rule in applied:
        text = insert_rule_into_contract(text, rule["section"], rule["rule_text"])
    return text


def report_contract_additions(
    summary: str,
    applied: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    path: Path,
) -> None:
    print()
    print("=" * 64)
    print("Project Contract 업데이트 (자동 적용됨)")
    print("=" * 64)
    if summary:
        print(summary)
    line = f"추가된 규칙: {len(applied)}개"
    if skipped:
        line += f" / 건너뜀: {len(skipped)}개"
    print(line)
    print()
    for rule in applied:
        print(f"  + [{rule['section']}] {rule['rule_text']}")
        if rule.get("reason"):
            print(f"      이유: {rule['reason']}")
    if skipped:
        print()
        print("  건너뛴 후보(이미 있음/중복/과길이):")
        for item in skipped:
            print(f"  - ({item.get('skip_reason')}) {item.get('rule_text')}")
    print()
    print(f"적용 파일: {path}")


def run_contract_update_phase(
    harness: Any,
    args: argparse.Namespace,
    *,
    request: str,
    plan_files: list[Path],
    reference_folders: list[Path],
    reuse_folders: list[Path],
    ordered: list[dict[str, Any]],
    summary: str,
    logs_dir: Path,
) -> dict[str, Any]:
    """분해 완료 후 별도 1회 호출로 project_contract.md에 규칙을 '추가'하고 자동 적용한다."""
    harness.ensure_project_contract_file()
    contract_path = harness.project_contract_path()
    current = contract_path.read_text(encoding="utf-8")

    proposal = run_contract_update(
        harness,
        args,
        request=request,
        plan_files=plan_files,
        reference_folders=reference_folders,
        reuse_folders=reuse_folders,
        ordered=ordered,
        summary=summary,
        current_contract=current,
        logs_dir=logs_dir,
    )
    applied, skipped = normalize_added_rules(proposal, current)
    proposal_summary = di.compact_text(proposal.get("summary"))

    if not applied:
        print()
        print("Project Contract 업데이트: 추가할 새 규칙이 없습니다. (파일을 변경하지 않음)")
        if skipped:
            print(f"  건너뜀: {len(skipped)}개 (이미 있음/중복/과길이)")
        return {"applied": [], "skipped": skipped, "path": str(contract_path)}

    new_contract = apply_contract_additions(current, applied)
    # 안전장치: 추가-전용이므로 기존 비어있지 않은 줄은 전부 보존되어야 한다.
    for original_line in current.splitlines():
        if original_line.strip() and original_line not in new_contract:
            raise PlanningError(
                "내부 오류: 기존 계약 줄이 보존되지 않았습니다(추가-전용 위반). 계약을 변경하지 않습니다."
            )
    if not new_contract.endswith("\n"):
        new_contract += "\n"
    contract_path.write_text(new_contract, encoding="utf-8")
    report_contract_additions(proposal_summary, applied, skipped, contract_path)
    return {"applied": applied, "skipped": skipped, "path": str(contract_path)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="프로젝트 기획서를 feature 단위 harness run 명령 시퀀스로 분해한다(실행하지 않고 추천만)."
    )
    parser.add_argument("request", nargs="*", help="프로젝트 전체에 대한 자연어 요청/지시.")
    parser.add_argument(
        "--plan-file",
        action="append",
        dest="plan_files",
        metavar="PATH",
        help="기획서 로컬 파일(docx/md/txt/pdf). 여러 번 지정 가능. ppt는 pdf로 변환 후 전달.",
    )
    parser.add_argument(
        "--plan-folder",
        action="append",
        dest="plan_folders",
        metavar="DIR",
        help="기획서가 모여 있는 폴더. 재귀 스캔해 지원 형식 파일(docx/md/txt/pdf)을 모두 참고한다. "
        "여러 번 지정 가능. 폴더 안의 비지원 파일은 건너뛴다.",
    )
    parser.add_argument(
        "--reference-folder",
        action="append",
        dest="reference_folders",
        metavar="DIR",
        help="참고용 레퍼런스 코드베이스 폴더(명세 아님, 통째로 베끼지 말 것). 재귀 스캔해 '파일 맵'(경로 목록)으로 제공하고, "
        "에이전트가 필요한 파일만 직접 연다. 본문은 인라인하지 않는다(이미지/바이너리·빌드산출물 제외). 여러 번 지정 가능.",
    )
    parser.add_argument(
        "--reuse-folder",
        action="append",
        dest="reuse_folders",
        metavar="DIR",
        help="재사용할 내부 플랫폼/SDK 코드베이스 폴더. 레퍼런스와 달리 '최대한 재사용·의존하라(재구현 금지)' 톤으로 제공한다. "
        "재귀 스캔해 '파일 맵'으로 주고 에이전트가 필요한 파일만 직접 연다(이미지/바이너리·빌드산출물 제외). 여러 번 지정 가능.",
    )
    parser.add_argument("--mode", choices=["auto", "interactive"], default="auto", help="분해 모드(기본 auto).")
    parser.add_argument(
        "--strategy",
        choices=["single", "parallel", "max"],
        default="single",
        help="분해 전략. single=단일 에이전트(기본). "
        "parallel=가용 provider들이 블라인드 독립 초안을 쓰고 --model이 종합. "
        "max=parallel 위에 grounded 순차 릴레이(방향선택->레퍼런스 코드 대조·심화->사전부검) 추가. "
        "(deep_thinking parallel/max 벤치마킹)",
    )
    parser.add_argument("--model", choices=["codex", "agy", "claude"], default="codex", help="분해 에이전트. parallel에서는 최종 종합(owner) 담당(기본 codex).")
    parser.add_argument("--project", help="프로젝트 slug/이름. 생략하면 요청/파일명에서 유추.")
    parser.add_argument("--out-dir", help="출력 디렉터리 override. 기본은 .ai/projects/<project-slug>/.")
    parser.add_argument("--timeout", type=int, default=1800, help="provider 호출 타임아웃(초).")
    parser.add_argument(
        "--performance",
        choices=["lite", "medium", "high"],
        default="medium",
        help="provider 성능 프로파일.",
    )
    parser.add_argument(
        "--update-contract",
        action="store_true",
        help="분해 완료 후 별도 에이전트(분해 owner와 동일 모델)가 현재 project_contract.md에 "
        "이 프로젝트 전역 규칙을 '추가'(삭제·수정 없음)하고 자동 적용한다. 추가/건너뜀 항목은 콘솔에 보고한다.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        ensure_requirements_installed(ROOT)
        args = build_parser().parse_args(argv)
        request = di.compact_text(" ".join(args.request)) if args.request else ""
        plan_files = resolve_plan_files(args.plan_files)
        folder_files, plan_folders = resolve_plan_folders(args.plan_folders)
        plan_files = merge_plan_files(plan_files, folder_files)
        reference_folders = resolve_reference_folders(args.reference_folders)
        reuse_folders = resolve_reuse_folders(args.reuse_folders)
        if not request and not plan_files:
            raise PlanningError(
                "요청 텍스트나 --plan-file / --plan-folder 중 최소 하나는 필요합니다. "
                "(--reference-folder / --reuse-folder 는 참고 자료라 단독으로는 분해를 시작할 수 없습니다.)"
            )

        harness = di.load_harness_module()
        try:
            available = bool(harness.provider_available(args.model))
        except Exception as exc:  # noqa: BLE001 - harness 예외를 이 CLI 스타일로 변환.
            raise PlanningError(f"provider 가용성 확인 실패({args.model}): {exc}") from exc
        if not available:
            raise PlanningError(f"provider 사용 불가/비활성: {args.model}")

        project_slug = derive_project_slug(args, request, plan_files, plan_folders)
        out_dir = Path(args.out_dir).resolve() if args.out_dir else (PROJECTS_DIR / project_slug)
        logs_dir = out_dir / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        transcript: list[dict[str, Any]] = []
        if args.mode == "interactive":
            collected = run_interactive(
                harness,
                args,
                request=request,
                plan_files=plan_files,
                reference_folders=reference_folders,
                reuse_folders=reuse_folders,
                logs_dir=logs_dir,
            )
            if collected is None:
                return 130
            transcript = collected

        if args.strategy == "parallel":
            decomposition = run_parallel_decompose(
                harness,
                args,
                request=request,
                plan_files=plan_files,
                reference_folders=reference_folders,
                reuse_folders=reuse_folders,
                transcript=transcript,
                logs_dir=logs_dir,
            )
        elif args.strategy == "max":
            decomposition = run_max_decompose(
                harness,
                args,
                request=request,
                plan_files=plan_files,
                reference_folders=reference_folders,
                reuse_folders=reuse_folders,
                transcript=transcript,
                logs_dir=logs_dir,
            )
        else:
            decompose_prompt = build_decompose_prompt(
                request=request,
                plan_files=plan_files,
                reference_folders=reference_folders,
                reuse_folders=reuse_folders,
                transcript=transcript,
            )
            decomposition = plan_model_json(
                harness,
                args,
                prompt=decompose_prompt,
                logs_dir=logs_dir,
                log_prefix="decompose",
                repair_schema=DECOMPOSE_SCHEMA,
                status_message="프로젝트를 feature로 분해하는 중",
            )
        features = decomposition.get("features")
        if not isinstance(features, list) or not features:
            raise PlanningError("모델이 features 배열을 반환하지 않았습니다. logs를 확인하세요.")

        ordered = topological_order([f for f in features if isinstance(f, dict)])
        for feature in ordered:
            feature["_performance"] = normalize_performance(
                feature.get("performance"), feature.get("tier")
            )
        summary = di.compact_text(decomposition.get("summary")) or project_slug

        plan_text = render_plan_text(
            project_slug=project_slug,
            summary=summary,
            model=args.model,
            mode=args.mode,
            strategy=args.strategy,
            plan_files=plan_files,
            reference_folders=reference_folders,
            reuse_folders=reuse_folders,
            ordered=ordered,
        )
        plan_path = out_dir / "plan.txt"
        plan_path.write_text(plan_text, encoding="utf-8")

        decomposition_record = {
            "project_slug": project_slug,
            "summary": summary,
            "model": args.model,
            "mode": args.mode,
            "strategy": args.strategy,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "plan_files": [str(path) for path in plan_files],
            "reference_folders": [str(path) for path in reference_folders],
            "reuse_folders": [str(path) for path in reuse_folders],
            "features": [
                {
                    "id": feature["_id"],
                    "slug": feature["_slug"],
                    "title": feature.get("title"),
                    "description": feature.get("description"),
                    "tier": feature.get("tier"),
                    "tier_reason": feature.get("tier_reason"),
                    "performance": feature_performance(feature),
                    "performance_reason": feature.get("performance_reason"),
                    "depends_on": feature.get("_deps"),
                    "refined_prompt": feature.get("refined_prompt"),
                    "command": feature_command(feature),
                }
                for feature in ordered
            ],
        }
        decomposition_path = out_dir / "decomposition.json"
        decomposition_path.write_text(
            json.dumps(decomposition_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        print()
        print(f"분해 완료: feature {len(ordered)}개")
        print(f"계획서   : {plan_path}")
        print(f"원본 그래프: {decomposition_path}")
        print()
        print("아래 명령들을 의존성 순서대로 실행하세요(plan.txt 하단의 '연속 실행 명령어 모음'):")
        for feature in ordered:
            print(f"  {feature_command(feature)}")

        if args.update_contract:
            try:
                run_contract_update_phase(
                    harness,
                    args,
                    request=request,
                    plan_files=plan_files,
                    reference_folders=reference_folders,
                    reuse_folders=reuse_folders,
                    ordered=ordered,
                    summary=summary,
                    logs_dir=logs_dir,
                )
            except (PlanningError, di.InterviewError) as exc:
                print(
                    f"warning: project_contract 업데이트 실패(분해 결과는 정상 저장됨): {exc}",
                    file=sys.stderr,
                )
        return 0
    except HarnessRequirementsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (PlanningError, di.InterviewError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
