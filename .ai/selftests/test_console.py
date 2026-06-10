"""Unit tests for harness_core/console.py.

console.py is a pure presentation leaf (colour codes, event/status styling, human
duration/byte formatting). It has no runtime-state dependency, so the tests call
its functions directly. Colour output depends on TTY/NO_COLOR detection, which we
pin deterministically by patching ``console.color_enabled`` rather than relying on
the test environment's terminal.
"""
from __future__ import annotations

import unittest
from unittest import mock

from support import ensure_ai_path

ensure_ai_path()

from harness_core import console  # noqa: E402
from harness_core.status import RunStatus  # noqa: E402


class FormatDurationTests(unittest.TestCase):
    def test_minutes_seconds(self) -> None:
        self.assertEqual(console.format_duration(0), "00:00")
        self.assertEqual(console.format_duration(59), "00:59")
        self.assertEqual(console.format_duration(60), "01:00")
        self.assertEqual(console.format_duration(125), "02:05")

    def test_promotes_to_hours(self) -> None:
        self.assertEqual(console.format_duration(3600), "01:00:00")
        self.assertEqual(console.format_duration(3661), "01:01:01")

    def test_negative_and_fractional_clamp(self) -> None:
        self.assertEqual(console.format_duration(-5), "00:00")
        # fractional seconds truncate toward the lower whole second
        self.assertEqual(console.format_duration(90.9), "01:30")


class FormatBytesTests(unittest.TestCase):
    def test_bytes_unit(self) -> None:
        self.assertEqual(console.format_bytes(0), "0 B")
        self.assertEqual(console.format_bytes(1023), "1023 B")

    def test_kilobytes_unit(self) -> None:
        self.assertEqual(console.format_bytes(1024), "1.0 KB")
        self.assertEqual(console.format_bytes(1536), "1.5 KB")

    def test_megabytes_unit(self) -> None:
        self.assertEqual(console.format_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(console.format_bytes(1024 * 1024 + 512 * 1024), "1.5 MB")


class ColorTextTests(unittest.TestCase):
    def test_disabled_returns_plain_text(self) -> None:
        with mock.patch.object(console, "color_enabled", lambda: False):
            self.assertEqual(console.color_text("hello", "red", "bold"), "hello")

    def test_enabled_wraps_with_ansi_codes(self) -> None:
        with mock.patch.object(console, "color_enabled", lambda: True):
            out = console.color_text("hello", "red", "bold")
        self.assertEqual(out, "\033[31;1mhello\033[0m")

    def test_no_styles_returns_plain_text(self) -> None:
        with mock.patch.object(console, "color_enabled", lambda: True):
            self.assertEqual(console.color_text("hello"), "hello")

    def test_unknown_styles_filtered_out(self) -> None:
        with mock.patch.object(console, "color_enabled", lambda: True):
            # no recognised style -> no codes -> plain text
            self.assertEqual(console.color_text("hello", "chartreuse"), "hello")
            # known style survives, unknown dropped
            self.assertEqual(console.color_text("hi", "green", "nope"), "\033[32mhi\033[0m")


class ColorEnabledTests(unittest.TestCase):
    def test_no_color_env_forces_disabled(self) -> None:
        with mock.patch.dict(console.os.environ, {"NO_COLOR": "1"}, clear=False):
            self.assertFalse(console.color_enabled())

    def test_enabled_when_stdout_is_a_tty(self) -> None:
        fake_stdout = mock.Mock()
        fake_stdout.isatty.return_value = True
        fake_stderr = mock.Mock()
        fake_stderr.isatty.return_value = False
        env = {k: v for k, v in console.os.environ.items() if k != "NO_COLOR"}
        with mock.patch.dict(console.os.environ, env, clear=True), mock.patch.object(
            console.sys, "stdout", fake_stdout
        ), mock.patch.object(console.sys, "stderr", fake_stderr):
            self.assertTrue(console.color_enabled())

    def test_disabled_when_no_tty(self) -> None:
        fake = mock.Mock()
        fake.isatty.return_value = False
        env = {k: v for k, v in console.os.environ.items() if k != "NO_COLOR"}
        with mock.patch.dict(console.os.environ, env, clear=True), mock.patch.object(
            console.sys, "stdout", fake
        ), mock.patch.object(console.sys, "stderr", fake):
            self.assertFalse(console.color_enabled())


class EventLineTests(unittest.TestCase):
    def _wrapped(self, line: str, event: str) -> str:
        with mock.patch.object(console, "color_enabled", lambda: True):
            return console.event_line_for_console(line, event)

    def test_failure_events_are_red_bold(self) -> None:
        self.assertEqual(self._wrapped("x", "stage_blocked"), "\033[31;1mx\033[0m")
        self.assertEqual(self._wrapped("x", "provider_failed"), "\033[31;1mx\033[0m")

    def test_success_events_are_green(self) -> None:
        self.assertEqual(self._wrapped("x", "run_complete"), "\033[32mx\033[0m")
        self.assertEqual(self._wrapped("x", "feature_created"), "\033[32mx\033[0m")

    def test_progress_events_are_cyan(self) -> None:
        self.assertEqual(self._wrapped("x", "provider_started"), "\033[36mx\033[0m")
        self.assertEqual(self._wrapped("x", "auto_step"), "\033[36mx\033[0m")

    def test_warning_events_are_yellow(self) -> None:
        self.assertEqual(self._wrapped("x", "provider_retry"), "\033[33mx\033[0m")
        self.assertEqual(self._wrapped("x", "stage_skipped"), "\033[33mx\033[0m")

    def test_unmatched_event_is_unstyled(self) -> None:
        self.assertEqual(self._wrapped("x", "something_neutral"), "x")


class StatusStyleTests(unittest.TestCase):
    def test_known_statuses(self) -> None:
        self.assertEqual(console.status_style(RunStatus.COMPLETE), ("green", "bold"))
        self.assertEqual(console.status_style(RunStatus.MODEL_COMPLETED), ("green", "bold"))
        self.assertEqual(console.status_style(RunStatus.BLOCKED), ("red", "bold"))
        self.assertEqual(console.status_style(RunStatus.MODEL_RUNNING), ("cyan", "bold"))
        self.assertEqual(console.status_style(RunStatus.WAITING_FOR_MODEL), ("cyan", "bold"))
        self.assertEqual(console.status_style(RunStatus.CREATED), ("yellow", "bold"))

    def test_case_insensitive(self) -> None:
        self.assertEqual(console.status_style(str(RunStatus.COMPLETE).upper()), ("green", "bold"))

    def test_unknown_status_defaults_to_bold(self) -> None:
        self.assertEqual(console.status_style("totally-unknown"), ("bold",))


if __name__ == "__main__":
    unittest.main()
