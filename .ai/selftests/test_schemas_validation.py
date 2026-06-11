"""Selftests for the plan-stage interface schemas artifact (schemas.json).

Unit tests pin the validation rules of ``schemas_validation.py`` (the teeth:
structured signature, constraints as rule objects, no silent emptiness) and the
integration tests prove the workflow wiring: a full-pipeline plan PASS without a
valid schemas.json must block the run before the plan commit.
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
    validate_schemas_data,
    validate_schemas_file,
)
from integration_support import (  # noqa: E402
    fixture_workspace,
    read_json,
    run_pipeline,
)


def valid_symbol() -> dict[str, Any]:
    return {
        "id": "src/services/quote.py::get_quote",
        "kind": "function",
        "change": "new",
        "signature": {
            "name": "get_quote",
            "parameter_order": ["symbol", "at"],
            "parameters": {
                "symbol": {
                    "type": "str",
                    "required": True,
                    "nullable": False,
                    "default": {"kind": "none", "value": None},
                    "constraints": [
                        {"rule": "min_length", "value": 1},
                        {"rule": "regex", "pattern": "^[A-Z][A-Z0-9.-]*$"},
                    ],
                },
                "at": {
                    "type": "datetime",
                    "required": False,
                    "nullable": True,
                    "default": {"kind": "literal", "value": None},
                    "constraints": [
                        {"rule": "timezone", "value": "UTC", "applies_when": "not_null"}
                    ],
                },
            },
            "returns": {
                "type": "Quote",
                "nullable": False,
                "fields": {
                    "price": {
                        "type": "Decimal",
                        "required": True,
                        "nullable": False,
                        "constraints": [
                            {"rule": "min", "value": 0},
                            {"rule": "decimal_places", "value": 2},
                        ],
                    },
                },
                "constraints": [
                    {"rule": "object_schema_closed", "allow_extra_fields": False}
                ],
            },
        },
        "errors": [
            {
                "condition": {"type": "unknown_symbol", "parameter": "symbol"},
                "raises": "UnknownSymbolError",
                "retryable": False,
            },
            {
                "condition": {"type": "provider_network_failure"},
                "raises": "ProviderError",
                "retryable": True,
                "retry_policy": {
                    "max_attempts": 3,
                    "backoff": "exponential",
                    "initial_delay_ms": 200,
                },
            },
        ],
        "invariants": [
            {"rule": "no_persistent_side_effects", "scope": "function_call"}
        ],
        "ambiguity_resolutions": [
            {"topic": "at default", "decision": "at=null means current UTC at call time"}
        ],
    }


def valid_schemas(feature: str = "demo-feature") -> dict[str, Any]:
    return {
        "version": 1,
        "feature": feature,
        "frozen": True,
        "plan_sha": None,
        "specifiable": True,
        "symbols": [valid_symbol()],
        "tree_partition": {
            "impl_writes": ["src/", "tests/unit/"],
            "test_writes": ["tests/acceptance/"],
        },
    }


def joined(errors: list[str]) -> str:
    return "\n".join(errors)


class SchemasDataValidationTests(unittest.TestCase):
    def test_valid_schema_passes(self) -> None:
        self.assertEqual(validate_schemas_data(valid_schemas(), feature="demo-feature"), [])

    def test_parameterless_symbol_passes(self) -> None:
        data = valid_schemas()
        signature = data["symbols"][0]["signature"]
        signature["parameter_order"] = []
        signature["parameters"] = {}
        self.assertEqual(validate_schemas_data(data), [])

    def test_parameter_constraints_as_string_fails(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["parameters"]["symbol"]["constraints"] = (
            "non-empty, upper-case ticker"
        )
        errors = validate_schemas_data(data)
        self.assertTrue(errors)
        self.assertIn("signature.parameters.symbol.constraints", joined(errors))
        self.assertIn("not a string", joined(errors))

    def test_parameter_order_mismatch_fails(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["parameter_order"] = ["symbol"]
        errors = validate_schemas_data(data)
        self.assertIn("parameter_order", joined(errors))
        self.assertIn("at", joined(errors))

    def test_parameter_order_duplicate_names_fail(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["parameter_order"] = ["symbol", "symbol", "at"]
        errors = validate_schemas_data(data)
        self.assertIn("duplicate names", joined(errors))

    def test_return_field_constraints_empty_array_fails(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["returns"]["fields"]["price"]["constraints"] = []
        errors = validate_schemas_data(data)
        self.assertIn("signature.returns.fields.price.constraints", joined(errors))
        self.assertIn("non-empty", joined(errors))

    def test_returns_constraints_missing_fails(self) -> None:
        data = valid_schemas()
        del data["symbols"][0]["signature"]["returns"]["constraints"]
        errors = validate_schemas_data(data)
        self.assertIn("signature.returns.constraints", joined(errors))
        self.assertIn("missing", joined(errors))

    def test_unconstrained_rule_none_requires_description(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["returns"]["constraints"] = [{"rule": "none"}]
        errors = validate_schemas_data(data)
        self.assertIn("requires a non-empty 'description'", joined(errors))

        data["symbols"][0]["signature"]["returns"]["constraints"] = [
            {"rule": "none", "description": "opaque passthrough payload"}
        ]
        self.assertEqual(validate_schemas_data(data), [])

    def test_empty_symbols_with_specifiable_true_fails(self) -> None:
        data = valid_schemas()
        data["symbols"] = []
        errors = validate_schemas_data(data)
        self.assertIn("symbols", joined(errors))
        self.assertIn("specifiable:false", joined(errors))

    def test_duplicate_symbol_id_fails(self) -> None:
        data = valid_schemas()
        data["symbols"].append(valid_symbol())
        errors = validate_schemas_data(data)
        self.assertIn("duplicates symbols[0]", joined(errors))

    def test_kind_and_change_enums_enforced(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["kind"] = "functions"
        data["symbols"][0]["change"] = "create"
        errors = validate_schemas_data(data)
        self.assertIn("kind: must be one of", joined(errors))
        self.assertIn("change: must be one of", joined(errors))

    def test_required_true_conflicts_with_literal_default(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["parameters"]["symbol"]["default"] = {
            "kind": "literal",
            "value": "AAPL",
        }
        errors = validate_schemas_data(data)
        self.assertIn("required:true conflicts with default.kind 'literal'", joined(errors))

    def test_required_false_conflicts_with_none_default(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["parameters"]["at"]["default"] = {
            "kind": "none",
            "value": None,
        }
        errors = validate_schemas_data(data)
        self.assertIn("required:false conflicts with default.kind 'none'", joined(errors))

    def test_retryable_true_requires_retry_policy(self) -> None:
        data = valid_schemas()
        del data["symbols"][0]["errors"][1]["retry_policy"]
        errors = validate_schemas_data(data)
        self.assertIn("retry_policy: required when retryable is true", joined(errors))

    def test_retryable_true_requires_positive_max_attempts(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["errors"][1]["retry_policy"]["max_attempts"] = 0
        errors = validate_schemas_data(data)
        self.assertIn("max_attempts: must be an integer >= 1", joined(errors))

    def test_missing_errors_invariants_ambiguity_fields_fail(self) -> None:
        data = valid_schemas()
        symbol = data["symbols"][0]
        del symbol["errors"]
        del symbol["invariants"]
        del symbol["ambiguity_resolutions"]
        errors = validate_schemas_data(data)
        self.assertIn("errors: field is required", joined(errors))
        self.assertIn("invariants: field is required", joined(errors))
        self.assertIn("ambiguity_resolutions: field is required", joined(errors))

    def test_empty_errors_invariants_ambiguity_arrays_pass(self) -> None:
        data = valid_schemas()
        symbol = data["symbols"][0]
        symbol["errors"] = []
        symbol["invariants"] = []
        symbol["ambiguity_resolutions"] = []
        self.assertEqual(validate_schemas_data(data), [])

    def test_delete_symbol_only_needs_signature_name(self) -> None:
        data = valid_schemas()
        data["symbols"].append(
            {
                "id": "src/services/quote.py::legacy_quote",
                "kind": "function",
                "change": "delete",
                "signature": {"name": "legacy_quote"},
            }
        )
        self.assertEqual(validate_schemas_data(data), [])

    def test_id_without_path_separator_fails(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["id"] = "get_quote"
        errors = validate_schemas_data(data)
        self.assertIn("'<path>::<symbol>' form", joined(errors))

    def test_specifiable_false_with_reason_minimal_passes(self) -> None:
        data = {
            "version": 1,
            "feature": "demo-feature",
            "specifiable": False,
            "specifiability_reason": "exploratory spike; interfaces emerge during implementation",
        }
        self.assertEqual(validate_schemas_data(data, feature="demo-feature"), [])

    def test_specifiable_false_without_reason_fails(self) -> None:
        data = {"version": 1, "feature": "demo-feature", "specifiable": False}
        errors = validate_schemas_data(data)
        self.assertIn("specifiability_reason: required", joined(errors))

    def test_version_must_be_one(self) -> None:
        data = valid_schemas()
        data["version"] = 2
        errors = validate_schemas_data(data)
        self.assertIn("version: must be 1", joined(errors))

    def test_feature_mismatch_fails(self) -> None:
        errors = validate_schemas_data(valid_schemas("demo-feature"), feature="other-feature")
        self.assertIn("must match the run feature 'other-feature'", joined(errors))

    def test_tree_partition_shape_enforced_when_present(self) -> None:
        data = valid_schemas()
        data["tree_partition"] = {"impl_writes": ["src/"]}
        errors = validate_schemas_data(data)
        self.assertIn("tree_partition.test_writes", joined(errors))

    def test_non_object_top_level_fails(self) -> None:
        errors = validate_schemas_data(["not", "an", "object"])
        self.assertIn("top-level value must be a JSON object", joined(errors))


class SchemasFileValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="schemas-validation-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_file_reports_missing_artifact(self) -> None:
        error = validate_schemas_file(self.root / "schemas.json", feature="demo-feature")
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("Missing schemas artifact", error)

    def test_invalid_json_reports_parse_error(self) -> None:
        path = self.write("schemas.json", "{ this is not valid json\n")
        error = validate_schemas_file(path)
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("not valid JSON", error)

    def test_valid_file_passes(self) -> None:
        path = self.write(
            "schemas.json", json.dumps(valid_schemas(), ensure_ascii=False, indent=2)
        )
        self.assertIsNone(validate_schemas_file(path, feature="demo-feature"))

    def test_bom_tolerated(self) -> None:
        payload = json.dumps(valid_schemas(), ensure_ascii=False)
        path = self.root / "schemas.json"
        path.write_text(payload, encoding="utf-8-sig")
        self.assertIsNone(validate_schemas_file(path, feature="demo-feature"))

    def test_error_message_uses_display_path_and_lists_fields(self) -> None:
        data = valid_schemas()
        data["symbols"][0]["signature"]["parameters"]["symbol"]["constraints"] = []
        path = self.write("schemas.json", json.dumps(data, ensure_ascii=False))
        error = validate_schemas_file(
            path, feature="demo-feature", display_path=".project/features/demo-feature/schemas.json"
        )
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn(".project/features/demo-feature/schemas.json", error)
        self.assertIn("signature.parameters.symbol.constraints", error)


def blocked_reason(state: dict[str, object]) -> str:
    blocked = state.get("blocked")
    if not isinstance(blocked, dict):
        return ""
    return str(blocked.get("reason") or "")


class SchemasIntegrationTests(unittest.TestCase):
    """Full-pipeline runs with the deterministic fake provider (no real agents)."""

    def test_full_pipeline_writes_valid_schemas_and_completes(self) -> None:
        feature = "selftest-schemas-happy"
        with fixture_workspace() as fixture_root:
            proc = run_pipeline(
                fixture_root,
                pipeline_mode="full",
                feature=feature,
                command_timeout=180,
            )
            state = read_json(fixture_root / ".project" / "runs" / feature / "run.json")
            self.assertEqual(state["status"], "complete", proc.stdout + proc.stderr)

            schemas_path = (
                fixture_root / ".project" / "features" / feature / "schemas.json"
            )
            self.assertTrue(schemas_path.exists(), "plan stage must leave schemas.json")
            self.assertIsNone(validate_schemas_file(schemas_path, feature=feature))

    def test_full_pipeline_blocks_when_plan_omits_schemas(self) -> None:
        feature = "selftest-schemas-missing"
        with fixture_workspace() as fixture_root:
            run_pipeline(
                fixture_root,
                pipeline_mode="full",
                feature=feature,
                mode="schemas-missing",
                command_timeout=180,
                check=False,
            )
            state = read_json(fixture_root / ".project" / "runs" / feature / "run.json")
            self.assertEqual(state["status"], "blocked")
            blocked = state.get("blocked")
            self.assertIsInstance(blocked, dict)
            assert isinstance(blocked, dict)
            self.assertEqual(blocked.get("stage"), "01_plan")
            self.assertIn("Missing schemas artifact", blocked_reason(state))


if __name__ == "__main__":
    unittest.main()
