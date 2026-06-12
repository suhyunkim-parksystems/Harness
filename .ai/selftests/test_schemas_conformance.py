"""Selftests for Phase 2: implementation <-> schemas conformance + drift guard.

Unit tests pin the static conformance rules of ``schemas_validation.py``
(ast-based symbol existence and parameter name/order/count for Python,
token-level checks for other files, endpoint handler existence without
parameter comparison, warnings for declared error types). Integration tests prove the workflow wiring with the deterministic fake
provider: a tampered schemas.json blocks before the tampering stage commits
(INV-3 drift guard), and a schema declaring a symbol the implementation never
creates downgrades verify PASS to FAIL.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core.schemas_validation import (  # noqa: E402
    validate_schemas_conformance,
    validate_schemas_conformance_file,
)
from integration_support import (  # noqa: E402
    fixture_workspace,
    read_json,
    run_pipeline,
)


def symbol(
    symbol_id: str,
    *,
    kind: str = "function",
    change: str = "new",
    parameter_order: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    order = parameter_order or []
    parameters: dict[str, Any] = {}
    for index, name in enumerate(order):
        parameters[name] = {
            "type": "str",
            "required": index == 0,
            "nullable": False,
            "default": (
                {"kind": "none", "value": None}
                if index == 0
                else {"kind": "literal", "value": None}
            ),
            "constraints": [{"rule": "none", "description": "unit fixture"}],
        }
    built: dict[str, Any] = {
        "id": symbol_id,
        "kind": kind,
        "change": change,
        **({"binding": "GET /demo"} if kind == "endpoint" and change != "delete" else {}),
        "signature": {
            "name": symbol_id.rpartition("::")[2],
            "parameter_order": list(order),
            "parameters": parameters,
            "returns": {
                "type": "str",
                "nullable": False,
                "fields": {},
                "constraints": [{"rule": "none", "description": "unit fixture"}],
            },
        },
        "errors": errors if errors is not None else [],
        "invariants": [],
        "ambiguity_resolutions": [],
    }
    if change == "delete":
        built["signature"] = {"name": symbol_id.rpartition("::")[2]}
    return built


def schemas(symbols: list[dict[str, Any]], feature: str = "demo-feature") -> dict[str, Any]:
    return {
        "version": 1,
        "feature": feature,
        "frozen": True,
        "plan_sha": None,
        "specifiable": True,
        "symbols": symbols,
    }


class ConformanceUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="schemas-conformance-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def check(self, data: dict[str, Any]) -> tuple[list[str], list[str]]:
        return validate_schemas_conformance(data, self.root)

    # ------------------------------------------------------------ functions

    def test_matching_function_passes(self) -> None:
        self.write("src/app.py", "def get_quote(symbol, at=None):\n    return symbol\n")
        errors, warnings = self.check(
            schemas([symbol("src/app.py::get_quote", parameter_order=["symbol", "at"])])
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_symbol_fails(self) -> None:
        self.write("src/app.py", "def other():\n    return 1\n")
        errors, _ = self.check(schemas([symbol("src/app.py::get_quote")]))
        self.assertEqual(len(errors), 1)
        self.assertIn("get_quote", errors[0])
        self.assertIn("not found", errors[0])

    def test_missing_file_fails(self) -> None:
        errors, _ = self.check(schemas([symbol("src/nowhere.py::get_quote")]))
        self.assertEqual(len(errors), 1)
        self.assertIn("does not exist", errors[0])

    def test_parameter_name_mismatch_fails(self) -> None:
        self.write("src/app.py", "def get_quote(ticker, at=None):\n    return ticker\n")
        errors, _ = self.check(
            schemas([symbol("src/app.py::get_quote", parameter_order=["symbol", "at"])])
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("parameter mismatch", errors[0])
        self.assertIn("symbol", errors[0])
        self.assertIn("ticker", errors[0])

    def test_parameter_order_mismatch_fails(self) -> None:
        self.write("src/app.py", "def get_quote(at, symbol=None):\n    return symbol\n")
        errors, _ = self.check(
            schemas([symbol("src/app.py::get_quote", parameter_order=["symbol", "at"])])
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("parameter mismatch", errors[0])

    def test_var_args_and_kwonly_are_tolerated(self) -> None:
        self.write(
            "src/app.py",
            "def get_quote(symbol, *extra, at=None, **kw):\n    return symbol\n",
        )
        errors, _ = self.check(
            schemas([symbol("src/app.py::get_quote", parameter_order=["symbol", "at"])])
        )
        self.assertEqual(errors, [])

    def test_symbol_inside_if_guard_is_found(self) -> None:
        self.write(
            "src/app.py",
            "import sys\nif sys.platform == 'win32':\n"
            "    def get_quote(symbol):\n        return symbol\n",
        )
        errors, _ = self.check(
            schemas([symbol("src/app.py::get_quote", parameter_order=["symbol"])])
        )
        self.assertEqual(errors, [])

    def test_unparsable_python_fails(self) -> None:
        self.write("src/app.py", "def broken(:\n")
        errors, _ = self.check(schemas([symbol("src/app.py::broken")]))
        self.assertEqual(len(errors), 1)
        self.assertIn("cannot parse", errors[0])

    # ------------------------------------------------------- methods/classes

    def test_method_drops_self(self) -> None:
        self.write(
            "src/svc.py",
            "class Quote:\n    def fetch(self, symbol):\n        return symbol\n",
        )
        errors, _ = self.check(
            schemas(
                [symbol("src/svc.py::Quote.fetch", kind="method", parameter_order=["symbol"])]
            )
        )
        self.assertEqual(errors, [])

    def test_staticmethod_keeps_first_parameter(self) -> None:
        self.write(
            "src/svc.py",
            "class Quote:\n    @staticmethod\n    def fetch(symbol):\n        return symbol\n",
        )
        errors, _ = self.check(
            schemas(
                [symbol("src/svc.py::Quote.fetch", kind="method", parameter_order=["symbol"])]
            )
        )
        self.assertEqual(errors, [])

    def test_class_constructor_parameters_checked(self) -> None:
        self.write(
            "src/svc.py",
            "class Quote:\n    def __init__(self, symbol, at):\n        self.symbol = symbol\n",
        )
        errors, _ = self.check(
            schemas(
                [symbol("src/svc.py::Quote", kind="class", parameter_order=["symbol", "at"])]
            )
        )
        self.assertEqual(errors, [])

    def test_class_without_init_but_declared_params_fails(self) -> None:
        self.write("src/svc.py", "class Quote:\n    pass\n")
        errors, _ = self.check(
            schemas([symbol("src/svc.py::Quote", kind="class", parameter_order=["symbol"])])
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("no explicit __init__", errors[0])

    def test_dataclass_fields_count_as_constructor(self) -> None:
        self.write(
            "src/svc.py",
            "from dataclasses import dataclass\n\n"
            "@dataclass\nclass Quote:\n    symbol: str\n    at: str\n",
        )
        errors, _ = self.check(
            schemas(
                [symbol("src/svc.py::Quote", kind="class", parameter_order=["symbol", "at"])]
            )
        )
        self.assertEqual(errors, [])

    # ---------------------------------------------------------------- delete

    def test_delete_symbol_still_present_fails(self) -> None:
        self.write("src/app.py", "def legacy():\n    return 1\n")
        errors, _ = self.check(schemas([symbol("src/app.py::legacy", change="delete")]))
        self.assertEqual(len(errors), 1)
        self.assertIn("still", errors[0])

    def test_delete_symbol_absent_passes(self) -> None:
        self.write("src/app.py", "def kept():\n    return 1\n")
        errors, _ = self.check(schemas([symbol("src/app.py::legacy", change="delete")]))
        self.assertEqual(errors, [])

    def test_delete_with_missing_file_passes(self) -> None:
        errors, _ = self.check(schemas([symbol("src/gone.py::legacy", change="delete")]))
        self.assertEqual(errors, [])

    # ----------------------------------------------------- non-python/endpoint

    def test_non_python_token_presence(self) -> None:
        self.write("src/Service.cs", "public static string GetQuote(string symbol) {}\n")
        errors, _ = self.check(schemas([symbol("src/Service.cs::GetQuote")]))
        self.assertEqual(errors, [])

    def test_non_python_token_absence_fails(self) -> None:
        self.write("src/Service.cs", "public static string Other() {}\n")
        errors, _ = self.check(schemas([symbol("src/Service.cs::GetQuote")]))
        self.assertEqual(len(errors), 1)
        self.assertIn("token", errors[0])

    def test_non_python_delete_lingering_token_warns_only(self) -> None:
        self.write("src/Service.cs", "// GetQuote retired\n")
        errors, warnings = self.check(
            schemas([symbol("src/Service.cs::GetQuote", change="delete")])
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("weak signal", warnings[0])

    def test_endpoint_handler_existence_checked(self) -> None:
        errors, _ = self.check(
            schemas([symbol("src/api/routes.py::get_quotes", kind="endpoint")])
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("does not exist", errors[0])

    def test_endpoint_missing_handler_fails(self) -> None:
        self.write("src/api/routes.py", "def other():\n    return 1\n")
        errors, _ = self.check(
            schemas([symbol("src/api/routes.py::get_quotes", kind="endpoint")])
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("get_quotes", errors[0])
        self.assertIn("not found", errors[0])

    def test_endpoint_handler_parameters_not_compared(self) -> None:
        # DI/framework injection makes handler parameters legitimately differ
        # from the declared request schema: existence is the only static check.
        self.write(
            "src/api/routes.py",
            "def get_quotes(request, db, settings=None):\n    return []\n",
        )
        errors, warnings = self.check(
            schemas([symbol("src/api/routes.py::get_quotes", kind="endpoint")])
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_endpoint_delete_still_present_fails(self) -> None:
        self.write("src/api/routes.py", "def legacy_quotes():\n    return []\n")
        errors, _ = self.check(
            schemas(
                [symbol("src/api/routes.py::legacy_quotes", kind="endpoint", change="delete")]
            )
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("still", errors[0])

    def test_path_escape_fails(self) -> None:
        errors, _ = self.check(schemas([symbol("../outside.py::f")]))
        self.assertEqual(len(errors), 1)
        self.assertIn("escapes", errors[0])

    # ------------------------------------------------------------- warnings

    def test_declared_error_type_missing_warns(self) -> None:
        self.write("src/app.py", "def get_quote(symbol):\n    return symbol\n")
        errors, warnings = self.check(
            schemas(
                [
                    symbol(
                        "src/app.py::get_quote",
                        parameter_order=["symbol"],
                        errors=[
                            {
                                "condition": {"type": "unknown_symbol"},
                                "raises": "UnknownSymbolError",
                                "retryable": False,
                            }
                        ],
                    )
                ]
            )
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("UnknownSymbolError", warnings[0])

    def test_declared_error_type_present_no_warning(self) -> None:
        self.write(
            "src/app.py",
            "class UnknownSymbolError(Exception):\n    pass\n\n"
            "def get_quote(symbol):\n    raise UnknownSymbolError(symbol)\n",
        )
        errors, warnings = self.check(
            schemas(
                [
                    symbol(
                        "src/app.py::get_quote",
                        parameter_order=["symbol"],
                        errors=[
                            {
                                "condition": {"type": "unknown_symbol"},
                                "raises": "UnknownSymbolError",
                                "retryable": False,
                            }
                        ],
                    )
                ]
            )
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    # --------------------------------------------------------------- skips

    def test_specifiable_false_skips_all_checks(self) -> None:
        data = {
            "version": 1,
            "feature": "demo-feature",
            "specifiable": False,
            "specifiability_reason": "exploratory",
        }
        errors, warnings = self.check(data)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class ConformanceFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="schemas-conformance-file-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def write_schemas(self, data: dict[str, Any]) -> Path:
        path = self.root / "schemas.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_conforming_file_returns_none(self) -> None:
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "app.py").write_text(
            "def answer():\n    return 'fixed'\n", encoding="utf-8"
        )
        path = self.write_schemas(schemas([symbol("src/app.py::answer")]))
        error, warnings = validate_schemas_conformance_file(
            path, self.root, feature="demo-feature"
        )
        self.assertIsNone(error)
        self.assertEqual(warnings, [])

    def test_nonconforming_file_reports_display_path_and_symbol(self) -> None:
        path = self.write_schemas(schemas([symbol("src/app.py::answer")]))
        error, _ = validate_schemas_conformance_file(
            path,
            self.root,
            feature="demo-feature",
            display_path=".project/features/demo-feature/schemas.json",
        )
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn(".project/features/demo-feature/schemas.json", error)
        self.assertIn("src/app.py", error)

    def test_structurally_invalid_file_reports_structural_errors(self) -> None:
        path = self.write_schemas({"version": 1, "feature": "demo-feature", "symbols": []})
        error, _ = validate_schemas_conformance_file(path, self.root, feature="demo-feature")
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("structurally invalid", error)


def blocked_of(state: dict[str, Any]) -> dict[str, Any]:
    blocked = state.get("blocked")
    return blocked if isinstance(blocked, dict) else {}


def event_names(state: dict[str, Any]) -> list[str]:
    events = state.get("events")
    if not isinstance(events, list):
        return []
    return [str(item.get("event") or "") for item in events if isinstance(item, dict)]


class ConformanceIntegrationTests(unittest.TestCase):
    """Full-pipeline runs with the deterministic fake provider (no real agents)."""

    def test_develop_tampering_with_schemas_blocks_before_commit(self) -> None:
        feature = "selftest-schemas-drift"
        with fixture_workspace() as fixture_root:
            run_pipeline(
                fixture_root,
                pipeline_mode="full",
                feature=feature,
                mode="schemas-drift",
                command_timeout=240,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / feature / "run.json")
            self.assertEqual(state["status"], "blocked")
            blocked = blocked_of(state)
            self.assertEqual(blocked.get("stage"), "02_develop")
            self.assertIn("INV-3", str(blocked.get("reason") or ""))
            commits = state.get("commits") or {}
            self.assertIn("01_plan", commits)
            # The tampered artifact must never enter history via a stage commit.
            self.assertNotIn("02_develop", commits)

    def test_nonconformant_schema_downgrades_verify_until_quarantine(self) -> None:
        feature = "selftest-schemas-nonconf"
        with fixture_workspace() as fixture_root:
            run_pipeline(
                fixture_root,
                pipeline_mode="full",
                feature=feature,
                mode="schemas-nonconformant",
                max_verify_fix_retries=1,
                command_timeout=240,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / feature / "run.json")
            self.assertEqual(state["status"], "blocked")
            blocked = blocked_of(state)
            self.assertEqual(blocked.get("stage"), "05_verify")
            self.assertIn("retry limit", str(blocked.get("reason") or "").lower())
            self.assertIn("schemas_conformance_failed", event_names(state))

            # H3: the conformance verdict must be persisted to the verify
            # result.json (the channel the fix prompt is fed), not just held in
            # memory -- otherwise the fix stage re-enters seeing PASS on disk.
            verify_result = read_json(
                fixture_root / ".project" / "features" / feature / "05_verify.result.json"
            )
            self.assertEqual(verify_result.get("status"), "FAIL")
            fix_inputs = verify_result.get("fix_inputs")
            self.assertIsInstance(fix_inputs, dict)
            assert isinstance(fix_inputs, dict)
            self.assertTrue(fix_inputs.get("authoritative"))
            self.assertTrue(fix_inputs.get("items"))
            self.assertIn(
                "missing_function", " ".join(str(i) for i in fix_inputs["items"])
            )


if __name__ == "__main__":
    unittest.main()
