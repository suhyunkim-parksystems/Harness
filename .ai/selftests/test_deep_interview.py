from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from support import ensure_ai_path

ensure_ai_path()

import deep_interview as di  # noqa: E402


def _ns(**overrides: Any) -> types.SimpleNamespace:
    """Build an args namespace with sane defaults for run_interview."""
    base = dict(
        request=["build", "x"],
        model="codex",
        profile="standard",
        max_rounds=None,
        min_rounds=None,
        logs_dir=None,
        performance="medium",
        no_clarity_gate=True,
        timeout=10,
        feature=None,
        no_defaults=False,
        no_yes=False,
        no_deep_thinking=False,
        command_only=False,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


class _FakeHarness:
    def provider_available(self, provider: str) -> bool:  # noqa: ARG002
        return True


# --------------------------------------------------------------------------- #
# compact_text
# --------------------------------------------------------------------------- #
class CompactTextTests(unittest.TestCase):
    def test_collapses_internal_whitespace_and_newlines(self) -> None:
        self.assertEqual(di.compact_text("  a\n\n  b\t c  "), "a b c")

    def test_none_and_numbers(self) -> None:
        self.assertEqual(di.compact_text(None), "")
        self.assertEqual(di.compact_text(0), "")  # str(0 or "") -> str("") -> ""
        self.assertEqual(di.compact_text(123), "123")

    def test_truncation_keeps_ellipsis_within_budget(self) -> None:
        out = di.compact_text("a" * 50, max_chars=10)
        self.assertEqual(out, "aaaaaaa...")
        self.assertEqual(len(out), 10)

    def test_no_truncation_when_short(self) -> None:
        self.assertEqual(di.compact_text("short", max_chars=100), "short")


# --------------------------------------------------------------------------- #
# JSON extraction
# --------------------------------------------------------------------------- #
class JsonExtractionTests(unittest.TestCase):
    def test_balanced_none_when_no_brace(self) -> None:
        self.assertIsNone(di.balanced_json_text("no object here"))

    def test_balanced_handles_nested_and_braces_inside_strings(self) -> None:
        text = 'prefix {"a": {"b": "}{"}, "c": 1} trailing'
        block = di.balanced_json_text(text)
        self.assertEqual(json.loads(block), {"a": {"b": "}{"}, "c": 1})

    def test_balanced_respects_escaped_quote(self) -> None:
        text = r'{"a": "x\"y"}'
        block = di.balanced_json_text(text)
        self.assertEqual(json.loads(block), {"a": 'x"y'})

    def test_extract_from_fenced_json_block(self) -> None:
        text = "설명 문장\n```json\n{\"action\": \"final\"}\n```\n끝"
        self.assertEqual(di.extract_json_object(text), {"action": "final"})

    def test_extract_from_raw_prose(self) -> None:
        text = 'Here you go: {"feature_slug": "abc"} thanks'
        self.assertEqual(di.extract_json_object(text), {"feature_slug": "abc"})

    def test_extract_skips_invalid_fence_then_uses_valid_whole(self) -> None:
        # First fence is not valid JSON; whole-text scan still finds the object.
        text = "```\nnot json\n```\n{\"ok\": true}"
        self.assertEqual(di.extract_json_object(text), {"ok": True})

    def test_extract_raises_when_no_object(self) -> None:
        with self.assertRaises(di.InterviewError):
            di.extract_json_object("absolutely no json")

    def test_extract_ignores_top_level_array(self) -> None:
        # A bare array is not a dict; balanced_json_text only tracks objects.
        with self.assertRaises(di.InterviewError):
            di.extract_json_object("[1, 2, 3]")


class ProviderTextTests(unittest.TestCase):
    def test_prefers_stdout_when_present(self) -> None:
        self.assertEqual(
            di.provider_text({"stdout_text": "out", "stderr_text": "err"}), "out"
        )

    def test_falls_back_to_stderr_when_stdout_blank(self) -> None:
        self.assertEqual(
            di.provider_text({"stdout_text": "   ", "stderr_text": "err"}), "err"
        )

    def test_handles_missing_keys(self) -> None:
        self.assertEqual(di.provider_text({}), "")


# --------------------------------------------------------------------------- #
# Question dedup / sequencing logic
# --------------------------------------------------------------------------- #
class QuestionKeyTests(unittest.TestCase):
    def test_question_key_strips_punct_keeps_korean(self) -> None:
        self.assertEqual(di.question_key("Why? 왜!! "), "why왜")

    def test_similarity_identical_and_empty(self) -> None:
        self.assertEqual(di.question_similarity("같은 질문", "같은 질문"), 1.0)
        self.assertEqual(di.question_similarity("", "x"), 0.0)


class AnsweredDimensionsTests(unittest.TestCase):
    def test_excludes_system_and_empty(self) -> None:
        transcript = [
            {"dimension": "intent"},
            {"dimension": "system"},
            {"dimension": ""},
            {"dimension": "scope"},
        ]
        self.assertEqual(di.answered_dimensions(transcript), {"intent", "scope"})

    def test_next_sequence_question_returns_first_unasked(self) -> None:
        transcript = [{"dimension": "intent"}]
        item = di.next_sequence_question(transcript)
        self.assertIsNotNone(item)
        self.assertEqual(item[0], "outcome")  # 'intent' already answered

    def test_next_sequence_question_none_when_all_answered(self) -> None:
        transcript = [{"dimension": d} for d, _, _ in di.QUESTION_SEQUENCE]
        self.assertIsNone(di.next_sequence_question(transcript))


class IsRepeatedQuestionTests(unittest.TestCase):
    def test_exact_same_question_is_repeated(self) -> None:
        transcript = [{"dimension": "intent", "question": "이 작업이 왜 필요한가요?"}]
        q = {"dimension": "outcome", "question": "이 작업이 왜 필요한가요?"}
        self.assertTrue(di.is_repeated_question(q, transcript))

    def test_distinct_question_is_not_repeated(self) -> None:
        transcript = [{"dimension": "intent", "question": "이 작업이 왜 필요한가요?"}]
        q = {"dimension": "scope", "question": "첫 패스에서 제외할 것은 무엇인가요?"}
        self.assertFalse(di.is_repeated_question(q, transcript))

    def test_near_duplicate_above_threshold_is_repeated(self) -> None:
        transcript = [{"dimension": "intent", "question": "이 작업이 지금 왜 필요한가요"}]
        q = {"dimension": "intent", "question": "이 작업이 지금 왜 필요한가요?"}
        self.assertTrue(di.is_repeated_question(q, transcript))

    def test_generic_settled_tradeoff_is_repeated(self) -> None:
        transcript = [{"dimension": "tradeoff", "question": "무엇을 우선하나요?"}]
        q = {"dimension": "tradeoff", "question": "충돌하면 무엇을 가장 우선하나요?"}
        self.assertTrue(di.is_repeated_question(q, transcript))

    def test_decision_boundaries_risk_question_not_settled(self) -> None:
        # A risk-specific boundary question must still be allowed even after a
        # generic boundaries answer.
        transcript = [{"dimension": "decision_boundaries", "question": "기본값으로 둬도 되나요?"}]
        q = {
            "dimension": "decision_boundaries",
            "question": "데이터 삭제나 외부 배포도 기본값으로 진행해도 되나요?",
        }
        self.assertFalse(di.is_generic_settled_dimension_question(q, transcript))


class FallbackFollowupTests(unittest.TestCase):
    def test_fallback_moves_to_next_dimension_with_last_answer(self) -> None:
        transcript = [{"dimension": "intent", "answer": "검색 속도 개선"}]
        out = di.fallback_followup_question({"state_summary": "s"}, transcript)
        self.assertEqual(out["action"], "ask")
        self.assertEqual(out["dimension"], "outcome")
        self.assertIn("검색 속도 개선", out["question"])

    def test_fallback_finalizes_when_all_dimensions_answered(self) -> None:
        transcript = [{"dimension": d, "answer": "x"} for d, _, _ in di.QUESTION_SEQUENCE]
        out = di.fallback_followup_question({"state_summary": "s"}, transcript)
        self.assertEqual(out["action"], "final")


class MinimumRoundQuestionTests(unittest.TestCase):
    def test_returns_next_sequence_dimension(self) -> None:
        out = di.minimum_round_question([], round_no=1, min_rounds=2)
        self.assertEqual(out["action"], "ask")
        self.assertEqual(out["dimension"], "intent")

    def test_finalizes_when_all_answered(self) -> None:
        transcript = [{"dimension": d} for d, _, _ in di.QUESTION_SEQUENCE]
        out = di.minimum_round_question(transcript, round_no=9, min_rounds=2)
        self.assertEqual(out["action"], "final")


# --------------------------------------------------------------------------- #
# Sparse-request gate / final payload detection
# --------------------------------------------------------------------------- #
class SparseRequestTests(unittest.TestCase):
    def test_broad_build_request_is_sparse(self) -> None:
        self.assertTrue(di.is_sparse_broad_request("쇼핑몰 앱 만들어줘"))

    def test_detailed_request_is_not_sparse(self) -> None:
        req = "JWT 로그인 기능 추가, react 프론트, sqlite 사용, 테스트 포함, 관리자 제외"
        self.assertFalse(di.is_sparse_broad_request(req))

    def test_non_build_request_is_not_sparse(self) -> None:
        self.assertFalse(di.is_sparse_broad_request("이 버그가 왜 나는지 설명해줘"))

    def test_overlong_request_is_not_sparse(self) -> None:
        self.assertFalse(di.is_sparse_broad_request("앱 만들어줘 " + "x" * 230))

    def test_empty_request_is_not_sparse(self) -> None:
        self.assertFalse(di.is_sparse_broad_request(""))


class LooksLikeFinalTests(unittest.TestCase):
    def test_true_for_refined_prompt_or_slug(self) -> None:
        self.assertTrue(di.looks_like_final_payload({"refined_prompt": "x"}))
        self.assertTrue(di.looks_like_final_payload({"feature_slug": "x"}))
        self.assertTrue(di.looks_like_final_payload({"recommended_command": "x"}))

    def test_false_for_question_payload(self) -> None:
        self.assertFalse(di.looks_like_final_payload({"action": "ask", "question": "?"}))


# --------------------------------------------------------------------------- #
# Slug / command assembly / answer normalization
# --------------------------------------------------------------------------- #
class SanitizeSlugTests(unittest.TestCase):
    def test_basic_kebab(self) -> None:
        self.assertEqual(di.sanitize_feature_slug("My New Feature!"), "my-new-feature")

    def test_collapses_and_trims_dashes(self) -> None:
        self.assertEqual(di.sanitize_feature_slug("  --a___b--  "), "a-b")

    def test_empty_falls_back(self) -> None:
        self.assertEqual(di.sanitize_feature_slug(""), "interviewed-feature")
        self.assertEqual(di.sanitize_feature_slug("***"), "interviewed-feature")

    def test_length_capped_at_64(self) -> None:
        self.assertLessEqual(len(di.sanitize_feature_slug("a" * 200)), 64)


class PowershellQuoteTests(unittest.TestCase):
    def test_wraps_in_double_quotes(self) -> None:
        out = di.powershell_quote("hello world")
        self.assertTrue(out.startswith('"') and out.endswith('"'))

    def test_escapes_backtick_dollar_and_quote(self) -> None:
        out = di.powershell_quote('a "q" $v `t')
        # backtick-escaping: each special char is prefixed with a backtick.
        self.assertIn('`"', out)   # escaped double quote
        self.assertIn("`$", out)   # escaped dollar
        self.assertIn("``", out)   # escaped backtick


class BuildCommandTests(unittest.TestCase):
    def test_includes_all_flags(self) -> None:
        cmd = di.build_command(
            refined_prompt="do the thing",
            feature_slug="My Feat",
            include_defaults=True,
            include_yes=True,
            include_deep_thinking=True,
        )
        self.assertIn("python .ai/harness.py run", cmd)
        self.assertIn("--feature my-feat", cmd)
        self.assertIn("--defaults", cmd)
        self.assertIn("--yes", cmd)
        self.assertIn("--deep-thinking", cmd)

    def test_omits_disabled_flags(self) -> None:
        cmd = di.build_command(
            refined_prompt="x",
            feature_slug="f",
            include_defaults=False,
            include_yes=False,
            include_deep_thinking=False,
        )
        self.assertNotIn("--defaults", cmd)
        self.assertNotIn("--yes", cmd)
        self.assertNotIn("--deep-thinking", cmd)


class NormalizedAnswerTests(unittest.TestCase):
    def test_numeric_selects_option_with_description(self) -> None:
        options = [
            {"label": "A", "value": "a"},
            {"label": "B", "value": "b", "description": "두 번째"},
        ]
        self.assertEqual(di.normalized_answer("2", options), "B (b) - 두 번째")

    def test_out_of_range_returns_raw(self) -> None:
        options = [{"label": "A", "value": "a"}]
        self.assertEqual(di.normalized_answer("9", options), "9")

    def test_free_text_passes_through(self) -> None:
        self.assertEqual(di.normalized_answer("내 답변", None), "내 답변")


# --------------------------------------------------------------------------- #
# Prompt builders (structural assertions)
# --------------------------------------------------------------------------- #
class PromptBuilderTests(unittest.TestCase):
    def test_question_prompt_uses_open_schema_without_gate(self) -> None:
        prompt = di.build_question_prompt(
            request="검색 개선",
            profile="standard",
            round_no=1,
            max_rounds=6,
            min_rounds=0,
            force_question_reason=None,
            transcript=[],
        )
        self.assertIn("검색 개선", prompt)
        self.assertNotIn("질문 필요성 게이트", prompt)
        self.assertIn("action", prompt)

    def test_question_prompt_with_gate_forbids_final(self) -> None:
        prompt = di.build_question_prompt(
            request="앱 만들어줘",
            profile="standard",
            round_no=1,
            max_rounds=6,
            min_rounds=0,
            force_question_reason="첫 확인 턴이다.",
            transcript=[],
        )
        self.assertIn("질문 필요성 게이트", prompt)
        self.assertIn("action=final을 반환하지 않는다", prompt)

    def test_question_prompt_lists_previous_questions(self) -> None:
        transcript = [{"dimension": "intent", "question": "왜 필요한가요?", "answer": "속도"}]
        prompt = di.build_question_prompt(
            request="r",
            profile="quick",
            round_no=2,
            max_rounds=3,
            min_rounds=0,
            force_question_reason=None,
            transcript=transcript,
        )
        self.assertIn("왜 필요한가요?", prompt)
        self.assertIn("previous_questions", prompt)

    def test_final_prompt_contains_schema_and_request(self) -> None:
        prompt = di.build_final_prompt(
            request="원본 요청",
            profile="standard",
            transcript=[{"dimension": "intent", "answer": "x"}],
            feature_override=None,
            include_defaults=True,
            include_yes=True,
            include_deep_thinking=False,
        )
        self.assertIn("원본 요청", prompt)
        self.assertIn("feature_slug", prompt)
        self.assertIn("--deep-thinking 제외", prompt)


# --------------------------------------------------------------------------- #
# model_json: provider error handling + JSON repair (faked transport)
# --------------------------------------------------------------------------- #
class ModelJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="di-mj-"))
        # Never touch real git during these tests.
        self._git_patch = mock.patch.object(di, "git_status_porcelain", return_value="")
        self._git_patch.start()

    def tearDown(self) -> None:
        self._git_patch.stop()

    def _call(self, **kw: Any) -> dict[str, Any]:
        return di.model_json(
            object(),
            provider="codex",
            prompt="p",
            logs_dir=self.tmp,
            log_prefix="t",
            timeout_seconds=10,
            performance="medium",
            repair_schema=di.QUESTION_SCHEMA,
            status_message="...",
            **kw,
        )

    def test_returns_parsed_json_on_clean_output(self) -> None:
        fake = mock.Mock(
            return_value={"returncode": 0, "stdout_text": '{"action": "final"}', "stderr_text": ""}
        )
        with mock.patch.object(di, "run_deep_interview_provider_prompt", fake):
            out = self._call()
        self.assertEqual(out, {"action": "final"})
        self.assertEqual(fake.call_count, 1)

    def test_repair_path_runs_second_call(self) -> None:
        responses = [
            {"returncode": 0, "stdout_text": "쓸데없는 산문, JSON 아님", "stderr_text": ""},
            {"returncode": 0, "stdout_text": '{"action": "ask", "question": "복구됨"}', "stderr_text": ""},
        ]
        fake = mock.Mock(side_effect=responses)
        with mock.patch.object(di, "run_deep_interview_provider_prompt", fake):
            out = self._call()
        self.assertEqual(out["question"], "복구됨")
        self.assertEqual(fake.call_count, 2)  # original + repair

    def test_repair_failure_raises(self) -> None:
        bad = {"returncode": 0, "stdout_text": "not json", "stderr_text": ""}
        fake = mock.Mock(side_effect=[bad, bad])
        with mock.patch.object(di, "run_deep_interview_provider_prompt", fake):
            with self.assertRaises(di.InterviewError):
                self._call()

    def test_timeout_raises(self) -> None:
        fake = mock.Mock(return_value={"timed_out": True, "returncode": None})
        with mock.patch.object(di, "run_deep_interview_provider_prompt", fake):
            with self.assertRaises(di.InterviewError):
                self._call()

    def test_nonzero_returncode_raises(self) -> None:
        fake = mock.Mock(return_value={"returncode": 7, "stdout_text": "", "stderr_text": "boom"})
        with mock.patch.object(di, "run_deep_interview_provider_prompt", fake):
            with self.assertRaises(di.InterviewError):
                self._call()


# --------------------------------------------------------------------------- #
# run_interview loop (faked model_json + input + harness)
# --------------------------------------------------------------------------- #
class RunInterviewTests(unittest.TestCase):
    def _run(self, *, model_json_side: list, input_side: list, args: types.SimpleNamespace) -> int:
        with mock.patch.object(di, "load_harness_module", return_value=_FakeHarness()), \
             mock.patch.object(di, "model_json", mock.Mock(side_effect=model_json_side)) as mj, \
             mock.patch("builtins.input", mock.Mock(side_effect=input_side)):
            self._mj = mj
            return di.run_interview(args)

    def test_happy_path_one_question_then_final(self) -> None:
        rc = self._run(
            model_json_side=[
                {"action": "ask", "dimension": "intent", "question": "왜 필요한가요?", "options": []},
                {"action": "final"},
                {"feature_slug": "search-speed", "refined_prompt": "검색 속도를 개선한다"},
            ],
            input_side=["속도가 느려서"],
            args=_ns(),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self._mj.call_count, 3)

    def test_cancel_returns_130(self) -> None:
        rc = self._run(
            model_json_side=[
                {"action": "ask", "dimension": "intent", "question": "왜?", "options": []},
            ],
            input_side=["/cancel"],
            args=_ns(),
        )
        self.assertEqual(rc, 130)

    def test_done_shortcuts_to_final(self) -> None:
        rc = self._run(
            model_json_side=[
                {"action": "ask", "dimension": "intent", "question": "왜?", "options": []},
                {"feature_slug": "f", "refined_prompt": "정제된 요청"},
            ],
            input_side=["/done"],
            args=_ns(),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self._mj.call_count, 2)

    def test_min_rounds_gate_rejects_premature_final(self) -> None:
        # With a forced gate, two consecutive 'final' answers must raise rather
        # than silently finalize.
        with self.assertRaises(di.InterviewError):
            self._run(
                model_json_side=[{"action": "final"}, {"action": "final"}],
                input_side=[],
                args=_ns(min_rounds=1),
            )

    def test_missing_refined_prompt_raises(self) -> None:
        with self.assertRaises(di.InterviewError):
            self._run(
                model_json_side=[
                    {"action": "ask", "dimension": "intent", "question": "왜?", "options": []},
                    {"action": "final"},
                    {"feature_slug": "f"},  # no refined_prompt
                ],
                input_side=["답"],
                args=_ns(),
            )


if __name__ == "__main__":
    unittest.main()
