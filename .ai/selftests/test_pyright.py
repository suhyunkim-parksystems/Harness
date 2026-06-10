"""Standing static-type gate: pyright must report zero errors in harness_core.

The harness treats the LLM worker as untrusted and re-verifies its output; the
harness core should hold itself to the same bar -- so its own dependency surface
(``HarnessRuntime`` in context.py, consumed via ``ctx`` across the core) is
statically checked on every selftest run. This is what makes the typed contract
real rather than documentation: a signature drift between harness.py and a core
module, a typo, or a wrong argument count fails the suite here.

Scope and config come from the ``[tool.pyright]`` table in ``.ai/pyproject.toml``
(``include = ["harness_core"]``). If pyright is not installed the test skips
loudly rather than failing, so the
suite still runs in environments that have not adopted the gate yet; install it
with ``pip install pyright`` to enable enforcement.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from support import ensure_ai_path

AI_DIR = ensure_ai_path()


class PyrightTypeCheckTests(unittest.TestCase):
    def test_harness_core_has_no_type_errors(self) -> None:
        pyright = shutil.which("pyright")
        if not pyright:
            self.skipTest(
                "pyright not installed; run `pip install pyright` to enable the harness_core type-check gate"
            )

        proc = subprocess.run(
            [pyright, "--outputjson"],
            cwd=str(AI_DIR),
            capture_output=True,
            text=True,
        )
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.fail(
                "pyright did not return JSON output.\n"
                f"stdout: {proc.stdout[:1000]}\nstderr: {proc.stderr[:1000]}"
            )

        error_count = report.get("summary", {}).get("errorCount", 0)
        if error_count:
            errors = [
                "{file}:{line} [{rule}] {message}".format(
                    file=Path(diag["file"]).name,
                    line=diag["range"]["start"]["line"] + 1,
                    rule=diag.get("rule", ""),
                    message=diag["message"].splitlines()[0],
                )
                for diag in report.get("generalDiagnostics", [])
                if diag.get("severity") == "error"
            ]
            self.fail(
                f"pyright reported {error_count} error(s) in harness_core:\n" + "\n".join(errors)
            )


if __name__ == "__main__":
    unittest.main()
