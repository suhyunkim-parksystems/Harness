from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402
from harness_core import stage_runtime  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402


class StageRuntimeSelfTests(unittest.TestCase):
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

    def test_git_head_changed_requires_two_distinct_heads(self) -> None:
        # git_head_changed is pure but now takes a leading ctx (harness-facing API).
        self.assertFalse(stage_runtime.git_head_changed({}, "", "after"))
        self.assertFalse(stage_runtime.git_head_changed({}, "before", ""))
        self.assertFalse(stage_runtime.git_head_changed({}, "same", "same"))
        self.assertTrue(stage_runtime.git_head_changed({}, "before", "after"))


if __name__ == "__main__":
    unittest.main()
