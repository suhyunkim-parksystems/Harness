from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402
from harness_core.json_io import read_json_file  # noqa: E402


class StatePersistenceSelfTests(unittest.TestCase):
    """4b-1: save_state must persist run.json atomically.

    A crash, power loss, or disk-full condition during the write must never
    leave a half-written run.json behind (which would make the whole run
    unrecoverable on the next load_state).
    """

    def setUp(self) -> None:
        self._tmp_path = Path(tempfile.mkdtemp(prefix="harness_state_"))
        self._orig_runs_dir = harness.RUNS_DIR
        harness.RUNS_DIR = self._tmp_path
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        harness.RUNS_DIR = self._orig_runs_dir
        shutil.rmtree(self._tmp_path, ignore_errors=True)

    def test_save_state_writes_valid_round_trippable_json(self) -> None:
        state = {
            "feature_name": "demo",
            "current_stage": "00_specify",
            "status": "waiting_for_model",
        }
        harness.save_state(state)

        path = harness.state_path("demo")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["feature_name"], "demo")
        self.assertEqual(loaded["current_stage"], "00_specify")
        self.assertIn("updated_at", loaded)

        # A successful save must not leave any temporary scratch file behind.
        leftovers = list(path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [], f"unexpected temp files: {leftovers}")

    def test_load_state_accepts_utf8_bom(self) -> None:
        state = {
            "feature_name": "demo",
            "current_stage": "00_specify",
            "status": "waiting_for_model",
        }
        path = harness.state_path("demo")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps(state).encode("utf-8"))

        loaded = harness.load_state("demo")

        self.assertEqual(loaded["feature_name"], "demo")
        self.assertEqual(loaded["current_stage"], "00_specify")

    def test_read_json_file_accepts_utf8_bom(self) -> None:
        path = self._tmp_path / "bom.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"ok": True}).encode("utf-8"))

        loaded = read_json_file(path, {})

        self.assertEqual(loaded, {"ok": True})

    def test_save_state_preserves_existing_run_json_on_write_failure(self) -> None:
        # Arrange: a known-good run.json already on disk.
        good = {
            "feature_name": "demo",
            "current_stage": "04_fix",
            "verify_fix_retries_used": 1,
        }
        harness.save_state(good)
        path = harness.state_path("demo")

        # Inject a failure that mimics a partial write followed by a crash:
        # the writer corrupts whatever file it targets, then raises.
        real_write_text = harness.Path.write_text

        def failing_write_text(self_path, data, *args, **kwargs):  # type: ignore[no-untyped-def]
            real_write_text(self_path, "{ corrupted partial", encoding="utf-8")
            raise OSError("simulated write failure")

        harness.Path.write_text = failing_write_text
        try:
            with self.assertRaises(OSError):
                harness.save_state(
                    {
                        "feature_name": "demo",
                        "current_stage": "05_verify",
                        "verify_fix_retries_used": 2,
                    }
                )
        finally:
            harness.Path.write_text = real_write_text

        # The previously-saved run.json must still be intact and loadable.
        self.assertTrue(path.exists())
        recovered = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(recovered["current_stage"], "04_fix")
        self.assertEqual(recovered["verify_fix_retries_used"], 1)

        # A failed save must clean up after itself: no temp scratch file left.
        leftovers = list(path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [], f"unexpected temp files: {leftovers}")


if __name__ == "__main__":
    unittest.main()
