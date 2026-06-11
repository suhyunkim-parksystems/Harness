from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import cross_validation as xv  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402
from harness_core.errors import HarnessError  # noqa: E402


def make_schemas(**overrides: Any) -> dict[str, Any]:
    schemas: dict[str, Any] = {
        "version": 1,
        "feature": "demo",
        "specifiable": True,
        "symbols": [
            {
                "id": "src/app.py::answer",
                "kind": "function",
                "change": "new",
                "signature": {
                    "name": "answer",
                    "parameter_order": [],
                    "parameters": {},
                    "returns": {"type": "str", "nullable": False, "fields": {}, "constraints": []},
                },
                "errors": [],
                "invariants": [],
                "ambiguity_resolutions": [],
            }
        ],
    }
    schemas.update(overrides)
    return schemas


def make_cases(symbol_id: str = "src/app.py::answer", count: int = 3) -> list[dict[str, Any]]:
    classes = ["normal", "boundary", "violation"]
    return [
        {
            "id": f"case-{index}",
            "symbol_id": symbol_id,
            "target": {"type": "constraint", "ref": "returns"},
            "input_class": classes[index % 3],
            "citation": f"clause-{index}",
            "description": "d",
            "expected": "e",
        }
        for index in range(count)
    ]


class BackendResolutionTests(unittest.TestCase):
    def test_python_symbol_is_t1(self) -> None:
        tiers, problems = xv.resolve_backends(make_schemas())
        self.assertEqual(problems, [])
        self.assertEqual(tiers, {"src/app.py::answer": "t1-python"})

    def test_endpoint_is_t2(self) -> None:
        schemas = make_schemas()
        schemas["symbols"][0]["kind"] = "endpoint"
        schemas["symbols"][0]["id"] = "src/api.py::GET /quote"
        tiers, problems = xv.resolve_backends(schemas)
        self.assertEqual(problems, [])
        self.assertEqual(list(tiers.values()), ["t2-blackbox"])

    def test_non_python_symbol_is_unresolvable(self) -> None:
        schemas = make_schemas()
        schemas["symbols"][0]["id"] = "src/App.cs::Answer"
        tiers, problems = xv.resolve_backends(schemas)
        self.assertEqual(tiers, {})
        self.assertEqual(len(problems), 1)
        self.assertIn("no v1 backend", problems[0])

    def test_path_traversal_is_refused(self) -> None:
        schemas = make_schemas()
        schemas["symbols"][0]["id"] = "../../evil.py::boom"
        tiers, problems = xv.resolve_backends(schemas)
        self.assertEqual(tiers, {})
        self.assertTrue(any("escapes the repository root" in item for item in problems))

    def test_delete_symbols_are_exempt(self) -> None:
        schemas = make_schemas()
        schemas["symbols"][0]["change"] = "delete"
        schemas["symbols"][0]["id"] = "src/Old.cs::Gone"
        tiers, problems = xv.resolve_backends(schemas)
        self.assertEqual(tiers, {})
        self.assertEqual(problems, [])


class StubGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_creates_stub_for_missing_file(self) -> None:
        schemas = make_schemas()
        tiers, _ = xv.resolve_backends(schemas)
        created = xv.generate_stubs(self.root, schemas, tiers)
        self.assertEqual(created, ["src/app.py"])
        text = (self.root / "src" / "app.py").read_text(encoding="utf-8")
        self.assertIn("def answer():", text)
        self.assertIn("NotImplementedError", text)
        compiled = compile(text, "app.py", "exec")
        self.assertIsNotNone(compiled)

    def test_skips_existing_symbol_and_appends_missing(self) -> None:
        target = self.root / "src" / "app.py"
        target.parent.mkdir(parents=True)
        target.write_text("def answer():\n    return 'real'\n", encoding="utf-8")
        schemas = make_schemas()
        schemas["symbols"].append(
            {
                "id": "src/app.py::helper",
                "kind": "function",
                "change": "new",
                "signature": {
                    "name": "helper",
                    "parameter_order": ["value"],
                    "parameters": {"value": {"required": True}},
                    "returns": {},
                },
            }
        )
        tiers, _ = xv.resolve_backends(schemas)
        created = xv.generate_stubs(self.root, schemas, tiers)
        self.assertEqual(created, ["src/app.py"])
        text = target.read_text(encoding="utf-8")
        self.assertIn("return 'real'", text)  # the existing symbol is untouched
        self.assertEqual(text.count("def answer"), 1)
        self.assertIn("def helper(value):", text)

    def test_class_and_method_stubs_are_importable(self) -> None:
        schemas = make_schemas()
        schemas["symbols"] = [
            {
                "id": "src/svc.py::Quote",
                "kind": "class",
                "change": "new",
                "signature": {
                    "name": "Quote",
                    "parameter_order": ["symbol"],
                    "parameters": {"symbol": {"required": True}},
                    "returns": {},
                },
            },
            {
                "id": "src/svc.py::Quote.fetch",
                "kind": "method",
                "change": "new",
                "signature": {
                    "name": "Quote.fetch",
                    "parameter_order": ["at"],
                    "parameters": {"at": {"required": False}},
                    "returns": {},
                },
            },
        ]
        tiers, _ = xv.resolve_backends(schemas)
        xv.generate_stubs(self.root, schemas, tiers)
        text = (self.root / "src" / "svc.py").read_text(encoding="utf-8")
        namespace: dict[str, Any] = {}
        exec(compile(text, "svc.py", "exec"), namespace)  # noqa: S102 - selftest fixture
        quote_cls = namespace["Quote"]
        self.assertTrue(callable(getattr(quote_cls, "fetch")))
        with self.assertRaises(NotImplementedError):
            quote_cls("AAPL")


class ManifestValidationTests(unittest.TestCase):
    def test_valid_manifest_passes(self) -> None:
        manifest = {"cases": make_cases()}
        self.assertEqual(xv.validate_manifest(manifest, make_schemas()), [])

    def test_duplicate_pairs_do_not_count(self) -> None:
        cases = make_cases()
        for case in cases:
            case["citation"] = "same-clause"
            case["input_class"] = "normal"
        errors = xv.validate_manifest({"cases": cases}, make_schemas())
        self.assertTrue(any("unique (citation, input_class)" in item for item in errors))

    def test_unknown_symbol_fails(self) -> None:
        cases = make_cases(symbol_id="src/ghost.py::nope")
        errors = xv.validate_manifest({"cases": cases}, make_schemas())
        self.assertTrue(any("unknown symbol" in item for item in errors))

    def test_declared_error_needs_three_pairs(self) -> None:
        schemas = make_schemas()
        schemas["symbols"][0]["errors"] = [
            {"condition": {"type": "bad"}, "raises": "BadInput", "retryable": False}
        ]
        manifest = {"cases": make_cases()}
        errors = xv.validate_manifest(manifest, schemas)
        self.assertTrue(any("error 'BadInput'" in item for item in errors))
        # Add three uniquely-cited error cases targeting the declared error.
        for index in range(3):
            manifest["cases"].append(
                {
                    "id": f"err-{index}",
                    "symbol_id": "src/app.py::answer",
                    "target": {"type": "error", "ref": "BadInput"},
                    "input_class": ["normal", "boundary", "violation"][index],
                    "citation": f"error-clause-{index}",
                    "description": "d",
                    "expected": "raises BadInput",
                }
            )
        self.assertEqual(xv.validate_manifest(manifest, schemas), [])

    def test_missing_input_class_fails(self) -> None:
        cases = make_cases()
        cases[0]["input_class"] = "weird"
        errors = xv.validate_manifest({"cases": cases}, make_schemas())
        self.assertTrue(any("input_class" in item for item in errors))


class MarkerScanTests(unittest.TestCase):
    def test_markers_found_in_docstrings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_file = root / "test_a.py"
            test_file.write_text(
                'def test_one():\n    """XV-CASE: case-1"""\n    assert True\n\n'
                "# XV-CASE: case-2 (comment form also counts)\n",
                encoding="utf-8",
            )
            found = xv.scan_case_markers(root)
        self.assertEqual(found, {"case-1", "case-2"})


class JunitLeakFilterTests(unittest.TestCase):
    def test_failures_carry_name_and_message_only(self) -> None:
        xml = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest">
  <testcase classname="tests.acceptance.test_xv" name="test_enum">
    <failure message="AssertionError: assert 'broken' in {'fixed', 'needs-fix'}">def test_enum():
    SECRET TEST BODY LINE
    assert answer() in {"fixed", "needs-fix"}</failure>
  </testcase>
  <testcase classname="tests.acceptance.test_xv" name="test_ok"/>
</testsuite></testsuites>
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "junit.xml"
            path.write_text(xml, encoding="utf-8")
            failures = xv._parse_junit_failures(path)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["test"], "tests.acceptance.test_xv::test_enum")
        self.assertIn("assert 'broken'", failures[0]["message"])
        # Round blindness: the body of the test never reaches the impl fix.
        self.assertNotIn("SECRET TEST BODY LINE", failures[0]["message"])


def make_assignment_ctx(schedule_develop: str = "claude") -> Any:
    policy = {
        "code_write_allowed": ["claude", "codex"],
        "code_write_denied": ["agy"],
        "code_write_order": ["claude", "codex"],
    }
    capabilities = {
        "claude": {"code_write", "plan", "review"},
        "codex": {"code_write", "plan", "review"},
        "agy": {"plan", "review", "verify"},
    }
    return HarnessContext.from_namespace(
        {
            "DEVELOP_STAGE": "02_develop",
            "model_policy": lambda: policy,
            "available_providers": lambda: ["claude", "codex", "agy"],
            "provider_capabilities": lambda provider: capabilities[provider],
        }
    )


class AssignmentTests(unittest.TestCase):
    def test_assignments_use_three_distinct_providers(self) -> None:
        ctx = make_assignment_ctx()
        state = {"provider_schedule": {"02_develop": "claude"}}
        assignments = xv.assert_ready(ctx, state)
        self.assertEqual(assignments["develop"], "claude")
        self.assertEqual(assignments["author"], "codex")
        self.assertEqual(assignments["arbiter"], "agy")
        self.assertEqual(assignments["design"], "agy")

    def test_missing_third_provider_is_refused(self) -> None:
        policy = {
            "code_write_allowed": ["claude", "codex"],
            "code_write_denied": [],
            "code_write_order": ["claude", "codex"],
        }
        ctx = HarnessContext.from_namespace(
            {
                "DEVELOP_STAGE": "02_develop",
                "model_policy": lambda: policy,
                "available_providers": lambda: ["claude", "codex"],
                "provider_capabilities": lambda provider: {"code_write"},
            }
        )
        state = {"provider_schedule": {"02_develop": "claude"}}
        with self.assertRaises(HarnessError):
            xv.assert_ready(ctx, state)


class PartitionTests(unittest.TestCase):
    def _ctx(self, changed: list[str], root: Path | None = None) -> Any:
        return HarnessContext.from_namespace(
            {
                "PLAN_STAGE": "01_plan",
                "START_STAGE": "00_specify",
                "ROOT": root or Path("."),
                "filtered_changed_paths": lambda state, stage: changed,
            }
        )

    def test_disabled_flag_reports_nothing(self) -> None:
        ctx = self._ctx(["tests/acceptance/test_x.py"])
        self.assertEqual(xv.partition_violations(ctx, {}, "02_develop"), [])

    def test_impl_stage_writing_acceptance_is_violation(self) -> None:
        ctx = self._ctx(["src/app.py", "tests/acceptance/test_x.py"])
        state = {"cross_validation": True}
        violations = xv.partition_violations(ctx, state, "02_develop")
        self.assertEqual(len(violations), 1)
        self.assertIn("tests/acceptance/test_x.py", violations[0])
        self.assertIn("blind acceptance track", violations[0])

    def test_harness_copied_files_are_exempt(self) -> None:
        ctx = self._ctx(["tests/acceptance/test_x.py"])
        state = {
            "cross_validation": True,
            "xv_copied_files": ["tests/acceptance/test_x.py"],
        }
        self.assertEqual(xv.partition_violations(ctx, state, "06_document"), [])

    def test_collapsed_untracked_tests_dir_is_expanded(self) -> None:
        # git status collapses a wholly-untracked tree to "tests/"; the guard
        # must still see the acceptance file hiding underneath.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rogue = root / "tests" / "acceptance" / "test_rogue.py"
            rogue.parent.mkdir(parents=True)
            rogue.write_text("def test_rogue():\n    assert True\n", encoding="utf-8")
            ctx = self._ctx(["tests/"], root=root)
            state = {"cross_validation": True}
            violations = xv.partition_violations(ctx, state, "02_develop")
        self.assertEqual(len(violations), 1)
        self.assertIn("tests/acceptance/test_rogue.py", violations[0])


class CopyFrozenAcceptanceBoundaryTests(unittest.TestCase):
    """_copy_frozen_acceptance merges the blind track's frozen tests into the
    impl tree. A pre-existing foreign file at a destination is a boundary
    conflict; files xv itself copied earlier are freely overwritten/removed."""

    def _setup(self, tmp: Path) -> tuple[HarnessContext, Path, Path]:
        root = tmp / "repo"
        run_dir = root / ".project" / "runs" / "demo"
        frozen = run_dir / "xv" / "frozen" / "tests" / "acceptance"
        frozen.mkdir(parents=True)
        root.joinpath("tests").mkdir(parents=True, exist_ok=True)
        ctx = HarnessContext.from_namespace({
            "ROOT": root,
            "run_dir": lambda feature: root / ".project" / "runs" / feature,
        })
        return ctx, root, frozen

    def test_foreign_preexisting_file_is_conflict_and_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ctx, root, frozen = self._setup(Path(raw))
            (frozen / "test_a.py").write_text("frozen version\n", encoding="utf-8")
            target = root / "tests" / "acceptance" / "test_a.py"
            target.parent.mkdir(parents=True)
            target.write_text("impl wrote this first\n", encoding="utf-8")
            state = {"feature_name": "demo"}

            copied, conflicts = xv._copy_frozen_acceptance(ctx, state)

            self.assertEqual(conflicts, ["tests/acceptance/test_a.py"])
            self.assertEqual(copied, [])
            self.assertEqual(
                target.read_text(encoding="utf-8"), "impl wrote this first\n"
            )
            self.assertEqual(state["xv_copied_files"], [])

    def test_identical_preexisting_file_copies_without_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ctx, root, frozen = self._setup(Path(raw))
            (frozen / "test_a.py").write_text("same content\n", encoding="utf-8")
            target = root / "tests" / "acceptance" / "test_a.py"
            target.parent.mkdir(parents=True)
            target.write_text("same content\n", encoding="utf-8")
            state = {"feature_name": "demo"}

            copied, conflicts = xv._copy_frozen_acceptance(ctx, state)

            self.assertEqual(conflicts, [])
            self.assertEqual(copied, ["tests/acceptance/test_a.py"])
            self.assertEqual(state["xv_copied_files"], ["tests/acceptance/test_a.py"])

    def test_previously_copied_file_is_freely_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ctx, root, frozen = self._setup(Path(raw))
            (frozen / "test_a.py").write_text("rewrite round 2\n", encoding="utf-8")
            target = root / "tests" / "acceptance" / "test_a.py"
            target.parent.mkdir(parents=True)
            target.write_text("round 1 content\n", encoding="utf-8")
            state = {
                "feature_name": "demo",
                "xv_copied_files": ["tests/acceptance/test_a.py"],
            }

            copied, conflicts = xv._copy_frozen_acceptance(ctx, state)

            self.assertEqual(conflicts, [])
            self.assertEqual(copied, ["tests/acceptance/test_a.py"])
            self.assertEqual(target.read_text(encoding="utf-8"), "rewrite round 2\n")

    def test_file_removed_from_frozen_set_is_unlinked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ctx, root, frozen = self._setup(Path(raw))
            (frozen / "test_keep.py").write_text("kept\n", encoding="utf-8")
            stale = root / "tests" / "acceptance" / "test_dropped.py"
            stale.parent.mkdir(parents=True)
            stale.write_text("copied in an earlier round\n", encoding="utf-8")
            state = {
                "feature_name": "demo",
                "xv_copied_files": ["tests/acceptance/test_dropped.py"],
            }

            copied, conflicts = xv._copy_frozen_acceptance(ctx, state)

            self.assertEqual(conflicts, [])
            self.assertEqual(copied, ["tests/acceptance/test_keep.py"])
            self.assertFalse(stale.exists())
            self.assertEqual(state["xv_copied_files"], ["tests/acceptance/test_keep.py"])


if __name__ == "__main__":
    unittest.main()
