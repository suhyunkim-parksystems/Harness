from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import providers, verification  # noqa: E402
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
                "path": ".project/runs/demo/verification/latest.json",
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

    def test_config_merge_appends_project_verification_commands(self) -> None:
        merged = providers.merge_config(
            {
                "verification": {
                    "enabled": True,
                    "commands": [
                        {
                            "name": "generic",
                            "command": ["python", "-m", "py_compile", ".ai\\harness.py"],
                        },
                        {
                            "name": "duplicate-from-ai",
                            "command": ["dotnet", "test", "tests\\A.csproj"],
                            "cwd": ".",
                        },
                    ],
                }
            },
            {
                "verification": {
                    "commands": [
                        {
                            "name": "duplicate-from-project",
                            "command": ["dotnet", "test", "tests\\A.csproj"],
                            "cwd": ".",
                        },
                        {
                            "name": "project",
                            "command": ["dotnet", "test", "tests\\B.csproj"],
                            "cwd": ".",
                        },
                    ]
                }
            },
        )

        names = [item["name"] for item in merged["verification"]["commands"]]
        self.assertEqual(names, ["generic", "duplicate-from-ai", "project"])

    def test_promoted_dynamic_commands_are_written_to_project_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_config_path = root / ".project" / "harness.config.json"

            def load_project_config() -> dict[str, Any]:
                if not project_config_path.exists():
                    return {}
                return json.loads(project_config_path.read_text(encoding="utf-8"))

            def write_project_config(config: dict[str, Any]) -> None:
                project_config_path.parent.mkdir(parents=True, exist_ok=True)
                project_config_path.write_text(
                    json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            command = ["python", "-m", "pytest", "tests"]
            ctx = HarnessContext.from_namespace({
                "ROOT": root,
                "DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS": 600,
                "load_config": lambda: {"verification": {"timeout_seconds": 600, "commands": []}},
                "load_project_config": load_project_config,
                "write_project_config": write_project_config,
                "project_config_path": lambda: project_config_path,
                "configured_verification_commands": lambda feature: ([], True),
            })
            specs = [
                {
                    "name": "unit-tests",
                    "raw_command": command,
                    "cwd": root,
                    "config_cwd": ".",
                    "timeout_seconds": 600,
                    "persist": True,
                    "identity": verification._command_identity(command, root),
                }
            ]

            promoted = verification.promote_dynamic_verification_commands(ctx, "demo", specs)

            self.assertEqual(len(promoted), 1)
            saved = load_project_config()
            self.assertEqual(saved["verification"]["commands"][0]["name"], "unit-tests")
            self.assertEqual(saved["verification"]["commands"][0]["command"], command)


if __name__ == "__main__":
    unittest.main()
