from __future__ import annotations

import copy
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402


def standard_complete_state() -> dict:
    return {
        "feature_name": "todo-standard-demo",
        "pipeline_mode": "standard",
        "status": "complete",
        "current_stage": "done",
        "defaults_mode": True,
        "attempts": {
            "00_specify": 1,
            "01_develop": 1,
            "02_review": 1,
            "03_fix": 2,
            "04_verify": 2,
        },
        "provider_schedule": {
            "00_specify": "codex",
            "01_develop": "claude",
            "02_review": "agy",
            "03_fix": "claude",
            "04_verify": "codex",
        },
    }


class TodoModeAwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(harness.apply_pipeline, "full")

    def test_complete_artifacts_use_run_pipeline_not_active_wrapper(self) -> None:
        state = standard_complete_state()

        for active_mode in ("full", "fast", "standard"):
            with self.subTest(active_mode=active_mode):
                harness.apply_pipeline(active_mode)
                output, result_json = harness.todo_stage_artifacts_for_state(state)

                self.assertIn("04_verify.md", output)
                self.assertIn("04_verify.result.json", result_json)
                self.assertNotIn("06_document", output)
                self.assertNotIn("02_verify", output)

    def test_provider_and_attempt_use_run_pipeline_without_mutating_state(self) -> None:
        state = standard_complete_state()
        before = copy.deepcopy(state)

        harness.apply_pipeline("full")

        self.assertEqual(harness.todo_provider_for_state(state), "codex")
        self.assertEqual(harness.todo_attempt_for_state(state), "2")
        self.assertEqual(state, before)

    def test_next_action_uses_run_pipeline_script(self) -> None:
        state = {
            "feature_name": "todo-standard-demo",
            "pipeline_mode": "standard",
            "status": "waiting_for_model",
            "current_stage": "03_fix",
            "defaults_mode": True,
        }

        harness.apply_pipeline("full")

        self.assertEqual(
            harness.todo_next_action(state),
            "python .ai/harness_standard.py auto todo-standard-demo --yes --defaults",
        )

    def test_print_todo_emphasizes_next_command_before_artifacts(self) -> None:
        item = {
            "feature": "todo-standard-demo",
            "status": "waiting_for_model",
            "stage": "03_fix",
            "provider": "claude",
            "mode": "defaults",
            "performance": "medium",
            "attempt": "1",
            "reason": "",
            "prompt": ".project/runs/todo-standard-demo/prompts/03_fix_attempt1.md",
            "output": ".project/features/todo-standard-demo/03_fix.md (missing)",
            "result_json": ".project/features/todo-standard-demo/03_fix.result.json (missing)",
            "handoff": "",
            "last_event": "",
            "next": "python .ai/harness_standard.py auto todo-standard-demo --yes --defaults",
        }

        with mock.patch.object(harness, "todo_items", return_value=[item]):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                harness.print_todo()

        text = buffer.getvalue()
        self.assertIn("next command:", text)
        self.assertLess(text.index("next command:"), text.index("output:"))


if __name__ == "__main__":
    unittest.main()
