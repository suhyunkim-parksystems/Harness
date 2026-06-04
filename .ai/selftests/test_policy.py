from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import policy  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402


def _policy_context(meta: dict[str, Any], changed_paths: list[str]) -> HarnessContext:
    def rel(path: Any) -> str:
        return str(path).replace("\\", "/")

    return HarnessContext.from_namespace({
        "read_preset": lambda stage: (meta, "", Path(f"presets/{stage}.md")),
        "filtered_changed_paths": lambda state, stage: changed_paths,
        "STAGES": ["01_develop"],
        "stage_output_path": lambda feature, stage: Path(f".ai/features/{feature}/01_dev.md"),
        "stage_result_json_path": lambda feature, stage: Path(f".ai/features/{feature}/01_dev.result.json"),
        "rel": rel,
        "log_event": lambda *args, **kwargs: None,
    })


class WritePolicySelfTests(unittest.TestCase):
    def test_forbidden_production_code_change_is_violation(self) -> None:
        meta = {
            "allowed_writes": [".ai/features/[기능명]/01_dev.md"],
            "forbidden_writes": ["production_code"],
        }
        state = {"feature_name": "demo"}

        violations = policy.write_policy_violations(
            _policy_context(meta, ["src/app.py"]),
            state,
            "01_develop",
        )

        self.assertEqual(len(violations), 1)
        self.assertIn("src/app.py", violations[0])
        self.assertIn("forbidden_writes", violations[0])

    def test_new_tests_policy_allows_new_test_path(self) -> None:
        meta = {
            "allowed_writes": ["new_tests"],
            "forbidden_writes": [],
        }
        state = {"feature_name": "demo"}

        violations = policy.write_policy_violations(
            _policy_context(meta, ["tests/test_app.py"]),
            state,
            "01_develop",
        )

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
