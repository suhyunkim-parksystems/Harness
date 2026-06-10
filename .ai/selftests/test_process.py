"""Unit tests for harness_core/process.py.

process.py is the bottom of the trust boundary: the harness owns git commits, and
every commit/HEAD/changed-path query goes through these thin wrappers. They take
an explicit repo ``root`` (no module state), so we exercise them against a *real*
throwaway git repository -- the point is to prove the wrappers behave against the
actual git binary, not a fake. A small set of real-git tests is enough; the
integration suite already drives these transitively under load.

Skips loudly if git is not on PATH. On Windows, .git holds read-only pack files
that block plain rmtree, so cleanup goes through an onerror chmod handler.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import ensure_ai_path

ensure_ai_path()

from harness_core import process  # noqa: E402

GIT = shutil.which("git")


def _force_rmtree(path: str) -> None:
    def on_error(func, p, _exc):  # noqa: ANN001
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=on_error)


@unittest.skipUnless(GIT, "git not installed; process.py wrappers need the real git binary")
class ProcessGitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(_force_rmtree, str(self.root))
        # Deterministic, isolated repo (no global identity/signing leakage).
        process.git(self.root, ["init", "-q"])
        process.git(self.root, ["config", "user.email", "harness@test.local"])
        process.git(self.root, ["config", "user.name", "Harness Test"])
        process.git(self.root, ["config", "commit.gpgsign", "false"])

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _commit(self, rel: str, text: str, message: str) -> str:
        self._write(rel, text)
        process.git_add(self.root, [rel])
        return process.git_commit(self.root, message)

    def test_commit_returns_resolved_head(self) -> None:
        head = self._commit("a.txt", "hello", "first")
        self.assertEqual(head, process.git_head(self.root))
        self.assertRegex(head, r"^[0-9a-f]{40}$")

    def test_head_advances_between_commits(self) -> None:
        first = self._commit("a.txt", "one", "c1")
        second = self._commit("b.txt", "two", "c2")
        self.assertNotEqual(first, second)

    def test_changed_paths_collapses_untracked_dir(self) -> None:
        self._commit("seed.txt", "seed", "seed")
        self._write("z.txt", "z")
        self._write("dir/a.txt", "a")
        self._write("dir/b.txt", "b")
        changed = process.git_changed_paths(self.root)
        # git porcelain collapses a wholly-untracked dir to "dir/"; result is
        # forward-slash normalized, deduped, and sorted.
        self.assertEqual(changed, ["dir/", "z.txt"])

    def test_changed_paths_lists_tracked_nested_file_modification(self) -> None:
        self._commit("dir/a.txt", "a", "seed nested")
        self._write("dir/a.txt", "a-modified")
        changed = process.git_changed_paths(self.root)
        # a tracked nested file reports per-file with a forward slash
        self.assertEqual(changed, ["dir/a.txt"])

    def test_changed_paths_empty_on_clean_tree(self) -> None:
        self._commit("a.txt", "hello", "first")
        self.assertEqual(process.git_changed_paths(self.root), [])

    def test_git_add_noop_on_empty_list(self) -> None:
        self._commit("a.txt", "hello", "first")
        # Should not raise and should not change the tree.
        process.git_add(self.root, [])
        self.assertEqual(process.git_changed_paths(self.root), [])

    def test_commit_amend_keeps_message_and_changes_hash(self) -> None:
        original = self._commit("a.txt", "hello", "original message")
        self._write("a.txt", "hello world")
        process.git_add(self.root, ["a.txt"])
        amended = process.git_commit(self.root, "ignored on amend", amend=True)
        self.assertNotEqual(original, amended)
        self.assertEqual(amended, process.git_head(self.root))
        subject = process.git_output(self.root, ["log", "-1", "--pretty=%s"])
        self.assertEqual(subject, "original message")

    def test_check_true_raises_on_failure(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            process.git(self.root, ["rev-parse", "does-not-exist"], check=True)

    def test_check_false_returns_nonzero(self) -> None:
        proc = process.git(self.root, ["rev-parse", "does-not-exist"], check=False)
        self.assertNotEqual(proc.returncode, 0)

    # --- run-per-branch primitives ---------------------------------------- #
    def test_current_branch_reports_active_branch(self) -> None:
        self._commit("a.txt", "hello", "first")
        branch = process.current_branch(self.root)
        self.assertTrue(branch)
        self.assertNotEqual(branch, "HEAD")

    def test_branch_exists_and_checkout_new_branch(self) -> None:
        self._commit("a.txt", "hello", "first")
        self.assertFalse(process.branch_exists(self.root, "run/x"))
        process.checkout_new_branch(self.root, "run/x")
        self.assertTrue(process.branch_exists(self.root, "run/x"))
        self.assertEqual(process.current_branch(self.root), "run/x")

    def test_checkout_new_branch_keeps_head_sha(self) -> None:
        head = self._commit("a.txt", "hello", "first")
        process.checkout_new_branch(self.root, "run/x")
        # Branching off the current HEAD must not move HEAD, so the harness's
        # provider HEAD-change guard never misfires on branch creation.
        self.assertEqual(process.git_head(self.root), head)

    def test_branch_is_merged_tracks_integration(self) -> None:
        self._commit("a.txt", "hello", "first")
        base = process.current_branch(self.root)
        process.checkout_new_branch(self.root, "run/x")
        self._commit("b.txt", "feature", "feature work")
        # Not yet merged: the run branch tip is not contained in base.
        self.assertFalse(process.branch_is_merged(self.root, "run/x", base))
        process.git(self.root, ["checkout", base])
        process.git(self.root, ["merge", "--no-ff", "run/x", "-m", "merge"])
        # After merging, the run branch tip is an ancestor of base.
        self.assertTrue(process.branch_is_merged(self.root, "run/x", base))

    def test_merge_tree_conflicts_clean(self) -> None:
        self._commit("a.txt", "hello", "first")
        base = process.current_branch(self.root)
        process.checkout_new_branch(self.root, "run/x")
        self._commit("b.txt", "feature", "adds b")
        result = process.merge_tree_conflicts(self.root, base, "run/x")
        # None => git too old to predict; otherwise a non-overlapping merge is clean.
        if result is not None:
            self.assertEqual(result, [])

    def test_merge_tree_conflicts_detects_conflict(self) -> None:
        self._commit("a.txt", "common\n", "seed")
        base = process.current_branch(self.root)
        self._commit("a.txt", "base-change\n", "base edit")
        # Branch from the seed (before the base edit) and edit a.txt differently.
        process.git(self.root, ["checkout", "-b", "run/x", "HEAD~1"])
        self._commit("a.txt", "branch-change\n", "branch edit")
        result = process.merge_tree_conflicts(self.root, base, "run/x")
        if result is not None:
            self.assertIn("a.txt", result)


if __name__ == "__main__":
    unittest.main()
