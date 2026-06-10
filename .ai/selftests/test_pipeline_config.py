from __future__ import annotations

import unittest

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402
from harness_core import pipeline  # noqa: E402


FULL_STAGES = [
    "00_specify",
    "01_plan",
    "02_develop",
    "03_review",
    "04_fix",
    "05_verify",
    "06_document",
]
FULL_STAGE_OUTPUTS = {
    "00_specify": "00_spec.md",
    "01_plan": "01_plan.md",
    "02_develop": "02_dev.md",
    "03_review": "03_review.md",
    "04_fix": "04_fix.md",
    "05_verify": "05_verify.md",
    "06_document": "06_document.md",
}


class PipelineBehaviorCharacterizationTests(unittest.TestCase):
    """Pins the externally observable pipeline behavior so the PipelineConfig
    refactor (4b-4) cannot silently drift it. These assertions hold both before
    and after the refactor (same public surface, same values)."""

    def test_full_mode_module_globals(self) -> None:
        self.assertEqual(harness.PIPELINE_MODE, "full")
        self.assertEqual(list(harness.STAGES), FULL_STAGES)
        self.assertEqual(dict(harness.STAGE_OUTPUTS), FULL_STAGE_OUTPUTS)
        self.assertEqual(harness.START_STAGE, "00_specify")
        self.assertEqual(harness.DEVELOP_STAGE, "02_develop")
        self.assertEqual(harness.VERIFY_STAGE, "05_verify")
        self.assertEqual(harness.VERIFY_RETRY_TARGET_STAGE, "04_fix")
        self.assertEqual(harness.FIX_STAGE, "04_fix")
        self.assertEqual(harness.DOCUMENT_STAGE, "06_document")
        self.assertEqual(harness.NO_COMMIT_STAGES, set())
        self.assertEqual(harness.COMMIT_STAGES, set(FULL_STAGES))
        self.assertEqual(harness.PRESETS_DIR.name, "full")
        self.assertEqual(harness.PRESETS_DIR.parent, harness.AI_DIR / "presets")

    def test_pipeline_extracts_pc_candidates_per_mode(self) -> None:
        self.assertFalse(harness.pipeline_extracts_pc_candidates("fast"))
        self.assertTrue(harness.pipeline_extracts_pc_candidates("standard"))
        self.assertTrue(harness.pipeline_extracts_pc_candidates("full"))
        # Empty/None falls back to the active module mode (full -> True).
        self.assertTrue(harness.pipeline_extracts_pc_candidates(None))
        # Unknown explicit mode is not an extracting pipeline.
        self.assertFalse(harness.pipeline_extracts_pc_candidates("weird"))

    def test_harness_script_per_mode(self) -> None:
        self.assertEqual(
            harness.harness_script_for_pipeline_mode("fast"), ".ai/harness_fast.py"
        )
        self.assertEqual(
            harness.harness_script_for_pipeline_mode("standard"),
            ".ai/harness_standard.py",
        )
        self.assertEqual(
            harness.harness_script_for_pipeline_mode("full"), ".ai/harness.py"
        )
        # Empty/None falls back to the active module mode (full).
        self.assertEqual(
            harness.harness_script_for_pipeline_mode(None), ".ai/harness.py"
        )
        # Unknown explicit mode defaults to the full harness script.
        self.assertEqual(
            harness.harness_script_for_pipeline_mode("weird"), ".ai/harness.py"
        )


class PipelineRegistryTests(unittest.TestCase):
    """Covers the new PipelineConfig registry and apply_pipeline mechanism
    introduced by 4b-4."""

    def test_registry_helpers_match_legacy_behavior(self) -> None:
        self.assertEqual(set(pipeline.PIPELINES), {"fast", "standard", "full"})

        self.assertFalse(pipeline.extracts_pc_candidates("fast"))
        self.assertTrue(pipeline.extracts_pc_candidates("standard"))
        self.assertTrue(pipeline.extracts_pc_candidates("full"))
        self.assertFalse(pipeline.extracts_pc_candidates("weird"))
        self.assertFalse(pipeline.extracts_pc_candidates(None))

        self.assertEqual(pipeline.harness_script("fast"), ".ai/harness_fast.py")
        self.assertEqual(pipeline.harness_script("standard"), ".ai/harness_standard.py")
        self.assertEqual(pipeline.harness_script("full"), ".ai/harness.py")
        self.assertEqual(pipeline.harness_script("weird"), ".ai/harness.py")
        self.assertEqual(pipeline.harness_script(None), ".ai/harness.py")

        self.assertTrue(pipeline.supports_deep_thinking("full"))
        self.assertFalse(pipeline.supports_deep_thinking("fast"))
        self.assertFalse(pipeline.supports_deep_thinking("standard"))
        self.assertFalse(pipeline.supports_deep_thinking("weird"))

    def test_apply_pipeline_rebinds_globals_for_each_mode(self) -> None:
        # apply_pipeline mutates the shared harness module; always restore full.
        self.addCleanup(harness.apply_pipeline, "full")

        harness.apply_pipeline("fast")
        self.assertEqual(harness.PIPELINE_MODE, "fast")
        self.assertEqual(list(harness.STAGES), ["00_specify", "01_develop", "02_verify"])
        self.assertEqual(harness.VERIFY_STAGE, "02_verify")
        self.assertEqual(harness.VERIFY_RETRY_TARGET_STAGE, "01_develop")
        self.assertIsNone(harness.FIX_STAGE)
        self.assertIsNone(harness.DOCUMENT_STAGE)
        self.assertEqual(harness.PRESETS_DIR.name, "fast")
        self.assertEqual(harness.PRESETS_DIR.parent, harness.AI_DIR / "presets")
        self.assertEqual(harness.COMMIT_STAGES, set(harness.STAGES))

        harness.apply_pipeline("standard")
        self.assertEqual(harness.PIPELINE_MODE, "standard")
        self.assertEqual(
            list(harness.STAGES),
            ["00_specify", "01_develop", "02_review", "03_fix", "04_verify"],
        )
        self.assertEqual(harness.VERIFY_STAGE, "04_verify")
        self.assertEqual(harness.VERIFY_RETRY_TARGET_STAGE, "03_fix")
        self.assertEqual(harness.FIX_STAGE, "03_fix")
        self.assertIsNone(harness.DOCUMENT_STAGE)
        self.assertEqual(harness.PRESETS_DIR.name, "standard")
        self.assertEqual(harness.PRESETS_DIR.parent, harness.AI_DIR / "presets")

        harness.apply_pipeline("full")
        self.assertEqual(harness.PIPELINE_MODE, "full")
        self.assertEqual(list(harness.STAGES), FULL_STAGES)
        self.assertEqual(harness.DOCUMENT_STAGE, "06_document")


if __name__ == "__main__":
    unittest.main()
