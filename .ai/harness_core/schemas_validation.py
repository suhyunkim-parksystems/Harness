"""Validation for the plan-stage interface schemas artifact (``schemas.json``).

The plan stage of the ``full`` pipeline must produce a frozen, machine-checkable
interface schema for every public/boundary symbol the feature will create or
change. This module enforces the structural rules so an incomplete schema fails
the plan stage with a message pointing at the exact symbol/field that is short.

Phase 2 adds the *conformance* layer: static checks that the implementation
actually matches the frozen schema (symbol existence, parameter names/order),
so the schema cannot rot into a lie after develop/fix.

Pattern follows ``docx_validation.py``: pure functions, no harness imports, a
``str`` error (or ``None``) as the result so the workflow can feed it straight
into ``block_state``.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, TypeGuard

ALLOWED_KINDS = ("function", "class", "method", "endpoint")
ALLOWED_CHANGES = ("new", "modify", "delete")
ALLOWED_DEFAULT_KINDS = ("none", "literal", "computed")
# Explicit "this is deliberately unconstrained" marker. Empty constraint arrays
# are rejected so absence of constraints is always a stated decision, never a
# silent omission.
UNCONSTRAINED_RULE = "none"

SCHEMAS_FILENAME = "schemas.json"


def _is_nonempty_str(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _type_name(value: Any) -> str:
    return type(value).__name__


def validate_schemas_file(
    path: Path, *, feature: str | None = None, display_path: str | None = None
) -> str | None:
    """Validate the schemas artifact at ``path``. Returns an error message or None."""
    shown = display_path or str(path)
    if not path.exists():
        return (
            f"Missing schemas artifact: {shown}. The plan stage must write this file in "
            "every case -- even for exploratory features the file itself is required, "
            "with specifiable:false and a specifiability_reason recorded inside it."
        )
    if not path.is_file():
        return f"Schemas artifact is not a file: {shown}"
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return f"Cannot read schemas artifact {shown}: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"Invalid schemas artifact {shown}: not valid JSON ({exc})"

    errors = validate_schemas_data(data, feature=feature)
    if errors:
        listed = "\n".join(f"- {item}" for item in errors)
        return f"Invalid schemas artifact {shown}:\n{listed}"
    return None


def validate_schemas_data(data: Any, *, feature: str | None = None) -> list[str]:
    """Validate parsed schemas JSON. Returns a list of specific errors (empty if valid)."""
    if not isinstance(data, dict):
        return [f"top-level value must be a JSON object, got {_type_name(data)}"]

    errors: list[str] = []

    version = data.get("version")
    if version != 1:
        errors.append(f"version: must be 1, got {version!r}")

    declared_feature = data.get("feature")
    if not _is_nonempty_str(declared_feature):
        errors.append("feature: must be a non-empty string (the feature slug)")
    elif feature is not None and declared_feature.strip() != feature:
        errors.append(
            f"feature: must match the run feature {feature!r}, got {declared_feature.strip()!r}"
        )

    frozen = data.get("frozen", True)  # missing means frozen (INV-3)
    if not isinstance(frozen, bool):
        errors.append(f"frozen: must be a boolean when present, got {_type_name(frozen)}")

    plan_sha = data.get("plan_sha")
    if plan_sha is not None and not isinstance(plan_sha, str):
        errors.append(f"plan_sha: must be a string or null, got {_type_name(plan_sha)}")

    specifiable = data.get("specifiable", True)
    if not isinstance(specifiable, bool):
        errors.append(f"specifiable: must be a boolean, got {_type_name(specifiable)}")
        specifiable = True

    _validate_tree_partition(errors, data.get("tree_partition"))

    if not specifiable:
        # Best-effort demotion for genuinely exploratory features: symbol-level
        # requirements are waived, but the demotion itself must be justified.
        if not _is_nonempty_str(data.get("specifiability_reason")):
            errors.append(
                "specifiability_reason: required (non-empty) when specifiable is false"
            )
        return errors

    symbols = data.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        errors.append(
            "symbols: must be a non-empty array (if this feature truly has no public/boundary "
            "symbols, set specifiable:false with a specifiability_reason)"
        )
        return errors

    seen_ids: dict[str, int] = {}
    for index, symbol in enumerate(symbols):
        _validate_symbol(errors, index, symbol, seen_ids)
    return errors


def _symbol_label(index: int, symbol: Any) -> str:
    if isinstance(symbol, dict) and _is_nonempty_str(symbol.get("id")):
        return f"symbols[{index}] ({str(symbol.get('id')).strip()})"
    return f"symbols[{index}]"


def _validate_symbol(
    errors: list[str], index: int, symbol: Any, seen_ids: dict[str, int]
) -> None:
    label = _symbol_label(index, symbol)
    if not isinstance(symbol, dict):
        errors.append(f"{label}: must be an object, got {_type_name(symbol)}")
        return

    symbol_id = symbol.get("id")
    if not _is_nonempty_str(symbol_id):
        errors.append(f"{label}: id: must be a non-empty string of the form '<path>::<symbol>'")
    else:
        sid = symbol_id.strip()
        if "::" not in sid:
            errors.append(f"{label}: id: must use the '<path>::<symbol>' form, got {sid!r}")
        if sid in seen_ids:
            errors.append(f"{label}: id: duplicates symbols[{seen_ids[sid]}] ({sid!r})")
        else:
            seen_ids[sid] = index

    kind = symbol.get("kind")
    if kind not in ALLOWED_KINDS:
        errors.append(f"{label}: kind: must be one of {'|'.join(ALLOWED_KINDS)}, got {kind!r}")
    change = symbol.get("change")
    if change not in ALLOWED_CHANGES:
        errors.append(
            f"{label}: change: must be one of {'|'.join(ALLOWED_CHANGES)}, got {change!r}"
        )

    # Endpoints anchor their id to the handler's code coordinate like every
    # other kind; the externally exposed identity (route/command/topic) lives
    # in `binding` so it stays machine-readable for the acceptance track.
    binding = symbol.get("binding")
    if kind == "endpoint" and change != "delete":
        if not _is_nonempty_str(binding):
            errors.append(
                f"{label}: binding: required for endpoint symbols -- the externally exposed "
                "identity as a non-empty string (e.g. 'GET /api/quotes', 'cli: mytool sync', "
                "'topic: orders.created'); the id must be the handler's code coordinate "
                "'<path>::<handler>'"
            )
    elif binding is not None and not _is_nonempty_str(binding):
        errors.append(f"{label}: binding: must be a non-empty string when present")

    signature = symbol.get("signature")
    if not isinstance(signature, dict):
        errors.append(
            f"{label}: signature: must be an object with name/parameter_order/parameters/returns, "
            f"got {_type_name(signature)}"
        )
        return
    if not _is_nonempty_str(signature.get("name")):
        errors.append(f"{label}: signature.name: must be a non-empty string")

    if change == "delete":
        # Deleted symbols only pin the name; describing the full interface of a
        # symbol being removed is waived (same condition as errors/invariants).
        return

    _validate_signature(errors, label, signature)
    _validate_errors_field(errors, label, symbol)
    _validate_invariants(errors, label, symbol)
    _validate_ambiguity_resolutions(errors, label, symbol)


def _validate_signature(errors: list[str], label: str, signature: dict[str, Any]) -> None:
    order = signature.get("parameter_order")
    order_ok = isinstance(order, list) and all(_is_nonempty_str(item) for item in order)
    if not order_ok:
        errors.append(
            f"{label}: signature.parameter_order: must be an array of parameter name strings "
            "(use [] for parameterless symbols)"
        )

    params = signature.get("parameters")
    params_ok = isinstance(params, dict)
    if not params_ok:
        errors.append(
            f"{label}: signature.parameters: must be an object keyed by parameter name "
            "(use {} for parameterless symbols)"
        )

    if order_ok and params_ok and isinstance(order, list) and isinstance(params, dict):
        order_names = [str(item).strip() for item in order]
        duplicates = sorted({name for name in order_names if order_names.count(name) > 1})
        if duplicates:
            errors.append(
                f"{label}: signature.parameter_order: duplicate names: {duplicates}"
            )
        missing = sorted(str(name) for name in params if str(name) not in order_names)
        extra = sorted(name for name in order_names if name not in params)
        if missing:
            errors.append(
                f"{label}: signature.parameter_order: missing names declared in "
                f"signature.parameters: {missing}"
            )
        if extra:
            errors.append(
                f"{label}: signature.parameter_order: lists names absent from "
                f"signature.parameters: {extra}"
            )

    if isinstance(params, dict):
        for name, spec in params.items():
            _validate_parameter(errors, f"{label}: signature.parameters.{name}", spec)

    returns = signature.get("returns")
    if not isinstance(returns, dict):
        errors.append(
            f"{label}: signature.returns: must be an object with type/nullable/fields/constraints, "
            f"got {_type_name(returns)}"
        )
        return
    returns_label = f"{label}: signature.returns"
    if not _is_nonempty_str(returns.get("type")):
        errors.append(f"{returns_label}.type: must be a non-empty string")
    if not isinstance(returns.get("nullable"), bool):
        errors.append(f"{returns_label}.nullable: must be a boolean")
    fields = returns.get("fields")
    if not isinstance(fields, dict):
        errors.append(
            f"{returns_label}.fields: must be an object "
            "(use {} for primitive/scalar return types)"
        )
    else:
        for name, spec in fields.items():
            _validate_return_field(errors, f"{returns_label}.fields.{name}", spec)
    _validate_constraints(
        errors, f"{returns_label}.constraints", returns.get("constraints"),
        present="constraints" in returns,
    )


def _validate_parameter(errors: list[str], label: str, spec: Any) -> None:
    if not isinstance(spec, dict):
        errors.append(
            f"{label}: must be an object with type/required/nullable/default/constraints, "
            f"got {_type_name(spec)}"
        )
        return
    if not _is_nonempty_str(spec.get("type")):
        errors.append(f"{label}.type: must be a non-empty string")
    required = spec.get("required")
    if not isinstance(required, bool):
        errors.append(f"{label}.required: must be a boolean")
    if not isinstance(spec.get("nullable"), bool):
        errors.append(f"{label}.nullable: must be a boolean")

    default = spec.get("default")
    default_kind: str | None = None
    if not isinstance(default, dict):
        errors.append(
            f"{label}.default: must be an object "
            '{"kind": "none|literal|computed", "value": ...}'
        )
    else:
        kind = default.get("kind")
        if kind not in ALLOWED_DEFAULT_KINDS:
            errors.append(
                f"{label}.default.kind: must be one of {'|'.join(ALLOWED_DEFAULT_KINDS)}, "
                f"got {kind!r}"
            )
        else:
            default_kind = str(kind)
        if "value" not in default:
            errors.append(
                f"{label}.default.value: key is required (use null when kind is 'none')"
            )

    if isinstance(required, bool) and default_kind is not None:
        if required and default_kind != "none":
            errors.append(
                f"{label}: required:true conflicts with default.kind {default_kind!r} "
                "(required parameters must use default.kind 'none')"
            )
        if not required and default_kind == "none":
            errors.append(
                f"{label}: required:false conflicts with default.kind 'none' "
                "(optional parameters must declare a 'literal' or 'computed' default)"
            )

    _validate_constraints(
        errors, f"{label}.constraints", spec.get("constraints"),
        present="constraints" in spec,
    )


def _validate_return_field(errors: list[str], label: str, spec: Any) -> None:
    if not isinstance(spec, dict):
        errors.append(
            f"{label}: must be an object with type/required/nullable/constraints, "
            f"got {_type_name(spec)}"
        )
        return
    if not _is_nonempty_str(spec.get("type")):
        errors.append(f"{label}.type: must be a non-empty string")
    if not isinstance(spec.get("required"), bool):
        errors.append(f"{label}.required: must be a boolean")
    if not isinstance(spec.get("nullable"), bool):
        errors.append(f"{label}.nullable: must be a boolean")
    _validate_constraints(
        errors, f"{label}.constraints", spec.get("constraints"),
        present="constraints" in spec,
    )


def _validate_constraints(errors: list[str], label: str, value: Any, *, present: bool) -> None:
    escape_hint = (
        'use [{"rule": "none", "description": "<why unconstrained>"}] '
        "when genuinely unconstrained"
    )
    if not present:
        errors.append(f"{label}: missing -- constraints must be declared ({escape_hint})")
        return
    if isinstance(value, str):
        errors.append(f"{label}: must be an array of rule objects, not a string")
        return
    if not isinstance(value, list) or not value:
        errors.append(
            f"{label}: must be a non-empty array of rule objects ({escape_hint})"
        )
        return
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        if not isinstance(item, dict):
            errors.append(
                f"{item_label}: must be an object with a 'rule' key, got {_type_name(item)}"
            )
            continue
        rule = item.get("rule")
        if not _is_nonempty_str(rule):
            errors.append(f"{item_label}.rule: must be a non-empty string")
            continue
        if rule.strip() == UNCONSTRAINED_RULE and not _is_nonempty_str(item.get("description")):
            errors.append(
                f"{item_label}: rule 'none' requires a non-empty 'description' "
                "explaining why no constraint applies"
            )


def _validate_errors_field(errors: list[str], label: str, symbol: dict[str, Any]) -> None:
    if "errors" not in symbol:
        errors.append(
            f"{label}: errors: field is required (use [] when the symbol raises nothing)"
        )
        return
    value = symbol.get("errors")
    if not isinstance(value, list):
        errors.append(
            f"{label}: errors: must be an array of error objects, got {_type_name(value)}"
        )
        return
    for index, item in enumerate(value):
        item_label = f"{label}: errors[{index}]"
        if not isinstance(item, dict):
            errors.append(
                f"{item_label}: must be an object with condition/raises/retryable, "
                f"got {_type_name(item)}"
            )
            continue
        condition = item.get("condition")
        if not isinstance(condition, dict) or not _is_nonempty_str(condition.get("type")):
            errors.append(f"{item_label}.condition: must be an object with a non-empty 'type'")
        if not _is_nonempty_str(item.get("raises")):
            errors.append(
                f"{item_label}.raises: must be a non-empty string (exception/error type)"
            )
        retryable = item.get("retryable")
        if not isinstance(retryable, bool):
            errors.append(f"{item_label}.retryable: must be a boolean")
        retry_policy = item.get("retry_policy")
        if retryable is True:
            if not isinstance(retry_policy, dict):
                errors.append(f"{item_label}.retry_policy: required when retryable is true")
            else:
                max_attempts = retry_policy.get("max_attempts")
                if (
                    not isinstance(max_attempts, int)
                    or isinstance(max_attempts, bool)
                    or max_attempts < 1
                ):
                    errors.append(
                        f"{item_label}.retry_policy.max_attempts: must be an integer >= 1 "
                        "when retryable is true"
                    )
        elif retry_policy is not None and not isinstance(retry_policy, dict):
            errors.append(f"{item_label}.retry_policy: must be an object when present")


def _validate_invariants(errors: list[str], label: str, symbol: dict[str, Any]) -> None:
    if "invariants" not in symbol:
        errors.append(
            f"{label}: invariants: field is required (use [] when there are none)"
        )
        return
    value = symbol.get("invariants")
    if not isinstance(value, list):
        errors.append(
            f"{label}: invariants: must be an array of rule objects, got {_type_name(value)}"
        )
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not _is_nonempty_str(item.get("rule")):
            errors.append(
                f"{label}: invariants[{index}]: must be an object with a non-empty 'rule'"
            )


def _validate_ambiguity_resolutions(
    errors: list[str], label: str, symbol: dict[str, Any]
) -> None:
    if "ambiguity_resolutions" not in symbol:
        errors.append(
            f"{label}: ambiguity_resolutions: field is required (use [] when the spec left "
            "no ambiguity for this symbol)"
        )
        return
    value = symbol.get("ambiguity_resolutions")
    if not isinstance(value, list):
        errors.append(
            f"{label}: ambiguity_resolutions: must be an array of objects, got {_type_name(value)}"
        )
        return
    for index, item in enumerate(value):
        item_label = f"{label}: ambiguity_resolutions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label}: must be an object with topic/decision")
            continue
        if not _is_nonempty_str(item.get("topic")):
            errors.append(f"{item_label}.topic: must be a non-empty string")
        if not _is_nonempty_str(item.get("decision")):
            errors.append(f"{item_label}.decision: must be a non-empty string")


def _validate_tree_partition(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"tree_partition: must be an object when present, got {_type_name(value)}")
        return
    for key in ("impl_writes", "test_writes"):
        paths = value.get(key)
        if not isinstance(paths, list) or not paths or not all(
            _is_nonempty_str(item) for item in paths
        ):
            errors.append(
                f"tree_partition.{key}: must be a non-empty array of path strings"
            )


# ---------------------------------------------------------------------------
# Phase 2: implementation <-> schemas conformance (static checks)
# ---------------------------------------------------------------------------
#
# Decided depth (UPGRADE_PROGRESS, 2026-06-11): Python files are checked with
# ``ast`` for symbol existence plus parameter names/order/count; declared type
# strings are NOT compared (abstract notation, false-fail risk). Non-Python
# files get a token-presence check only. ``kind: endpoint`` ids anchor the
# handler's code coordinate, so handler existence IS checked; parameter
# comparison is skipped (request parameters legitimately differ from the
# handler signature under DI/framework injection) and the route-level contract
# declared in ``binding`` is owned by acceptance tests. Declared error types
# are a weak static signal and produce non-blocking warnings only --
# acceptance tests own the strong guarantee (Phase 3).

PYTHON_SUFFIXES = (".py", ".pyw")


def validate_schemas_conformance_file(
    path: Path, root: Path, *, feature: str | None = None, display_path: str | None = None
) -> tuple[str | None, list[str]]:
    """Check the implementation under ``root`` against the schemas artifact.

    Returns ``(error, warnings)``: ``error`` is a verify-FAIL message (or None)
    and ``warnings`` are non-blocking notes (e.g. declared error types that do
    not appear in the code).
    """
    shown = display_path or str(path)
    if not path.exists():
        return (f"Missing schemas artifact for conformance check: {shown}", [])
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return (f"Cannot read schemas artifact {shown}: {exc}", [])
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return (f"Invalid schemas artifact {shown}: not valid JSON ({exc})", [])

    structural = validate_schemas_data(data, feature=feature)
    if structural:
        listed = "\n".join(f"- {item}" for item in structural)
        return (
            f"Schemas artifact {shown} is structurally invalid (conformance not checked):\n{listed}",
            [],
        )

    errors, warnings = validate_schemas_conformance(data, root)
    if errors:
        listed = "\n".join(f"- {item}" for item in errors)
        return (f"Implementation does not conform to {shown}:\n{listed}", warnings)
    return (None, warnings)


def validate_schemas_conformance(data: Any, root: Path) -> tuple[list[str], list[str]]:
    """Validate parsed schemas JSON against the code tree. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return errors, warnings
    if data.get("specifiable", True) is False:
        # Best-effort demotion: nothing was pinned, so nothing can drift.
        return errors, warnings
    symbols = data.get("symbols")
    if not isinstance(symbols, list):
        return errors, warnings
    for index, symbol in enumerate(symbols):
        if isinstance(symbol, dict):
            _check_symbol_conformance(errors, warnings, index, symbol, root)
    return errors, warnings


def _resolve_symbol_file(root: Path, raw_path: str) -> Path | None:
    norm = raw_path.replace("\\", "/").strip().strip("/")
    if not norm or ":" in norm:
        return None
    parts = norm.split("/")
    if any(part in ("", "..") for part in parts):
        return None
    return root.joinpath(*parts)


def _check_symbol_conformance(
    errors: list[str], warnings: list[str], index: int, symbol: dict[str, Any], root: Path
) -> None:
    label = _symbol_label(index, symbol)
    symbol_id = str(symbol.get("id") or "")
    if "::" not in symbol_id:
        return  # structural validation already rejected this id
    raw_path, _, symbol_name = symbol_id.partition("::")
    raw_path = raw_path.strip()
    symbol_name = symbol_name.strip()
    kind = symbol.get("kind")
    change = symbol.get("change")

    file_path = _resolve_symbol_file(root, raw_path)
    if file_path is None:
        errors.append(f"{label}: id path escapes the repository root: {raw_path!r}")
        return

    if change == "delete":
        _check_symbol_deleted(errors, warnings, label, symbol_name, raw_path, file_path)
        return

    if not file_path.is_file():
        errors.append(f"{label}: declared file does not exist: {raw_path}")
        return
    try:
        source = file_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        errors.append(f"{label}: cannot read {raw_path}: {exc}")
        return

    if file_path.suffix.lower() in PYTHON_SUFFIXES:
        _check_python_symbol(errors, label, symbol, symbol_name, raw_path, source, kind)
    else:
        _check_token_symbol(errors, label, symbol_name, raw_path, source)
    _warn_missing_error_types(warnings, label, symbol, raw_path, source)


def _python_public_symbols(tree: ast.Module) -> dict[str, ast.AST]:
    """Public/boundary symbols: module top level plus direct class members
    (``Class.method``). if/try wrappers are traversed (TYPE_CHECKING, platform
    guards); function-local definitions are private by definition and skipped."""
    symbols: dict[str, ast.AST] = {}

    def visit(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.setdefault(prefix + node.name, node)
            elif isinstance(node, ast.ClassDef):
                symbols.setdefault(prefix + node.name, node)
                if not prefix:
                    visit(node.body, node.name + ".")
            elif isinstance(node, (ast.If, ast.Try)):
                visit(node.body, prefix)
                for handler in getattr(node, "handlers", []):
                    visit(handler.body, prefix)
                visit(list(getattr(node, "orelse", [])), prefix)
                visit(list(getattr(node, "finalbody", [])), prefix)

    visit(tree.body, "")
    return symbols


def _has_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, name: str) -> bool:
    for decorator in node.decorator_list:
        target: ast.expr = decorator
        if isinstance(target, ast.Call):
            target = target.func
        if isinstance(target, ast.Attribute) and target.attr == name:
            return True
        if isinstance(target, ast.Name) and target.id == name:
            return True
    return False


def _callable_param_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef, *, drop_first: bool
) -> list[str]:
    args = node.args
    names = [item.arg for item in args.posonlyargs] + [item.arg for item in args.args]
    if drop_first and names:
        names = names[1:]
    names += [item.arg for item in args.kwonlyargs]
    return names


def _class_constructor_params(node: ast.ClassDef) -> list[str] | None:
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
            return _callable_param_names(item, drop_first=True)
    if _has_decorator(node, "dataclass"):
        fields: list[str] = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(item.target.id)
        return fields
    return None


def _declared_parameter_order(symbol: dict[str, Any]) -> list[str] | None:
    signature = symbol.get("signature")
    if not isinstance(signature, dict):
        return None
    order = signature.get("parameter_order")
    if not isinstance(order, list):
        return None
    return [str(item).strip() for item in order]


def _check_python_symbol(
    errors: list[str],
    label: str,
    symbol: dict[str, Any],
    symbol_name: str,
    raw_path: str,
    source: str,
    kind: Any,
) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(f"{label}: cannot parse {raw_path} for conformance: {exc}")
        return
    symbols = _python_public_symbols(tree)
    node = symbols.get(symbol_name)
    if node is None:
        errors.append(
            f"{label}: symbol {symbol_name!r} not found in {raw_path} "
            "(searched module top level and direct class members)"
        )
        return

    if kind == "endpoint":
        # Handler existence is the static guarantee; its parameters legitimately
        # differ from the declared request schema (DI/framework injection), and
        # the route-level contract in `binding` is owned by acceptance tests.
        return

    declared = _declared_parameter_order(symbol)
    if declared is None:
        return  # malformed signature is a structural error, reported upstream

    if kind == "class":
        if not isinstance(node, ast.ClassDef):
            errors.append(f"{label}: {symbol_name!r} in {raw_path} is not a class")
            return
        actual = _class_constructor_params(node)
        if actual is None:
            if declared:
                errors.append(
                    f"{label}: class {symbol_name!r} in {raw_path} has no explicit __init__ "
                    f"(or dataclass fields) but the schema declares constructor parameters {declared}"
                )
            return
    else:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            errors.append(
                f"{label}: {symbol_name!r} in {raw_path} is not a function/method "
                f"(found {_type_name(node)})"
            )
            return
        drop_first = kind == "method" and not _has_decorator(node, "staticmethod")
        actual = _callable_param_names(node, drop_first=drop_first)

    if actual != declared:
        errors.append(
            f"{label}: parameter mismatch in {raw_path}::{symbol_name}: schema declares "
            f"{declared}, implementation has {actual} "
            "(names and order must match; *args/**kwargs are ignored)"
        )


def _check_token_symbol(
    errors: list[str], label: str, symbol_name: str, raw_path: str, source: str
) -> None:
    for part in symbol_name.split("."):
        if part and not re.search(rf"\b{re.escape(part)}\b", source):
            errors.append(
                f"{label}: token {part!r} not found in {raw_path} "
                "(non-Python file: token-level existence check)"
            )
            return


def _check_symbol_deleted(
    errors: list[str],
    warnings: list[str],
    label: str,
    symbol_name: str,
    raw_path: str,
    file_path: Path,
) -> None:
    if not file_path.is_file():
        return  # file gone entirely: deletion satisfied
    try:
        source = file_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        errors.append(f"{label}: cannot read {raw_path}: {exc}")
        return
    if file_path.suffix.lower() in PYTHON_SUFFIXES:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            errors.append(f"{label}: cannot parse {raw_path} for conformance: {exc}")
            return
        if symbol_name in _python_public_symbols(tree):
            errors.append(
                f"{label}: symbol {symbol_name!r} is declared change:delete but is still "
                f"present in {raw_path}"
            )
    else:
        # Token presence in a non-Python file may be a comment; weak signal only.
        last = symbol_name.split(".")[-1]
        if last and re.search(rf"\b{re.escape(last)}\b", source):
            warnings.append(
                f"{label}: change:delete but token {last!r} still appears in {raw_path} "
                "(non-Python file: weak signal, verify manually)"
            )


def _warn_missing_error_types(
    warnings: list[str], label: str, symbol: dict[str, Any], raw_path: str, source: str
) -> None:
    declared_errors = symbol.get("errors")
    if not isinstance(declared_errors, list):
        return
    for item in declared_errors:
        if not isinstance(item, dict):
            continue
        raises = item.get("raises")
        if not isinstance(raises, str) or not raises.strip():
            continue
        name = raises.strip()
        if not re.search(rf"\b{re.escape(name)}\b", source):
            warnings.append(
                f"{label}: declared error type {name!r} does not appear in {raw_path} "
                "(weak static signal; acceptance tests give the strong guarantee)"
            )
