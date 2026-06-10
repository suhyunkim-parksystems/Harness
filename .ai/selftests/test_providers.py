from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from support import ensure_ai_path

AI_DIR = ensure_ai_path()

from harness_core import json_io, providers  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402
from harness_core.errors import HarnessError  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixtures
#
# Every providers.* scheduling function reaches its collaborators through
# `ctx.<helper>` (the same indirection the real harness facade uses). To unit
# test the scheduler faithfully we wire the *real* providers.* functions into a
# HarnessContext and stub only the four true external leaves:
#   - available_providers()        -> avoid shutil.which / installed-CLI dependence
#   - preset_provider_for_stage()  -> avoid preset *.md file I/O
#   - pipeline_extracts_pc_candidates() -> control PC stage inclusion per case
#   - model_policy()               -> inject the policy dict directly (A/D only)
# This keeps the tests hermetic, deterministic, and free of git/filesystem/CLI.
# No runtime module is modified by this file; it is selftest-only.
# ---------------------------------------------------------------------------

PC_STAGE = "pc_candidates"
DEFAULT_AVAILABLE = ("codex", "claude", "agy")
STANDARD_STAGES = ["00_specify", "01_develop", "02_review", "03_fix", "04_verify"]

# Mirrors harness.DEFAULT_PROVIDER_CAPABILITIES: agy has no code_write.
BASE_CAPS = {
    "codex": ["plan", "code_write", "review", "verify", "document", "pc_extract"],
    "claude": ["plan", "code_write", "review", "verify", "document", "pc_extract"],
    "agy": ["plan", "review", "verify", "document", "pc_extract"],
}

# Mirrors harness.DEFAULT_MODEL_POLICY.
BASE_POLICY: dict[str, Any] = {
    "min_distinct_agents": 2,
    "no_adjacent_same_provider": True,
    "on_independence_violation": "block",
    "code_write_allowed": ["claude", "codex"],
    "code_write_denied": ["agy"],
    "code_write_order": ["claude", "codex"],
    "non_code_order": ["agy", "codex", "claude"],
    "role_orders": {
        "plan": ["agy", "codex", "claude"],
        "review": ["agy", "codex", "claude"],
        "verify": ["codex", "agy", "claude"],
        "document": ["agy", "codex", "claude"],
        "pc_extract": ["claude", "codex", "agy"],
    },
    "avoid_reusing_recent_code_writer_for_review": True,
    "reserve_code_writers_for_code_stages": True,
}

# providers.* functions that take (ctx, ...) and must be wired to the real impl.
_WIRED = (
    "provider_schedule_stages",
    "stage_role",
    "provider_order_for_role",
    "candidate_providers_for_stage",
    "latest_code_writer",
    "stage_provider_score",
    "compute_provider_schedule",
    "build_provider_schedule",
    "ensure_provider_schedule",
    "known_provider_names",
    "provider_config",
)


def _make_ctx(
    *,
    policy: dict[str, Any] | None = None,
    available: tuple[str, ...] = DEFAULT_AVAILABLE,
    capabilities: dict[str, list[str]] | None = None,
    stages: list[str] | None = None,
    preset: dict[str, str] | None = None,
    extracts_pc: bool = False,
    **overrides: Any,
) -> HarnessContext:
    pol = dict(BASE_POLICY)
    if policy:
        pol.update(policy)
    caps = capabilities if capabilities is not None else BASE_CAPS
    stage_list = list(stages if stages is not None else STANDARD_STAGES)

    holder: dict[str, HarnessContext] = {}

    def bind(fn: Callable[..., Any]) -> Callable[..., Any]:
        return lambda *a, **k: fn(holder["ctx"], *a, **k)

    namespace: dict[str, Any] = {
        # stubbed leaves
        "model_policy": lambda: pol,
        "available_providers": lambda: list(available),
        "provider_capabilities": lambda p: set(caps.get(p, ())),
        "preset_provider_for_stage": lambda s: (preset or {}).get(s),
        "pipeline_extracts_pc_candidates": lambda *_a: extracts_pc,
        "load_config": lambda: {"providers": {p: {} for p in available}},
        "PROVIDERS": tuple(available),
        "STAGES": stage_list,
        "PC_REVIEW_STAGE": PC_STAGE,
        "PIPELINE_MODE": "standard",
    }
    namespace.update({name: bind(getattr(providers, name)) for name in _WIRED})
    namespace.update(overrides)

    ctx = HarnessContext.from_namespace(namespace)
    holder["ctx"] = ctx
    return ctx


def _code_write_stages(ctx: HarnessContext, stages: list[str]) -> list[str]:
    return [s for s in stages if ctx.stage_role(s) == "code_write"]


class TestProviderExecutableResolution(unittest.TestCase):
    def _blank_env(self, provider: str, **values: str) -> dict[str, str]:
        env = {name: "" for name in providers.PROVIDER_EXECUTABLE_ENV_VARS[provider]}
        env.update(values)
        return env

    def test_env_executable_wins_over_configured_name(self) -> None:
        calls: list[str] = []

        def fake_which(candidate: str) -> str | None:
            calls.append(candidate)
            return "/tools/codex.exe" if candidate == "/tools/codex.exe" else None

        env = self._blank_env("codex", CODEX_BIN="/tools/codex.exe")
        with patch.dict(os.environ, env, clear=False), patch.object(providers.shutil, "which", fake_which):
            command = providers.resolve_provider_command("codex", ["codex.cmd", "exec"])

        self.assertEqual(command, ["/tools/codex.exe", "exec"])
        self.assertEqual(calls[0], "/tools/codex.exe")

    def test_falls_back_from_cmd_to_exe_candidate(self) -> None:
        calls: list[str] = []

        def fake_which(candidate: str) -> str | None:
            calls.append(candidate)
            return "C:/bin/codex.exe" if candidate == "codex.exe" else None

        env = self._blank_env("codex")
        with patch.dict(os.environ, env, clear=False), patch.object(providers.shutil, "which", fake_which):
            command = providers.resolve_provider_command("codex", ["codex.cmd", "exec"])

        self.assertEqual(command, ["C:/bin/codex.exe", "exec"])
        self.assertEqual(calls[:2], ["codex.cmd", "codex.exe"])

    def test_prepare_provider_command_returns_resolved_fallback(self) -> None:
        root = Path("repo-root")

        def fake_which(candidate: str) -> str | None:
            return "C:/bin/agy.cmd" if candidate == "agy.cmd" else None

        ctx = HarnessContext.from_namespace(
            {
                "ROOT": root,
                "raw_provider_command": lambda _provider: ["agy.exe", "--add-dir", "{cwd}"],
                "apply_performance_to_command": lambda _provider, command, _performance: command,
            }
        )
        env = self._blank_env("agy")
        with patch.dict(os.environ, env, clear=False), patch.object(providers.shutil, "which", fake_which):
            command, prompt_in_command = providers.prepare_provider_command(ctx, "agy")

        self.assertFalse(prompt_in_command)
        self.assertEqual(command, ["C:/bin/agy.cmd", "--add-dir", str(root)])


# ---------------------------------------------------------------------------
# Group A: end-to-end scheduler invariants
#
# Only properties that MUST hold for any valid schedule are asserted here.
# Exact provider placement is intentionally NOT asserted (the scoring interplay
# between reserve/avoid/index makes it brittle); the precise score weights are
# covered in Group D instead.
# ---------------------------------------------------------------------------
class TestSchedulerInvariants(unittest.TestCase):
    def _schedule(self, **kwargs: Any) -> tuple[dict[str, str], HarnessContext, list[str]]:
        ctx = _make_ctx(**kwargs)
        state = {"feature_name": "demo", "pipeline_mode": "standard"}
        ordered = ctx.provider_schedule_stages(state)
        schedule = ctx.build_provider_schedule(state)
        return schedule, ctx, ordered

    def test_schedule_covers_all_stages(self) -> None:
        schedule, _ctx, ordered = self._schedule()
        self.assertEqual(set(schedule), set(ordered))
        for stage in ordered:
            self.assertTrue(schedule[stage], f"empty provider for {stage}")

    def test_no_adjacent_same_provider(self) -> None:
        schedule, _ctx, ordered = self._schedule()
        for a, b in zip(ordered, ordered[1:]):
            self.assertNotEqual(schedule[a], schedule[b], f"adjacent {a}/{b} share a provider")

    def test_min_distinct_providers_satisfied(self) -> None:
        schedule, _ctx, _ordered = self._schedule()
        self.assertGreaterEqual(len(set(schedule.values())), BASE_POLICY["min_distinct_agents"])

    def test_agy_excluded_from_code_write_stages(self) -> None:
        schedule, ctx, ordered = self._schedule()
        for stage in _code_write_stages(ctx, ordered):
            self.assertNotEqual(schedule[stage], "agy", f"denied provider on code stage {stage}")
            self.assertIn(schedule[stage], {"claude", "codex"})

    def test_preset_preferred_provider_is_honored(self) -> None:
        # Without a preset, code_write_order makes develop -> claude. A preset
        # pointing at codex must flip it (codex sorts to candidate index 0).
        baseline, _ctx, _ordered = self._schedule(stages=["01_develop", "02_review"])
        self.assertEqual(baseline["01_develop"], "claude")

        schedule, _ctx2, _ordered2 = self._schedule(
            stages=["01_develop", "02_review"],
            preset={"01_develop": "codex"},
        )
        self.assertEqual(schedule["01_develop"], "codex")

    def test_pc_candidates_stage_appended_when_extracting(self) -> None:
        schedule, ctx, ordered = self._schedule(extracts_pc=True)
        self.assertIn(PC_STAGE, ordered)
        self.assertEqual(ordered[-1], PC_STAGE)
        self.assertTrue(schedule[PC_STAGE])
        # invariants still hold across the appended stage
        for a, b in zip(ordered, ordered[1:]):
            self.assertNotEqual(schedule[a], schedule[b])

    def test_schedule_is_deterministic(self) -> None:
        # Two independent contexts, identical inputs -> byte-identical schedule.
        state = {"feature_name": "demo", "pipeline_mode": "standard"}
        first = _make_ctx().build_provider_schedule(state)
        second = _make_ctx().build_provider_schedule(state)
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# Group D: low-level helper correctness
# ---------------------------------------------------------------------------
class TestSchedulerHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = _make_ctx()
        self.policy = self.ctx.model_policy()

    def test_stage_role_maps_each_stage(self) -> None:
        cases = {
            "00_specify": "plan",
            "01_plan": "plan",
            "02_develop": "code_write",
            "03_review": "review",
            "04_fix": "code_write",
            "05_verify": "verify",
            "06_document": "document",
            PC_STAGE: "pc_extract",
        }
        for stage, role in cases.items():
            self.assertEqual(self.ctx.stage_role(stage), role, f"stage {stage}")

    def test_candidate_filters_by_capability_and_deny(self) -> None:
        available = list(DEFAULT_AVAILABLE)
        code = self.ctx.candidate_providers_for_stage("01_develop", self.policy, available)
        # agy lacks code_write capability and is denied.
        self.assertNotIn("agy", code)
        self.assertEqual(set(code), {"claude", "codex"})
        # code_write_order puts claude first.
        self.assertEqual(code[0], "claude")
        # review allows agy.
        review = self.ctx.candidate_providers_for_stage("02_review", self.policy, available)
        self.assertIn("agy", review)

    def test_candidate_respects_code_write_allowlist(self) -> None:
        restricted = dict(self.policy, code_write_allowed=["claude"])
        code = self.ctx.candidate_providers_for_stage(
            "01_develop", restricted, list(DEFAULT_AVAILABLE)
        )
        self.assertEqual(code, ["claude"])

    def test_candidate_puts_preset_provider_first(self) -> None:
        ctx = _make_ctx(preset={"01_develop": "codex"})
        code = ctx.candidate_providers_for_stage(
            "01_develop", ctx.model_policy(), list(DEFAULT_AVAILABLE)
        )
        self.assertEqual(code[0], "codex")

    def test_latest_code_writer_returns_most_recent(self) -> None:
        stages = ["00_specify", "01_develop", "02_review", "03_fix"]
        assignments = {
            "00_specify": "agy",
            "01_develop": "claude",
            "02_review": "agy",
            "03_fix": "codex",
        }
        self.assertEqual(self.ctx.latest_code_writer(assignments, stages), "codex")

    def test_latest_code_writer_none_without_code_stage(self) -> None:
        stages = ["00_specify", "02_review"]
        assignments = {"00_specify": "agy", "02_review": "claude"}
        self.assertIsNone(self.ctx.latest_code_writer(assignments, stages))

    def test_score_penalizes_recent_code_writer_for_review(self) -> None:
        # Isolate the +80 avoid-reuse penalty: identical setup except whether the
        # candidate equals the latest code writer.
        candidates = ["claude", "agy"]
        with_reuse = self.ctx.stage_provider_score(
            "02_review", "claude", candidates, {"01_develop": "claude"}, ["01_develop"], self.policy
        )
        without_reuse = self.ctx.stage_provider_score(
            "02_review", "claude", candidates, {}, [], self.policy
        )
        self.assertEqual(with_reuse - without_reuse, 80)

    def test_score_reserves_code_writers_for_non_code_stage(self) -> None:
        # On a non-code (verify) stage, a code-writer candidate is penalized +30
        # when a non-code candidate is also available.
        candidates = ["agy", "claude"]
        agy_score = self.ctx.stage_provider_score("04_verify", "agy", candidates, {}, [], self.policy)
        claude_score = self.ctx.stage_provider_score(
            "04_verify", "claude", candidates, {}, [], self.policy
        )
        self.assertEqual(agy_score, 0)            # index 0, non-code: no penalty
        self.assertEqual(claude_score, 100 + 30)  # index 1 *100, +30 reserve

    def test_ensure_provider_schedule_reuses_existing(self) -> None:
        # A complete schedule already in state must be returned verbatim WITHOUT
        # recomputing. We prove "no recompute" by making available_providers blow
        # up if the build path is ever entered.
        def explode() -> Any:
            raise AssertionError("schedule was recomputed instead of reused")

        complete = {stage: "claude" for stage in STANDARD_STAGES}
        state = {
            "feature_name": "demo",
            "pipeline_mode": "standard",
            "provider_schedule": dict(complete),
        }
        ctx = _make_ctx(available_providers=explode)
        result = ctx.ensure_provider_schedule(state, record_event=False, persist=False)
        self.assertEqual(result, complete)

    def test_ensure_provider_schedule_builds_when_missing(self) -> None:
        state = {"feature_name": "demo", "pipeline_mode": "standard", "events": None}
        ctx = _make_ctx()
        built = ctx.ensure_provider_schedule(state, record_event=False, persist=False)
        expected = _make_ctx().build_provider_schedule(state)
        self.assertEqual(built, expected)
        self.assertEqual(set(built), set(STANDARD_STAGES))


# ---------------------------------------------------------------------------
# Group B: failure paths
#
# The scheduler must refuse impossible configurations loudly (HarnessError) or
# signal infeasibility (None) rather than silently emit a policy-violating
# schedule.
# ---------------------------------------------------------------------------
class TestSchedulerFailurePaths(unittest.TestCase):
    @staticmethod
    def _state() -> dict[str, Any]:
        return {"feature_name": "demo", "pipeline_mode": "standard"}

    def test_too_few_available_providers_raises(self) -> None:
        # Policy requires >= 2 distinct providers; only one is available.
        ctx = _make_ctx(available=("claude",))
        with self.assertRaises(HarnessError) as caught:
            ctx.compute_provider_schedule(self._state(), strict_independence=True)
        self.assertIn("distinct", str(caught.exception).lower())

    def test_stage_with_no_eligible_provider_raises(self) -> None:
        # Enough providers are available, but every code writer is denied, so the
        # code_write stage ends up with zero candidates.
        ctx = _make_ctx(
            stages=["01_develop", "02_review"],
            policy={"code_write_denied": ["claude", "codex", "agy"]},
        )
        with self.assertRaises(HarnessError) as caught:
            ctx.compute_provider_schedule(self._state(), strict_independence=True)
        self.assertIn("01_develop", str(caught.exception))

    def test_strict_independence_infeasible_returns_none(self) -> None:
        # Only claude may write code, so two adjacent code stages cannot avoid
        # repeating a provider under strict independence -> infeasible (None).
        ctx = _make_ctx(
            available=("claude", "agy"),
            stages=["01_develop", "03_fix"],
            policy={"min_distinct_agents": 1, "code_write_allowed": ["claude"]},
        )
        result = ctx.compute_provider_schedule(self._state(), strict_independence=True)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Group C: build_provider_schedule fallback policy
#
# When strict independence is infeasible (compute returns None), build_provider_
# schedule branches on model_policy.on_independence_violation:
#   "block" -> raise; "allow" -> retry without strict independence.
# Reuses Group B's infeasible setup (only claude may write two adjacent code
# stages).
# ---------------------------------------------------------------------------
class TestBuildScheduleFallback(unittest.TestCase):
    @staticmethod
    def _state() -> dict[str, Any]:
        return {"feature_name": "demo", "pipeline_mode": "standard"}

    def _infeasible_ctx(self, violation: str) -> HarnessContext:
        return _make_ctx(
            available=("claude", "agy"),
            stages=["01_develop", "03_fix"],
            policy={
                "min_distinct_agents": 1,
                "code_write_allowed": ["claude"],
                "on_independence_violation": violation,
            },
        )

    def test_block_raises_when_independence_unsatisfiable(self) -> None:
        ctx = self._infeasible_ctx("block")
        with self.assertRaises(HarnessError) as caught:
            ctx.build_provider_schedule(self._state())
        self.assertIn("independence", str(caught.exception).lower())

    def test_allow_falls_back_to_non_strict_schedule(self) -> None:
        ctx = self._infeasible_ctx("allow")
        schedule = ctx.build_provider_schedule(self._state())
        # Fallback succeeds even though strict independence is impossible: both
        # code stages go to the only eligible writer (adjacent duplicate allowed).
        self.assertEqual(schedule, {"01_develop": "claude", "03_fix": "claude"})


# ---------------------------------------------------------------------------
# Group E: contract test against the REAL shipping config
#
# Loads the actual .ai/harness.config.json policy (through json_io, honoring the
# BOM-tolerant reader) and asserts that, for every pipeline mode, the scheduler
# produces a schedule that satisfies the shipped policy. This guards against the
# shipping config drifting into an unsatisfiable / policy-violating state.
# ---------------------------------------------------------------------------
CONFIG_PATH = AI_DIR / "harness.config.json"


class TestRealConfigContract(unittest.TestCase):
    def _real_ctx(self, available: list[str], stages: list[str], extracts_pc: bool) -> HarnessContext:
        import harness  # local import: importing rebinds harness pipeline globals

        holder: dict[str, HarnessContext] = {}

        def bind(fn: Callable[..., Any]) -> Callable[..., Any]:
            return lambda *a, **k: fn(holder["ctx"], *a, **k)

        wired = (
            "model_policy",
            "provider_config",
            "provider_capabilities",
            "known_provider_names",
            "provider_schedule_stages",
            "stage_role",
            "provider_order_for_role",
            "candidate_providers_for_stage",
            "latest_code_writer",
            "stage_provider_score",
            "compute_provider_schedule",
            "build_provider_schedule",
        )
        namespace: dict[str, Any] = {
            "AI_DIR": AI_DIR,
            "DEFAULT_MODEL_POLICY": harness.DEFAULT_MODEL_POLICY,
            "DEFAULT_PROVIDER_CAPABILITIES": harness.DEFAULT_PROVIDER_CAPABILITIES,
            "PROVIDERS": harness.PROVIDERS,
            "PC_REVIEW_STAGE": harness.PC_REVIEW_STAGE,
            "STAGES": list(stages),
            # real config from disk (BOM-tolerant), but availability is forced so
            # the test does not depend on which provider CLIs are installed.
            "load_config": lambda: json_io.read_json_value_file(CONFIG_PATH),
            "available_providers": lambda: list(available),
            "preset_provider_for_stage": lambda _s: None,
            "pipeline_extracts_pc_candidates": lambda *_a: extracts_pc,
        }
        namespace.update({name: bind(getattr(providers, name)) for name in wired})
        ctx = HarnessContext.from_namespace(namespace)
        holder["ctx"] = ctx
        return ctx

    def test_each_mode_schedule_satisfies_shipped_policy(self) -> None:
        import harness

        self.addCleanup(harness.apply_pipeline, "full")
        available = ["codex", "claude", "agy"]

        for mode in ("fast", "standard", "full"):
            with self.subTest(mode=mode):
                harness.apply_pipeline(mode)
                stages = list(harness.STAGES)
                extracts = bool(harness.pipeline_extracts_pc_candidates(mode))
                ctx = self._real_ctx(available, stages, extracts)
                state = {"feature_name": "demo", "pipeline_mode": mode}

                ordered = ctx.provider_schedule_stages(state)
                schedule = ctx.build_provider_schedule(state)
                policy = ctx.model_policy()
                min_distinct = int(policy.get("min_distinct_agents", 2) or 0)
                denied = {str(p).strip().lower() for p in policy.get("code_write_denied", [])}

                # full coverage
                self.assertEqual(set(schedule), set(ordered))
                for stage in ordered:
                    self.assertTrue(schedule[stage], f"{mode}: empty provider for {stage}")
                # no adjacent duplicates (config sets no_adjacent_same_provider)
                for a, b in zip(ordered, ordered[1:]):
                    self.assertNotEqual(schedule[a], schedule[b], f"{mode}: {a}/{b} share provider")
                # distinct floor
                self.assertGreaterEqual(
                    len(set(schedule.values())), min_distinct, f"{mode}: too few distinct providers"
                )
                # code-write deny honored
                for stage in ordered:
                    if ctx.stage_role(stage) == "code_write":
                        self.assertNotIn(
                            schedule[stage].lower(), denied, f"{mode}: denied provider on {stage}"
                        )


if __name__ == "__main__":
    unittest.main()
