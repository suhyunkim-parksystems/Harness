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


class DynamicCommandSafetyMatrixSelfTests(unittest.TestCase):
    def test_rejection_matrix_covers_each_safety_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _verification_context(root)
            cases: list[tuple[str, dict[str, Any], str]] = [
                (
                    "powershell_wrapper",
                    {"name": "ps", "command": ["powershell", "-Command", "echo hi"], "cwd": "."},
                    "shell wrapper commands are not allowed",
                ),
                (
                    "cmd_wrapper",
                    {"name": "cmd", "command": ["cmd", "/c", "dir"], "cwd": "."},
                    "shell wrapper commands are not allowed",
                ),
                (
                    "bash_wrapper",
                    {"name": "bash", "command": ["bash", "-lc", "ls"], "cwd": "."},
                    "shell wrapper commands are not allowed",
                ),
                (
                    "curl_executable",
                    {"name": "curl", "command": ["curl", "https://example.invalid"], "cwd": "."},
                    "destructive or network command is not allowed",
                ),
                (
                    "del_executable",
                    {"name": "del", "command": ["del", "build"], "cwd": "."},
                    "destructive or network command is not allowed",
                ),
                (
                    "bare_npm",
                    {"name": "npm", "command": ["npm", "test"], "cwd": "."},
                    "use npm.cmd",
                ),
                (
                    "and_and_control_token",
                    {"name": "andand", "command": ["python", "-m", "pytest", "&&", "echo"], "cwd": "."},
                    "shell control operators are not allowed",
                ),
                (
                    "pipe_control_token",
                    {"name": "pipe", "command": ["python", "-m", "pytest", "|", "tee"], "cwd": "."},
                    "shell control operators are not allowed",
                ),
                (
                    "dangerous_git_subcommand",
                    {"name": "git-co", "command": ["git", "checkout", "main"], "cwd": "."},
                    "git checkout is not allowed",
                ),
                (
                    "dangerous_token_in_args",
                    {"name": "rm-arg", "command": ["python", "-m", "pytest", "rm"], "cwd": "."},
                    "destructive or network command token is not allowed",
                ),
                (
                    "python_script_not_allowlisted",
                    {"name": "pyscript", "command": ["python", "script.py"], "cwd": "."},
                    "not in the dynamic verification allowlist",
                ),
                (
                    "direct_pytest_not_allowlisted",
                    {"name": "pytest", "command": ["pytest", "tests"], "cwd": "."},
                    "not in the dynamic verification allowlist",
                ),
                (
                    "cwd_outside_repo",
                    {"name": "outside", "command": ["python", "-m", "pytest"], "cwd": ".."},
                    "cwd is outside the repository",
                ),
                (
                    "cwd_missing_directory",
                    {"name": "no-dir", "command": ["python", "-m", "pytest"], "cwd": "no_such_dir"},
                    "cwd does not exist or is not a directory",
                ),
                (
                    "path_arg_escapes_repo",
                    {"name": "escape", "command": ["python", "-m", "pytest", "..\\..\\x"], "cwd": "."},
                    "path argument points outside the repository",
                ),
                (
                    "empty_command_array",
                    {"name": "empty", "command": [], "cwd": "."},
                    "command array is empty",
                ),
                (
                    "missing_command",
                    {"name": "missing", "cwd": "."},
                    "command must be an array",
                ),
            ]

            for case_name, entry, expected_reason in cases:
                with self.subTest(case=case_name):
                    plan = verification.dynamic_verification_commands(
                        ctx,
                        "demo",
                        {"test_commands": [entry]},
                        [],
                    )
                    self.assertEqual(plan["commands"], [])
                    self.assertEqual(plan["skipped"], [])
                    self.assertEqual(len(plan["rejected"]), 1)
                    self.assertIn(expected_reason, str(plan["rejected"][0]["reason"]))

    def test_allowlisted_command_forms_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _verification_context(root)
            result = {
                "test_commands": [
                    {"name": "python-pytest", "command": ["python", "-m", "pytest", "tests"], "cwd": "."},
                    {"name": "npm-test", "command": ["npm.cmd", "test"], "cwd": "."},
                    {"name": "npm-build", "command": ["npm.cmd", "run", "build"], "cwd": "."},
                    {"name": "dotnet-test", "command": ["dotnet", "test"], "cwd": "."},
                    {"name": "dotnet-build", "command": ["dotnet", "build"], "cwd": "."},
                ]
            }

            plan = verification.dynamic_verification_commands(ctx, "demo", result, [])

            self.assertEqual(plan["rejected"], [])
            self.assertEqual(plan["skipped"], [])
            self.assertEqual(
                [item["name"] for item in plan["commands"]],
                ["python-pytest", "npm-test", "npm-build", "dotnet-test", "dotnet-build"],
            )


if __name__ == "__main__":
    unittest.main()
