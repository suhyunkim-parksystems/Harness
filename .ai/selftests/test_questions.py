"""Unit tests for harness_core/questions.py.

questions.py drives the interactive human-gate: it normalizes whatever question
shape a stage emitted into a canonical list, then collects answers from the
terminal. It is intentionally built for testing -- ``collect_answers`` takes
injectable ``input_fn``/``output_fn``/``stdin`` -- so these tests script the I/O
rather than touching a real TTY. Coverage spans question normalization (type
inference, option parsing, fallbacks), default resolution, the choice/yes-no/text
answer loops (including invalid-then-valid retries), the TTY guard, and the answer
formatting/markdown helpers.
"""
from __future__ import annotations

import unittest

from support import ensure_ai_path

ensure_ai_path()

from harness_core import questions  # noqa: E402
from harness_core.questions import QuestionInputError  # noqa: E402


class _ScriptedInput:
    """Callable that returns queued responses in order (ignores the prompt)."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str = "") -> str:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("input_fn called more times than scripted")
        return self._responses.pop(0)


class _FakeStdin:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class NormalizeQuestionsTests(unittest.TestCase):
    def test_choice_question_with_object_options(self) -> None:
        result = {
            "questions": [
                {
                    "id": "db",
                    "type": "choice",
                    "question": "Which database?",
                    "options": [
                        {"id": "pg", "label": "Postgres", "description": "relational"},
                        {"label": "SQLite"},
                    ],
                }
            ]
        }
        out = questions.normalize_questions(result)
        self.assertEqual(len(out), 1)
        q = out[0]
        self.assertEqual(q["id"], "db")
        self.assertEqual(q["type"], "choice")
        self.assertEqual(q["options"][0], {"id": "pg", "label": "Postgres", "description": "relational"})
        # missing id falls back to 1-based index
        self.assertEqual(q["options"][1]["id"], "2")

    def test_type_inferred_from_options_presence(self) -> None:
        # declared "choice" but no options -> downgraded to text
        out = questions.normalize_questions(
            {"questions": [{"question": "Anything?", "type": "choice", "options": []}]}
        )
        self.assertEqual(out[0]["type"], "text")
        self.assertEqual(out[0]["options"], [])

    def test_yes_no_aliases(self) -> None:
        out = questions.normalize_questions(
            {"questions": [{"question": "Proceed?", "type": "confirm"}]}
        )
        self.assertEqual(out[0]["type"], "yes_no")

    def test_bare_string_questions(self) -> None:
        out = questions.normalize_questions({"questions": ["What is the goal?"]})
        self.assertEqual(out[0]["type"], "text")
        self.assertEqual(out[0]["question"], "What is the goal?")
        self.assertEqual(out[0]["id"], "question_1")

    def test_prompt_and_text_keys_accepted(self) -> None:
        out = questions.normalize_questions({"questions": [{"prompt": "via prompt key"}]})
        self.assertEqual(out[0]["question"], "via prompt key")

    def test_empty_questions_fall_back_to_blocking_reason(self) -> None:
        out = questions.normalize_questions({"blocking_reason": "Need scope decision"})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "user_input")
        self.assertEqual(out[0]["question"], "Need scope decision")

    def test_empty_questions_default_reason(self) -> None:
        out = questions.normalize_questions({})
        self.assertEqual(out[0]["question"], "Stage requested user input.")

    def test_blank_question_text_skipped(self) -> None:
        out = questions.normalize_questions(
            {"questions": [{"question": "   "}, {"question": "real one"}]}
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["question"], "real one")


class NormalizeHelperTests(unittest.TestCase):
    def test_normalize_options_skips_unlabeled(self) -> None:
        opts = questions._normalize_options([{"description": "no label"}, "Plain"])
        self.assertEqual(len(opts), 1)
        self.assertEqual(opts[0]["label"], "Plain")

    def test_normalize_type_defaults(self) -> None:
        self.assertEqual(questions._normalize_type("", []), "text")
        self.assertEqual(questions._normalize_type("", [{"id": "1", "label": "x", "description": ""}]), "choice")
        self.assertEqual(questions._normalize_type("free-text", []), "text")


class ChoiceAnswerTests(unittest.TestCase):
    def _question(self, **over):
        base = {
            "id": "db",
            "type": "choice",
            "question": "Which database?",
            "options": [
                {"id": "pg", "label": "Postgres", "description": ""},
                {"id": "sqlite", "label": "SQLite", "description": ""},
            ],
            "default": None,
        }
        base.update(over)
        return base

    def test_valid_selection(self) -> None:
        out = questions._choice_answer(self._question(), _ScriptedInput(["2"]), lambda _l: None)
        self.assertEqual(out["answer"], "SQLite")
        self.assertEqual(out["selected_index"], 2)
        self.assertEqual(out["selected_option_id"], "sqlite")

    def test_invalid_then_valid_retry(self) -> None:
        errors: list[str] = []
        out = questions._choice_answer(
            self._question(), _ScriptedInput(["9", "abc", "1"]), errors.append
        )
        self.assertEqual(out["selected_option_id"], "pg")
        # two rejections were reported before the valid input
        self.assertGreaterEqual(len(errors), 2)

    def test_default_used_on_empty_input(self) -> None:
        out = questions._choice_answer(
            self._question(default="2"), _ScriptedInput([""]), lambda _l: None
        )
        self.assertEqual(out["selected_index"], 2)


class YesNoAnswerTests(unittest.TestCase):
    def _question(self, **over):
        base = {"id": "go", "type": "yes_no", "question": "Proceed?", "default": None}
        base.update(over)
        return base

    def test_yes_and_no(self) -> None:
        yes = questions._yes_no_answer(self._question(), _ScriptedInput(["y"]), lambda _l: None)
        self.assertIs(yes["answer"], True)
        no = questions._yes_no_answer(self._question(), _ScriptedInput(["no"]), lambda _l: None)
        self.assertIs(no["answer"], False)

    def test_invalid_then_valid(self) -> None:
        errors: list[str] = []
        out = questions._yes_no_answer(self._question(), _ScriptedInput(["maybe", "yes"]), errors.append)
        self.assertIs(out["answer"], True)
        self.assertEqual(len(errors), 1)

    def test_default_on_empty(self) -> None:
        out = questions._yes_no_answer(self._question(default=True), _ScriptedInput([""]), lambda _l: None)
        self.assertIs(out["answer"], True)


class TextAnswerTests(unittest.TestCase):
    def _question(self, **over):
        base = {"id": "name", "type": "text", "question": "Name?", "default": ""}
        base.update(over)
        return base

    def test_strips_and_returns(self) -> None:
        out = questions._text_answer(self._question(), _ScriptedInput(["  hello  "]), lambda _l: None)
        self.assertEqual(out["answer"], "hello")

    def test_empty_then_value(self) -> None:
        # _text_answer also echoes the question via output_fn each loop, so we
        # count only the empty-answer rejection line.
        outputs: list[str] = []
        out = questions._text_answer(self._question(), _ScriptedInput(["", "real"]), outputs.append)
        self.assertEqual(out["answer"], "real")
        self.assertEqual(sum("빈 답변" in line for line in outputs), 1)

    def test_default_used(self) -> None:
        out = questions._text_answer(self._question(default="fallback"), _ScriptedInput([""]), lambda _l: None)
        self.assertEqual(out["answer"], "fallback")


class CollectAnswersTests(unittest.TestCase):
    def test_requires_tty_when_guarded(self) -> None:
        with self.assertRaises(QuestionInputError):
            questions.collect_answers(
                [{"id": "q", "type": "text", "question": "?", "options": [], "default": ""}],
                feature="feat",
                stage="00_specify",
                input_fn=_ScriptedInput([]),
                output_fn=lambda _l: None,
                stdin=_FakeStdin(tty=False),
            )

    def test_collects_mixed_question_types(self) -> None:
        outputs: list[str] = []
        qs = [
            {
                "id": "db",
                "type": "choice",
                "question": "Which database?",
                "options": [{"id": "pg", "label": "Postgres", "description": ""}],
                "default": None,
            },
            {"id": "go", "type": "yes_no", "question": "Proceed?", "options": [], "default": None},
            {"id": "name", "type": "text", "question": "Name?", "options": [], "default": ""},
        ]
        answers = questions.collect_answers(
            qs,
            feature="feat",
            stage="00_specify",
            input_fn=_ScriptedInput(["1", "y", "Alice"]),
            output_fn=outputs.append,
            stdin=_FakeStdin(tty=True),
        )
        self.assertEqual([a["answer"] for a in answers], ["Postgres", True, "Alice"])
        # the harness prints a closing instruction line
        self.assertTrue(any("retry the same stage" in line for line in outputs))

    def test_no_tty_required_when_guard_off(self) -> None:
        answers = questions.collect_answers(
            [{"id": "name", "type": "text", "question": "Name?", "options": [], "default": ""}],
            feature="feat",
            stage="00_specify",
            input_fn=_ScriptedInput(["Bob"]),
            output_fn=lambda _l: None,
            require_tty=False,
            stdin=_FakeStdin(tty=False),
        )
        self.assertEqual(answers[0]["answer"], "Bob")


class AnswerFormattingTests(unittest.TestCase):
    def test_format_answer_value_bool(self) -> None:
        self.assertEqual(questions.format_answer_value({"answer": True}), "yes")
        self.assertEqual(questions.format_answer_value({"answer": False}), "no")
        self.assertEqual(questions.format_answer_value({"answer": "  text  "}), "text")

    def test_summarize_answers(self) -> None:
        summary = questions.summarize_answers(
            [{"id": "db", "answer": "Postgres"}, {"id": "go", "answer": True}]
        )
        self.assertEqual(summary, "db=Postgres; go=yes")

    def test_answers_markdown_includes_choice_metadata(self) -> None:
        md = questions.answers_markdown(
            {
                "blocking_reason": "need input",
                "answers": [
                    {
                        "id": "db",
                        "type": "choice",
                        "question": "Which database?",
                        "answer": "Postgres",
                        "selected_option_id": "pg",
                        "selected_index": 1,
                    },
                    "not-a-dict-skip-me",
                ],
            }
        )
        self.assertIn("## Interactive User Answers", md)
        self.assertIn("original_blocking_reason: need input", md)
        self.assertIn("selected_option_id: pg", md)
        self.assertIn("question: Which database?", md)


if __name__ == "__main__":
    unittest.main()
