from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

AI_DIR = ensure_ai_path()

from harness_core import pipeline, stage_runtime  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402
from harness_core.errors import HarnessError  # noqa: E402
from harness_core.frontmatter import parse_frontmatter  # noqa: E402
from harness_core.status import RunStatus  # noqa: E402

PROJECT_CONTRACT_TEXT = "## Project Contract\n- 없음"


def _rel(path: Any) -> str:
    return str(path).replace("\\", "/")


def make_prompt_ctx(tmp: Path, mode: str) -> HarnessContext:
    """Hand-built context for stage_runtime.generate_prompt using the REAL
    preset files but temp-dir artifact paths, fixed clock, and stub git."""
    config = pipeline.PIPELINES[mode]
    presets_dir = AI_DIR / "presets" / config.presets_subdir

    def read_preset(stage: str) -> tuple[dict[str, Any], str, str]:
        text = (presets_dir / f"{stage}.md").read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        return meta, body, text

    def stage_output_path(feature: str, stage: str) -> Path:
        return tmp / "features" / feature / config.stage_outputs[stage]

    def stage_result_json_path(feature: str, stage: str) -> Path:
        output = stage_output_path(feature, stage)
        return output.with_name(f"{output.stem}.result.json")

    return HarnessContext.from_namespace({
        "PIPELINE_MODE": config.mode,
        "STAGES": list(config.stages),
        "VERIFY_STAGE": config.verify_stage,
        "VERIFY_RETRY_TARGET_STAGE": config.verify_retry_target_stage,
        "DOCUMENT_STAGE": config.document_stage,
        "read_preset": read_preset,
        "provider_for_stage": lambda stage, state: "codex",
        "stage_output_path": stage_output_path,
        "stage_result_json_path": stage_result_json_path,
        "ensure_project_contract_file": lambda: None,
        "file_policy_snapshot": lambda feature: {},
        "project_contract_prompt_text": lambda: PROJECT_CONTRACT_TEXT,
        "latest_verification_result_path": (
            lambda feature: tmp / "runs" / feature / "verification" / "latest.json"
        ),
        "state_path": lambda feature: tmp / "runs" / feature / "run.json",
        "run_dir": lambda feature: tmp / "runs" / feature,
        "rel": _rel,
        "iso_now": lambda: "2026-06-12T00:00:00",
        "normalize_performance": lambda value: str(value or "medium"),
        "safe_git_head": lambda: "abc1234",
        "filtered_changed_paths": lambda state, stage: [],
        "log_event": lambda *args, **kwargs: None,
        "save_state": lambda state: None,
    })


def make_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "feature_name": "demo-feature",
        "request": "데모 기능을 만들어 주세요",
    }
    state.update(overrides)
    return state


class GeneratePromptContractTests(unittest.TestCase):
    def _generate(self, mode: str, stage: str, state: dict[str, Any]) -> tuple[str, dict[str, Any], Path]:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ctx = make_prompt_ctx(tmp, mode)
            path = stage_runtime.generate_prompt(ctx, state, stage)
            text = path.read_text(encoding="utf-8")
        return text, state, path

    def test_feature_placeholder_fully_substituted(self) -> None:
        # standard 00_specify uses [기능명] heavily in paths and templates.
        text, _, _ = self._generate("standard", "00_specify", make_state())
        self.assertNotIn("[기능명]", text)
        self.assertIn("demo-feature", text)

    def test_harness_instruction_sections_present(self) -> None:
        text, _, _ = self._generate("standard", "00_specify", make_state())
        for heading in (
            "# Local Harness Prompt",
            "## Harness Context",
            "## Decision Policy",
            "## Manual Provider Instructions",
            "## Machine Result JSON Contract",
            "## Original User Request",
            "## Previous Stage Outputs",
            "## Current Git Hints",
        ):
            self.assertIn(heading, text)
        self.assertIn("Do not run `git commit`", text)
        self.assertIn(PROJECT_CONTRACT_TEXT, text)
        self.assertIn("- current_head: abc1234", text)

    def test_output_and_result_json_paths_advertised(self) -> None:
        text, _, _ = self._generate("standard", "01_develop", make_state())
        self.assertIn("features/demo-feature/01_dev.md", text)
        self.assertIn("features/demo-feature/01_dev.result.json", text)

    def test_prompt_ends_with_preset_body(self) -> None:
        # The wrapper instruction is prepended; the preset (with its own
        # 금지 사항 section) must follow it intact.
        text, _, _ = self._generate("standard", "01_develop", make_state())
        self.assertIn("## 금지 사항", text)
        self.assertLess(text.index("# Local Harness Prompt"), text.index("## 금지 사항"))

    def test_decision_policy_varies_by_mode(self) -> None:
        manual, _, _ = self._generate("standard", "00_specify", make_state())
        defaults, _, _ = self._generate("standard", "00_specify", make_state(defaults_mode=True))
        interactive, _, _ = self._generate(
            "standard", "00_specify", make_state(interactive_mode=True)
        )
        self.assertIn("Ask for user input when the preset's question criteria require it", manual)
        self.assertIn("Use recommended defaults for ambiguous decisions", defaults)
        self.assertIn('include a structured `questions` array', interactive)
        self.assertIn("- defaults_mode: true", defaults)
        self.assertIn("- interactive_mode: true", interactive)

    def test_both_decision_modes_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ctx = make_prompt_ctx(Path(raw), "standard")
            state = make_state(defaults_mode=True, interactive_mode=True)
            with self.assertRaises(HarnessError):
                stage_runtime.generate_prompt(ctx, state, "00_specify")

    def test_non_final_stage_forbids_done(self) -> None:
        text, _, _ = self._generate("standard", "00_specify", make_state())
        self.assertIn('do not use "done"', text)
        self.assertIn("`01_develop`", text)

    def test_final_stage_allows_done(self) -> None:
        text, _, _ = self._generate("standard", "04_verify", make_state())
        self.assertIn('use "done" only when the run is complete', text)
        self.assertNotIn('do not use "done"', text)

    def test_state_transitions_recorded(self) -> None:
        text, state, path = self._generate("standard", "00_specify", make_state())
        self.assertEqual(state["current_stage"], "00_specify")
        self.assertEqual(state["status"], RunStatus.WAITING_FOR_MODEL)
        self.assertEqual(state["attempts"]["00_specify"], 1)
        self.assertTrue(path.name.endswith("attempt1.md"))
        self.assertEqual(state["current_prompt"], _rel(path))

    def test_retry_context_block_included(self) -> None:
        text, _, _ = self._generate(
            "standard",
            "01_develop",
            make_state(),
        )
        self.assertIn("## Retry Context\n- none", text)
        with tempfile.TemporaryDirectory() as raw:
            ctx = make_prompt_ctx(Path(raw), "standard")
            path = stage_runtime.generate_prompt(
                ctx, make_state(), "01_develop", retry_context="이전 시도가 실패했습니다"
            )
            retried = path.read_text(encoding="utf-8")
        self.assertIn("이전 시도가 실패했습니다", retried)

    def test_verify_retry_target_lists_verify_artifacts_when_present(self) -> None:
        # In standard mode the retry target is 03_fix; when the verify stage
        # already produced its output, it must surface as an additional input.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ctx = make_prompt_ctx(tmp, "standard")
            verify_output = tmp / "features" / "demo-feature" / "04_verify.md"
            verify_output.parent.mkdir(parents=True, exist_ok=True)
            verify_output.write_text("# 04_verify - demo-feature\n", encoding="utf-8")
            path = stage_runtime.generate_prompt(ctx, make_state(), "03_fix")
            text = path.read_text(encoding="utf-8")
        self.assertIn("## Additional Stage Inputs", text)
        self.assertIn("features/demo-feature/04_verify.md", text)

    def test_full_pipeline_prompt_generates_for_every_stage(self) -> None:
        config = pipeline.PIPELINES["full"]
        for stage in config.stages:
            with self.subTest(stage=stage):
                text, _, _ = self._generate("full", stage, make_state())
                self.assertIn("## Machine Result JSON Contract", text)
                self.assertNotIn("[기능명]", text)


if __name__ == "__main__":
    unittest.main()
