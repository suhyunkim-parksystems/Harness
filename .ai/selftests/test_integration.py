from __future__ import annotations

import unittest

from integration_support import (
    PIPELINE_EXTRACTS_PC_CANDIDATES,
    PIPELINE_MODES,
    PIPELINE_STAGE_OUTPUTS,
    announce,
    fixture_workspace,
    read_json,
    run,
    run_pipeline,
)


class HarnessIntegrationSelfTests(unittest.TestCase):
    def test_pipelines_dry_run_use_fake_provider_and_isolated_fixture(self) -> None:
        for pipeline_mode in PIPELINE_MODES:
            with self.subTest(pipeline_mode=pipeline_mode):
                feature = f"selftest-{pipeline_mode}"
                announce(f"integration happy path: starting {pipeline_mode} fixture run")
                with fixture_workspace() as fixture_root:
                    proc = run_pipeline(fixture_root, pipeline_mode=pipeline_mode, feature=feature)

                    state = read_json(fixture_root / ".project" / "runs" / feature / "run.json")
                    self.assertEqual(state["status"], "complete", proc.stdout + proc.stderr)
                    self.assertEqual(state["current_stage"], "done")
                    self.assertEqual(state.get("pipeline_mode"), pipeline_mode)
                    self.assertEqual(state.get("verify_fix_retries_used"), 1)

                    commits = state.get("commits")
                    self.assertIsInstance(commits, dict)
                    feature_dir = fixture_root / ".project" / "features" / feature
                    stage_outputs = PIPELINE_STAGE_OUTPUTS[pipeline_mode]
                    for stage, output_name in stage_outputs.items():
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
                    if PIPELINE_EXTRACTS_PC_CANDIDATES[pipeline_mode]:
                        self.assertEqual(state.get("pc_candidate_extraction", {}).get("status"), "PASS")
                        self.assertIn("pc_candidate_extraction_completed", events)
                        self.assertTrue((fixture_root / ".project" / "history" / "pc_candidates.json").exists())
                    else:
                        self.assertNotIn("pc_candidate_extraction_completed", events)

                    self.assertTrue((fixture_root / ".project" / "history" / "summary.md").exists())
                    self.assertTrue((fixture_root / ".project" / "history" / "index.json").exists())

                    log = run(["git", "log", "--oneline", "--no-decorate"], fixture_root).stdout
                    self.assertIn(f"[{feature}]", log)
                    self.assertIn(list(stage_outputs)[-1], log)


if __name__ == "__main__":
    unittest.main()
