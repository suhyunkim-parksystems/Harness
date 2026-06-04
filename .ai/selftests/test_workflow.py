from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import workflow  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _workflow_context(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    stages: list[str] | None = None,
    default_next_by_stage: dict[str, str] | None = None,
    document_stage: str | None = None,
    verify_stage: str = "05_verify",
    verify_retry_target_stage: str = "04_fix",
    no_commit_stages: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    calls: dict[str, list[Any]] = {"events": [], "saves": [], "handoffs": [], "prompts": []}
    default_next_by_stage = default_next_by_stage or {}

    def log_event(run_state: dict[str, Any], event: str, message: str, **fields: Any) -> None:
        calls["events"].append({"event": event, "message": message, **fields})
        run_state.setdefault("events", []).append({"event": event, **fields})

    def save_state(run_state: dict[str, Any]) -> None:
        calls["saves"].append(dict(run_state))

    def write_handoff(ctx: dict[str, Any], run_state: dict[str, Any], reason: str, **kwargs: Any) -> Path:
        calls["handoffs"].append({"reason": reason, **kwargs})
        return Path(".ai/runs/demo/handoff.md")

    def generate_prompt(run_state: dict[str, Any], stage: str, **kwargs: Any) -> Path:
        calls["prompts"].append({"stage": stage, **kwargs})
        run_state["current_prompt"] = f".ai/runs/demo/prompts/{stage}_attempt1.md"
        # The real generate_prompt persists state before returning
        # (stage_runtime.py:275); mirror that so saved-state snapshots are
        # faithful for atomicity assertions.
        save_state(run_state)
        return Path(run_state["current_prompt"])

    def load_stage_result(
        ctx: dict[str, Any], feature: str, stage: str, run_state: dict[str, Any]
    ) -> tuple[Path, str, dict[str, Any]]:
        return (
            Path(f".ai/features/{feature}/{stage}.md"),
            "",
            result,
        )

    def stage_default_next(stage: str) -> str:
        if stage in default_next_by_stage:
            return default_next_by_stage[stage]
        return result.get("next_stage") or "done"

    ctx = {
        "load_state": lambda feature: state,
        "_selftest_load_stage_result": load_stage_result,
        "_selftest_write_handoff": write_handoff,
        "stage_status": lambda stage_result: str(stage_result.get("status", "")).strip().upper(),
        "stage_default_next": stage_default_next,
        "write_policy_violations": lambda run_state, stage: [],
        "boolish": _boolish,
        "enforce_harness_verify_result": lambda run_state, stage_result, status, next_stage: (status, next_stage),
        "should_extract_pc_candidates": lambda run_state: False,
        "validate_document_stage_artifacts": lambda feature: None,
        "record_project_history": lambda run_state: {
            "status": "recorded",
            "event_id": "selftest",
            "index": ".ai/history/index.json",
        },
        "log_event": log_event,
        "save_state": save_state,
        "write_handoff": write_handoff,
        "generate_prompt": generate_prompt,
        "rel": lambda path: str(path).replace("\\", "/"),
        "STAGES": stages or ["01_develop", "02_review", "04_fix", "05_verify"],
        "START_STAGE": "00_specify",
        "VERIFY_STAGE": verify_stage,
        "VERIFY_RETRY_TARGET_STAGE": verify_retry_target_stage,
        "PC_REVIEW_STAGE": "pc_candidates",
        "DOCUMENT_STAGE": document_stage,
        "NO_COMMIT_STAGES": set(no_commit_stages or set()),
    }
    return ctx, calls


def _resume_with_fake_stage_result(ctx: dict[str, Any], feature: str, **kwargs: Any) -> dict[str, Any]:
    # load_stage_result/write_handoff are workflow's own functions, now called
    # directly as module functions, so override them as module attributes.
    original_load_stage_result = workflow.load_stage_result
    original_write_handoff = workflow.write_handoff
    workflow.load_stage_result = ctx["_selftest_load_stage_result"]
    workflow.write_handoff = ctx["_selftest_write_handoff"]
    try:
        return workflow.resume_run(HarnessContext.from_namespace(ctx), feature, **kwargs)
    finally:
        workflow.load_stage_result = original_load_stage_result
        workflow.write_handoff = original_write_handoff


class WorkflowSelfTests(unittest.TestCase):
    def test_verify_failure_returns_to_retry_target_under_limit(self) -> None:
        state = {
            "feature_name": "demo",
            "current_stage": "05_verify",
            "status": "model_completed",
            "verify_fix_retries_used": 0,
        }
        result = {
            "status": "FAIL",
            "next_stage": "done",
            "human_gate_required": False,
            "blocking_reason": "unit tests failed",
        }
        ctx, calls = _workflow_context(state, result)

        updated = _resume_with_fake_stage_result(ctx, "demo", max_verify_fix_retries=3)

        self.assertIs(updated, state)
        self.assertEqual(state["verify_fix_retries_used"], 1)
        self.assertEqual(state["current_stage"], "04_fix")
        self.assertEqual(state["status"], "waiting_for_model")
        self.assertEqual(calls["prompts"][0]["stage"], "04_fix")
        self.assertIn("unit tests failed", calls["handoffs"][0]["reason"])

    def test_verify_retry_counter_increment_is_atomic_with_stage_transition(self) -> None:
        # 4b-2: incrementing verify_fix_retries_used and transitioning to the
        # fix stage must land on disk together. If the counter is persisted
        # while current_stage is still the verify stage, a crash in that gap
        # makes resume re-count the same failure (retry budget double-spent).
        state = {
            "feature_name": "demo",
            "current_stage": "05_verify",
            "status": "model_completed",
            "verify_fix_retries_used": 0,
        }
        result = {
            "status": "FAIL",
            "next_stage": "done",
            "human_gate_required": False,
            "blocking_reason": "unit tests failed",
        }
        ctx, calls = _workflow_context(state, result)

        _resume_with_fake_stage_result(ctx, "demo", max_verify_fix_retries=3)

        # Final in-memory state is correct (also covered elsewhere, kept as a guard).
        self.assertEqual(state["verify_fix_retries_used"], 1)
        self.assertEqual(state["current_stage"], "04_fix")

        # No persisted snapshot may show the incremented counter while the
        # stage is still the verify stage (the crash double-count window).
        premature = [
            snapshot
            for snapshot in calls["saves"]
            if snapshot.get("verify_fix_retries_used", 0) >= 1
            and snapshot.get("current_stage") == "05_verify"
        ]
        self.assertEqual(
            premature,
            [],
            "retry counter was persisted before the stage transition "
            "(crash here would double-count the same verify failure)",
        )

        # The increment must still be durably persisted, carried by the
        # transition save (otherwise a crash could lose the retry entirely).
        persisted_with_transition = [
            snapshot
            for snapshot in calls["saves"]
            if snapshot.get("verify_fix_retries_used", 0) >= 1
            and snapshot.get("current_stage") == "04_fix"
        ]
        self.assertTrue(
            persisted_with_transition,
            "incremented retry counter was never persisted together with the transition",
        )

    def test_verify_retry_limit_blocks_without_generating_fix_prompt(self) -> None:
        state = {
            "feature_name": "demo",
            "current_stage": "05_verify",
            "status": "model_completed",
            "verify_fix_retries_used": 3,
        }
        result = {
            "status": "FAIL",
            "next_stage": "done",
            "human_gate_required": False,
            "blocking_reason": "still failing",
        }
        ctx, calls = _workflow_context(state, result)

        updated = _resume_with_fake_stage_result(ctx, "demo", max_verify_fix_retries=3)

        self.assertIs(updated, state)
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["blocked"]["stage"], "05_verify")
        self.assertIn("Verify/Fix retry limit reached", state["blocked"]["reason"])
        self.assertEqual(calls["prompts"], [])

    def test_non_final_done_advances_to_default_next_stage_with_warning(self) -> None:
        state = {
            "feature_name": "demo",
            "current_stage": "02_review",
            "status": "model_completed",
        }
        result = {
            "status": "PASS",
            "next_stage": "done",
            "human_gate_required": False,
            "blocking_reason": "",
        }
        ctx, calls = _workflow_context(
            state,
            result,
            default_next_by_stage={"02_review": "04_fix"},
            no_commit_stages={"02_review"},
        )

        updated = _resume_with_fake_stage_result(ctx, "demo")

        self.assertIs(updated, state)
        self.assertEqual(state["current_stage"], "04_fix")
        self.assertEqual(state["status"], "waiting_for_model")
        self.assertEqual(calls["prompts"][0]["stage"], "04_fix")
        warning_events = [
            event for event in calls["events"] if event["event"] == "stage_next_stage_corrected_warning"
        ]
        self.assertEqual(len(warning_events), 1)
        self.assertEqual(warning_events[0]["corrected_next_stage"], "04_fix")

    def test_final_stage_done_completes_run(self) -> None:
        state = {
            "feature_name": "demo",
            "current_stage": "02_verify",
            "status": "model_completed",
        }
        result = {
            "status": "PASS",
            "next_stage": "done",
            "human_gate_required": False,
            "blocking_reason": "",
        }
        ctx, calls = _workflow_context(
            state,
            result,
            stages=["00_specify", "01_develop", "02_verify"],
            verify_stage="02_verify",
            verify_retry_target_stage="01_develop",
            no_commit_stages={"02_verify"},
        )

        updated = _resume_with_fake_stage_result(ctx, "demo")

        self.assertIs(updated, state)
        self.assertEqual(state["current_stage"], "done")
        self.assertEqual(state["status"], "complete")
        self.assertEqual(calls["prompts"], [])
        warning_events = [
            event for event in calls["events"] if event["event"] == "stage_next_stage_corrected_warning"
        ]
        self.assertEqual(warning_events, [])

    def test_pass_with_unapproved_human_gate_blocks(self) -> None:
        state = {
            "feature_name": "demo",
            "current_stage": "01_develop",
            "status": "model_completed",
            "approved_stages": [],
        }
        result = {
            "status": "PASS",
            "next_stage": "02_review",
            "human_gate_required": True,
            "blocking_reason": "",
        }
        ctx, calls = _workflow_context(state, result)

        updated = _resume_with_fake_stage_result(ctx, "demo")

        self.assertIs(updated, state)
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["blocked"]["reason"], "Human gate approval required.")
        self.assertEqual(state["blocked"]["next_stage"], "02_review")
        self.assertEqual(calls["prompts"], [])


if __name__ == "__main__":
    unittest.main()
