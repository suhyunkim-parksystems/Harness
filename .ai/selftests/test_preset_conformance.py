from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

AI_DIR = ensure_ai_path()

import harness  # noqa: E402
from harness_core import pipeline, verification  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402
from harness_core.frontmatter import parse_frontmatter  # noqa: E402

PRESETS_DIR = AI_DIR / "presets"

# allowed_writes/forbidden_writes entries must be either one of the tokens
# policy.policy_item_matches understands, or an explicit path. A typo'd token
# (e.g. "new_test") would silently degrade to a never-matching path filter.
KNOWN_POLICY_TOKENS = {"production_code", "tests", "new_tests", "existing_tests"}

# The dynamic verification allowlist as documented in the verify presets. The
# code-side source of truth is the rejection message in
# harness_core/verification.py; drift in either direction must fail here.
EXPECTED_ALLOWLIST_FORMS = (
    "python -m pytest",
    "npm.cmd test",
    "npm.cmd run build",
    "dotnet test",
    "dotnet build",
)

DYNAMIC_SECTION_HEADING = "## Dynamic Harness Verification Commands"


def load_presets(mode: str) -> dict[str, tuple[dict[str, Any], str]]:
    """Return {stage: (frontmatter_meta, full_text)} for every preset of a mode."""
    presets: dict[str, tuple[dict[str, Any], str]] = {}
    for path in sorted((PRESETS_DIR / pipeline.PIPELINES[mode].presets_subdir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        presets[path.stem] = (meta, text)
    return presets


def routing_values(meta: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("default_next_stage", "default_next_stage_on_pass", "default_next_stage_on_fail"):
        value = meta.get(key)
        if value:
            values.append(str(value))
    return values


def dynamic_allowlist_rejection_reason() -> str:
    """Drive the real dynamic-command validation with a non-allowlisted command
    and return its rejection reason (which embeds the code-side allowlist)."""
    root = AI_DIR.parent
    ctx = HarnessContext.from_namespace({
        "ROOT": root,
        "DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS": 600,
        "load_config": lambda: {"verification": {"timeout_seconds": 600}},
        "expand_runtime_placeholders": lambda value, feature: str(value),
        "display_cwd": lambda path: str(path),
    })
    result = {
        "test_commands": [
            {"name": "bogus", "command": ["python", "script.py"], "cwd": "."},
        ]
    }
    plan = verification.dynamic_verification_commands(ctx, "demo", result, [])
    rejected = plan["rejected"]
    assert len(rejected) == 1, rejected
    return str(rejected[0]["reason"])


class PresetRegistryConformanceTests(unittest.TestCase):
    """Presets and the pipeline registry must describe the same machine."""

    def test_preset_files_match_registry_stages(self) -> None:
        for mode, config in pipeline.PIPELINES.items():
            with self.subTest(mode=mode):
                presets = load_presets(mode)
                self.assertEqual(set(presets), set(config.stages))

    def test_frontmatter_stage_matches_filename(self) -> None:
        for mode in pipeline.PIPELINES:
            for stage, (meta, _) in load_presets(mode).items():
                with self.subTest(mode=mode, stage=stage):
                    self.assertEqual(str(meta.get("stage")), stage)

    def test_registry_stage_output_is_declared_in_preset_outputs(self) -> None:
        # 06_document declares the .docx artifact first, so membership (not
        # first position) is the contract.
        for mode, config in pipeline.PIPELINES.items():
            presets = load_presets(mode)
            for stage in config.stages:
                with self.subTest(mode=mode, stage=stage):
                    meta, _ = presets[stage]
                    declared = [
                        Path(str(item)).name for item in meta.get("outputs", [])
                    ]
                    self.assertIn(config.stage_outputs[stage], declared)

    def test_next_stage_routing_targets_exist(self) -> None:
        for mode, config in pipeline.PIPELINES.items():
            valid = set(config.stages) | {"done"}
            presets = load_presets(mode)
            for stage in config.stages:
                meta, _ = presets[stage]
                for target in routing_values(meta):
                    with self.subTest(mode=mode, stage=stage, target=target):
                        self.assertIn(target, valid)

    def test_verify_preset_failure_routes_to_registry_retry_target(self) -> None:
        for mode, config in pipeline.PIPELINES.items():
            with self.subTest(mode=mode):
                meta, _ = load_presets(mode)[config.verify_stage]
                self.assertEqual(
                    str(meta.get("default_next_stage_on_fail")),
                    config.verify_retry_target_stage,
                )

    def test_write_policy_entries_are_known_tokens_or_paths(self) -> None:
        for mode in pipeline.PIPELINES:
            for stage, (meta, _) in load_presets(mode).items():
                for key in ("allowed_writes", "forbidden_writes"):
                    for item in meta.get(key, []):
                        with self.subTest(mode=mode, stage=stage, key=key, item=item):
                            entry = str(item)
                            self.assertTrue(
                                entry in KNOWN_POLICY_TOKENS or "/" in entry,
                                f"{entry!r} is neither a known policy token nor a path",
                            )

    def test_preferred_models_are_known_provider_aliases(self) -> None:
        for mode in pipeline.PIPELINES:
            for stage, (meta, _) in load_presets(mode).items():
                with self.subTest(mode=mode, stage=stage):
                    self.assertIn(
                        str(meta.get("preferred_model")),
                        set(harness.PROVIDER_BY_MODEL),
                    )


class DynamicAllowlistDriftTests(unittest.TestCase):
    """The allowlist documented in verify presets must equal the one the
    verification code actually enforces (read from its rejection message)."""

    def test_code_rejection_message_lists_expected_forms(self) -> None:
        reason = dynamic_allowlist_rejection_reason()
        match = re.search(r"\(([^)]+)\)", reason)
        self.assertIsNotNone(match, reason)
        code_forms = {part.strip() for part in match.group(1).split(",")}
        self.assertEqual(code_forms, set(EXPECTED_ALLOWLIST_FORMS))

    def test_verify_presets_document_every_enforced_form(self) -> None:
        found_dynamic_section = False
        for mode in pipeline.PIPELINES:
            for stage, (_, text) in load_presets(mode).items():
                if DYNAMIC_SECTION_HEADING not in text:
                    continue
                found_dynamic_section = True
                for form in EXPECTED_ALLOWLIST_FORMS:
                    with self.subTest(mode=mode, stage=stage, form=form):
                        self.assertIn(form, text)
        self.assertTrue(found_dynamic_section, "no preset documents dynamic commands")


class DocumentPresetPlaceholderRegressionTests(unittest.TestCase):
    """[기능명] is substituted with the real feature slug at prompt-generation
    time, so it must never appear as a 'fail if this remains' placeholder
    (regression guard for the 06_document self-defeating check)."""

    def test_forbidden_placeholder_list_excludes_feature_name_token(self) -> None:
        text = (PRESETS_DIR / "full" / "06_document.md").read_text(encoding="utf-8")
        blocks = re.findall(r"forbidden_placeholders\s*=\s*\[(.*?)\]", text, re.S)
        self.assertTrue(blocks, "forbidden_placeholders block not found")
        for block in blocks:
            self.assertNotIn("[기능명]", block)

    def test_validation_prose_excludes_feature_name_token(self) -> None:
        text = (PRESETS_DIR / "full" / "06_document.md").read_text(encoding="utf-8")
        prose = [line for line in text.splitlines() if "placeholder가 남아 있으면" in line]
        self.assertTrue(prose)
        for line in prose:
            self.assertNotIn("[기능명]", line)


if __name__ == "__main__":
    unittest.main()
