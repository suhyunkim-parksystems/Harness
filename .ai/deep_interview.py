#!/usr/bin/env python
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import importlib.util
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AI_DIR = ROOT / ".ai"
HARNESS_PATH = AI_DIR / "harness.py"
DEFAULT_LOGS_DIR = AI_DIR / "runs" / "_deep_interview" / "logs"

if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from harness_core.requirements import HarnessRequirementsError, ensure_requirements_installed  # noqa: E402

PROFILES: dict[str, dict[str, float | int]] = {
    "quick": {"min_rounds": 0, "max_rounds": 3, "target_ambiguity": 0.30},
    "standard": {"min_rounds": 0, "max_rounds": 6, "target_ambiguity": 0.20},
    "deep": {"min_rounds": 0, "max_rounds": 10, "target_ambiguity": 0.10},
}

QUESTION_SEQUENCE: list[tuple[str, str, str]] = [
    (
        "intent",
        "이 작업이 지금 필요한 이유를 한 문장으로 잡는다면 무엇인가요?",
        "해결책보다 먼저 실제 의도를 맞추기 위해서입니다.",
    ),
    (
        "outcome",
        "완료된 뒤 사용자가 실제로 보거나 할 수 있는 변화 하나는 무엇인가요?",
        "사용자 결과를 먼저 선명하게 하기 위해서입니다.",
    ),
    (
        "scope",
        "첫 패스에 반드시 들어갈 것 하나와 일부러 뺄 것 하나를 고르면 무엇인가요?",
        "구현 범위를 너무 넓히지 않기 위해서입니다.",
    ),
    (
        "constraints",
        "반드시 지켜야 하는 기술 스택, 데이터, 비용, 보안, 실행 환경 제약이 있나요?",
        "하네스가 잘못된 기본값을 고르지 않게 하기 위해서입니다.",
    ),
    (
        "success",
        "완료 후 성공 여부를 판단할 때 가장 먼저 확인할 기준은 무엇인가요?",
        "검증 가능한 완료 기준을 만들기 위해서입니다.",
    ),
    (
        "non_goals",
        "이번 작업에서 일부러 하지 않을 것을 하나 정한다면 무엇인가요?",
        "스펙이 커지는 것을 막기 위해서입니다.",
    ),
    (
        "decision_boundaries",
        "모호한 부분은 하네스가 기본값으로 밀어도 되나요, 아니면 비용/삭제/외부 배포처럼 멈춰서 확인해야 할 예외가 있나요?",
        "자동화가 임의로 정해도 되는 것과 멈춰야 하는 것을 구분하기 위해서입니다.",
    ),
    (
        "tradeoff",
        "품질, 속도, 범위가 충돌하면 무엇을 줄이거나 늦추는 쪽이 맞나요?",
        "뒤에서 충돌이 생길 때 일관된 선택 기준을 갖기 위해서입니다.",
    ),
]

INTERVIEW_PRESET = """
너는 `.ai/harness.py run` 명령을 만들기 위한 사전 인터뷰 담당자다.

목표:
- 사용자의 러프한 자연어 요청을 하네스가 바로 실행하기 좋은 정제된 요청문으로 바꾼다.
- 최종 산출물은 스펙 문서가 아니라 `python .ai/harness.py run "..." --feature ...`에 들어갈 입력이다.
- 실제 개발, 파일 수정, stage 실행, 커밋은 하지 않는다.

질문 철학:
- 사용자가 말한 해결책 뒤의 실제 의도와 원하는 결과를 먼저 확인한다.
- intent, outcome, scope, constraints, success criteria, non-goals, decision boundaries를 선명하게 만든다.
- 한 번에 질문 하나만 한다. 여러 질문을 한 문장에 섞지 않는다.
- 사용자가 이미 말한 사실은 다시 묻지 않는다.
- 답변이 모호하면 같은 질문을 반복하지 말고, 사용자의 직전 답변을 전제로 더 구체적인 후속 질문을 한다.
- 이전 질문과 실질적으로 같은 문장 또는 같은 의도의 질문은 금지한다.
- 질문 개수를 채우기 위해 묻지 않는다. 다음 답변이 실행 방향을 바꾸지 않으면 final로 끝낸다.
- 고정 질문표를 순서대로 소화하지 않는다. 가장 약한 모호성 축을 고르되, 이미 답한 내용은 스마트 스킵한다.
- 직전 답변은 주장으로 보고 필요하면 구체 사례, 숨은 가정, 범위 경계, 트레이드오프 중 하나를 압박한다.
- 최소 한 번은 기존 답변의 숨은 가정, 트레이드오프, 범위 경계를 압박한다. 단, 이미 충분하면 억지로 늘리지 않는다.
- 사용자가 결정해야 하는 판단과, 하네스/모델이 기본값으로 결정해도 되는 영역을 분리한다.
- 사용자가 "없어", "디폴트로 해", "전부 기본값"처럼 말하면 그것을 유효한 결정으로 기록한다. 단, 삭제/비용/외부 배포/비밀정보처럼 되돌리기 어렵거나 위험한 예외가 남는지만 확인한다.
- 사용자가 "전부 중요하지만 품질이 우선"처럼 답하면 품질 우선 정책으로 기록하고 같은 tradeoff 질문을 반복하지 않는다.
- 코드베이스에서 직접 확인 가능한 사실은 사용자에게 묻는 대신 "확인할 필요가 있는 사실"로만 기록한다.
- 최종 요청문은 구체적이어야 하지만 00_specify의 역할을 빼앗지 않는다. 스펙 확정은 기존 하네스가 한다.

정제 요청문에 포함하면 좋은 내용:
- 구현 목표와 사용자 가치
- 반드시 지켜야 할 기술 스택, 실행 환경, 데이터/보안/비용 제약
- 화면/API/파일/스크립트 등 기대 산출물
- 제외할 것과 하지 말아야 할 것
- 성공 기준과 검증 관점
- 애매한 부분에 대해 defaults 모드가 선택해도 되는 기본 결정

금지:
- 파일을 수정하지 않는다.
- shell 명령을 실행하지 않는다.
- 가짜로 확인한 척하지 않는다.
- 원본 요청에 없는 큰 기능을 마음대로 추가하지 않는다.
- 최종 프롬프트에 "인터뷰", "deep-interview", "office-hours" 같은 내부 과정 표현을 넣지 않는다.
""".strip()


QUESTION_SCHEMA = """
반드시 JSON 객체 하나만 출력한다.

질문이 더 필요하면:
{
  "action": "ask",
  "dimension": "intent|outcome|scope|constraints|success|non_goals|decision_boundaries|tradeoff|pressure|closure",
  "question": "사용자에게 물을 한국어 질문 하나",
  "why": "이 질문이 필요한 짧은 이유",
  "options": [
    {"label": "선택지", "value": "short_value", "description": "선택 시 의미"}
  ],
  "state_summary": "현재까지 이해한 내용 한두 문장",
  "missing": ["아직 불명확한 핵심 항목"]
}

이미 충분히 명확하면:
{
  "action": "final",
  "state_summary": "최종 정제 가능 상태 요약",
  "missing": []
}

규칙:
- options는 정말 선택지가 자연스러운 경우에만 2~4개 제공한다.
- options가 있어도 사용자는 자유 입력을 할 수 있다.
- 이전 질문과 같은 질문을 반복하지 않는다.
- 같은 dimension을 더 물어야 하면 직전 답변을 인용해서 더 좁고 구체적인 후속 질문으로 바꾼다.
- 이미 답변에서 결정된 선호나 기본값을 다시 확인하지 않는다.
- 질문은 다음 실행 요청문을 실제로 바꿀 때만 한다. 더 묻는 것이 문장 다듬기 수준이면 final을 반환한다.
- JSON 밖에 설명 문장을 쓰지 않는다.
""".strip()


QUESTION_ONLY_SCHEMA = """
반드시 JSON 객체 하나만 출력한다.

이번 턴은 질문을 해야 하므로 action은 반드시 "ask"다.
{
  "action": "ask",
  "dimension": "intent|outcome|scope|constraints|success|non_goals|decision_boundaries|tradeoff|pressure|closure",
  "question": "사용자에게 물을 한국어 질문 하나",
  "why": "이 질문이 필요한 짧은 이유",
  "options": [
    {"label": "선택지", "value": "short_value", "description": "선택 시 의미"}
  ],
  "state_summary": "현재까지 이해한 내용 한두 문장",
  "missing": ["아직 불명확한 핵심 항목"]
}

규칙:
- action=final은 금지한다.
- options는 정말 선택지가 자연스러운 경우에만 2~4개 제공한다.
- options가 있어도 사용자는 자유 입력을 할 수 있다.
- 코드의 고정 질문표처럼 보이는 문장을 만들지 말고, 현재 요청에서 가장 레버리지가 큰 모호성 하나를 직접 고른다.
- JSON 밖에 설명 문장을 쓰지 않는다.
""".strip()


FINAL_SCHEMA = """
반드시 JSON 객체 하나만 출력한다.

{
  "feature_slug": "ascii-kebab-case-feature-name",
  "refined_prompt": "하네스 run 명령에 넣을 한국어 정제 요청문",
  "intent": "사용자가 원하는 본질",
  "non_goals": ["제외할 것"],
  "decision_boundaries": ["하네스/모델이 기본값으로 결정해도 되는 것 또는 반드시 사용자 확인이 필요한 것"],
  "assumptions": ["정제 과정에서 둔 가정"],
  "success_criteria": ["완료 판단 기준"]
}

규칙:
- feature_slug는 영어 소문자, 숫자, 하이픈만 사용한다.
- refined_prompt는 한 번의 `harness.py run` 요청으로 쓰기 좋게 구체적으로 작성한다.
- refined_prompt는 내부 인터뷰 과정을 언급하지 않는다.
- refined_prompt는 너무 장황하지 않게 5~12문장 정도로 작성한다.
- 사용자가 명시하지 않은 큰 기능을 추가하지 않는다.
- 불가피한 가정은 assumptions에 남긴다.
- JSON 밖에 설명 문장을 쓰지 않는다.
""".strip()


class InterviewError(RuntimeError):
    pass


class Spinner:
    def __init__(self, message: str) -> None:
        self.message = message
        self.enabled = sys.stdout.isatty()
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = 0.0

    def __enter__(self) -> Spinner:
        if not self.enabled:
            return self
        self._started = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self.enabled:
            return
        self._done.set()
        if self._thread is not None:
            self._thread.join(timeout=0.3)
        width = max(80, len(self.message) + 32)
        print("\r" + " " * width + "\r", end="", flush=True)

    def _run(self) -> None:
        frames = "|/-\\"
        index = 0
        while not self._done.is_set():
            elapsed = int(time.time() - self._started)
            minutes, seconds = divmod(elapsed, 60)
            frame = frames[index % len(frames)]
            print(f"\r{self.message} {minutes:02d}:{seconds:02d} {frame}", end="", flush=True)
            index += 1
            self._done.wait(0.12)


def load_harness_module() -> Any:
    if not HARNESS_PATH.exists():
        raise InterviewError(f"Missing harness.py: {HARNESS_PATH}")
    spec = importlib.util.spec_from_file_location("local_harness_for_deep_interview", HARNESS_PATH)
    if spec is None or spec.loader is None:
        raise InterviewError(f"Cannot load harness.py: {HARNESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact_text(value: Any, *, max_chars: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    if max_chars is not None and len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def read_request(args: argparse.Namespace) -> str:
    if args.request:
        return compact_text(" ".join(args.request))
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            return compact_text(piped)
    print("러프한 요청을 입력하세요. 비워두면 취소합니다.")
    request = input("> ").strip()
    if not request:
        raise InterviewError("No request provided.")
    return compact_text(request)


def git_status_porcelain(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-c", f"safe.directory={root}", "status", "--porcelain"],
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""


def balanced_json_text(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json_object(text: str) -> dict[str, Any]:
    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL):
        block = balanced_json_text(match.group(1))
        if block:
            candidates.append(block)
    whole = balanced_json_text(text)
    if whole:
        candidates.append(whole)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise InterviewError("Provider response did not contain a valid JSON object.")


def provider_text(result: dict[str, Any]) -> str:
    stdout = str(result.get("stdout_text") or "")
    stderr = str(result.get("stderr_text") or "")
    if stdout.strip():
        return stdout
    return stderr


def run_deep_interview_provider_prompt(
    harness: Any,
    provider: str,
    prompt_text: str,
    *,
    logs_dir: Path,
    log_prefix: str,
    timeout_seconds: int,
    performance: str | None,
) -> dict[str, Any]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = harness.now_stamp() if hasattr(harness, "now_stamp") else time.strftime("%Y%m%d-%H%M%S")
    safe_prefix = re.sub(r"[^a-zA-Z0-9_.-]+", "-", log_prefix).strip("-") or "provider"
    stdout_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.out.txt"
    stderr_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.err.txt"
    meta_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.json"
    cli_log_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.cli.log"

    command, prompt_in_command = harness.prepare_provider_command(
        provider,
        prompt_text,
        log_file=cli_log_path.resolve(),
        performance=performance,
    )
    executable = harness.resolve_executable(command)
    if not executable:
        raise InterviewError(f"Provider executable not found for {provider}: {command[0]}")

    started = time.time()
    try:
        run_kwargs: dict[str, Any] = {
            "cwd": ROOT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "timeout": timeout_seconds,
            "check": False,
        }
        if prompt_in_command:
            run_kwargs["stdin"] = subprocess.DEVNULL
        else:
            run_kwargs["input"] = prompt_text
        proc = subprocess.run(command, **run_kwargs)
        elapsed = round(time.time() - started, 2)
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        timed_out = False
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - started, 2)
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        if isinstance(stdout_text, bytes):
            stdout_text = stdout_text.decode("utf-8", errors="replace")
        if isinstance(stderr_text, bytes):
            stderr_text = stderr_text.decode("utf-8", errors="replace")
        stderr_text = str(stderr_text) + f"\nTimed out after {timeout_seconds} seconds.\n"
        timed_out = True
        returncode = None

    stdout_path.write_text(str(stdout_text), encoding="utf-8")
    stderr_path.write_text(str(stderr_text), encoding="utf-8")
    rel = harness.rel if hasattr(harness, "rel") else lambda path: str(path)
    redact = harness.redact_prompt_command if hasattr(harness, "redact_prompt_command") else lambda cmd, _prompt: cmd
    result = {
        "provider": provider,
        "command": redact(command, prompt_text),
        "returncode": returncode,
        "timed_out": timed_out,
        "elapsed_seconds": elapsed,
        "stdout": rel(stdout_path),
        "stderr": rel(stderr_path),
        "meta": rel(meta_path),
        "provider_log": rel(cli_log_path),
        "finished_at": harness.iso_now() if hasattr(harness, "iso_now") else time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result | {"stdout_text": str(stdout_text), "stderr_text": str(stderr_text)}


def question_key(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "").lower())


def question_similarity(left: Any, right: Any) -> float:
    left_key = question_key(left)
    right_key = question_key(right)
    if not left_key or not right_key:
        return 0.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def is_generic_settled_dimension_question(question: dict[str, Any], transcript: list[dict[str, Any]]) -> bool:
    dimension = str(question.get("dimension") or "")
    if dimension not in answered_dimensions(transcript):
        return False
    text = compact_text(question.get("question")).lower()
    if dimension == "tradeoff":
        return any(marker in text for marker in ["무엇을 우선", "가장 우선", "중 하나"])
    if dimension == "decision_boundaries":
        risk_terms = ["삭제", "비용", "배포", "공개", "비밀", "보안", "마이그레이션"]
        if any(term in text for term in risk_terms):
            return False
        return any(term in text for term in ["기본값", "디폴트"]) and any(
            term in text for term in ["확인", "사용자", "모호"]
        )
    return False


def is_repeated_question(question: dict[str, Any], transcript: list[dict[str, Any]]) -> bool:
    if is_generic_settled_dimension_question(question, transcript):
        return True
    current_text = str(question.get("question") or "")
    current = question_key(current_text)
    if not current:
        return False
    for item in transcript:
        previous_text = str(item.get("question") or "")
        previous = question_key(previous_text)
        if not previous:
            continue
        if previous == current:
            return True
        if len(current) >= 18 and len(previous) >= 18 and (current in previous or previous in current):
            return True
        if question_similarity(current_text, previous_text) >= 0.92:
            return True
    return False


def repeated_question_note(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": "dedupe",
        "dimension": "system",
        "question": str(question.get("question") or ""),
        "why": "duplicate question rejected by deep_interview.py",
        "answer": (
            "위 질문은 이미 사용자에게 물어본 질문과 동일하다. 같은 질문을 반복하지 말고, "
            "직전 답변을 전제로 더 좁고 구체적인 후속 질문을 하나 생성하라. "
            "이미 충분하면 action=final을 반환하라."
        ),
    }


def forced_question_note(reason: str) -> dict[str, Any]:
    return {
        "round": "gate",
        "dimension": "system",
        "question": "",
        "why": "deep_interview.py requested one clarifying question before final.",
        "answer": (
            f"{reason} action=final로 끝내지 말고, 정해진 템플릿이 아니라 현재 요청에서 가장 레버리지가 큰 "
            "사용자 질문 하나를 직접 고른다."
        ),
    }


def answered_dimensions(transcript: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("dimension") or "")
        for item in transcript
        if str(item.get("dimension") or "") and str(item.get("dimension") or "") != "system"
    }


def next_sequence_question(transcript: list[dict[str, Any]]) -> tuple[str, str, str] | None:
    asked = answered_dimensions(transcript)
    return next((item for item in QUESTION_SEQUENCE if item[0] not in asked), None)


def fallback_followup_question(question: dict[str, Any], transcript: list[dict[str, Any]]) -> dict[str, Any]:
    last = transcript[-1] if transcript else {}
    next_item = next_sequence_question(transcript)
    if next_item is None:
        return {
            "action": "final",
            "state_summary": str(question.get("state_summary") or ""),
            "missing": [],
        }
    dimension, template, _why = next_item
    last_answer = compact_text(last.get("answer"), max_chars=120)
    base = f"방금 답변은 `{last_answer}`였습니다. " if last_answer else ""
    return {
        "action": "ask",
        "dimension": dimension,
        "question": base + template,
        "why": "같은 질문 반복을 피하고 아직 묻지 않은 핵심 축으로 넘어가기 위해서입니다.",
        "options": [],
        "state_summary": str(question.get("state_summary") or ""),
        "missing": question.get("missing") if isinstance(question.get("missing"), list) else [],
    }


def looks_like_final_payload(value: dict[str, Any]) -> bool:
    return bool(value.get("refined_prompt") or value.get("feature_slug") or value.get("recommended_command"))


def is_sparse_broad_request(request: str) -> bool:
    text = compact_text(request).lower()
    if not text or len(text) > 220:
        return False
    broad_subject_terms = [
        "기능",
        "앱",
        "서비스",
        "시스템",
        "대시보드",
        "페이지",
        "화면",
        "도구",
        "workflow",
        "플로우",
    ]
    build_terms = ["만들", "구현", "추가", "개발", "붙여", "넣어", "만들고싶", "만들고 싶"]
    if not any(term in text for term in broad_subject_terms):
        return False
    if not any(term in text for term in build_terms):
        return False
    detail_markers = [
        "반드시",
        "제외",
        "하지 마",
        "하지말",
        "성공",
        "검증",
        "테스트",
        "스택",
        "db",
        "jwt",
        "react",
        "fastapi",
        "sqlite",
        "postgres",
        "사용자",
        "관리자",
        "파일",
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        "버그",
        "오류",
        "에러",
    ]
    detail_count = sum(1 for marker in detail_markers if marker in text)
    return detail_count < 3


def minimum_round_question(transcript: list[dict[str, Any]], round_no: int, min_rounds: int) -> dict[str, Any]:
    next_item = next_sequence_question(transcript)
    if next_item is None:
        return {
            "action": "final",
            "state_summary": "",
            "missing": [],
        }
    dimension, question, why = next_item
    remaining = max(min_rounds - len(transcript), 1)
    return {
        "action": "ask",
        "dimension": dimension,
        "question": question,
        "why": f"{why} 최소 {min_rounds}개 질문 중 {remaining}개가 더 필요합니다.",
        "options": [],
        "state_summary": "",
        "missing": [],
    }


def model_json(
    harness: Any,
    *,
    provider: str,
    prompt: str,
    logs_dir: Path,
    log_prefix: str,
    timeout_seconds: int,
    performance: str | None,
    repair_schema: str,
    status_message: str,
) -> dict[str, Any]:
    before_status = git_status_porcelain(ROOT)
    try:
        with Spinner(status_message):
            result = run_deep_interview_provider_prompt(
                harness,
                provider,
                prompt,
                logs_dir=logs_dir,
                log_prefix=log_prefix,
                timeout_seconds=timeout_seconds,
                performance=performance,
            )
    except Exception as exc:  # noqa: BLE001 - provider helpers surface several harness-specific exceptions.
        raise InterviewError(f"Provider call failed for {provider}: {exc}") from exc
    after_status = git_status_porcelain(ROOT)
    if after_status != before_status:
        print("warning: provider changed the working tree during deep interview. Inspect git status.", file=sys.stderr)

    if result.get("timed_out"):
        raise InterviewError(f"{provider} timed out after {timeout_seconds} seconds.")
    returncode = result.get("returncode")
    if returncode not in {0, None}:
        raise InterviewError(
            f"{provider} exited with code {returncode}. "
            f"stdout={result.get('stdout')} stderr={result.get('stderr')}"
        )

    raw = provider_text(result)
    try:
        return extract_json_object(raw)
    except InterviewError:
        repair_prompt = (
            "아래 출력에서 의도한 JSON 객체만 복구해서 JSON 하나만 출력해.\n"
            "새로운 내용을 만들지 말고, 누락된 필드는 합리적인 빈 값으로 채워.\n\n"
            f"{repair_schema}\n\n"
            "원본 출력:\n"
            "```text\n"
            f"{raw[-12000:]}\n"
            "```"
        )
        try:
            with Spinner("응답 형식을 정리하는 중"):
                repair = run_deep_interview_provider_prompt(
                    harness,
                    provider,
                    repair_prompt,
                    logs_dir=logs_dir,
                    log_prefix=f"{log_prefix}_repair",
                    timeout_seconds=timeout_seconds,
                    performance=performance,
                )
        except Exception as exc:  # noqa: BLE001 - keep CLI errors concise.
            raise InterviewError(f"Provider repair call failed for {provider}: {exc}") from exc
        repaired_raw = provider_text(repair)
        try:
            return extract_json_object(repaired_raw)
        except InterviewError as exc:
            raise InterviewError(
                "Could not parse provider JSON response. "
                f"See logs: stdout={result.get('stdout')} stderr={result.get('stderr')}"
            ) from exc


def build_question_prompt(
    *,
    request: str,
    profile: str,
    round_no: int,
    max_rounds: int,
    min_rounds: int,
    force_question_reason: str | None,
    transcript: list[dict[str, Any]],
) -> str:
    profile_info = PROFILES[profile]
    answered_count = len(transcript)
    dimension_set = answered_dimensions(transcript)
    previous_questions = [
        str(item.get("question") or "")
        for item in transcript
        if str(item.get("question") or "").strip()
    ]
    answered_dimension_names = [
        str(item.get("dimension") or "")
        for item in transcript
        if str(item.get("dimension") or "").strip() and str(item.get("dimension") or "") != "system"
    ]
    latest_answer = compact_text(transcript[-1].get("answer"), max_chars=240) if transcript else "없음"
    readiness = {
        "non_goals_answered": "non_goals" in dimension_set,
        "decision_boundaries_answered": "decision_boundaries" in dimension_set,
        "pressure_or_tradeoff_answered": bool({"pressure", "tradeoff"} & dimension_set),
    }
    if min_rounds > 0:
        minimum_rule = (
            f"- optional_minimum_questions_before_final: {min_rounds}\n"
            "- answered_questions가 optional_minimum_questions_before_final보다 작으면 되도록 질문하되, "
            "모든 핵심 축이 이미 답변됐으면 final을 반환한다.\n\n"
        )
    else:
        minimum_rule = (
            "- minimum_questions_before_final: none\n"
            "- 질문 개수를 채우기 위해 묻지 않는다. 충분하면 즉시 final을 반환한다.\n\n"
        )
    if force_question_reason:
        mission = (
            "사용자 요청을 정제하기 위한 다음 인터뷰 질문 하나를 만든다.\n"
            "이번 턴은 충분함을 판단하는 턴이 아니라, 넓은 요청을 좁히는 첫 확인 턴이다.\n"
        )
        gate_rule = (
            "## 질문 필요성 게이트\n"
            f"- {force_question_reason}\n"
            "- 이번 턴에는 action=final을 반환하지 않는다.\n"
            "- 질문 문장은 코드의 고정 템플릿처럼 만들지 말고, 원본 요청과 인터뷰 기록을 보고 직접 고른다.\n"
            "- 가장 레버리지가 큰 모호성 하나만 묻는다. 예: 첫 사용자 흐름, 제외 범위, 성공 기준, 위험한 기본값 중 현재 제일 중요한 것.\n\n"
        )
        output_schema = QUESTION_ONLY_SCHEMA
    else:
        mission = (
            "사용자 요청을 정제하기 위한 다음 인터뷰 행동을 결정한다.\n"
            "충분히 명확하면 final을 반환하고, 아니면 가장 중요한 질문 하나만 반환한다.\n"
        )
        gate_rule = ""
        output_schema = QUESTION_SCHEMA
    return (
        f"{INTERVIEW_PRESET}\n\n"
        "## 현재 임무\n"
        f"{mission}\n"
        f"- profile: {profile}\n"
        f"- target_ambiguity: {profile_info['target_ambiguity']}\n"
        f"- round: {round_no}/{max_rounds}\n\n"
        f"- answered_questions: {answered_count}\n"
        f"{minimum_rule}"
        f"{gate_rule}"
        "## 원본 요청\n"
        f"{request}\n\n"
        "## 지금까지의 인터뷰 기록\n"
        "```json\n"
        f"{json.dumps(transcript, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "## 반복 방지 정보\n"
        "- 아래 previous_questions와 같은 질문을 다시 출력하지 않는다.\n"
        "- 답변이 모호해서 같은 dimension을 더 물어야 하면 latest_answer를 전제로 더 구체적인 후속 질문을 만든다.\n"
        "- latest_answer가 이미 선호, 기본값 허용, 제외 범위, 우선순위를 답했다면 같은 축을 다시 묻지 않는다.\n"
        "```json\n"
        f"{json.dumps({'previous_questions': previous_questions, 'answered_dimensions': answered_dimension_names, 'latest_answer': latest_answer, 'readiness': readiness}, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "## 질문 품질 기준\n"
        "- 가장 약한 모호성 축 하나만 고른다. 정해진 질문표를 순서대로 소화하지 않는다.\n"
        "- 다음 답변이 구현 목표, 범위, 검증, 기본 결정 정책을 바꾸지 않으면 action=final을 반환한다.\n"
        "- 직전 답변이 느슨하면 같은 질문을 반복하지 말고 구체 사례, 숨은 가정, 명시적 제외, 충돌 시 선택 중 하나로 압박한다.\n"
        "- `없어, 디폴트로 할거야`는 decision_boundaries 답변으로 인정한다. 필요하면 위험 예외만 좁게 확인한다.\n"
        "- `전부 중요하지만 품질이 우선`은 tradeoff 답변으로 인정한다. 같은 우선순위 질문을 반복하지 않는다.\n\n"
        "## 출력 계약\n"
        f"{output_schema}\n"
    )


def build_final_prompt(
    *,
    request: str,
    profile: str,
    transcript: list[dict[str, Any]],
    feature_override: str | None,
    include_defaults: bool,
    include_yes: bool,
    include_deep_thinking: bool,
) -> str:
    option_notes = [
        "--defaults 포함" if include_defaults else "--defaults 제외",
        "--yes 포함" if include_yes else "--yes 제외",
        "--deep-thinking 포함" if include_deep_thinking else "--deep-thinking 제외",
    ]
    feature_note = feature_override or "모델이 적절한 feature slug를 제안"
    return (
        f"{INTERVIEW_PRESET}\n\n"
        "## 현재 임무\n"
        "인터뷰 기록을 바탕으로 하네스 run 명령에 넣을 최종 정제 요청문을 만든다.\n"
        "명령 문자열 자체는 파이썬 스크립트가 조립하므로 JSON에는 shell quoting을 신경 쓰지 말고 순수 값을 넣는다.\n\n"
        f"- profile: {profile}\n"
        f"- feature_slug 정책: {feature_note}\n"
        f"- 최종 명령 옵션: {', '.join(option_notes)}\n\n"
        "## 정제 기준\n"
        "- 사용자가 기본값 위임을 명시했으면 하네스가 합리적 기본값을 선택해도 된다고 적는다.\n"
        "- 사용자가 품질/속도/범위 우선순위를 답했으면 충돌 시 선택 정책으로 적는다.\n"
        "- 질문에서 확정되지 않은 큰 기능은 추가하지 말고 assumptions에 남긴다.\n\n"
        "## 원본 요청\n"
        f"{request}\n\n"
        "## 인터뷰 기록\n"
        "```json\n"
        f"{json.dumps(transcript, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "## 출력 계약\n"
        f"{FINAL_SCHEMA}\n"
    )


def sanitize_feature_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        slug = "interviewed-feature"
    return slug[:64].strip("-") or "interviewed-feature"


def powershell_quote(value: str) -> str:
    text = compact_text(value)
    text = text.replace("`", "``").replace('"', '`"').replace("$", "`$")
    return f'"{text}"'


def build_command(
    *,
    refined_prompt: str,
    feature_slug: str,
    include_defaults: bool,
    include_yes: bool,
    include_deep_thinking: bool,
) -> str:
    parts = [
        "python",
        ".ai/harness.py",
        "run",
        powershell_quote(refined_prompt),
        "--feature",
        sanitize_feature_slug(feature_slug),
    ]
    if include_defaults:
        parts.append("--defaults")
    if include_yes:
        parts.append("--yes")
    if include_deep_thinking:
        parts.append("--deep-thinking")
    return " ".join(parts)


def print_question(question: dict[str, Any], round_no: int, max_rounds: int) -> None:
    dimension = str(question.get("dimension") or "clarity")
    print()
    print(f"[{round_no}/{max_rounds}] {dimension}")
    why = compact_text(question.get("why"))
    if why:
        print(f"이유: {why}")
    print(str(question.get("question") or "").strip())
    options = question.get("options")
    if isinstance(options, list) and options:
        for index, option in enumerate(options, start=1):
            if isinstance(option, dict):
                label = str(option.get("label") or option.get("value") or f"Option {index}")
                description = compact_text(option.get("description"))
                suffix = f" - {description}" if description else ""
                print(f"  {index}. {label}{suffix}")
            else:
                print(f"  {index}. {option}")


def normalized_answer(raw: str, options: Any) -> str:
    answer = raw.strip()
    if isinstance(options, list) and answer.isdigit():
        index = int(answer) - 1
        if 0 <= index < len(options):
            option = options[index]
            if isinstance(option, dict):
                label = str(option.get("label") or option.get("value") or answer)
                value = str(option.get("value") or label)
                description = compact_text(option.get("description"))
                return f"{label} ({value})" + (f" - {description}" if description else "")
            return str(option)
    return answer


def run_interview(args: argparse.Namespace) -> int:
    harness = load_harness_module()
    provider = args.model
    if provider not in {"codex", "agy", "claude"}:
        raise InterviewError(f"Unknown model/provider: {provider}")
    try:
        available = bool(harness.provider_available(provider))
    except Exception as exc:  # noqa: BLE001 - convert harness-specific errors to this CLI's error style.
        raise InterviewError(f"Could not check provider availability for {provider}: {exc}") from exc
    if not available:
        raise InterviewError(f"Provider is not available or disabled: {provider}")

    request = read_request(args)
    profile = args.profile
    max_rounds = int(args.max_rounds or PROFILES[profile]["max_rounds"])
    configured_min_rounds = int(args.min_rounds if args.min_rounds is not None else 0)
    min_rounds = max(0, min(configured_min_rounds, max_rounds))
    logs_dir = Path(args.logs_dir).resolve() if args.logs_dir else DEFAULT_LOGS_DIR
    performance = args.performance
    transcript: list[dict[str, Any]] = []

    min_rounds_label = f"min_rounds={min_rounds}" if min_rounds else "no_min_rounds"
    clarity_gate_label = "clarity_gate=off" if args.no_clarity_gate else "clarity_gate=on"
    print(
        f"deep interview: model={provider} profile={profile} "
        f"{min_rounds_label} {clarity_gate_label} max_rounds={max_rounds}"
    )
    print("답변 입력 중 `/done`은 바로 정제, `/cancel`은 취소입니다.")

    for round_no in range(1, max_rounds + 1):
        question: dict[str, Any] | None = None
        force_question_reason = None
        if round_no == 1 and not args.no_clarity_gate and is_sparse_broad_request(request):
            force_question_reason = "원본 요청이 큰 기능 단위인데 세부 맥락이 짧아서, 최소 한 번은 방향을 좁혀야 한다."
        elif len(transcript) < min_rounds:
            force_question_reason = (
                f"사용자가 --min-rounds {min_rounds}를 지정했고 현재 답변 수는 {len(transcript)}개다."
            )

        prompt_transcript = transcript
        for dedupe_attempt in range(2):
            prompt = build_question_prompt(
                request=request,
                profile=profile,
                round_no=round_no,
                max_rounds=max_rounds,
                min_rounds=min_rounds,
                force_question_reason=force_question_reason,
                transcript=prompt_transcript,
            )
            question = model_json(
                harness,
                provider=provider,
                prompt=prompt,
                logs_dir=logs_dir,
                log_prefix=f"round{round_no}" if dedupe_attempt == 0 else f"round{round_no}_dedupe{dedupe_attempt}",
                timeout_seconds=args.timeout,
                performance=performance,
                repair_schema=QUESTION_ONLY_SCHEMA if force_question_reason else QUESTION_SCHEMA,
                status_message=f"질문을 고르는 중 {round_no}/{max_rounds}",
            )
            if str(question.get("action") or "").lower() == "final":
                if force_question_reason and dedupe_attempt == 0:
                    prompt_transcript = [*transcript, forced_question_note(force_question_reason)]
                    continue
                break
            if not is_repeated_question(question, transcript):
                break
            prompt_transcript = [*transcript, repeated_question_note(question)]
        if question is None:
            break
        action = str(question.get("action") or "").lower()
        question_text = str(question.get("question") or "").strip()
        if force_question_reason and action == "final":
            raise InterviewError("Provider returned final during a question-only gate. Retry or use --no-clarity-gate.")
        if len(transcript) < min_rounds and (action == "final" or not question_text or looks_like_final_payload(question)):
            question = minimum_round_question(transcript, round_no, min_rounds)
            action = str(question.get("action") or "").lower()
            question_text = str(question.get("question") or "").strip()
        if str(question.get("action") or "").lower() != "final" and is_repeated_question(question, transcript):
            question = fallback_followup_question(question, transcript)
            action = str(question.get("action") or "").lower()
            question_text = str(question.get("question") or "").strip()
        if action == "final":
            break
        if action != "ask":
            question["action"] = "ask"
        if not question_text:
            break

        print_question(question, round_no, max_rounds)
        raw_answer = input("답변> ").strip()
        lowered = raw_answer.lower()
        if lowered in {"/cancel", "cancel", "quit", "exit"}:
            print("cancelled")
            return 130
        if lowered in {"/done", "done", "final", "finish"}:
            break
        answer = normalized_answer(raw_answer, question.get("options"))
        transcript.append(
            {
                "round": round_no,
                "dimension": str(question.get("dimension") or ""),
                "question": str(question.get("question") or ""),
                "why": str(question.get("why") or ""),
                "answer": answer,
                "raw_answer": raw_answer,
                "state_summary_before_answer": str(question.get("state_summary") or ""),
            }
        )

    final_prompt = build_final_prompt(
        request=request,
        profile=profile,
        transcript=transcript,
        feature_override=args.feature,
        include_defaults=not args.no_defaults,
        include_yes=not args.no_yes,
        include_deep_thinking=not args.no_deep_thinking,
    )
    final = model_json(
        harness,
        provider=provider,
        prompt=final_prompt,
        logs_dir=logs_dir,
        log_prefix="final",
        timeout_seconds=args.timeout,
        performance=performance,
        repair_schema=FINAL_SCHEMA,
        status_message="추천 명령을 정리하는 중",
    )
    feature_slug = sanitize_feature_slug(args.feature or str(final.get("feature_slug") or ""))
    refined_prompt = compact_text(final.get("refined_prompt"))
    if not refined_prompt:
        raise InterviewError("Final model response did not include refined_prompt.")

    command = build_command(
        refined_prompt=refined_prompt,
        feature_slug=feature_slug,
        include_defaults=not args.no_defaults,
        include_yes=not args.no_yes,
        include_deep_thinking=not args.no_deep_thinking,
    )

    print()
    print("Recommended command:")
    print()
    print(command)
    if not args.command_only:
        print()
        print(f"feature: {feature_slug}")
        print(f"model: {provider}")
        print(f"profile: {profile}")
        print(f"logs: {logs_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interview a rough request and print a refined harness run command.",
    )
    parser.add_argument("request", nargs="*", help="Rough natural-language request.")
    parser.add_argument("--model", choices=["codex", "agy", "claude"], default="codex", help="Interview provider.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="standard", help="Interview depth.")
    parser.add_argument("--feature", help="Force the final feature slug.")
    parser.add_argument("--max-rounds", type=int, help="Override the profile round limit.")
    parser.add_argument("--min-rounds", type=int, help="Optional minimum questions before the model may finalize.")
    parser.add_argument(
        "--no-clarity-gate",
        action="store_true",
        help="Allow sparse broad requests to finalize without the first clarifying question.",
    )
    parser.add_argument("--timeout", type=int, default=1800, help="Provider timeout in seconds per question.")
    parser.add_argument("--performance", choices=["lite", "medium", "high"], default="medium", help="Provider performance profile.")
    parser.add_argument("--logs-dir", help="Directory for provider logs.")
    parser.add_argument("--no-deep-thinking", action="store_true", help="Omit --deep-thinking from the final command.")
    parser.add_argument("--no-heavy-thinking", dest="no_deep_thinking", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-defaults", action="store_true", help="Omit --defaults from the final command.")
    parser.add_argument("--no-yes", action="store_true", help="Omit --yes from the final command.")
    parser.add_argument("--command-only", action="store_true", help="Print no metadata after the recommended command.")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        ensure_requirements_installed(ROOT)
        parser = build_parser()
        args = parser.parse_args(argv)
        return run_interview(args)
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        return 130
    except HarnessRequirementsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except InterviewError as exc:
        print(f"deep_interview: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
