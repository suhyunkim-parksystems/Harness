from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import policy  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402


def _policy_context(meta: dict[str, Any], changed_paths: list[str]) -> HarnessContext:
    def rel(path: Any) -> str:
        return str(path).replace("\\", "/")

    return HarnessContext.from_namespace({
        "read_preset": lambda stage: (meta, "", Path(f".ai/presets/{stage}.md")),
        "filtered_changed_paths": lambda state, stage: changed_paths,
        "STAGES": ["01_develop"],
        "stage_output_path": lambda feature, stage: Path(f".project/features/{feature}/01_dev.md"),
        "stage_result_json_path": lambda feature, stage: Path(f".project/features/{feature}/01_dev.result.json"),
        "rel": rel,
        "log_event": lambda *args, **kwargs: None,
    })


class WritePolicySelfTests(unittest.TestCase):
    def test_forbidden_production_code_change_is_violation(self) -> None:
        meta = {
            "allowed_writes": [".project/features/[기능명]/01_dev.md"],
            "forbidden_writes": ["production_code"],
        }
        state = {"feature_name": "demo"}

        violations = policy.write_policy_violations(
            _policy_context(meta, ["src/app.py"]),
            state,
            "01_develop",
        )

        self.assertEqual(len(violations), 1)
        self.assertIn("src/app.py", violations[0])
        self.assertIn("forbidden_writes", violations[0])

    def test_new_tests_policy_allows_new_test_path(self) -> None:
        meta = {
            "allowed_writes": ["new_tests"],
            "forbidden_writes": [],
        }
        state = {"feature_name": "demo"}

        violations = policy.write_policy_violations(
            _policy_context(meta, ["tests/test_app.py"]),
            state,
            "01_develop",
        )

        self.assertEqual(violations, [])


class PolicyItemMatchesMatrixSelfTests(unittest.TestCase):
    def test_policy_item_matches_token_and_path_matrix(self) -> None:
        existing = {"tests/test_old.py": "hash-old"}
        cases: list[tuple[str, str, dict[str, str], bool]] = [
            # production_code token: repository-root src/ only, never tests/.
            ("src/app.py", "production_code", {}, True),
            ("src\\nested\\module.py", "production_code", {}, True),
            ("tests/test_app.py", "production_code", {}, False),
            ("docs/readme.md", "production_code", {}, False),
            ("src", "production_code", {}, False),
            # tests token: "tests" itself or anything below tests/.
            ("tests/test_app.py", "tests", {}, True),
            ("tests", "tests", {}, True),
            ("src/tests/helper.py", "tests", {}, False),
            # new_tests: test paths absent from the before snapshot.
            ("tests/test_new.py", "new_tests", {}, True),
            ("tests/test_old.py", "new_tests", existing, False),
            ("src/app.py", "new_tests", {}, False),
            # existing_tests: test paths present in the before snapshot.
            ("tests/test_old.py", "existing_tests", existing, True),
            ("tests/test_new.py", "existing_tests", existing, False),
            ("tests/test_new.py", "existing_tests", {}, False),
            # direct path match: exact file, directory prefix, "none" sentinel.
            ("docs/guide.md", "docs/guide.md", {}, True),
            ("docs/guide.md", "docs", {}, True),
            ("docs/guide.md", "docs/", {}, True),
            ("docs2/guide.md", "docs", {}, False),
            ("docs/guide.md", "none", {}, False),
            ("docs/guide.md", "NONE", {}, False),
            ("docs/guide.md", "", {}, False),
        ]
        for path, item, snapshot, expected in cases:
            with self.subTest(path=path, item=item):
                self.assertIs(policy.policy_item_matches(path, item, snapshot), expected)


class WritePolicyViolationScenarioSelfTests(unittest.TestCase):
    def test_forbidden_writes_wins_over_allowed_writes_when_both_match(self) -> None:
        meta = {
            "allowed_writes": ["src"],
            "forbidden_writes": ["production_code"],
        }
        state = {"feature_name": "demo"}

        violations = policy.write_policy_violations(
            _policy_context(meta, ["src/app.py"]),
            state,
            "01_develop",
        )

        self.assertEqual(len(violations), 1)
        self.assertIn("src/app.py", violations[0])
        self.assertIn("matches forbidden_writes entry 'production_code'", violations[0])

    def test_stage_output_md_and_result_json_are_auto_allowed(self) -> None:
        # write_policy_violations appends the stage output .md AND its
        # .result.json to the allowed list even when allowed_writes is empty.
        # Both are warning-class extensions (.md/.json), so without the
        # auto-allow they would surface as warnings below.
        meta = {"allowed_writes": [], "forbidden_writes": []}
        state = {"feature_name": "demo"}
        changed = [
            ".project/features/demo/01_dev.md",
            ".project/features/demo/01_dev.result.json",
        ]

        violations = policy.write_policy_violations(
            _policy_context(meta, changed),
            state,
            "01_develop",
        )

        self.assertEqual(violations, [])
        self.assertNotIn("write_policy_warnings", state)

    def test_warning_class_file_outside_allowed_warns_without_violation(self) -> None:
        meta = {"allowed_writes": ["tests"], "forbidden_writes": []}
        state = {"feature_name": "demo"}

        violations = policy.write_policy_violations(
            _policy_context(meta, ["pyproject.toml"]),
            state,
            "01_develop",
        )

        self.assertEqual(violations, [])
        entries = state["write_policy_warnings"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["stage"], "01_develop")
        self.assertEqual(len(entries[0]["warnings"]), 1)
        self.assertIn("pyproject.toml", entries[0]["warnings"][0])
        self.assertIn("warning only", entries[0]["warnings"][0])

    def test_non_source_non_warning_path_outside_allowed_is_ignored(self) -> None:
        # NOTE: pins current behavior — a changed path that is neither hard
        # source-policy (src/tests code) nor warning-policy (config/doc class)
        # is silently dropped: no violation and no warning entry is recorded.
        meta = {"allowed_writes": [], "forbidden_writes": []}
        state = {"feature_name": "demo"}

        violations = policy.write_policy_violations(
            _policy_context(meta, ["assets/logo.png"]),
            state,
            "01_develop",
        )

        self.assertEqual(violations, [])
        self.assertNotIn("write_policy_warnings", state)

    def test_harness_internal_run_paths_skipped_except_document_build(self) -> None:
        self.assertTrue(
            policy.is_harness_internal_path(".project/runs/demo/verification/latest.json", "demo")
        )
        self.assertFalse(
            policy.is_harness_internal_path(".project/runs/demo/document_build.py", "demo")
        )
        # document_build.py of a *different* feature stays internal.
        self.assertTrue(
            policy.is_harness_internal_path(".project/runs/other/document_build.py", "demo")
        )

        # A warning-class file under .project/runs/<feature>/ is skipped before
        # any policy matching, while the same file class outside runs/ warns.
        meta = {"allowed_writes": [], "forbidden_writes": []}
        state = {"feature_name": "demo"}
        changed = [".project/runs/demo/notes.md", ".project/notes.md"]

        violations = policy.write_policy_violations(
            _policy_context(meta, changed),
            state,
            "01_develop",
        )

        self.assertEqual(violations, [])
        warnings = state["write_policy_warnings"][0]["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertIn(".project/notes.md", warnings[0])


if __name__ == "__main__":
    unittest.main()
