"""Selftests for the cleanup_run path-traversal guard (audit finding C1).

`cleanup <feature>` must only ever remove a direct child of the runs/features
directories. Before the fix, the slug was unvalidated and the root guard was
inverted (it permitted resolved == root), so `cleanup ..` deleted .project and
`cleanup ../..` deleted the whole repository.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402
from harness_core.errors import HarnessError  # noqa: E402


class CleanupGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cleanup-guard-"))
        self._orig = {
            name: getattr(harness, name)
            for name in ("ROOT", "PROJECT_DIR", "RUNS_DIR", "FEATURES_DIR")
        }
        harness.ROOT = self.tmp
        harness.PROJECT_DIR = self.tmp / ".project"
        harness.RUNS_DIR = harness.PROJECT_DIR / "runs"
        harness.FEATURES_DIR = harness.PROJECT_DIR / "features"
        harness.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        harness.FEATURES_DIR.mkdir(parents=True, exist_ok=True)
        # A canary file at the repo root that must survive every rejected call.
        (self.tmp / "canary.txt").write_text("keep me", encoding="utf-8")

    def tearDown(self) -> None:
        for name, value in self._orig.items():
            setattr(harness, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_traversal_to_project_is_rejected(self) -> None:
        with self.assertRaises(HarnessError):
            harness.cleanup_run("..")
        self.assertTrue(harness.PROJECT_DIR.exists())

    def test_traversal_to_root_is_rejected(self) -> None:
        with self.assertRaises(HarnessError):
            harness.cleanup_run("../..")
        self.assertTrue((self.tmp / "canary.txt").exists())

    def test_absolute_path_is_rejected(self) -> None:
        with self.assertRaises(HarnessError):
            harness.cleanup_run(str(self.tmp))
        self.assertTrue((self.tmp / "canary.txt").exists())

    def test_nested_slug_is_rejected(self) -> None:
        with self.assertRaises(HarnessError):
            harness.cleanup_run("foo/bar")

    def test_valid_feature_is_removed(self) -> None:
        feature = "demo-feature"
        run_d = harness.RUNS_DIR / feature
        feat_d = harness.FEATURES_DIR / feature
        run_d.mkdir(parents=True)
        feat_d.mkdir(parents=True)
        (run_d / "run.json").write_text("{}", encoding="utf-8")
        (feat_d / "00_spec.md").write_text("x", encoding="utf-8")

        harness.cleanup_run(feature)

        self.assertFalse(run_d.exists())
        self.assertFalse(feat_d.exists())
        # The parent directories themselves must remain.
        self.assertTrue(harness.RUNS_DIR.exists())
        self.assertTrue(harness.FEATURES_DIR.exists())

    def test_keep_feature_preserves_feature_dir(self) -> None:
        feature = "demo-feature"
        run_d = harness.RUNS_DIR / feature
        feat_d = harness.FEATURES_DIR / feature
        run_d.mkdir(parents=True)
        feat_d.mkdir(parents=True)

        harness.cleanup_run(feature, keep_feature=True)

        self.assertFalse(run_d.exists())
        self.assertTrue(feat_d.exists())


if __name__ == "__main__":
    unittest.main()
