from __future__ import annotations

import sys
from typing import Any, Callable


class QuestionInputError(RuntimeError):
    pass


YES_VALUES = {"yes", "y"}
NO_VALUES = {"no", "n"}


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _question_id(raw: dict[str, Any], index: int) -> str:
    for key in ("id", "name", "key"):
        value = _as_text(raw.get(key))
        if value:
            return value
    return f"question_{index + 1}"


def _normalize_options(raw_options: Any) -> list[dict[str, str]]:
    if not isinstance(raw_options, list):
        return []
    options: list[dict[str, str]] = []
    for index, item in enumerate(raw_options):
        if isinstance(item, dict):
            label = (
                _as_text(item.get("label"))
                or _as_text(item.get("title"))
                or _as_text(item.get("value"))
                or _as_text(item.get("id"))
            )
            if not label:
                continue
            option_id = _as_text(item.get("id")) or _as_text(item.get("value")) or str(index + 1)
            description = _as_text(item.get("description") or item.get("detail") or item.get("reason"))
        else:
            label = _as_text(item)
            if not label:
                continue
            option_id = str(index + 1)
            description = ""
        options.append({"id": option_id, "label": label, "description": description})
    return options


def _normalize_type(raw_type: Any, options: list[dict[str, str]]) -> str:
    text = _as_text(raw_type).lower().replace("-", "_")
    if text in {"choice", "select", "single_choice", "multiple_choice", "option"}:
        return "choice" if options else "text"
    if text in {"yes_no", "yesno", "boolean", "bool", "confirm", "confirmation"}:
        return "yes_no"
    if text in {"text", "free_text", "freeform", "input"}:
        return "text"
    return "choice" if options else "text"


def normalize_questions(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_questions = result.get("questions")
    questions: list[dict[str, Any]] = []
    if isinstance(raw_questions, list):
        for index, item in enumerate(raw_questions):
            if isinstance(item, dict):
                question = _as_text(item.get("question") or item.get("prompt") or item.get("text"))
                if not question:
                    continue
                options = _normalize_options(item.get("options"))
                q_type = _normalize_type(item.get("type"), options)
                questions.append(
                    {
                        "id": _question_id(item, index),
                        "type": q_type,
                        "question": question,
                        "options": options if q_type == "choice" else [],
                        "default": item.get("default"),
                    }
                )
            else:
                question = _as_text(item)
                if question:
                    questions.append(
                        {
                            "id": f"question_{index + 1}",
                            "type": "text",
                            "question": question,
                            "options": [],
                            "default": "",
                        }
                    )
    if questions:
        return questions

    reason = _as_text(result.get("blocking_reason")) or "Stage requested user input."
    return [
        {
            "id": "user_input",
            "type": "text",
            "question": reason,
            "options": [],
            "default": "",
        }
    ]


def _default_choice_index(question: dict[str, Any]) -> int | None:
    default = _as_text(question.get("default"))
    if not default:
        return None
    options = question.get("options") if isinstance(question.get("options"), list) else []
    if default.isdigit():
        index = int(default) - 1
        if 0 <= index < len(options):
            return index
    for index, option in enumerate(options):
        if default in {_as_text(option.get("id")), _as_text(option.get("label"))}:
            return index
    return None


def _default_yes_no(question: dict[str, Any]) -> bool | None:
    default = question.get("default")
    if isinstance(default, bool):
        return default
    text = _as_text(default).lower()
    if text in YES_VALUES:
        return True
    if text in NO_VALUES:
        return False
    return None


def _print_choice_question(output_fn: Callable[[str], None], question: dict[str, Any]) -> None:
    output_fn(question["question"])
    options = question.get("options") if isinstance(question.get("options"), list) else []
    for index, option in enumerate(options, start=1):
        line = f"  {index}. {option['label']}"
        if option.get("description"):
            line += f" - {option['description']}"
        output_fn(line)


def _choice_answer(
    question: dict[str, Any],
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> dict[str, Any]:
    options = question.get("options") if isinstance(question.get("options"), list) else []
    default_index = _default_choice_index(question)
    while True:
        suffix = f" [{default_index + 1}]" if default_index is not None else ""
        raw = input_fn(f"선택 번호를 입력하세요{suffix}: ").strip()
        if not raw and default_index is not None:
            raw = str(default_index + 1)
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(options):
                option = options[index]
                return {
                    "id": question["id"],
                    "type": "choice",
                    "question": question["question"],
                    "answer": option["label"],
                    "raw_input": raw,
                    "selected_index": index + 1,
                    "selected_option_id": option["id"],
                    "selected_label": option["label"],
                }
        output_fn(f"1부터 {len(options)} 사이의 번호를 입력하세요.")


def _yes_no_answer(
    question: dict[str, Any],
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> dict[str, Any]:
    default = _default_yes_no(question)
    while True:
        suffix = " [Y/n]" if default is True else " [y/N]" if default is False else " [y/n]"
        raw = input_fn(f"{question['question']}{suffix}: ").strip()
        if not raw and default is not None:
            value = default
        else:
            low = raw.lower()
            if low in YES_VALUES:
                value = True
            elif low in NO_VALUES:
                value = False
            else:
                output_fn("yes/y 또는 no/n으로 답하세요.")
                continue
        return {
            "id": question["id"],
            "type": "yes_no",
            "question": question["question"],
            "answer": value,
            "raw_input": raw,
        }


def _text_answer(
    question: dict[str, Any],
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> dict[str, Any]:
    default = _as_text(question.get("default"))
    while True:
        output_fn(question["question"])
        suffix = f" [{default}]" if default else ""
        raw = input_fn(f"답변을 입력하세요{suffix}: ")
        answer = raw.strip() or default
        if answer:
            return {
                "id": question["id"],
                "type": "text",
                "question": question["question"],
                "answer": answer,
                "raw_input": raw,
            }
        output_fn("빈 답변은 사용할 수 없습니다.")


def collect_answers(
    questions: list[dict[str, Any]],
    *,
    feature: str,
    stage: str,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    require_tty: bool = True,
    stdin: Any | None = None,
) -> list[dict[str, Any]]:
    stdin = sys.stdin if stdin is None else stdin
    if require_tty and not getattr(stdin, "isatty", lambda: False)():
        raise QuestionInputError("--interactive requires a TTY stdin so the harness can ask questions.")

    output_fn("")
    output_fn(f"Interactive questions for {feature} / {stage}")
    output_fn("-" * 60)
    answers: list[dict[str, Any]] = []
    total = len(questions)
    for index, question in enumerate(questions, start=1):
        output_fn("")
        output_fn(f"[{index}/{total}] {question.get('id')}")
        q_type = question.get("type")
        if q_type == "choice":
            _print_choice_question(output_fn, question)
            answers.append(_choice_answer(question, input_fn, output_fn))
        elif q_type == "yes_no":
            answers.append(_yes_no_answer(question, input_fn, output_fn))
        else:
            answers.append(_text_answer(question, input_fn, output_fn))
    output_fn("")
    output_fn("Interactive answers recorded. The harness will retry the same stage.")
    return answers


def format_answer_value(answer: dict[str, Any]) -> str:
    value = answer.get("answer")
    if isinstance(value, bool):
        return "yes" if value else "no"
    return _as_text(value)


def summarize_answers(answers: list[dict[str, Any]]) -> str:
    parts = []
    for answer in answers:
        key = _as_text(answer.get("id"), "answer")
        parts.append(f"{key}={format_answer_value(answer)}")
    return "; ".join(parts)


def answers_markdown(record: dict[str, Any]) -> str:
    lines = [
        "## Interactive User Answers",
        "",
        "Use these answers as authoritative. Continue the same stage.",
        "Do not ask the same question again unless the answer is unusable or contradictory.",
        "",
    ]
    blocking_reason = _as_text(record.get("blocking_reason"))
    if blocking_reason:
        lines.append(f"- original_blocking_reason: {blocking_reason}")
    for answer in record.get("answers", []):
        if not isinstance(answer, dict):
            continue
        lines.append(f"- {answer.get('id')}: {format_answer_value(answer)}")
        question = _as_text(answer.get("question"))
        if question:
            lines.append(f"  - question: {question}")
        if answer.get("type") == "choice":
            lines.append(f"  - selected_option_id: {answer.get('selected_option_id')}")
            lines.append(f"  - selected_index: {answer.get('selected_index')}")
    return "\n".join(lines)
