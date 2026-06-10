from __future__ import annotations

import unittest

from integration_support import PIPELINE_MODES, announce, fixture_workspace, read_json, run_pipeline, run_standard_pipeline


def blocked_reason(state: dict[str, object]) -> str:
    blocked = state.get("blocked")
    if not isinstance(blocked, dict):
        return ""
    return str(blocked.get("reason") or "")


class HarnessIntegrationFailureSelfTests(unittest.TestCase):
    def test_malformed_result_json_blocks_run(self) -> None:
        announce("integration failure: malformed result json")
        with fixture_workspace() as fixture_root:
            proc = run_standard_pipeline(
                fixture_root,
                feature="selftest-malformed-json",
                mode="malformed-json",
                command_timeout=45,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / "selftest-malformed-json" / "run.json")

            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(state["status"], "blocked")
            self.assertIn("Invalid stage result JSON", blocked_reason(state))

    def test_write_policy_violation_blocks_run(self) -> None:
        announce("integration failure: write policy violation")
        with fixture_workspace() as fixture_root:
            proc = run_standard_pipeline(
                fixture_root,
                feature="selftest-write-policy",
                mode="write-policy-violation",
                command_timeout=45,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / "selftest-write-policy" / "run.json")

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(state["status"], "blocked")
            reason = blocked_reason(state)
            self.assertIn("Write policy violation", reason)
            self.assertIn("src/policy_violation.py", reason)

    def test_provider_git_head_change_blocks_run(self) -> None:
        announce("integration failure: provider changed Git HEAD")
        with fixture_workspace() as fixture_root:
            proc = run_standard_pipeline(
                fixture_root,
                feature="selftest-head-change",
                mode="git-head-change",
                command_timeout=45,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / "selftest-head-change" / "run.json")

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(state["status"], "blocked")
            self.assertIn("Provider changed Git HEAD", blocked_reason(state))
            events = [str(item.get("event")) for item in state.get("events", []) if isinstance(item, dict)]
            self.assertIn("blocked_provider_changed_head", events)

    def test_verify_retry_limit_blocks_run(self) -> None:
        for pipeline_mode in PIPELINE_MODES:
            with self.subTest(pipeline_mode=pipeline_mode):
                feature = f"selftest-{pipeline_mode}-retry-limit"
                announce(f"integration failure: {pipeline_mode} verify retry limit")
                with fixture_workspace() as fixture_root:
                    proc = run_pipeline(
                        fixture_root,
                        pipeline_mode=pipeline_mode,
                        feature=feature,
                        mode="verify-always-fail",
                        max_verify_fix_retries=1,
                        command_timeout=120,
                        check=False,
                    )
                    state = read_json(fixture_root / ".project" / "runs" / feature / "run.json")

                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertEqual(state["status"], "blocked")
                    self.assertEqual(state.get("pipeline_mode"), pipeline_mode)
                    self.assertEqual(state.get("verify_fix_retries_used"), 1)
                    self.assertIn("Verify/Fix retry limit reached", blocked_reason(state))

    def test_provider_nonzero_exit_blocks_run(self) -> None:
        announce("integration failure: provider non-zero exit")
        with fixture_workspace() as fixture_root:
            proc = run_standard_pipeline(
                fixture_root,
                feature="selftest-provider-nonzero",
                mode="provider-nonzero",
                command_timeout=45,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / "selftest-provider-nonzero" / "run.json")

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(state["status"], "blocked")
            self.assertIn("exited with code 7", blocked_reason(state))

    def test_provider_silent_success_blocks_run(self) -> None:
        announce("integration failure: provider silent success")
        with fixture_workspace() as fixture_root:
            proc = run_standard_pipeline(
                fixture_root,
                feature="selftest-provider-silent",
                mode="provider-silent",
                command_timeout=45,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / "selftest-provider-silent" / "run.json")

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(state["status"], "blocked")
            self.assertIn("produced no stdout", blocked_reason(state))


if __name__ == "__main__":
    unittest.main()
