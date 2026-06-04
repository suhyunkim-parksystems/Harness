from __future__ import annotations

import unittest

from integration_support import (
    STANDARD_STAGE_OUTPUTS,
    announce,
    fixture_workspace,
    read_json,
    run,
    run_standard_pipeline,
)


class HarnessIntegrationSelfTests(unittest.TestCase):
    def test_standard_pipeline_dry_run_uses_fake_provider_and_isolated_fixture(self) -> None:
        announce("integration happy path: starting standard fixture run")
        with fixture_workspace() as fixture_root:
            proc = run_standard_pipeline(fixture_root)

            state = read_json(fixture_root / ".ai" / "runs" / "selftest-demo" / "run.json")
            self.assertEqual(state["status"], "complete", proc.stdout + proc.stderr)
            self.assertEqual(state["current_stage"], "done")
            self.assertEqual(state.get("verify_fix_retries_used"), 1)
            self.assertEqual(state.get("pc_candidate_extraction", {}).get("status"), "PASS")

            commits = state.get("commits")
            self.assertIsInstance(commits, dict)
            feature_dir = fixture_root / ".ai" / "features" / "selftest-demo"
            for stage, output_name in STANDARD_STAGE_OUTPUTS.items():
                self.assertIn(stage, commits)
                self.assertTrue((feature_dir / output_name).exists())
                self.assertTrue((feature_dir / output_name.replace(".md", ".result.json")).exists())

            latest_verification = state.get("last_harness_verification")
            self.assertTrue(latest_verification)
            verification = read_json(fixture_root / str(latest_verification))
            self.assertEqual(verification["status"], "PASS")
            self.assertTrue(verification["passed"])

            events = [str(item.get("event")) for item in state.get("events", []) if isinstance(item, dict)]
            self.assertIn("verify_failed_returning_to_development", events)
            self.assertIn("pc_candidate_extraction_completed", events)

            self.assertTrue((fixture_root / ".ai" / "history" / "summary.md").exists())
            self.assertTrue((fixture_root / ".ai" / "history" / "index.json").exists())
            self.assertTrue((fixture_root / ".ai" / "history" / "pc_candidates.json").exists())

            log = run(["git", "log", "--oneline", "--no-decorate"], fixture_root).stdout
            self.assertIn("[selftest-demo]", log)
            self.assertIn("04_verify", log)


if __name__ == "__main__":
    unittest.main()
