from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

from integration_support import (
    announce,
    fixture_env,
    fixture_workspace,
    read_json,
    run,
    run_pipeline,
)

FEATURE = "selftest-demo"


def run_xv_pipeline(fixture_root: Path, *, mode: str | None = None, check: bool = True) -> Any:
    return run_pipeline(
        fixture_root,
        pipeline_mode="full",
        feature=FEATURE,
        mode=mode,
        max_steps=40,
        command_timeout=420,
        timeout_seconds=60,
        check=check,
        extra_args=["--cross-validation"],
    )


def load_state(fixture_root: Path) -> dict[str, Any]:
    return read_json(fixture_root / ".project" / "runs" / FEATURE / "run.json")


def load_decisions(fixture_root: Path) -> list[dict[str, Any]]:
    path = fixture_root / ".project" / "history" / "xv_decisions.json"
    if not path.exists():
        return []
    parsed = read_json(path)
    records = parsed.get("records")
    return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []


def decision_verdicts(fixture_root: Path) -> list[str]:
    return [str(item.get("verdict")) for item in load_decisions(fixture_root)]


class CrossValidationCleanPathTest(unittest.TestCase):
    def test_full_pipeline_with_cross_validation_converges_clean(self) -> None:
        announce("cross-validation: happy path (CLEAN on first join)")
        with fixture_workspace() as fixture_root:
            run_xv_pipeline(fixture_root)

            state = load_state(fixture_root)
            self.assertEqual(state.get("status"), "complete")
            self.assertEqual(int(state.get("xv_rounds_used", -1)), 0)
            xv_summary = state.get("xv") or {}
            self.assertEqual(xv_summary.get("last_verdict"), "CLEAN")
            tier_summary = xv_summary.get("tier_summary") or {}
            self.assertEqual(tier_summary.get("t1_python"), 1)

            # The blind acceptance tests landed in the impl tree and were
            # committed by the harness (the verify stage commit sweeps them).
            acceptance = fixture_root / "tests" / "acceptance" / "test_xv.py"
            self.assertTrue(acceptance.exists())
            tracked = run(
                ["git", "ls-files", "tests/acceptance/test_xv.py"], fixture_root
            ).stdout.strip()
            self.assertTrue(tracked, "acceptance tests must be committed after CLEAN")

            # CLEAN promotes the suite into the project verification config.
            project_config = read_json(fixture_root / ".project" / "harness.config.json")
            commands = project_config.get("verification", {}).get("commands", [])
            names = {str(item.get("name")) for item in commands if isinstance(item, dict)}
            self.assertIn("acceptance-tests", names)  # slugified by promotion

            # Invisible aftermath: the blind clone is gone, the decision record
            # (with its tier label) stays.
            self.assertFalse((fixture_root / ".project" / "runs" / FEATURE / "blind").exists())
            self.assertIn("CLEAN", decision_verdicts(fixture_root))

            # The blind track's intermediate artifacts stay run-internal.
            track = read_json(fixture_root / ".project" / "runs" / FEATURE / "xv" / "track.json")
            self.assertEqual(track.get("status"), "frozen")


class CrossValidationImplFaultTest(unittest.TestCase):
    def test_impl_fault_routes_to_fix_and_converges(self) -> None:
        announce("cross-validation: impl fault -> arbiter -> fix re-entry -> CLEAN")
        with fixture_workspace() as fixture_root:
            run_xv_pipeline(fixture_root, mode="xv-impl-bug")

            state = load_state(fixture_root)
            self.assertEqual(state.get("status"), "complete")
            self.assertEqual(int(state.get("xv_rounds_used", -1)), 1)
            verdicts = decision_verdicts(fixture_root)
            self.assertIn("CONFLICT-IMPL", verdicts)
            self.assertIn("CLEAN", verdicts)

            # The schema-violating implementation was actually repaired.
            app_text = (fixture_root / "src" / "app.py").read_text(encoding="utf-8")
            self.assertNotIn("broken", app_text)

            # The xv re-entry must not consume the verify/fix retry budget
            # (only the normal pre-join verify failure does).
            self.assertEqual(int(state.get("verify_fix_retries_used", -1)), 1)

            # Round blindness: the fix prompt carried names + assertion
            # messages, never the test body.
            verify_result = read_json(
                fixture_root / ".project" / "features" / FEATURE / "05_verify.result.json"
            )
            events = state.get("events") or []
            self.assertTrue(any(e.get("event") == "xv_fix_reentry" for e in events))
            self.assertTrue(any(e.get("event") == "xv_routed_fix" for e in events))
            self.assertEqual(verify_result.get("status"), "PASS")  # final verify attempt


class CrossValidationTestFaultTest(unittest.TestCase):
    def test_overspecified_test_is_rewritten_blind(self) -> None:
        announce("cross-validation: test fault -> blind rewrite -> CLEAN")
        with fixture_workspace() as fixture_root:
            run_xv_pipeline(fixture_root, mode="xv-test-overspec")

            state = load_state(fixture_root)
            self.assertEqual(state.get("status"), "complete")
            self.assertEqual(int(state.get("xv_rounds_used", -1)), 1)
            verdicts = decision_verdicts(fixture_root)
            self.assertIn("CONFLICT-TEST", verdicts)
            self.assertIn("CLEAN", verdicts)

            acceptance = (
                fixture_root / "tests" / "acceptance" / "test_xv.py"
            ).read_text(encoding="utf-8")
            self.assertNotIn("test_answer_overspecified", acceptance)
            self.assertIn("test_answer_enum", acceptance)

            # The implementation was never touched by the test-fault round.
            events = state.get("events") or []
            self.assertTrue(any(e.get("event") == "xv_routed_test_rewrite" for e in events))
            self.assertFalse(any(e.get("event") == "xv_fix_reentry" for e in events))


class CrossValidationSpecAmbiguityTest(unittest.TestCase):
    def test_spec_ambiguity_quarantines_then_human_override_completes(self) -> None:
        announce("cross-validation: spec ambiguity -> quarantine -> human override")
        with fixture_workspace() as fixture_root:
            run_xv_pipeline(fixture_root, mode="xv-spec-ambiguous")

            state = load_state(fixture_root)
            self.assertEqual(state.get("status"), "blocked")
            blocked = state.get("blocked") or {}
            reason = str(blocked.get("reason") or "")
            self.assertTrue(reason.startswith("XV-QUARANTINE"), reason)
            # The highest-value output: the ambiguous clause is named.
            self.assertIn("spec_ambiguous", reason)
            self.assertIn("schemas.json", reason)
            self.assertIn("SPEC-AMBIGUOUS", decision_verdicts(fixture_root))
            self.assertEqual(int(state.get("xv_rounds_used", -1)), 0)

            # approve = explicit human override (INV-7: never a silent pass).
            run(
                [
                    sys.executable,
                    ".ai/harness.py",
                    "approve",
                    FEATURE,
                    "--auto",
                    "--yes",
                    "--defaults",
                    "--max-steps",
                    "40",
                ],
                fixture_root,
                timeout=420,
                env=fixture_env("xv-spec-ambiguous"),
            )
            state = load_state(fixture_root)
            self.assertEqual(state.get("status"), "complete")
            verdicts = decision_verdicts(fixture_root)
            self.assertIn("OVERRIDE", verdicts)
            records = load_decisions(fixture_root)
            override = next(r for r in records if r.get("verdict") == "OVERRIDE")
            self.assertTrue(override.get("human_override"))


class CrossValidationPartitionTest(unittest.TestCase):
    def test_impl_track_writing_acceptance_is_blocked(self) -> None:
        announce("cross-validation: impl track writing tests/acceptance is blocked")
        with fixture_workspace() as fixture_root:
            # Reuse the generic write-policy-violation lever: have the impl
            # side create an acceptance file during develop by planting it via
            # a custom mode? Simpler: simulate the partition check directly by
            # running a normal xv pipeline, then asserting the guard exists in
            # the develop stage's view. Cheapest deterministic check: a file
            # planted before the develop stage must trip the partition guard.
            proc = run(
                [
                    sys.executable,
                    ".ai/harness.py",
                    "run",
                    "partition probe",
                    "--feature",
                    FEATURE,
                    "--yes",
                    "--defaults",
                    "--timeout",
                    "60",
                    "--max-steps",
                    "6",
                    "--max-verify-fix-retries",
                    "2",
                    "--performance",
                    "lite",
                    "--cross-validation",
                ],
                fixture_root,
                timeout=420,
                env=fixture_env("xv-impl-writes-acceptance"),
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            state = load_state(fixture_root)
            self.assertEqual(state.get("status"), "blocked")
            blocked = state.get("blocked") or {}
            self.assertIn("blind acceptance track", str(blocked.get("reason") or ""))


if __name__ == "__main__":
    unittest.main()
