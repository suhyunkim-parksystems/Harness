"""Unit tests for harness_core/json_io.py.

Covers BOM-tolerant JSON reading, the documented failure modes (invalid JSON
raises ``json.JSONDecodeError`` from the strict readers, while ``read_json_file``
swallows it and returns the default), atomic ``write_json_file`` (round-trip plus
no leftover ``.tmp`` sibling), and the Windows-oriented ``replace_with_retry``
loop. The retry tests monkeypatch ``os``/``time`` in the json_io module
namespace so no real sleeping or global patching occurs.
"""
from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from support import ensure_ai_path

ensure_ai_path()

from harness_core import json_io  # noqa: E402

UTF8_BOM = "﻿"


class _FlakyReplace:
    """Callable standing in for os.replace that fails N times, then succeeds."""

    def __init__(self, failures: int, on_success=None) -> None:
        self.failures = failures
        self.calls = 0
        self.on_success = on_success

    def __call__(self, source, target) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise PermissionError("transiently locked by antivirus/indexer")
        if self.on_success is not None:
            self.on_success(source, target)


class JsonTextTests(unittest.TestCase):
    def test_loads_json_text_plain(self) -> None:
        self.assertEqual(json_io.loads_json_text('{"a": 1}'), {"a": 1})

    def test_loads_json_text_strips_utf8_bom(self) -> None:
        self.assertEqual(json_io.loads_json_text(UTF8_BOM + '{"a": 1}'), {"a": 1})

    def test_loads_json_text_invalid_raises_json_decode_error(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            json_io.loads_json_text("{not json")


class JsonFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_read_json_value_file_accepts_utf8_bom(self) -> None:
        path = self.root / "bom.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"k": "v"}).encode("utf-8"))
        self.assertEqual(json_io.read_json_value_file(path), {"k": "v"})

    def test_read_json_value_file_without_bom(self) -> None:
        path = self.root / "plain.json"
        path.write_text('[1, 2, 3]', encoding="utf-8")
        self.assertEqual(json_io.read_json_value_file(path), [1, 2, 3])

    def test_read_json_value_file_invalid_raises_json_decode_error(self) -> None:
        path = self.root / "broken.json"
        path.write_text("{oops", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            json_io.read_json_value_file(path)

    def test_write_json_file_round_trips_and_leaves_no_tmp_sibling(self) -> None:
        path = self.root / "out.json"
        value = {"name": "검증", "items": [1, 2], "ok": True}
        json_io.write_json_file(path, value)
        self.assertEqual(json_io.read_json_value_file(path), value)
        # Atomic write goes through "<name>.tmp"; success must clean it up.
        self.assertFalse((self.root / "out.json.tmp").exists())
        self.assertEqual([p.name for p in self.root.iterdir()], ["out.json"])
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        self.assertIn("검증", text)  # ensure_ascii=False keeps non-ASCII readable

    def test_write_json_file_creates_parent_directories(self) -> None:
        path = self.root / "nested" / "deeper" / "out.json"
        json_io.write_json_file(path, {"x": 1})
        self.assertEqual(json_io.read_json_value_file(path), {"x": 1})

    def test_read_json_file_missing_returns_default(self) -> None:
        sentinel = {"default": True}
        self.assertIs(json_io.read_json_file(self.root / "missing.json", sentinel), sentinel)

    def test_read_json_file_invalid_json_returns_default(self) -> None:
        path = self.root / "bad.json"
        path.write_text("not json at all", encoding="utf-8")
        self.assertEqual(json_io.read_json_file(path, "fallback"), "fallback")

    def test_read_json_file_valid_returns_value(self) -> None:
        path = self.root / "ok.json"
        path.write_text('{"v": 7}', encoding="utf-8")
        self.assertEqual(json_io.read_json_file(path, None), {"v": 7})


class ReplaceWithRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "src.tmp"
        self.target = self.root / "dst.json"
        self.source.write_text('{"v": 1}', encoding="utf-8")

    def _patches(self, replace, sleeps: list[float]):
        fake_os = types.SimpleNamespace(replace=replace)
        fake_time = types.SimpleNamespace(sleep=sleeps.append)
        return (
            mock.patch.object(json_io, "os", fake_os),
            mock.patch.object(json_io, "time", fake_time),
        )

    def test_succeeds_after_transient_permission_errors(self) -> None:
        real_replace = json_io.os.replace
        flaky = _FlakyReplace(failures=3, on_success=real_replace)
        sleeps: list[float] = []
        patch_os, patch_time = self._patches(flaky, sleeps)
        with patch_os, patch_time:
            json_io.replace_with_retry(self.source, self.target)
        self.assertEqual(flaky.calls, 4)  # 3 failures + 1 success
        self.assertEqual(sleeps, [0.05, 0.1, 0.2])  # exponential backoff, no real sleep
        self.assertTrue(self.target.exists())
        self.assertFalse(self.source.exists())
        self.assertEqual(self.target.read_text(encoding="utf-8"), '{"v": 1}')

    def test_raises_after_exhausting_attempts(self) -> None:
        flaky = _FlakyReplace(failures=10_000)
        sleeps: list[float] = []
        patch_os, patch_time = self._patches(flaky, sleeps)
        with patch_os, patch_time:
            with self.assertRaises(PermissionError):
                json_io.replace_with_retry(self.source, self.target, attempts=4)
        self.assertEqual(flaky.calls, 4)
        # No sleep after the final failing attempt.
        self.assertEqual(len(sleeps), 3)

    def test_backoff_delay_is_capped(self) -> None:
        flaky = _FlakyReplace(failures=10_000)
        sleeps: list[float] = []
        patch_os, patch_time = self._patches(flaky, sleeps)
        with patch_os, patch_time:
            with self.assertRaises(PermissionError):
                json_io.replace_with_retry(self.source, self.target, attempts=8)
        # 0.05 doubles each retry but never exceeds 0.5.
        self.assertEqual(sleeps, [0.05, 0.1, 0.2, 0.4, 0.5, 0.5, 0.5])


if __name__ == "__main__":
    unittest.main()
