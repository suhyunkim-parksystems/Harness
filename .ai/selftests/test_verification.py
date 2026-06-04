from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import verification  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402


def _verification_context(root: Path) -> HarnessContext:
    def expand(value: Any, feature: str) -> str:
        return str(value).replace("{root}", str(root)).replace("{feature}", feature)

    def display_cwd(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(root.resolve())) or "."
        except ValueError:
            return str(path)

    return HarnessContext.from_namespace({
        "ROOT": root,
        "DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS": 600,
        "load_config": lambda: {"verification": {"timeout_seconds": 600}},
        "expand_runtime_placeholders": expand,
        "display_cwd": display_cwd,
    })


class VerificationSelfTests(unittest.TestCase):
    def test_dynamic_commands_accept_safe_and_reject_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = {
                "test_commands": [
                    {
                        "name": "unit_tests",
                        "command": ["python", "-m", "pytest", "tests"],
                        "cwd": ".",
                        "persist": True,
                    },
                    {
                        "name": "shell_wrapper",
                        "command": ["powershell", "-Command", "echo hi"],
                        "cwd": ".",
                    },
                    {
                        "name": "git_reset",
                        "command": ["git", "reset", "--hard"],
                        "cwd": ".",
                    },
                ]
            }

            plan = verification.dynamic_verification_commands(
                _verification_context(root),
                "demo",
                result,
                [],
            )

            self.assertEqual([item["name"] for item in plan["commands"]], ["unit-tests"])
            reasons = " ".join(str(item["reason"]) for item in plan["rejected"])
            self.assertIn("shell wrapper", reasons)
            self.assertIn("git reset", reasons)

    def test_dynamic_commands_skip_configured_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configured = [
                {
                    "name": "existing_tests",
                    "command": ["python", "-m", "pytest", "tests"],
                    "cwd": root,
                }
            ]
            result = {
                "test_commands": [
                    {
                        "name": "same_tests",
                        "command": ["python", "-m", "pytest", "tests"],
                        "cwd": ".",
                    }
                ]
            }

            plan = verification.dynamic_verification_commands(
                _verification_context(root),
                "demo",
                result,
                configured,
            )

            self.assertEqual(plan["commands"], [])
            self.assertEqual(len(plan["skipped"]), 1)
            self.assertEqual(plan["skipped"][0]["reason"], "already configured")

    def test_enforce_verify_result_overrides_model_pass_on_harness_failure(self) -> None:
        result = {"status": "PASS", "next_stage": "done"}
        ctx = HarnessContext.from_namespace({
            "VERIFY_STAGE": "05_verify",
            "VERIFY_RETRY_TARGET_STAGE": "04_fix",
            "run_harness_verification": lambda state, stage_result: {
                "passed": False,
                "status": "FAIL",
                "path": ".ai/runs/demo/verification/latest.json",
            },
        })

        status, next_stage = verification.enforce_harness_verify_result(
            ctx,
            {"current_stage": "05_verify"},
            result,
            "PASS",
            "done",
        )

        self.assertEqual(status, "FAIL")
        self.assertEqual(next_stage, "04_fix")
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["harness_commit_required"])
        self.assertIn("Harness verification failed", result["blocking_reason"])


if __name__ == "__main__":
    unittest.main()
