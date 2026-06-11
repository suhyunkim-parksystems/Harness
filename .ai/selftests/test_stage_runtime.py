from __future__ import annotations

import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402
from harness_core import stage_runtime  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402


class StageRuntimeSelfTests(unittest.TestCase):
    class _TtyStringIO(io.StringIO):
        def isatty(self) -> bool:
            return True

    class _HeartbeatContext:
        def file_size(self, path: Path) -> int:
            return path.stat().st_size

        def color_text(self, text: str, *_styles: str) -> str:
            return text

        def format_duration(self, _seconds: float) -> str:
            return "00:01"

        def format_bytes(self, size: int) -> str:
            return f"{size} B"

    def test_parse_result_json_from_fenced_text(self) -> None:
        text = """
        ignored preface
        ```json
        {"status": "PASS", "next_stage": "done", "human_gate_required": false, "blocking_reason": ""}
        ```
        ignored tail
        """

        result = harness.parse_result_json_from_text(text)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["next_stage"], "done")
        self.assertFalse(result["human_gate_required"])

    def test_parse_result_json_from_fenced_text_accepts_bom(self) -> None:
        text = """
        ignored preface
        ```json
        \ufeff{"status": "PASS", "next_stage": "done", "human_gate_required": false, "blocking_reason": ""}
        ```
        """

        result = harness.parse_result_json_from_text(text)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["next_stage"], "done")

    def test_find_stage_result_parses_markdown_section(self) -> None:
        text = """
        # 01_dev

        ## 단계 결과
        - status: PASS
        - next_stage: 02_review
        - human_gate_required: false
        - blocking_reason: 없음
        - changed_files:
          - src/app.py

        ## 다음 섹션
        - ignored: true
        """

        result = harness.find_stage_result(text)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["next_stage"], "02_review")
        self.assertFalse(result["human_gate_required"])
        self.assertEqual(result["blocking_reason"], "")
        self.assertEqual(result["changed_files"], ["src/app.py"])

    def test_read_stage_result_json_rejects_non_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stage.result.json"
            path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

            with self.assertRaises(harness.HarnessError):
                stage_runtime.read_stage_result_json(
                    HarnessContext.from_namespace(
                        {
                            "rel": lambda value: str(value),
                        }
                    ),
                    path,
                )

    def test_read_stage_result_json_accepts_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stage.result.json"
            path.write_bytes(
                b"\xef\xbb\xbf"
                + json.dumps(
                    {
                        "status": "PASS",
                        "next_stage": "done",
                        "human_gate_required": False,
                        "blocking_reason": "",
                    }
                ).encode("utf-8")
            )

            result = stage_runtime.read_stage_result_json(
                HarnessContext.from_namespace(
                    {
                        "rel": lambda value: str(value),
                    }
                ),
                path,
            )

            self.assertEqual(result["status"], "PASS")

    def test_git_head_changed_requires_two_distinct_heads(self) -> None:
        # git_head_changed is pure but now takes a leading ctx (harness-facing API).
        self.assertFalse(stage_runtime.git_head_changed({}, "", "after"))
        self.assertFalse(stage_runtime.git_head_changed({}, "before", ""))
        self.assertFalse(stage_runtime.git_head_changed({}, "same", "same"))
        self.assertTrue(stage_runtime.git_head_changed({}, "before", "after"))

    def test_provider_heartbeat_rewrites_only_after_first_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout_path = Path(tmp) / "provider.out.txt"
            stderr_path = Path(tmp) / "provider.err.txt"
            stdout_path.write_text("abc", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            output = self._TtyStringIO()

            with contextlib.redirect_stdout(output):
                stdout_size, stderr_size = stage_runtime.print_provider_heartbeat(
                    self._HeartbeatContext(),
                    stage="01_develop",
                    provider="claude",
                    started=time.time() - 1,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    last_stdout_size=0,
                    last_stderr_size=0,
                )
                stdout_path.write_text("abcdef", encoding="utf-8")
                stage_runtime.print_provider_heartbeat(
                    self._HeartbeatContext(),
                    stage="01_develop",
                    provider="claude",
                    started=time.time() - 2,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    last_stdout_size=stdout_size,
                    last_stderr_size=stderr_size,
                    replace_previous=True,
                )
                stage_runtime.finish_provider_heartbeat(True)

            rendered = output.getvalue()
            self.assertFalse(rendered.startswith("\r\x1b[2K"))
            self.assertIn("\r\x1b[2K", rendered)
            self.assertTrue(rendered.endswith("\n"))


class StageResultParsingSelfTests(unittest.TestCase):
    """Result-parsing helpers called directly on stage_runtime with a minimal
    context: parse_result_json_from_text / find_stage_result /
    parse_result_scalar read no ctx member, so an empty HarnessContext works;
    read_stage_result_json only uses ctx.rel for error messages."""

    def setUp(self) -> None:
        self.ctx = HarnessContext.from_namespace({})

    def test_parse_result_json_clean_object(self) -> None:
        result = stage_runtime.parse_result_json_from_text(
            self.ctx, '{"status": "PASS", "next_stage": "done"}'
        )

        self.assertEqual(result, {"status": "PASS", "next_stage": "done"})

    def test_parse_result_json_object_embedded_in_prose(self) -> None:
        text = 'provider chatter before\nresult: {"status": "FAIL", "next_stage": "04_fix"} trailing words'

        result = stage_runtime.parse_result_json_from_text(self.ctx, text)

        self.assertEqual(result, {"status": "FAIL", "next_stage": "04_fix"})

    def test_parse_result_json_two_concatenated_objects_returns_empty(self) -> None:
        # NOTE: pins current behavior — without a fence the parser slices from
        # the first "{" to the last "}", so '{"a": 1} {"b": 2}' becomes a single
        # invalid JSON document ("Extra data") and the helper returns {} rather
        # than either object.
        result = stage_runtime.parse_result_json_from_text(self.ctx, '{"a": 1} {"b": 2}')

        self.assertEqual(result, {})

    def test_parse_result_json_prefers_fenced_block_over_bare_braces(self) -> None:
        text = (
            'noise with braces {"status": "IGNORED"}\n'
            "```json\n"
            '{"status": "PASS", "next_stage": "done"}\n'
            "```\n"
        )

        result = stage_runtime.parse_result_json_from_text(self.ctx, text)

        self.assertEqual(result, {"status": "PASS", "next_stage": "done"})

    def test_parse_result_json_truncated_returns_empty(self) -> None:
        # NOTE: pins fallback — truncated JSON without a closing brace has no
        # extractable {...} span, so the helper returns {}.
        result = stage_runtime.parse_result_json_from_text(
            self.ctx, '{"status": "PASS", "next_stage": '
        )

        self.assertEqual(result, {})

    def test_parse_result_json_invalid_fence_returns_empty(self) -> None:
        # NOTE: pins fallback — invalid JSON inside a ```json fence is
        # swallowed (json.JSONDecodeError) and the helper returns {}.
        result = stage_runtime.parse_result_json_from_text(
            self.ctx, "```json\n{this is not json}\n```"
        )

        self.assertEqual(result, {})

    def test_parse_result_json_non_object_fence_returns_empty(self) -> None:
        # NOTE: pins current behavior — a fenced JSON array parses fine but is
        # not a dict, so the helper returns {}.
        result = stage_runtime.parse_result_json_from_text(self.ctx, "```json\n[1, 2, 3]\n```")

        self.assertEqual(result, {})

    def test_read_stage_result_json_reads_utf8_bom_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stage.result.json"
            payload = {"status": "PASS", "next_stage": "done", "human_gate_required": False}
            path.write_text(json.dumps(payload), encoding="utf-8-sig")

            result = stage_runtime.read_stage_result_json(
                HarnessContext.from_namespace({"rel": lambda value: str(value)}),
                path,
            )

            self.assertEqual(result, payload)

    def test_parse_result_scalar_coercions(self) -> None:
        cases = [
            ("true", True),
            ("True", True),
            ("false", False),
            ("FALSE", False),
            ("없음", ""),
            ("  PASS  ", "PASS"),
            # NOTE: pins current behavior — numbers are NOT coerced;
            # parse_result_scalar only maps true/false/없음 and returns every
            # other value as the raw (stripped) string.
            ("42", "42"),
            ("3.14", "3.14"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(stage_runtime.parse_result_scalar(self.ctx, raw), expected)

    def test_find_stage_result_parses_stage_block_fields(self) -> None:
        text = (
            "# output\n"
            "\n"
            "## 단계 결과\n"
            "- status: FAIL\n"
            "- next_stage: 04_fix\n"
            "- human_gate_required: true\n"
            "- harness_commit_required: false\n"
            "- blocking_reason: tests failing\n"
            "\n"
            "## 다음 섹션\n"
            "- status: PASS\n"
        )

        result = stage_runtime.find_stage_result(self.ctx, text)

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["next_stage"], "04_fix")
        self.assertIs(result["human_gate_required"], True)
        self.assertIs(result["harness_commit_required"], False)
        self.assertEqual(result["blocking_reason"], "tests failing")

    def test_find_stage_result_without_section_returns_empty(self) -> None:
        result = stage_runtime.find_stage_result(self.ctx, "# no result section\n- status: PASS\n")

        self.assertEqual(result, {})

    def test_find_stage_result_uses_last_stage_result_section(self) -> None:
        # NOTE: pins current behavior — when the output contains multiple
        # '## 단계 결과' headings, the scan keeps overwriting the start index,
        # so the LAST section wins.
        text = (
            "## 단계 결과\n"
            "- status: FAIL\n"
            "- next_stage: 04_fix\n"
            "\n"
            "## 중간 섹션\n"
            "- noise: x\n"
            "\n"
            "## 단계 결과\n"
            "- status: PASS\n"
            "- next_stage: done\n"
        )

        result = stage_runtime.find_stage_result(self.ctx, text)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["next_stage"], "done")

    def test_find_stage_result_prefers_json_in_section_over_bullets(self) -> None:
        text = (
            "## 단계 결과\n"
            "```json\n"
            '{"status": "PASS", "next_stage": "done", "human_gate_required": false}\n'
            "```\n"
            "- status: FAIL\n"
        )

        result = stage_runtime.find_stage_result(self.ctx, text)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["next_stage"], "done")
        self.assertIs(result["human_gate_required"], False)


if __name__ == "__main__":
    unittest.main()
