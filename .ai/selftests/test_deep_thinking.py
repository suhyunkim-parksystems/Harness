from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402  (full module used as the injected ctx base)
from harness_core import deep_thinking as dt  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402


PROMPT_OUTPUT_RE = re.compile(r"^- output_file:\s*(.+?)\s*$", re.M)
PROMPT_RESULT_RE = re.compile(r"^- result_json_file:\s*(.+?)\s*$", re.M)

PLAN_STAGE = "01_plan"
FEATURE = "demo-feat"


def _candidate_body() -> str:
    # Intentionally neutral: no provider name, no actual_model in the human body so the
    # test can assert that the *structured* identity channels are what gets scrubbed.
    return "# 01_plan\n\n초안 본문입니다.\n\n## 단계 결과\nstatus: PASS\n"


def _fake_run_factory(records: list[dict[str, Any]], fail_providers: tuple[str, ...] = ()) -> Any:
    def fake_run(
        provider: str,
        prompt_text: str,
        *,
        logs_dir: Path,
        log_prefix: str,
        timeout_seconds: int,
        performance: Any | None = None,
    ) -> dict[str, Any]:
        records.append({"provider": provider, "log_prefix": log_prefix, "prompt": prompt_text})
        base = {
            "provider": provider,
            "timed_out": False,
            "stdout": ".ai/x.out.txt",
            "stderr": ".ai/x.err.txt",
            "provider_log": ".ai/x.cli.log",
            "elapsed_seconds": 0.1,
        }
        if provider in fail_providers:
            return {**base, "returncode": 9}

        out_rel = PROMPT_OUTPUT_RE.search(prompt_text).group(1)
        rj_rel = PROMPT_RESULT_RE.search(prompt_text).group(1)
        result = {
            "status": "PASS",
            "next_stage": "02_develop",
            "human_gate_required": False,
            "blocking_reason": "",
            "risk_level": "low",
            "actual_model": provider,
            "model_mismatch": False,
        }
        out_path = Path(harness.ROOT) / out_rel
        rj_path = Path(harness.ROOT) / rj_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rj_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_candidate_body(), encoding="utf-8")
        rj_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**base, "returncode": 0}

    return fake_run


class ParallelPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dt-selftest-"))
        self._orig = {name: getattr(harness, name) for name in ("ROOT", "AI_DIR", "RUNS_DIR", "FEATURES_DIR")}
        harness.ROOT = self.tmp
        harness.AI_DIR = self.tmp / ".ai"
        harness.RUNS_DIR = harness.AI_DIR / "runs"
        harness.FEATURES_DIR = harness.AI_DIR / "features"
        harness.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        harness.FEATURES_DIR.mkdir(parents=True, exist_ok=True)
        self.config_path = harness.AI_DIR / "harness.config.json"
        self._write_config({})
        self._write_prompt()

    def tearDown(self) -> None:
        for name, value in self._orig.items():
            setattr(harness, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_raw_config(self, config: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_config(self, deep_thinking: dict[str, Any]) -> None:
        self._write_raw_config({"deep_thinking": deep_thinking})

    def _write_legacy_config(self, heavy_thinking: dict[str, Any]) -> None:
        self._write_raw_config({"heavy_thinking": heavy_thinking})

    def _write_prompt(self) -> None:
        official_md = harness.rel(harness.stage_output_path(FEATURE, PLAN_STAGE))
        official_rj = harness.rel(harness.stage_result_json_path(FEATURE, PLAN_STAGE))
        self.official_md = official_md
        self.official_rj = official_rj
        prompt_dir = harness.RUNS_DIR / FEATURE / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = prompt_dir / f"{PLAN_STAGE}_attempt1.md"
        prompt_file.write_text(
            "# Local Harness Prompt\n\n"
            "## Harness Context\n"
            f"- feature_name: {FEATURE}\n"
            f"- stage: {PLAN_STAGE}\n"
            f"- output_file: {official_md}\n"
            f"- result_json_file: {official_rj}\n\n"
            "## Manual Provider Instructions\n"
            f"3. Write the stage output exactly at `{official_md}`.\n"
            f"4. Write the result JSON exactly at `{official_rj}`.\n",
            encoding="utf-8",
        )
        self.prompt_rel = harness.rel(prompt_file)

    def _state(self, strategy: str | None = "parallel") -> dict[str, Any]:
        return {
            "feature_name": FEATURE,
            "current_stage": PLAN_STAGE,
            "current_prompt": self.prompt_rel,
            "status": "waiting_for_model",
            "performance": "lite",
            "deep_thinking": True,
            "strategy": strategy,
            "events": [],
        }

    def _ctx(
        self,
        fake_run: Any,
        *,
        synthesizer: str = "codex",
        available: tuple[str, ...] = ("codex", "claude", "agy"),
    ) -> dict[str, Any]:
        available_set = set(available)
        ctx = {name: value for name, value in vars(harness).items() if not name.startswith("__")}
        ctx["run_text_provider_prompt"] = fake_run
        ctx["safe_git_head"] = lambda: "HEAD0"
        ctx["provider_available"] = lambda provider: provider in available_set
        ctx["provider_capabilities"] = lambda provider: {
            "plan",
            "code_write",
            "review",
            "verify",
            "document",
            "pc_extract",
        }
        ctx["known_provider_names"] = lambda: ["codex", "claude", "agy"]
        ctx["available_providers"] = lambda: [p for p in ("codex", "claude", "agy") if p in available_set]
        ctx["provider_for_stage"] = lambda stage, state=None: synthesizer
        return HarnessContext.from_namespace(ctx)

    def _features_plan_files(self) -> list[str]:
        feature_dir = harness.FEATURES_DIR / FEATURE
        if not feature_dir.exists():
            return []
        return sorted(path.name for path in feature_dir.glob("*.md"))

    def _draft_prompts(self, records: list[dict[str, Any]]) -> list[str]:
        return [r["prompt"] for r in records if "독립 초안" in r["prompt"]]

    def _synthesis_prompts(self, records: list[dict[str, Any]]) -> list[str]:
        return [r["prompt"] for r in records if "종합 지시" in r["prompt"]]

    def _relay_prompts(self, records: list[dict[str, Any]]) -> list[str]:
        return [r["prompt"] for r in records if "## Deep Thinking 단계 지시" in r["prompt"]]

    # ------------------------------------------------------------------ tests

    def test_parallel_produces_single_official_plan(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        state = dt.execute_plan(ctx, self._state(), 30)

        self.assertEqual(state["status"], "model_completed")
        # UX guarantee: exactly one plan file is visible under .ai/features.
        self.assertEqual(self._features_plan_files(), ["01_plan.md"])
        self.assertTrue((harness.FEATURES_DIR / FEATURE / "01_plan.result.json").exists())
        # Intermediate drafts are not surfaced as feature artifacts.
        self.assertFalse(list((harness.FEATURES_DIR / FEATURE).glob("*draft*")))
        # Temp scratch is cleaned by default (persist_intermediate_outputs: false).
        temp_dir = harness.RUNS_DIR / FEATURE / ".tmp" / "deep_thinking"
        self.assertFalse(temp_dir.exists())
        # 3 independent drafts + 1 synthesis.
        self.assertEqual(len(self._draft_prompts(records)), 3)
        self.assertEqual(len(self._synthesis_prompts(records)), 1)
        self.assertEqual(state["provider_schedule"][PLAN_STAGE], "codex")

    def test_drafts_are_blind_and_synthesis_is_anonymized(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        dt.execute_plan(ctx, self._state(), 30)

        # Blind: each draft prompt carries no prior candidate context.
        for prompt in self._draft_prompts(records):
            self.assertNotIn("종합 대상", prompt)
            self.assertNotIn("후보 계획 1", prompt)

        synth = self._synthesis_prompts(records)[0]
        self.assertIn("종합 대상 후보 계획 (익명)", synth)
        self.assertIn("### 후보 계획 1", synth)
        # Anonymized: the structured identity channels are stripped.
        self.assertNotIn("- provider:", synth)
        self.assertNotIn("actual_model", synth)

    def test_failed_draft_is_dropped_and_run_continues(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records, fail_providers=("agy",)))
        state = dt.execute_plan(ctx, self._state(), 30)

        self.assertEqual(state["status"], "model_completed")
        self.assertEqual(self._features_plan_files(), ["01_plan.md"])
        # Two surviving drafts still trigger synthesis.
        self.assertEqual(len(self._synthesis_prompts(records)), 1)
        self.assertTrue(any("agy" in warning for warning in state.get("deep_thinking_warnings", [])))

    def test_single_surviving_draft_is_promoted_without_synthesis(self) -> None:
        self._write_config({"max_drafters": 2})
        records: list[dict[str, Any]] = []
        # Drafters are [agy, claude]; failing agy leaves exactly one candidate.
        ctx = self._ctx(_fake_run_factory(records, fail_providers=("agy",)))
        state = dt.execute_plan(ctx, self._state(), 30)

        self.assertEqual(state["status"], "model_completed")
        self.assertEqual(self._features_plan_files(), ["01_plan.md"])
        # No synthesis step ran; the lone draft was promoted directly.
        self.assertEqual(len(self._synthesis_prompts(records)), 0)
        plan_text = (harness.FEATURES_DIR / FEATURE / "01_plan.md").read_text(encoding="utf-8")
        self.assertIn("초안 본문입니다.", plan_text)

    def test_legacy_config_key_is_still_supported(self) -> None:
        self._write_legacy_config({"max_drafters": 2})
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        state = dt.execute_plan(ctx, self._state(), 30)

        self.assertEqual(state["status"], "model_completed")
        self.assertEqual(len(self._draft_prompts(records)), 2)

    def test_legacy_state_key_still_enables_execution(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        state = self._state()
        state["heavy_thinking"] = state.pop("deep_thinking")

        self.assertTrue(dt.should_execute_plan(ctx, state))

    # ----------------------------------------------------------- max strategy

    def test_max_full_relay_three_agents(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        state = dt.execute_plan(ctx, self._state("max"), 30)

        self.assertEqual(state["status"], "model_completed")
        # UX guarantee holds for max too: exactly one plan file surfaces.
        self.assertEqual(self._features_plan_files(), ["01_plan.md"])
        self.assertFalse(list((harness.FEATURES_DIR / FEATURE).glob("*draft*")))
        temp_dir = harness.RUNS_DIR / FEATURE / ".tmp" / "deep_thinking"
        self.assertFalse(temp_dir.exists())
        # 3 blind drafts (breadth) + 3 grounded relay steps (depth).
        self.assertEqual(len(self._draft_prompts(records)), 3)
        self.assertEqual(len(self._relay_prompts(records)), 3)
        # Owner (the would-be single-mode plan provider) writes the final official plan.
        self.assertEqual(state["provider_schedule"][PLAN_STAGE], "codex")

    def test_max_relay_steps_are_distinct_grounded_jobs(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        dt.execute_plan(ctx, self._state("max"), 30)

        relays = self._relay_prompts(records)
        joined = "\n".join(relays)
        # The three relay steps are different jobs, not "refine x3".
        self.assertIn("종합 대상 후보 계획 (익명)", joined)  # select (direction)
        self.assertIn("실제 코드베이스에 대조", joined)        # ground (verify against code)
        self.assertIn("사전 부검", joined)                    # pre-mortem (adversarial)
        # Drafts stay blind; the select step stays anonymized.
        for prompt in self._draft_prompts(records):
            self.assertNotIn("종합 대상", prompt)
        select_prompt = next(p for p in relays if "종합 대상 후보 계획 (익명)" in p)
        self.assertNotIn("- provider:", select_prompt)
        self.assertNotIn("actual_model", select_prompt)

    def test_max_degrades_to_two_agents(self) -> None:
        records: list[dict[str, Any]] = []
        # Simulate claude turned off (token budget): only codex + agy can plan.
        ctx = self._ctx(_fake_run_factory(records), available=("codex", "agy"))
        state = dt.execute_plan(ctx, self._state("max"), 30)

        self.assertEqual(state["status"], "model_completed")
        self.assertEqual(self._features_plan_files(), ["01_plan.md"])
        self.assertEqual(len(self._draft_prompts(records)), 2)
        relays = self._relay_prompts(records)
        # Jobs bundle into two passes: [select+ground] then [pre-mortem+finalize].
        self.assertEqual(len(relays), 2)
        self.assertIn("종합 대상 후보 계획 (익명)", relays[0])
        self.assertIn("실제 코드베이스에 대조", relays[0])
        self.assertIn("사전 부검", relays[1])
        self.assertEqual(state["provider_schedule"][PLAN_STAGE], "codex")

    def test_max_single_candidate_still_grounds(self) -> None:
        records: list[dict[str, Any]] = []
        # Two of three drafts fail -> one candidate. No select needed, but the depth
        # passes (ground + pre-mortem) must still run, unlike parallel which just promotes.
        ctx = self._ctx(_fake_run_factory(records, fail_providers=("agy", "claude")))
        state = dt.execute_plan(ctx, self._state("max"), 30)

        self.assertEqual(state["status"], "model_completed")
        self.assertEqual(self._features_plan_files(), ["01_plan.md"])
        joined = "\n".join(self._relay_prompts(records))
        self.assertNotIn("종합 대상 후보 계획 (익명)", joined)  # nothing to select among
        self.assertIn("실제 코드베이스에 대조", joined)          # ground still runs
        self.assertIn("사전 부검", joined)                      # pre-mortem still runs

    def test_max_select_step_is_framed_as_intermediate(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        dt.execute_plan(ctx, self._state("max"), 30)

        relays = self._relay_prompts(records)
        select_prompt = next(p for p in relays if "종합 대상 후보 계획 (익명)" in p)
        # The select step is intermediate; it must not claim to be the final artifact.
        self.assertIn("임시 중간 결과이며 최종이 아니다", select_prompt)
        self.assertNotIn("이 결과만 실제 `01_plan` stage 산출물로 인정된다", select_prompt)

    # ----------------------------------------------------- sequential (relay)

    def _iteration_prompts(self, records: list[dict[str, Any]]) -> list[str]:
        return [r["prompt"] for r in records if "## Deep Thinking 내부 지시" in r["prompt"]]

    def test_sequential_relay_writes_single_official_plan(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        state = dt.execute_plan(ctx, self._state("sequential"), 30)

        self.assertEqual(state["status"], "model_completed")
        self.assertEqual(self._features_plan_files(), ["01_plan.md"])
        # Default iterations=3 -> three relay iterations.
        self.assertEqual(len(self._iteration_prompts(records)), 3)

    def test_sequential_relay_substitutes_paths_without_override(self) -> None:
        records: list[dict[str, Any]] = []
        ctx = self._ctx(_fake_run_factory(records))
        dt.execute_plan(ctx, self._state("sequential"), 30)

        iters = self._iteration_prompts(records)
        self.assertEqual(len(iters), 3)
        # The contradictory output-path override section is gone.
        for prompt in iters:
            self.assertNotIn("출력 경로 지시", prompt)
        # Non-final iterations target their own temp candidate path; the final one targets official.
        out_files = [PROMPT_OUTPUT_RE.search(prompt).group(1) for prompt in iters]
        self.assertIn("candidate", out_files[0])
        self.assertIn("candidate", out_files[1])
        self.assertEqual(out_files[2], self.official_md)


class DeepThinkingUnitTests(unittest.TestCase):
    def test_anonymize_strips_provider_and_actual_model(self) -> None:
        candidates = [
            {
                "iteration": 1,
                "provider": "claude",
                "output_text": "계획 본문",
                "result": {"status": "PASS", "actual_model": "Claude", "model_mismatch": False},
            }
        ]
        text = dt._previous_candidate_context(candidates, {"anonymize_candidates": True})
        self.assertIn("### 후보 계획 1", text)
        self.assertNotIn("claude", text.lower())
        self.assertNotIn("actual_model", text)

    def test_non_anonymized_keeps_provider_label(self) -> None:
        candidates = [
            {
                "iteration": 1,
                "provider": "claude",
                "output_text": "계획 본문",
                "result": {"status": "PASS"},
            }
        ]
        text = dt._previous_candidate_context(candidates, {"anonymize_candidates": False})
        self.assertIn("- provider: claude", text)
        self.assertIn("### 1회차 후보 계획", text)

    def test_strategy_resolution(self) -> None:
        # HarnessError is now a real import in deep_thinking (harness_core.errors),
        # so no runtime injection is needed for this unit test.
        self.assertEqual(dt._strategy({"strategy": None}, {"strategy": "parallel"}), "parallel")
        self.assertEqual(dt._strategy({"strategy": "sequential"}, {}), "sequential")
        self.assertEqual(dt._strategy({"strategy": "relay"}, {}), "sequential")
        self.assertEqual(dt._strategy({}, {}), "parallel")
        with self.assertRaises(harness.HarnessError):
            dt._strategy({"strategy": "bogus"}, {})


if __name__ == "__main__":
    unittest.main()
