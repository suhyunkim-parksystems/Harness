from __future__ import annotations

import unittest

from integration_support import (
    PIPELINE_EXTRACTS_PC_CANDIDATES,
    PIPELINE_MODES,
    PIPELINE_STAGE_OUTPUTS,
    announce,
    fixture_workspace,
    read_json,
    run_pipeline,
)


# Real-style model-independence knobs. The default fixture deliberately turns
# these OFF (min_distinct_agents=1, no_adjacent_same_provider=False) so the other
# integration tests focus on the state machine. Here we turn them ON to prove the
# scheduler honors the policy through an actual end-to-end run.
STRICT_MODEL_POLICY = {
    "min_distinct_agents": 2,
    "no_adjacent_same_provider": True,
    "on_independence_violation": "block",
}

CODE_WRITE_STAGES_BY_MODE = {
    "fast": {"01_develop"},
    "standard": {"01_develop", "03_fix"},
    "full": {"02_develop", "04_fix"},
}
PC_STAGE = "pc_candidates"


class ProviderIndependenceIntegrationTests(unittest.TestCase):
    """Group F: run each pipeline with the independence knobs ON and assert the
    persisted provider_schedule honors the policy end-to-end.

    Uses the deterministic fake provider (a local Python script) -- no real
    agents, LLM calls, or network. The fake provider keys its behavior on the
    stage name, not the provider name, so flipping the knobs does not change the
    pipeline outcome, only how providers are assigned across stages.
    """

    def test_strict_independence_schedule_is_honored_end_to_end(self) -> None:
        for pipeline_mode in PIPELINE_MODES:
            with self.subTest(pipeline_mode=pipeline_mode):
                feature = f"selftest-{pipeline_mode}-independence"
                announce(f"integration independence: {pipeline_mode} run with strict knobs ON")
                with fixture_workspace(model_policy_overrides=STRICT_MODEL_POLICY) as fixture_root:
                    proc = run_pipeline(fixture_root, pipeline_mode=pipeline_mode, feature=feature)

                    state = read_json(fixture_root / ".project" / "runs" / feature / "run.json")
                    # The strict knobs must not break a feasible 3-provider run.
                    self.assertEqual(state["status"], "complete", proc.stdout + proc.stderr)

                    schedule = state.get("provider_schedule")
                    self.assertIsInstance(schedule, dict, state)

                    ordered = list(PIPELINE_STAGE_OUTPUTS[pipeline_mode])
                    if PIPELINE_EXTRACTS_PC_CANDIDATES[pipeline_mode]:
                        ordered.append(PC_STAGE)
                    # full coverage, non-empty
                    for stage in ordered:
                        self.assertIn(stage, schedule, schedule)
                        self.assertTrue(schedule[stage], f"empty provider for {stage}")
                    # no two adjacent stages share a provider
                    for a, b in zip(ordered, ordered[1:]):
                        self.assertNotEqual(schedule[a], schedule[b], f"{a}/{b} share a provider")
                    # at least 2 distinct providers across the run
                    distinct = {schedule[s] for s in ordered}
                    self.assertGreaterEqual(len(distinct), 2, schedule)
                    # agy (code_write_denied) never lands on a code stage
                    for stage in CODE_WRITE_STAGES_BY_MODE[pipeline_mode]:
                        self.assertNotEqual(schedule[stage], "agy", f"denied provider on {stage}")

                    # The harness records the policy snapshot it actually enforced.
                    policy_snapshot = state.get("provider_policy", {})
                    self.assertTrue(policy_snapshot.get("no_adjacent_same_provider"))
                    self.assertGreaterEqual(int(policy_snapshot.get("min_distinct_agents", 0)), 2)


if __name__ == "__main__":
    unittest.main()
