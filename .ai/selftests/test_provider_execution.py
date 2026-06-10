"""Unit tests for the provider-execution control logic in harness_core/stage_runtime.py.

This is the operationally critical part of the harness: when a provider is spawned
to run a stage, stage_runtime decides when to kill it (timeout), how to tear it
down cleanly (terminate -> kill escalation), and whether to salvage stable stage
artifacts and stop early. Previously only the JSON-parsing/heartbeat helpers were
unit-tested; the kill/timeout/teardown logic was exercised only indirectly.

The real polling loop spawns a subprocess and reads ``time.time()`` / ``proc.poll()``
directly, so these tests drive the *extracted* control helpers with a fake process
object and a recording context -- no real subprocess, no real clock, no real
waiting. The timeout path that would otherwise block for ``timeout_seconds`` is
proven in microseconds.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import stage_runtime  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402
from harness_core.status import RunStatus  # noqa: E402


class FakeProc:
    """Minimal stand-in for subprocess.Popen that records teardown calls."""

    def __init__(
        self,
        *,
        poll_value: int | None = None,
        returncode: int = 0,
        wait_timeout_raises: bool = False,
    ) -> None:
        self._poll_value = poll_value
        self.returncode = returncode
        self._wait_timeout_raises = wait_timeout_raises
        self.terminate_called = False
        self.kill_called = False
        self.wait_calls: list[float | None] = []

    def poll(self) -> int | None:
        return self._poll_value

    def terminate(self) -> None:
        self.terminate_called = True

    def kill(self) -> None:
        self.kill_called = True

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if timeout is not None and self._wait_timeout_raises:
            raise subprocess.TimeoutExpired(cmd="provider", timeout=timeout)
        return self.returncode


def make_recording_ctx(root: Path) -> tuple[HarnessContext, dict[str, list[Any]]]:
    """A lightweight ctx wiring just the members the teardown helpers touch.

    Unset members resolve to None via HarnessContext.__getattr__, so we only
    supply what the timeout/salvage code actually calls. Records every handoff /
    log_event / save_state so tests can assert the side effects.
    """
    records: dict[str, list[Any]] = {"handoffs": [], "events": [], "saves": []}

    def rel(path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(root).as_posix()
        except ValueError:
            return str(path)

    ctx = HarnessContext(
        ROOT=root,
        PIPELINE_MODE="standard",
        DEFAULT_PERFORMANCE="balanced",
        rel=rel,
        normalize_performance=lambda performance: performance or "balanced",
        write_handoff=lambda state, reason, **kw: records["handoffs"].append((reason, kw)),
        log_event=lambda state, event, message, **fields: records["events"].append(
            (event, message, fields)
        ),
        save_state=lambda state: records["saves"].append(dict(state)),
    )
    return ctx, records


class StopProviderTeardownTests(unittest.TestCase):
    def test_already_exited_returns_code_without_terminate(self) -> None:
        proc = FakeProc(poll_value=0, returncode=0)
        result = stage_runtime.stop_provider_after_artifact_completion(proc)
        self.assertEqual(result, 0)
        self.assertFalse(proc.terminate_called)
        self.assertFalse(proc.kill_called)

    def test_running_terminates_gracefully(self) -> None:
        proc = FakeProc(poll_value=None, returncode=143)
        result = stage_runtime.stop_provider_after_artifact_completion(proc)
        self.assertEqual(result, 143)
        self.assertTrue(proc.terminate_called)
        self.assertFalse(proc.kill_called)
        # graceful path waits once, with the 5s grace timeout
        self.assertEqual(proc.wait_calls, [5])

    def test_running_escalates_to_kill_on_timeout(self) -> None:
        proc = FakeProc(poll_value=None, returncode=137, wait_timeout_raises=True)
        result = stage_runtime.stop_provider_after_artifact_completion(proc)
        self.assertEqual(result, 137)
        self.assertTrue(proc.terminate_called)
        self.assertTrue(proc.kill_called)
        # first the graceful 5s wait (raises), then an unbounded wait after kill
        self.assertEqual(proc.wait_calls, [5, None])


class HandleProviderTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.stdout = self.root / "stage.out.txt"
        self.stderr = self.root / "stage.err.txt"
        self.cli_log = self.root / "stage.cli.log"
        self.stdout.write_text("building...\nstill working\n", encoding="utf-8")
        self.stderr.write_text("warn: slow\n", encoding="utf-8")
        self.cli_log.write_text("", encoding="utf-8")

    def test_timeout_kills_proc_and_blocks_run(self) -> None:
        ctx, records = make_recording_ctx(self.root)
        proc = FakeProc(poll_value=None, returncode=137)
        state: dict[str, Any] = {
            "feature_name": "demo",
            "current_stage": "01_develop",
            "pipeline_mode": "standard",
            "performance": "balanced",
        }

        out = stage_runtime._handle_provider_timeout(
            ctx,
            state,
            proc,
            stage="01_develop",
            provider="codex",
            timeout_seconds=42,
            started=time.time(),
            stdout_path=self.stdout,
            stderr_path=self.stderr,
            cli_log_path=self.cli_log,
        )

        # process was force-killed and reaped
        self.assertTrue(proc.kill_called)
        self.assertIn(None, proc.wait_calls)
        # run is blocked with a timeout reason
        self.assertIs(out, state)
        self.assertEqual(state["status"], RunStatus.BLOCKED)
        self.assertEqual(state["blocked"]["stage"], "01_develop")
        self.assertIn("timed out after 42 seconds", state["blocked"]["reason"])
        # a retry command was suggested
        self.assertIn("retry", state["blocked"]["retry_command"])
        # side effects recorded
        self.assertEqual(len(records["handoffs"]), 1)
        self.assertEqual(len(records["saves"]), 1)
        events = [event for event, _msg, _fields in records["events"]]
        self.assertIn("provider_failed", events)

    def test_timeout_event_carries_log_tails(self) -> None:
        ctx, records = make_recording_ctx(self.root)
        proc = FakeProc(poll_value=None, returncode=137)
        state = {"feature_name": "demo", "current_stage": "01_develop", "pipeline_mode": "standard"}

        stage_runtime._handle_provider_timeout(
            ctx,
            state,
            proc,
            stage="01_develop",
            provider="codex",
            timeout_seconds=10,
            started=time.time(),
            stdout_path=self.stdout,
            stderr_path=self.stderr,
            cli_log_path=self.cli_log,
        )

        failed = next(fields for event, _msg, fields in records["events"] if event == "provider_failed")
        # tails are surfaced into the failure event for operator triage
        self.assertIn("stdout_tail", failed)
        self.assertIn("still working", failed["stdout_tail"])
        self.assertIn("stderr_tail", failed)


class ArtifactSignatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.ctx, _ = make_recording_ctx(self.root)

    def test_signature_is_none_when_any_path_missing(self) -> None:
        present = self.root / "a.txt"
        present.write_text("hi", encoding="utf-8")
        missing = self.root / "gone.txt"
        self.assertIsNone(stage_runtime.stage_artifact_signature(self.ctx, [present, missing]))

    def test_signature_captures_each_existing_path(self) -> None:
        a = self.root / "a.txt"
        b = self.root / "b.txt"
        a.write_text("hello", encoding="utf-8")
        b.write_text("world!!", encoding="utf-8")
        signature = stage_runtime.stage_artifact_signature(self.ctx, [a, b])
        self.assertIsNotNone(signature)
        assert signature is not None  # for type-narrowing in the asserts below
        self.assertEqual(len(signature), 2)
        sizes = {rel: size for rel, size, _mtime in signature}
        self.assertEqual(sizes["a.txt"], 5)
        self.assertEqual(sizes["b.txt"], 7)

    def test_signature_changes_when_content_grows(self) -> None:
        a = self.root / "a.txt"
        a.write_text("hi", encoding="utf-8")
        first = stage_runtime.stage_artifact_signature(self.ctx, [a])
        a.write_text("hi there, much longer now", encoding="utf-8")
        second = stage_runtime.stage_artifact_signature(self.ctx, [a])
        self.assertNotEqual(first, second)


class GitHeadChangedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = HarnessContext()

    def test_distinct_heads_detected(self) -> None:
        self.assertTrue(stage_runtime.git_head_changed(self.ctx, "aaa", "bbb"))

    def test_same_head_is_unchanged(self) -> None:
        self.assertFalse(stage_runtime.git_head_changed(self.ctx, "aaa", "aaa"))

    def test_empty_heads_are_unchanged(self) -> None:
        self.assertFalse(stage_runtime.git_head_changed(self.ctx, "", "bbb"))
        self.assertFalse(stage_runtime.git_head_changed(self.ctx, "aaa", ""))


if __name__ == "__main__":
    unittest.main()
