"""Cross-validation (Phase 3, ``--cross-validation``): blind acceptance track.

Same spec/plan/schemas, two independent derivations: the implementation track
(the normal full pipeline, P1) and a *blind* acceptance-test track (P2) that
never sees the implementation. The tracks join after verify; only a CLEAN
verdict (all acceptance tests pass, no boundary violations, schema conformant)
auto-passes. CONFLICT is adjudicated by a third provider (P3) into a mutually
exclusive 3-way verdict -- impl fault / test fault / spec ambiguous -- with a
mandatory spec citation.

Design decisions (UPGRADE_PROGRESS Phase 3 사전 결정, 2026-06-11):
- Blind tree = shallow clone at the plan commit under ``.project/runs/<feat>/
  blind/`` -- a *separate object store* (worktrees share ``.git`` objects, so a
  parallel impl commit would be reachable via ``git show``; INV-6 demands
  isolation, not prompt discipline). Auto-removed when the run finishes.
- Harness-generated stubs (from schemas.json only -- zero information leak)
  let the blind track self-check imports/collection before submitting, so the
  LLM-mistake class of join failures (binding/syntax) is eliminated before it
  can burn adjudication rounds.
- All prompts are internal ("수면 아래"): no preset files, no preset edits.
- Coverage gate: per symbol and per declared error, >=3 unique
  (citation, input_class) pairs counted from the design manifest.
- Round-to-round blindness: an impl fix sees failing test *names + assertion
  messages* only, never test bodies. A test rewrite sees the arbiter's
  citation-grounded findings, never the implementation.

Everything here is flag-gated: with ``cross_validation`` off the full pipeline
is byte-identical to Phase 2 behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import HarnessRuntime

import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import HarnessError
from .json_io import loads_json_text, read_json_file, write_json_file
from .process import kill_process_tree
from .providers import resolve_provider_command
from .status import ResultStatus

BLIND_DIRNAME = "blind"
XV_DIRNAME = "xv"
QUARANTINE_MARKER = "XV-QUARANTINE"
CASE_MARKER = "XV-CASE"
INPUT_CLASSES = ("normal", "boundary", "violation")
MIN_UNIQUE_PAIRS = 3
DEFAULT_MAX_ROUNDS = 3
AUTHOR_GATE_MAX_ROUNDS = 3
TRACK_STEPS = ("clone", "stubs", "design", "author", "gate", "review", "freeze")
ACCEPTANCE_DIR = "tests/acceptance"
PYTHON_SUFFIXES = (".py", ".pyw")
DECISIONS_FILENAME = "xv_decisions.json"

VERDICT_IMPL = "impl_fault"
VERDICT_TEST = "test_fault"
VERDICT_SPEC = "spec_ambiguous"
VERDICT_INVALID = "invalid"
ALLOWED_VERDICTS = (VERDICT_IMPL, VERDICT_TEST, VERDICT_SPEC)

# Live track threads, keyed by feature. The thread NEVER touches the run state
# dict or run.json; it persists progress only to xv/track.json (atomic writes),
# which the join step in the main thread reads. A dead/missing thread is fine:
# join re-runs the remaining steps synchronously from the persisted track file.
_TRACK_THREADS: dict[str, threading.Thread] = {}
_TRACK_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Paths / small helpers
# ---------------------------------------------------------------------------


def blind_dir(ctx: HarnessRuntime, feature: str) -> Path:
    return ctx.run_dir(feature) / BLIND_DIRNAME


def xv_dir(ctx: HarnessRuntime, feature: str) -> Path:
    return ctx.run_dir(feature) / XV_DIRNAME


def _track_path(xv_root: Path) -> Path:
    return xv_root / "track.json"


def _manifest_path(xv_root: Path) -> Path:
    return xv_root / "manifest.json"


def _frozen_dir(xv_root: Path) -> Path:
    return xv_root / "frozen"


def rmtree_robust(path: Path) -> None:
    """Remove a tree even when git made object files read-only (Windows)."""

    def _on_error(func: Any, p: Any, _exc: Any) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=_on_error)


def remove_blind_clone(ctx: HarnessRuntime, feature: str) -> None:
    rmtree_robust(blind_dir(ctx, feature))


def enabled(state: dict[str, Any]) -> bool:
    return bool(state.get("cross_validation"))


def _extract_json_object(text: str) -> dict[str, Any]:
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S | re.I)
    if fence:
        text = fence.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        text = text[start : end + 1]
    try:
        parsed = loads_json_text(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _git(root: Path, args: list[str], check: bool = True) -> "subprocess.CompletedProcess[str]":
    cmd = ["git", "-c", f"safe.directory={root.as_posix()}", "-c", "core.quotepath=false"] + args
    return subprocess.run(
        cmd,
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


# ---------------------------------------------------------------------------
# Provider role assignment / readiness
# ---------------------------------------------------------------------------


def compute_assignments(ctx: HarnessRuntime, state: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve providers for the blind-track roles.

    author: a code-write provider different from the impl developer (P2 != P1).
    design/review/arbiter: a judge provider different from the author --
    preferring non-code providers (the judge writes nothing). Raises
    HarnessError when the roles cannot be staffed with distinct providers.
    """
    policy = ctx.model_policy()
    available = list(ctx.available_providers())
    develop_provider = ""
    if state is not None:
        schedule = state.get("provider_schedule")
        if isinstance(schedule, dict):
            develop_provider = str(schedule.get(ctx.DEVELOP_STAGE) or "")
    if not develop_provider:
        code_order = [str(item) for item in policy.get("code_write_order", [])]
        develop_provider = next((p for p in code_order if p in available), "")

    denied = {str(item).strip().lower() for item in policy.get("code_write_denied", [])}
    allowed = {str(item).strip().lower() for item in policy.get("code_write_allowed", [])}
    code_writers = [
        p
        for p in available
        if "code_write" in ctx.provider_capabilities(p)
        and p not in denied
        and (not allowed or p in allowed)
    ]
    author = next((p for p in code_writers if p != develop_provider), "")
    if not author:
        raise HarnessError(
            "--cross-validation requires a code-write provider distinct from the "
            f"impl developer ({develop_provider or 'unknown'}). Available code "
            f"writers: {', '.join(code_writers) or 'none'}."
        )

    non_code = [p for p in available if "code_write" not in ctx.provider_capabilities(p)]
    judge = next((p for p in non_code if p != author), "")
    if not judge:
        judge = next((p for p in available if p != author), "")
    if not judge:
        raise HarnessError(
            "--cross-validation requires a judge provider distinct from the "
            "acceptance author. Enable a third provider."
        )
    return {
        "develop": develop_provider,
        "author": author,
        "design": judge,
        "review": judge,
        "arbiter": judge,
    }


def assert_ready(ctx: HarnessRuntime, state: dict[str, Any] | None = None) -> dict[str, str]:
    assignments = compute_assignments(ctx, state)
    if len({assignments["develop"], assignments["author"], assignments["arbiter"]}) < 3:
        raise HarnessError(
            "--cross-validation requires three distinct providers "
            f"(impl/author/judge), got: {assignments}"
        )
    return assignments


# ---------------------------------------------------------------------------
# Backend resolution (tiers) and stub generation
# ---------------------------------------------------------------------------


def _symbol_path_and_name(symbol: dict[str, Any]) -> tuple[str, str]:
    raw = str(symbol.get("id") or "")
    path, _, name = raw.partition("::")
    return path.strip().replace("\\", "/"), name.strip()


def _is_safe_repo_relative(path: str) -> bool:
    if not path or ":" in path or path.startswith("/"):
        return False
    return not any(part in ("", "..") for part in path.split("/"))


def resolve_backends(schemas: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Map each symbol id to a tier ("t1-python" | "t2-blackbox").

    Returns (tiers, unresolvable_reasons). delete-change symbols are exempt
    (they pin an absence, which conformance already verifies statically).
    """
    tiers: dict[str, str] = {}
    problems: list[str] = []
    for symbol in schemas.get("symbols", []) or []:
        if not isinstance(symbol, dict):
            continue
        sid = str(symbol.get("id") or "")
        if symbol.get("change") == "delete":
            continue
        path, name = _symbol_path_and_name(symbol)
        if symbol.get("kind") == "endpoint":
            tiers[sid] = "t2-blackbox"
            continue
        if not _is_safe_repo_relative(path):
            # A traversal/absolute path here would let stub generation write
            # outside the blind clone -- refuse instead.
            problems.append(f"{sid}: symbol path escapes the repository root")
            continue
        if path.lower().endswith(PYTHON_SUFFIXES) and name:
            tiers[sid] = "t1-python"
            continue
        problems.append(
            f"{sid}: no v1 backend (not a Python symbol, not an endpoint). "
            "Cross-validation v1 supports Python symbols (T1) and endpoints "
            "(T2 blackbox); run without --cross-validation or adjust the schema."
        )
    return tiers, problems


def _stub_params(signature: dict[str, Any]) -> str:
    order = signature.get("parameter_order")
    params = signature.get("parameters")
    names = [str(item) for item in order] if isinstance(order, list) else []
    rendered: list[str] = []
    for name in names:
        spec = params.get(name) if isinstance(params, dict) else None
        required = bool(spec.get("required")) if isinstance(spec, dict) else True
        rendered.append(name if required else f"{name}=None")
    return ", ".join(rendered)


def _stub_for_symbol(symbol: dict[str, Any]) -> str:
    kind = symbol.get("kind")
    signature = symbol.get("signature") if isinstance(symbol.get("signature"), dict) else {}
    _, name = _symbol_path_and_name(symbol)
    params = _stub_params(signature or {})
    if kind == "class":
        init_params = f"self, {params}" if params else "self"
        return (
            f"class {name}:\n"
            f"    def __init__({init_params}):\n"
            f"        raise NotImplementedError('xv stub')\n"
        )
    if kind == "method":
        cls, _, method = name.partition(".")
        method_params = f"self, {params}" if params else "self"
        return (
            f"def _xv_stub_{cls}_{method}({method_params}):\n"
            f"    raise NotImplementedError('xv stub')\n"
            f"{cls}.{method} = _xv_stub_{cls}_{method}\n"
        )
    return (
        f"def {name}({params}):\n"
        f"    raise NotImplementedError('xv stub')\n"
    )


def _existing_python_names(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(f"{node.name}.{item.name}")
    return names


def generate_stubs(clone_root: Path, schemas: dict[str, Any], tiers: dict[str, str]) -> list[str]:
    """Create importable stubs in the blind clone for every T1 symbol whose
    target is missing at the plan commit. Derived solely from schemas.json --
    the blind track already holds that input, so nothing leaks."""
    created: list[str] = []
    by_path: dict[str, list[dict[str, Any]]] = {}
    for symbol in schemas.get("symbols", []) or []:
        if not isinstance(symbol, dict):
            continue
        sid = str(symbol.get("id") or "")
        if tiers.get(sid) != "t1-python":
            continue
        path, _ = _symbol_path_and_name(symbol)
        by_path.setdefault(path, []).append(symbol)

    for rel_path, symbols in sorted(by_path.items()):
        target = clone_root.joinpath(*rel_path.split("/"))
        existing = ""
        if target.exists():
            try:
                existing = target.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                existing = ""
        have = _existing_python_names(existing) if existing else set()
        # Classes must be defined before method-attach stubs reference them.
        ordered = sorted(
            symbols,
            key=lambda item: 0 if item.get("kind") == "class" else 1,
        )
        additions: list[str] = []
        for symbol in ordered:
            _, name = _symbol_path_and_name(symbol)
            if name in have:
                continue
            if symbol.get("kind") == "method":
                cls = name.partition(".")[0]
                if cls not in have and not any(
                    other.get("kind") == "class"
                    and _symbol_path_and_name(other)[1] == cls
                    for other in ordered
                ):
                    # Method on a class that neither exists nor is declared:
                    # emit a bare class shell first so the attach works.
                    additions.append(f"class {cls}:\n    pass\n")
                    have.add(cls)
            additions.append(_stub_for_symbol(symbol))
            have.add(name)
        if not additions:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        header = "" if existing else "# xv stub module (generated from schemas.json; no impl information)\n"
        body = existing + ("\n\n" if existing and not existing.endswith("\n\n") else "")
        body += header + "\n\n".join(additions) + "\n"
        target.write_text(body, encoding="utf-8")
        created.append(rel_path)
    return created


# ---------------------------------------------------------------------------
# Acceptance manifest (design output) validation + coverage quota
# ---------------------------------------------------------------------------


def validate_manifest(manifest: Any, schemas: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest: must be a JSON object"]
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        return ["manifest.cases: must be a non-empty array"]

    symbol_ids = {
        str(symbol.get("id") or "")
        for symbol in schemas.get("symbols", []) or []
        if isinstance(symbol, dict)
    }
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{label}: must be an object")
            continue
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            errors.append(f"{label}.id: must be a non-empty string")
        elif case_id in seen_ids:
            errors.append(f"{label}.id: duplicate id {case_id!r}")
        else:
            seen_ids.add(case_id)
        symbol_id = str(case.get("symbol_id") or "").strip()
        if symbol_id not in symbol_ids:
            errors.append(f"{label}.symbol_id: unknown symbol {symbol_id!r}")
        input_class = str(case.get("input_class") or "").strip()
        if input_class not in INPUT_CLASSES:
            errors.append(
                f"{label}.input_class: must be one of {'|'.join(INPUT_CLASSES)}, got {input_class!r}"
            )
        if not str(case.get("citation") or "").strip():
            errors.append(f"{label}.citation: must quote the spec/schema clause this case encodes")
        target = case.get("target")
        if not isinstance(target, dict) or not str(target.get("type") or "").strip():
            errors.append(f"{label}.target: must be an object with a non-empty 'type'")

    errors.extend(_coverage_errors(cases, schemas))
    return errors


def _coverage_errors(cases: list[Any], schemas: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for symbol in schemas.get("symbols", []) or []:
        if not isinstance(symbol, dict) or symbol.get("change") == "delete":
            continue
        sid = str(symbol.get("id") or "")
        pairs = {
            (str(case.get("citation") or "").strip(), str(case.get("input_class") or "").strip())
            for case in cases
            if isinstance(case, dict) and str(case.get("symbol_id") or "") == sid
        }
        pairs.discard(("", ""))
        if len(pairs) < MIN_UNIQUE_PAIRS:
            errors.append(
                f"coverage: symbol {sid}: {len(pairs)} unique (citation, input_class) "
                f"pairs, need >= {MIN_UNIQUE_PAIRS}"
            )
        declared_errors = symbol.get("errors")
        if isinstance(declared_errors, list):
            for err in declared_errors:
                if not isinstance(err, dict):
                    continue
                raises = str(err.get("raises") or "").strip()
                if not raises:
                    continue
                err_pairs = {
                    (
                        str(case.get("citation") or "").strip(),
                        str(case.get("input_class") or "").strip(),
                    )
                    for case in cases
                    if isinstance(case, dict)
                    and str(case.get("symbol_id") or "") == sid
                    and isinstance(case.get("target"), dict)
                    and str(case["target"].get("type") or "") == "error"
                    and str(case["target"].get("ref") or "") == raises
                }
                err_pairs.discard(("", ""))
                if len(err_pairs) < MIN_UNIQUE_PAIRS:
                    errors.append(
                        f"coverage: symbol {sid} error {raises!r}: {len(err_pairs)} unique "
                        f"(citation, input_class) pairs, need >= {MIN_UNIQUE_PAIRS}"
                    )
    return errors


def _case_ids(manifest: dict[str, Any]) -> list[str]:
    return [
        str(case.get("id") or "").strip()
        for case in manifest.get("cases", [])
        if isinstance(case, dict) and str(case.get("id") or "").strip()
    ]


def scan_case_markers(acceptance_root: Path) -> set[str]:
    found: set[str] = set()
    if not acceptance_root.exists():
        return found
    for path in sorted(acceptance_root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for match in re.finditer(rf"{CASE_MARKER}:\s*([A-Za-z0-9_.-]+)", text):
            found.add(match.group(1))
    return found


# ---------------------------------------------------------------------------
# Internal prompts (수면 아래 -- never preset files)
# ---------------------------------------------------------------------------


def _limit(text: str, max_chars: int = 24000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def _design_prompt(xvc: "XvTrackContext", capture_file: Path, retry_errors: list[str]) -> str:
    retry_block = ""
    if retry_errors:
        retry_block = (
            "\n## Previous Attempt Was Rejected\n"
            "Fix every issue below and return the full corrected manifest:\n"
            + "\n".join(f"- {item}" for item in retry_errors)
            + "\n"
        )
    return f"""# Blind Acceptance Case Design

- xv_step: design
- feature_name: {xvc.feature}
- capture_file: {capture_file}

You are the blind acceptance-test DESIGNER for an independent verification
track. You must derive acceptance cases from the spec, plan and interface
schema ONLY. The implementation does not exist in your tree and you must not
guess at it.

Rules:
1. Output exactly one JSON object (schema below). Also write the same JSON to
   the capture_file path above (create parent directories if needed). Do not
   modify any other file.
2. Every case MUST cite the exact spec/schema clause it encodes (`citation`).
   A case without a defensible citation is over-specification and will be
   rejected later -- do not invent requirements.
3. Coverage quota (machine-checked): for EVERY non-delete symbol, and for
   EVERY declared error (`errors[].raises`), provide at least {MIN_UNIQUE_PAIRS}
   cases with unique (citation, input_class) pairs. input_class is one of
   normal | boundary | violation. Duplicated pairs count once -- vary the
   clause or the input class, not the wording.
4. Prefer concrete inputs and expected outcomes (values, types, raised error
   types) over prose.
{retry_block}
## Output JSON schema
{{
  "version": 1,
  "feature": "{xvc.feature}",
  "cases": [
    {{
      "id": "case-001",
      "symbol_id": "<path>::<symbol>",
      "target": {{"type": "signature|constraint|error|invariant", "ref": "<clause ref, e.g. error raises name>"}},
      "input_class": "normal|boundary|violation",
      "citation": "<verbatim quote or precise pointer into spec/schemas>",
      "description": "<what this case verifies>",
      "expected": "<concrete expected outcome>"
    }}
  ]
}}

## Spec (00_spec.md)
{_limit(xvc.spec_text)}

## Plan (01_plan.md)
{_limit(xvc.plan_text)}

## Interface schema (schemas.json) -- frozen law
{_limit(xvc.schemas_text)}
"""


def _author_prompt(xvc: "XvTrackContext", manifest_text: str, retry_errors: list[str]) -> str:
    retry_block = ""
    if retry_errors:
        retry_block = (
            "\n## Previous Attempt Failed The Mechanical Gate\n"
            "Fix every issue below, then ensure `python -m pytest --collect-only "
            f"{ACCEPTANCE_DIR}` succeeds from the repository root:\n"
            + "\n".join(f"- {item}" for item in retry_errors)
            + "\n"
        )
    return f"""# Blind Acceptance Test Authoring

- xv_step: author
- feature_name: {xvc.feature}

You are the blind acceptance-test AUTHOR. Your working tree was forked at the
plan commit: the implementation is physically absent. Target symbols exist as
harness-generated stubs that raise NotImplementedError -- import them and
encode the SCHEMA contract, never stub behavior.

Rules:
1. Write pytest tests under `{ACCEPTANCE_DIR}/` ONLY. Do not touch any other
   path (src/, schemas.json, plan/spec files are read-only).
2. Implement EVERY case in the manifest below. Each test function's docstring
   must start with `{CASE_MARKER}: <case id>` so the harness can trace it.
3. Tests must be self-contained pytest (no network, no external services) and
   must import the real symbol paths from the schema (e.g. `from src.x.y
   import f`). They will be executed later against the real implementation.
4. Assert only what the citation supports. Over-specified assertions will be
   classified as test faults at adjudication.
5. Self-check before finishing: `python -m pytest --collect-only -q
   {ACCEPTANCE_DIR}` must succeed (run it from the repository root). All tests
   FAILING here (NotImplementedError) is expected and correct.
{retry_block}
## Acceptance manifest (implement all cases)
{_limit(manifest_text)}

## Interface schema (schemas.json) -- frozen law
{_limit(xvc.schemas_text)}

## Spec (00_spec.md)
{_limit(xvc.spec_text)}
"""


def _review_prompt(xvc: "XvTrackContext", manifest_text: str, tests_text: str, capture_file: Path) -> str:
    return f"""# Blind Acceptance Test Review

- xv_step: review
- feature_name: {xvc.feature}
- capture_file: {capture_file}

You are the blind REVIEWER of acceptance tests. You have never seen the
implementation and must judge only: does every assertion trace to a cited
spec/schema clause? Flag over-specification (assertions the citations do not
support) and under-specification (manifest cases not faithfully encoded).

Output exactly one JSON object (also write it to capture_file):
{{
  "approved": true/false,
  "findings": [
    {{"case_id": "<id or empty>", "test": "<test name>", "issue": "<what is wrong>",
      "citation_check": "<why the citation does or does not support it>"}}
  ]
}}
Use findings=[] with approved=true when everything traces cleanly.

## Acceptance manifest
{_limit(manifest_text)}

## Acceptance tests
{_limit(tests_text, 32000)}

## Interface schema (schemas.json)
{_limit(xvc.schemas_text)}

## Spec (00_spec.md)
{_limit(xvc.spec_text)}
"""


def _rewrite_prompt(
    xvc: "XvTrackContext",
    manifest_text: str,
    tests_text: str,
    findings: list[dict[str, Any]],
) -> str:
    findings_text = json.dumps(findings, ensure_ascii=False, indent=2)
    return f"""# Blind Acceptance Test Rewrite

- xv_step: rewrite
- feature_name: {xvc.feature}

You are the blind acceptance-test AUTHOR, re-entering after adjudication. An
independent arbiter judged the findings below against the spec/schema: the
flagged assertions are NOT supported by any cited clause (test fault). You
still must not see or guess the implementation.

Rules:
1. Fix ONLY what the findings justify: remove or correct unsupported
   assertions, keep every spec-grounded assertion intact. Do not weaken tests
   to make anything pass -- ground every assertion in a citation.
2. Write only under `{ACCEPTANCE_DIR}/`. Keep `{CASE_MARKER}: <id>` docstring
   markers intact and coverage complete.
3. Self-check: `python -m pytest --collect-only -q {ACCEPTANCE_DIR}` must
   succeed from the repository root.

## Arbiter findings (citation-grounded)
{findings_text}

## Current acceptance tests
{_limit(tests_text, 32000)}

## Acceptance manifest
{_limit(manifest_text)}

## Interface schema (schemas.json)
{_limit(xvc.schemas_text)}
"""


def _arbiter_prompt(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    failures: list[dict[str, str]],
    tests_text: str,
    impl_text: str,
    manifest_text: str,
    schemas_text: str,
    spec_text: str,
    capture_file: Path,
) -> str:
    failures_text = json.dumps(failures, ensure_ascii=False, indent=2)
    return f"""# Cross-Validation Arbiter (independent adjudication)

- xv_step: arbiter
- feature_name: {state.get("feature_name")}
- capture_file: {capture_file}

Two independent derivations of the same spec disagree: the implementation
passed its own pipeline, but blind acceptance tests fail. You are the third,
uninvolved judge. You change nothing -- you only classify each failing test
into EXACTLY ONE of three mutually exclusive verdicts:

- "{VERDICT_IMPL}": the spec/schema requires X, the test asserts X, the
  implementation does Y. The implementation must change.
- "{VERDICT_TEST}": the test asserts something NO cited spec/schema clause
  requires (over-specification or a broken test). The test must change.
- "{VERDICT_SPEC}": both readings are defensible -- the spec/schema is
  genuinely ambiguous at a specific clause. Name that exact clause; this is
  the most valuable verdict and must not be used as an "unsure" bucket.

Hard rules:
1. Every verdict MUST include `citation`: the verbatim spec/schema clause that
   grounds it. A {VERDICT_TEST} or {VERDICT_SPEC} verdict without a usable
   citation is invalid and quarantines the feature -- cite or classify as
   {VERDICT_IMPL} only when the spec genuinely requires the tested behavior.
2. Never propose weakening a test so code passes; judge against the spec only.

Output exactly one JSON object (also write it to capture_file):
{{
  "classifications": [
    {{"test": "<failing test name>", "verdict": "{VERDICT_IMPL}|{VERDICT_TEST}|{VERDICT_SPEC}",
      "citation": "<verbatim clause>", "explanation": "<one paragraph>"}}
  ]
}}

## Failing acceptance tests (name + assertion message)
{failures_text}

## Acceptance test sources
{_limit(tests_text, 28000)}

## Implementation sources (schema-declared files)
{_limit(impl_text, 28000)}

## Acceptance manifest
{_limit(manifest_text, 12000)}

## Interface schema (schemas.json)
{_limit(schemas_text, 16000)}

## Spec (00_spec.md)
{_limit(spec_text, 12000)}
"""


# ---------------------------------------------------------------------------
# Provider execution (cwd-scoped, internal)
# ---------------------------------------------------------------------------


def _build_role_command(
    ctx: HarnessRuntime,
    provider: str,
    cwd: Path,
    performance: Any,
) -> list[str]:
    """Resolve a provider command template scoped to ``cwd`` (the blind clone
    for track roles, the repo root for the arbiter). ``{log_file}`` and
    ``{prompt*}`` placeholders are left for call time."""
    command: list[str] = []
    for part in ctx.raw_provider_command(provider):
        command.append(str(part).replace("{cwd}", str(cwd)))
    command = ctx.apply_performance_to_command(provider, command, performance)
    return resolve_provider_command(provider, command)


def _run_provider(
    command_template: list[str],
    prompt_text: str,
    cwd: Path,
    log_base: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    log_base.parent.mkdir(parents=True, exist_ok=True)
    cli_log = log_base.with_suffix(".cli.log")
    command: list[str] = []
    prompt_in_command = False
    for part in command_template:
        rendered = part.replace("{log_file}", str(cli_log))
        if "{prompt}" in rendered:
            prompt_in_command = True
            rendered = rendered.replace("{prompt}", prompt_text)
        command.append(rendered)

    started = time.time()
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=None if prompt_in_command else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout_text, stderr_text = proc.communicate(
            input=None if prompt_in_command else prompt_text,
            timeout=timeout_seconds,
        )
        timed_out = False
    except subprocess.TimeoutExpired:
        kill_process_tree(proc)
        try:
            stdout_text, stderr_text = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            stdout_text, stderr_text = "", ""
        stderr_text = (stderr_text or "") + f"\nTimed out after {timeout_seconds} seconds.\n"
        timed_out = True
    stdout_text = stdout_text or ""
    stderr_text = stderr_text or ""
    log_base.with_suffix(".out.txt").write_text(stdout_text, encoding="utf-8")
    log_base.with_suffix(".err.txt").write_text(stderr_text, encoding="utf-8")
    return {
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "stdout_text": stdout_text,
        "stderr_text": stderr_text,
        "elapsed_seconds": round(time.time() - started, 2),
    }


def _provider_json(
    result: dict[str, Any],
    capture_file: Path,
) -> dict[str, Any]:
    if result.get("timed_out") or result.get("returncode") != 0:
        return {}
    parsed = _extract_json_object(str(result.get("stdout_text") or ""))
    if parsed:
        return parsed
    if capture_file.exists():
        try:
            text = capture_file.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return {}
        return _extract_json_object(text)
    return {}


# ---------------------------------------------------------------------------
# Track context + steps (thread-safe: no ctx/state access inside steps)
# ---------------------------------------------------------------------------


@dataclass
class XvTrackContext:
    feature: str
    root: Path
    run_branch: str
    plan_sha: str
    blind: Path
    xv: Path
    logs: Path
    assignments: dict[str, str]
    commands: dict[str, list[str]]
    timeout_seconds: int
    spec_relpath: str
    plan_relpath: str
    schemas_relpath: str
    spec_text: str = ""
    plan_text: str = ""
    schemas_text: str = ""
    schemas: dict[str, Any] = field(default_factory=dict)

    def log(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {message}\n"
        self.logs.mkdir(parents=True, exist_ok=True)
        with (self.logs / "track.log").open("a", encoding="utf-8") as fh:
            fh.write(line)


def _read_track(xv_root: Path) -> dict[str, Any]:
    parsed = read_json_file(_track_path(xv_root), {})
    return parsed if isinstance(parsed, dict) else {}


def _write_track(xv_root: Path, track: dict[str, Any]) -> None:
    write_json_file(_track_path(xv_root), track)


def _track_step_done(track: dict[str, Any], step: str) -> bool:
    done = track.get("completed_steps")
    return isinstance(done, list) and step in done


def _mark_step(xv_root: Path, track: dict[str, Any], step: str, **extra: Any) -> None:
    done = track.setdefault("completed_steps", [])
    if step not in done:
        done.append(step)
    track.update(extra)
    track["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_track(xv_root, track)


def _fail_track(xv_root: Path, track: dict[str, Any], reason: str) -> None:
    track["status"] = "failed"
    track["error"] = reason
    track["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_track(xv_root, track)


def build_track_context(ctx: HarnessRuntime, state: dict[str, Any]) -> XvTrackContext:
    feature = str(state["feature_name"])
    commits = state.get("commits") if isinstance(state.get("commits"), dict) else {}
    plan_sha = str((commits or {}).get(ctx.PLAN_STAGE) or "")
    if not plan_sha:
        raise HarnessError("cross-validation track requires a recorded plan commit")
    assignments_raw = state.get("xv_assignments")
    assignments = (
        {str(k): str(v) for k, v in assignments_raw.items()}
        if isinstance(assignments_raw, dict)
        else compute_assignments(ctx, state)
    )
    performance = ctx.normalize_performance(state.get("performance"))
    blind = blind_dir(ctx, feature)
    commands = {
        "design": _build_role_command(ctx, assignments["design"], blind, performance),
        "author": _build_role_command(ctx, assignments["author"], blind, performance),
        "review": _build_role_command(ctx, assignments["review"], blind, performance),
        "rewrite": _build_role_command(ctx, assignments["author"], blind, performance),
        "arbiter": _build_role_command(ctx, assignments["arbiter"], ctx.ROOT, performance),
    }
    spec_rel = ctx.rel(ctx.stage_output_path(feature, ctx.START_STAGE))
    plan_rel = ctx.rel(ctx.stage_output_path(feature, ctx.PLAN_STAGE))
    schemas_rel = ctx.rel(ctx.feature_schemas_path(feature))
    return XvTrackContext(
        feature=feature,
        root=ctx.ROOT,
        run_branch=str(state.get("run_branch") or ""),
        plan_sha=plan_sha,
        blind=blind,
        xv=xv_dir(ctx, feature),
        logs=xv_dir(ctx, feature) / "logs",
        assignments=assignments,
        commands=commands,
        timeout_seconds=int(state.get("xv_step_timeout_seconds") or 1800),
        spec_relpath=spec_rel,
        plan_relpath=plan_rel,
        schemas_relpath=schemas_rel,
    )


def _load_blind_inputs(xvc: XvTrackContext) -> str | None:
    """Read spec/plan/schemas from the BLIND clone (plan-commit content)."""
    for attr, rel_path in (
        ("spec_text", xvc.spec_relpath),
        ("plan_text", xvc.plan_relpath),
        ("schemas_text", xvc.schemas_relpath),
    ):
        path = xvc.blind.joinpath(*rel_path.split("/"))
        if not path.exists():
            return f"blind clone is missing {rel_path} (plan commit incomplete?)"
        try:
            setattr(xvc, attr, path.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError as exc:
            return f"cannot read {rel_path} in blind clone: {exc}"
    try:
        parsed = loads_json_text(xvc.schemas_text)
    except json.JSONDecodeError as exc:
        return f"blind schemas.json is not valid JSON: {exc}"
    if not isinstance(parsed, dict):
        return "blind schemas.json is not an object"
    xvc.schemas = parsed
    return None


def _step_clone(xvc: XvTrackContext) -> str | None:
    """Shallow-fetch the plan commit into a fresh repo: separate object store,
    so impl commits made later in the main repo are unreachable (hard blind)."""
    if xvc.blind.exists():
        rmtree_robust(xvc.blind)
    xvc.blind.mkdir(parents=True, exist_ok=True)
    ref = f"refs/xv/{xvc.feature}"
    try:
        _git(xvc.root, ["update-ref", ref, xvc.plan_sha])
        init = subprocess.run(
            ["git", "init", "--quiet", str(xvc.blind)],
            cwd=xvc.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if init.returncode != 0:
            return f"git init failed for blind clone: {init.stderr.strip()}"
        fetch = _git(xvc.blind, ["fetch", "--quiet", "--depth", "1", str(xvc.root), ref], check=False)
        if fetch.returncode != 0:
            return f"git fetch of plan commit failed: {fetch.stderr.strip()}"
        checkout = _git(xvc.blind, ["checkout", "--quiet", "--detach", "FETCH_HEAD"], check=False)
        if checkout.returncode != 0:
            return f"git checkout of plan commit failed: {checkout.stderr.strip()}"
    finally:
        _git(xvc.root, ["update-ref", "-d", ref], check=False)
    head = _git(xvc.blind, ["rev-parse", "HEAD"], check=False).stdout.strip()
    if head != xvc.plan_sha:
        return f"blind clone HEAD {head} does not match plan commit {xvc.plan_sha}"
    return None


def _step_stubs(xvc: XvTrackContext, track: dict[str, Any]) -> str | None:
    error = _load_blind_inputs(xvc)
    if error:
        return error
    if xvc.schemas.get("specifiable", True) is False:
        return (
            "cross-validation requires a specifiable schema (specifiable:false "
            "declares an exploratory feature; run without --cross-validation)"
        )
    tiers, problems = resolve_backends(xvc.schemas)
    if problems:
        return "unresolvable symbols for cross-validation v1:\n" + "\n".join(
            f"- {item}" for item in problems
        )
    if not tiers:
        return "schema declares no testable symbols for cross-validation"
    created = generate_stubs(xvc.blind, xvc.schemas, tiers)
    track["tiers"] = tiers
    track["stub_files"] = created
    xvc.log(f"stubs generated: {created or 'none needed'}; tiers: {tiers}")
    return None


def _step_design(xvc: XvTrackContext, track: dict[str, Any]) -> str | None:
    if not xvc.schemas:
        error = _load_blind_inputs(xvc)
        if error:
            return error
    capture = xvc.xv / "design_capture.json"
    retry_errors: list[str] = []
    for attempt in range(1, 4):
        if capture.exists():
            capture.unlink()
        prompt = _design_prompt(xvc, capture, retry_errors)
        result = _run_provider(
            xvc.commands["design"],
            prompt,
            xvc.blind,
            xvc.logs / f"design_attempt{attempt}",
            xvc.timeout_seconds,
        )
        manifest = _provider_json(result, capture)
        errors = validate_manifest(manifest, xvc.schemas) if manifest else ["no JSON manifest returned"]
        if not errors:
            write_json_file(_manifest_path(xvc.xv), manifest)
            track["manifest_cases"] = len(manifest.get("cases", []))
            xvc.log(f"design accepted on attempt {attempt}: {track['manifest_cases']} cases")
            return None
        retry_errors = errors
        xvc.log(f"design attempt {attempt} rejected: {errors}")
    return "acceptance case design failed validation after 3 attempts:\n" + "\n".join(
        f"- {item}" for item in retry_errors
    )


def _clone_changed_paths(xvc: XvTrackContext) -> list[str]:
    proc = _git(xvc.blind, ["status", "--porcelain=v1"], check=False)
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        raw = line[2:].lstrip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        paths.append(raw.strip().strip('"').replace("\\", "/"))
    return sorted(set(paths))


def _clone_partition_errors(xvc: XvTrackContext, allowed_extra: tuple[str, ...] = ()) -> list[str]:
    """The blind author may only create acceptance tests (plus harness-internal
    xv scratch). Stub files written by the harness before authoring are part of
    the allowed baseline."""
    allowed_prefixes = (
        f"{ACCEPTANCE_DIR}/",
        ".xv_capture",
    ) + allowed_extra
    stub_files = set()
    track = _read_track(xvc.xv)
    for item in track.get("stub_files", []) or []:
        stub_files.add(str(item).replace("\\", "/"))
    errors: list[str] = []
    for path in _clone_changed_paths(xvc):
        if path in stub_files:
            continue
        if path == ACCEPTANCE_DIR or path.startswith(allowed_prefixes):
            continue
        # A collapsed untracked-directory entry ("tests/" when acceptance is
        # the only new content underneath) is fine.
        if path.rstrip("/") in {"tests", "tests/acceptance"}:
            continue
        errors.append(path)
    return errors


def _step_author(xvc: XvTrackContext, track: dict[str, Any]) -> str | None:
    manifest = read_json_file(_manifest_path(xvc.xv), {})
    if not isinstance(manifest, dict) or not manifest:
        return "author step requires a validated manifest"
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    retry_errors: list[str] = []
    for attempt in range(1, AUTHOR_GATE_MAX_ROUNDS + 1):
        prompt = _author_prompt(xvc, manifest_text, retry_errors)
        result = _run_provider(
            xvc.commands["author"],
            prompt,
            xvc.blind,
            xvc.logs / f"author_attempt{attempt}",
            xvc.timeout_seconds,
        )
        if result.get("timed_out"):
            retry_errors = [f"author provider timed out after {xvc.timeout_seconds}s"]
            continue
        gate_errors = _gate_errors(xvc, manifest)
        partition = _clone_partition_errors(xvc)
        if partition:
            gate_errors.append(
                "blind track wrote outside tests/acceptance: " + ", ".join(partition)
            )
        if not gate_errors:
            xvc.log(f"author + gate passed on attempt {attempt}")
            track["author_attempts"] = attempt
            return None
        retry_errors = gate_errors
        xvc.log(f"author attempt {attempt} failed gate: {gate_errors}")
    return "acceptance authoring failed the mechanical gate after retries:\n" + "\n".join(
        f"- {item}" for item in retry_errors
    )


def _gate_errors(xvc: XvTrackContext, manifest: dict[str, Any]) -> list[str]:
    """Deterministic gate: pytest collection succeeds AND every manifest case
    id appears as an XV-CASE marker in the acceptance tests."""
    acceptance_root = xvc.blind / "tests" / "acceptance"
    if not acceptance_root.exists():
        return [f"{ACCEPTANCE_DIR}/ was not created"]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", ACCEPTANCE_DIR],
        cwd=xvc.blind,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    errors: list[str] = []
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-25:])
        errors.append(f"pytest --collect-only failed (exit {proc.returncode}):\n{tail}")
        return errors
    found = scan_case_markers(acceptance_root)
    missing = [case_id for case_id in _case_ids(manifest) if case_id not in found]
    if missing:
        errors.append(
            f"manifest cases without an {CASE_MARKER} marker in any test: {', '.join(missing)}"
        )
    return errors


def _acceptance_sources(root: Path) -> str:
    acceptance_root = root / "tests" / "acceptance"
    blocks: list[str] = []
    if not acceptance_root.exists():
        return ""
    for path in sorted(acceptance_root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        blocks.append(f"### {rel}\n```python\n{text}\n```")
    return "\n\n".join(blocks)


def _step_review(xvc: XvTrackContext, track: dict[str, Any]) -> str | None:
    manifest = read_json_file(_manifest_path(xvc.xv), {})
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    capture = xvc.xv / "review_capture.json"
    warnings: list[str] = []
    for round_index in range(1, 3):
        if capture.exists():
            capture.unlink()
        tests_text = _acceptance_sources(xvc.blind)
        prompt = _review_prompt(xvc, manifest_text, tests_text, capture)
        result = _run_provider(
            xvc.commands["review"],
            prompt,
            xvc.blind,
            xvc.logs / f"review_round{round_index}",
            xvc.timeout_seconds,
        )
        verdict = _provider_json(result, capture)
        findings = verdict.get("findings") if isinstance(verdict, dict) else None
        findings = [item for item in findings if isinstance(item, dict)] if isinstance(findings, list) else []
        if not findings:
            track["review_rounds"] = round_index
            track["review_warnings"] = warnings
            xvc.log(f"review approved on round {round_index}")
            return None
        if round_index >= 2:
            # Budget spent: keep remaining findings as warnings, do not deadlock.
            track["review_rounds"] = round_index
            track["review_warnings"] = warnings + [json.dumps(item, ensure_ascii=False) for item in findings]
            xvc.log(f"review still has findings after fix round; recorded as warnings")
            return None
        xvc.log(f"review round {round_index} findings: {len(findings)}; running author fix")
        fix_prompt = _rewrite_prompt(xvc, manifest_text, tests_text, findings)
        fix_result = _run_provider(
            xvc.commands["author"],
            fix_prompt,
            xvc.blind,
            xvc.logs / f"review_fix_round{round_index}",
            xvc.timeout_seconds,
        )
        if fix_result.get("timed_out"):
            return "review fix round timed out"
        gate = _gate_errors(xvc, manifest if isinstance(manifest, dict) else {})
        if gate:
            return "review fix round broke the mechanical gate:\n" + "\n".join(f"- {g}" for g in gate)
    return None


def _step_freeze(xvc: XvTrackContext, track: dict[str, Any]) -> str | None:
    source = xvc.blind / "tests" / "acceptance"
    if not source.exists():
        return "freeze: acceptance directory missing in blind clone"
    rmtree_robust(_frozen_dir(xvc.xv))
    target = _frozen_dir(xvc.xv) / "tests" / "acceptance"
    shutil.copytree(source, target, dirs_exist_ok=True)
    files = sorted(
        str(path.relative_to(_frozen_dir(xvc.xv))).replace("\\", "/")
        for path in target.rglob("*")
        if path.is_file()
    )
    track["frozen_files"] = files
    xvc.log(f"frozen {len(files)} acceptance files")
    return None


def run_track(xvc: XvTrackContext) -> dict[str, Any]:
    """Run (or resume) the blind track step machine; idempotent per step."""
    xvc.xv.mkdir(parents=True, exist_ok=True)
    track = _read_track(xvc.xv)
    if not track:
        track = {
            "version": 1,
            "feature": xvc.feature,
            "plan_sha": xvc.plan_sha,
            "status": "running",
            "assignments": xvc.assignments,
            "completed_steps": [],
        }
        _write_track(xvc.xv, track)
    if track.get("status") == "frozen":
        return track
    track["status"] = "running"
    track.pop("error", None)

    steps: list[tuple[str, Any]] = [
        ("clone", lambda: _step_clone(xvc)),
        ("stubs", lambda: _step_stubs(xvc, track)),
        ("design", lambda: _step_design(xvc, track)),
        ("author", lambda: _step_author(xvc, track)),
        ("review", lambda: _step_review(xvc, track)),
        ("freeze", lambda: _step_freeze(xvc, track)),
    ]
    # Inputs (spec/plan/schemas snapshots) live in the clone; when resuming past
    # the clone step they must be reloaded for later steps' prompts.
    if _track_step_done(track, "clone") and not xvc.schemas:
        error = _load_blind_inputs(xvc)
        if error:
            _fail_track(xvc.xv, track, error)
            return track
    for name, runner in steps:
        if _track_step_done(track, name):
            continue
        try:
            error = runner()
        except Exception as exc:  # noqa: BLE001 - track failure must persist, not crash the thread
            error = f"{name} step crashed: {exc!r}"
        if error:
            xvc.log(f"step {name} failed: {error}")
            _fail_track(xvc.xv, track, f"[{name}] {error}")
            return track
        _mark_step(xvc.xv, track, name)
    track["status"] = "frozen"
    track["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_track(xvc.xv, track)
    xvc.log("track frozen")
    return track


def start_track_async(ctx: HarnessRuntime, state: dict[str, Any]) -> None:
    """Spawn the blind track in a daemon thread right after the plan commit.

    The thread shares nothing with the run state; all progress is persisted to
    xv/track.json so a later join (possibly in a different process) can resume
    synchronously from the last completed step."""
    if not enabled(state):
        return
    feature = str(state["feature_name"])
    existing_track = _read_track(xv_dir(ctx, feature))
    if existing_track.get("status") == "frozen":
        return
    with _TRACK_LOCK:
        thread = _TRACK_THREADS.get(feature)
        if thread is not None and thread.is_alive():
            return
        xvc = build_track_context(ctx, state)

        def _target() -> None:
            try:
                run_track(xvc)
            except Exception as exc:  # noqa: BLE001 - never let the thread die silently
                track = _read_track(xvc.xv)
                _fail_track(xvc.xv, track or {"version": 1, "feature": feature}, f"track thread crashed: {exc!r}")

        thread = threading.Thread(target=_target, name=f"xv-{feature}", daemon=True)
        _TRACK_THREADS[feature] = thread
        thread.start()
    ctx.log_event(
        state,
        "xv_track_started",
        "blind acceptance track started in parallel",
        stage=ctx.PLAN_STAGE,
        assignments=json.dumps(state.get("xv_assignments") or {}, ensure_ascii=False),
    )


def _wait_for_track(ctx: HarnessRuntime, state: dict[str, Any]) -> dict[str, Any]:
    """Join barrier: wait for the live thread, then resume any remaining steps
    synchronously (covers fresh processes after NEEDS_USER/blocked resumes)."""
    feature = str(state["feature_name"])
    with _TRACK_LOCK:
        thread = _TRACK_THREADS.get(feature)
    if thread is not None and thread.is_alive():
        ctx.log_event(state, "xv_join_waiting", "waiting for blind track to finish", stage=ctx.VERIFY_STAGE)
        deadline = time.time() + max(600, int(state.get("xv_step_timeout_seconds") or 1800) * 2)
        while thread.is_alive() and time.time() < deadline:
            thread.join(timeout=5)
    track = _read_track(xv_dir(ctx, feature))
    if track.get("status") == "frozen":
        return track
    # Not frozen (failed mid-step, or a fresh process after a blocked resume):
    # finish the remaining steps synchronously. Completed steps are skipped and
    # a previously failed step gets a fresh attempt, so a human-driven resume
    # retries the track without restarting it from scratch.
    xvc = build_track_context(ctx, state)
    return run_track(xvc)


# ---------------------------------------------------------------------------
# Join: copy, run, verdict, arbiter, routing
# ---------------------------------------------------------------------------


def _copy_frozen_acceptance(ctx: HarnessRuntime, state: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Copy frozen acceptance tests into the main tree. Returns
    (copied_relpaths, conflicts). Files previously copied by xv are freely
    overwritten/removed; a pre-existing foreign file is a boundary conflict."""
    feature = str(state["feature_name"])
    frozen_root = _frozen_dir(xv_dir(ctx, feature))
    files = [
        path
        for path in sorted(frozen_root.rglob("*"))
        if path.is_file()
    ]
    previously = {str(item) for item in state.get("xv_copied_files", []) or []}
    new_rels: list[str] = []
    conflicts: list[str] = []
    for path in files:
        rel = path.relative_to(frozen_root).as_posix()
        target = ctx.ROOT.joinpath(*rel.split("/"))
        if target.exists() and rel not in previously:
            try:
                if target.read_bytes() != path.read_bytes():
                    conflicts.append(rel)
                    continue
            except OSError:
                conflicts.append(rel)
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        new_rels.append(rel)
    # Remove files a rewrite round deleted from the frozen set.
    for rel in sorted(previously - set(new_rels)):
        stale = ctx.ROOT.joinpath(*rel.split("/"))
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                pass
    state["xv_copied_files"] = new_rels
    return new_rels, conflicts


def _run_acceptance(ctx: HarnessRuntime, state: dict[str, Any]) -> tuple[bool, list[dict[str, str]], str]:
    """Run the copied acceptance tests in the impl tree. Returns
    (all_passed, failures[name+message only -- the round-blindness leak level],
    error)."""
    feature = str(state["feature_name"])
    xml_path = xv_dir(ctx, feature) / f"join_{ctx.now_stamp()}.xml"
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(ctx.DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS or 600)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", ACCEPTANCE_DIR, "-q", f"--junitxml={xml_path}"],
            cwd=ctx.ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, [], f"acceptance run timed out after {timeout}s"
    if not xml_path.exists():
        tail = "\n".join((proc.stdout or "").splitlines()[-20:])
        return False, [], f"acceptance run produced no junit xml (exit {proc.returncode}):\n{tail}"
    failures = _parse_junit_failures(xml_path)
    if proc.returncode == 0 and not failures:
        return True, [], ""
    if proc.returncode != 0 and not failures:
        tail = "\n".join((proc.stdout or "").splitlines()[-20:])
        return False, [], f"acceptance run failed without parsable failures (exit {proc.returncode}):\n{tail}"
    return False, failures, ""


def _parse_junit_failures(xml_path: Path) -> list[dict[str, str]]:
    """Extract failing test names + assertion messages ONLY (round blindness:
    the impl fix never sees test bodies)."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    failures: list[dict[str, str]] = []
    for case in tree.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            name = f"{case.get('classname') or ''}::{case.get('name') or ''}".strip(":")
            message = str(node.get("message") or "").strip()
            failures.append({"test": name, "message": message[:600]})
            break
    return failures


def _impl_sources_for_arbiter(ctx: HarnessRuntime, schemas: dict[str, Any]) -> str:
    blocks: list[str] = []
    seen: set[str] = set()
    for symbol in schemas.get("symbols", []) or []:
        if not isinstance(symbol, dict):
            continue
        path, _ = _symbol_path_and_name(symbol)
        if not path or path in seen:
            continue
        seen.add(path)
        target = ctx.ROOT.joinpath(*path.split("/"))
        if not target.is_file():
            continue
        try:
            text = target.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        blocks.append(f"### {path}\n```\n{text}\n```")
    return "\n\n".join(blocks)


def _run_arbiter(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    failures: list[dict[str, str]],
) -> tuple[list[dict[str, str]], str]:
    """Returns (classifications, error). Each classification:
    {test, verdict, citation, explanation} with verdict possibly downgraded to
    'invalid' when a required citation is missing."""
    feature = str(state["feature_name"])
    xvc = build_track_context(ctx, state)
    error = _load_blind_inputs(xvc) if xvc.blind.exists() else "blind clone missing for arbiter inputs"
    spec_text = xvc.spec_text
    schemas_text = xvc.schemas_text
    schemas = xvc.schemas
    if error:
        # Clone may already be gone on a resumed run; fall back to main-tree
        # artifacts (the schema is drift-guarded, the spec is committed).
        spec_path = ctx.stage_output_path(feature, ctx.START_STAGE)
        schemas_path = ctx.feature_schemas_path(feature)
        try:
            spec_text = spec_path.read_text(encoding="utf-8-sig", errors="replace")
            schemas_text = schemas_path.read_text(encoding="utf-8-sig", errors="replace")
            parsed = loads_json_text(schemas_text)
            schemas = parsed if isinstance(parsed, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            return [], f"arbiter inputs unavailable: {exc}"
    manifest = read_json_file(_manifest_path(xv_dir(ctx, feature)), {})
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    tests_text = _acceptance_sources(ctx.ROOT)
    impl_text = _impl_sources_for_arbiter(ctx, schemas)
    capture = xv_dir(ctx, feature) / "arbiter_capture.json"
    if capture.exists():
        capture.unlink()
    prompt = _arbiter_prompt(
        ctx, state, failures, tests_text, impl_text, manifest_text, schemas_text, spec_text, capture
    )
    result = _run_provider(
        xvc.commands["arbiter"],
        prompt,
        ctx.ROOT,
        xv_dir(ctx, feature) / "logs" / f"arbiter_{ctx.now_stamp()}",
        xvc.timeout_seconds,
    )
    verdict = _provider_json(result, capture)
    raw = verdict.get("classifications") if isinstance(verdict, dict) else None
    if not isinstance(raw, list) or not raw:
        return [], "arbiter returned no classifications"
    classifications: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        verdict_value = str(item.get("verdict") or "").strip()
        citation = str(item.get("citation") or "").strip()
        if verdict_value not in ALLOWED_VERDICTS:
            verdict_value = VERDICT_INVALID
        elif verdict_value in {VERDICT_TEST, VERDICT_SPEC} and not citation:
            # 인용 불가 = 판정 무효 (INV-5 safeguard): never reroute tests
            # without a spec-grounded justification.
            verdict_value = VERDICT_INVALID
        classifications.append(
            {
                "test": str(item.get("test") or "").strip(),
                "verdict": verdict_value,
                "citation": citation,
                "explanation": str(item.get("explanation") or "").strip()[:1200],
            }
        )
    if not classifications:
        return [], "arbiter classifications were unusable"
    return classifications, ""


def _rewrite_tests(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    findings: list[dict[str, str]],
) -> str | None:
    """Blind test rewrite round: the author sees the arbiter's citation-grounded
    findings, never the implementation. Re-gates and re-freezes on success."""
    xvc = build_track_context(ctx, state)
    if not xvc.blind.exists():
        clone_error = _step_clone(xvc)
        if clone_error:
            return clone_error
        # Restore the authored tests into the fresh clone from the frozen copy.
        frozen = _frozen_dir(xvc.xv) / "tests" / "acceptance"
        if frozen.exists():
            shutil.copytree(frozen, xvc.blind / "tests" / "acceptance", dirs_exist_ok=True)
    error = _load_blind_inputs(xvc)
    if error:
        return error
    tiers, problems = resolve_backends(xvc.schemas)
    if not problems:
        generate_stubs(xvc.blind, xvc.schemas, tiers)
    manifest = read_json_file(_manifest_path(xvc.xv), {})
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    tests_text = _acceptance_sources(xvc.blind)
    prompt = _rewrite_prompt(xvc, manifest_text, tests_text, [dict(item) for item in findings])
    result = _run_provider(
        xvc.commands["rewrite"],
        prompt,
        xvc.blind,
        xvc.logs / f"rewrite_{ctx.now_stamp()}",
        xvc.timeout_seconds,
    )
    if result.get("timed_out"):
        return "test rewrite timed out"
    gate = _gate_errors(xvc, manifest if isinstance(manifest, dict) else {})
    if gate:
        return "test rewrite failed the mechanical gate:\n" + "\n".join(f"- {g}" for g in gate)
    track = _read_track(xvc.xv)
    freeze_error = _step_freeze(xvc, track)
    if freeze_error:
        return freeze_error
    _write_track(xvc.xv, track)
    return None


def _record_decision(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    *,
    verdict: str,
    round_index: int,
    classifications: list[dict[str, str]] | None = None,
    failures: list[dict[str, str]] | None = None,
    detail: str = "",
    human_override: bool = False,
) -> dict[str, Any]:
    feature = str(state["feature_name"])
    track = _read_track(xv_dir(ctx, feature))
    tiers = track.get("tiers") if isinstance(track.get("tiers"), dict) else {}
    tier_values = list(tiers.values()) if isinstance(tiers, dict) else []
    record = {
        "id": f"xv-{feature}-{ctx.now_stamp()}",
        "feature": feature,
        "at": ctx.iso_now(),
        "round": round_index,
        "verdict": verdict,
        "tier_summary": {
            "t1_python": tier_values.count("t1-python"),
            "t2_blackbox": tier_values.count("t2-blackbox"),
        },
        "manifest_cases": track.get("manifest_cases"),
        "failing_tests": [item.get("test") for item in (failures or [])],
        "classifications": classifications or [],
        "detail": detail,
        "human_override": human_override,
        "assignments": state.get("xv_assignments") or track.get("assignments") or {},
    }
    path = ctx.HISTORY_DIR / DECISIONS_FILENAME
    store = read_json_file(path, {"version": 1, "records": []})
    if not isinstance(store, dict):
        store = {"version": 1, "records": []}
    records = store.setdefault("records", [])
    if isinstance(records, list):
        records.append(record)
    ctx.write_json_file(path, store)
    summary = state.setdefault("xv", {})
    if isinstance(summary, dict):
        summary["last_verdict"] = verdict
        summary["rounds_used"] = int(state.get("xv_rounds_used", 0))
        summary["decision_record"] = record["id"]
        summary["tier_summary"] = record["tier_summary"]
    return record


def _quarantine_reason(
    classifications: list[dict[str, str]],
    failures: list[dict[str, str]],
    headline: str,
) -> str:
    lines = [
        f"{QUARANTINE_MARKER}: {headline}",
        "",
        "Cross-validation CONFLICT could not be auto-resolved (CLEAN-only-pass, INV-7).",
        "",
        "## 합류 실패 분류 (arbiter)",
    ]
    if classifications:
        for item in classifications:
            lines.append(
                f"- {item.get('test')}: {item.get('verdict')} | citation: "
                f"{item.get('citation') or '(없음)'} | {item.get('explanation')}"
            )
    else:
        for item in failures:
            lines.append(f"- {item.get('test')}: {item.get('message')}")
    lines.extend(
        [
            "",
            "다음 행동:",
            "- 명세를 명확히 한 뒤 plan부터 다시 파생: spec/plan 수정 후 새 run",
            "- 이 CONFLICT를 의도적으로 수용(override)하고 진행: approve 명령",
            "- 이 feature를 보류: 그대로 두면 배치는 이 feature만 FAIL로 계속 진행",
        ]
    )
    return "\n".join(lines)


def _route_fix(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    result: dict[str, Any],
    failures: list[dict[str, str]],
    classifications: list[dict[str, str]],
) -> None:
    """Downgrade the verify verdict so the existing verify->fix rail re-runs the
    implementation. Mirrors the Phase 2 conformance downgrade, but consumes the
    separate xv adjudication budget instead of the verify/fix budget."""
    items: list[str] = []
    notes = {item.get("test"): item for item in classifications if item.get("verdict") == VERDICT_IMPL}
    for failure in failures:
        name = failure.get("test") or ""
        note = notes.get(name)
        line = f"{name}: {failure.get('message') or '(no assertion message)'}"
        if note and note.get("explanation"):
            line += f" | arbiter: {note['explanation'][:300]}"
        items.append(line)
    reason = (
        "Cross-validation acceptance tests failed and the arbiter classified the "
        "implementation as at fault. Make the implementation satisfy the schema/"
        "spec contract; the acceptance tests are authoritative for this round."
    )
    result["status"] = ResultStatus.FAIL
    result["next_stage"] = ctx.VERIFY_RETRY_TARGET_STAGE
    result["harness_commit_required"] = False
    result["blocking_reason"] = reason
    result["xv_routing"] = True
    result["fix_inputs"] = {
        "reason": "cross-validation acceptance failure (arbiter: impl_fault)",
        "items": items,
        "authoritative": True,
    }
    verify_result_path = ctx.stage_result_json_path(str(state["feature_name"]), ctx.VERIFY_STAGE)
    try:
        ctx.write_json_file(verify_result_path, result)
    except OSError as exc:
        ctx.log_event(
            state,
            "xv_fix_route_persist_failed",
            f"could not persist xv verdict to {ctx.rel(verify_result_path)}: {exc}",
            stage=ctx.VERIFY_STAGE,
            console=False,
        )


def process_join(ctx: HarnessRuntime, state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """The join + verdict state machine, called at verify PASS (post-conformance,
    pre-commit). Returns a directive for the workflow:

    - {"action": "clean"}  -> CLEAN (or human override): continue the pipeline.
    - {"action": "fix"}    -> verify downgraded in-place; existing FAIL rail runs.
    - {"action": "block", "reason": ...} -> quarantine/infra block.
    """
    feature = str(state["feature_name"])
    max_rounds = int(state.get("xv_max_rounds") or DEFAULT_MAX_ROUNDS)

    if state.get("xv_override"):
        _copy_frozen_acceptance(ctx, state)
        _record_decision(
            ctx,
            state,
            verdict="OVERRIDE",
            round_index=int(state.get("xv_rounds_used", 0)),
            detail="human approved despite CONFLICT",
            human_override=True,
        )
        ctx.log_event(state, "xv_override_accepted", "CONFLICT accepted by human override", stage=ctx.VERIFY_STAGE)
        remove_blind_clone(ctx, feature)
        return {"action": "clean"}

    track = _wait_for_track(ctx, state)
    if track.get("status") != "frozen":
        reason = (
            "Cross-validation blind track failed: "
            + str(track.get("error") or "unknown error")
            + f"\nInspect {ctx.rel(xv_dir(ctx, feature))} and resume to retry the track."
        )
        return {"action": "block", "reason": reason}

    while True:
        copied, conflicts = _copy_frozen_acceptance(ctx, state)
        if conflicts:
            reason = _quarantine_reason(
                [],
                [{"test": rel, "message": "boundary conflict: file already exists in impl tree"} for rel in conflicts],
                "tree partition violated at join (impl tree already owns acceptance paths)",
            )
            _record_decision(
                ctx, state, verdict="CONFLICT-BOUNDARY", round_index=int(state.get("xv_rounds_used", 0)),
                detail="; ".join(conflicts),
            )
            return {"action": "block", "reason": reason}

        passed, failures, run_error = _run_acceptance(ctx, state)
        if run_error:
            return {
                "action": "block",
                "reason": f"Cross-validation acceptance run failed to execute: {run_error}",
            }
        if passed:
            record = _record_decision(
                ctx,
                state,
                verdict="CLEAN",
                round_index=int(state.get("xv_rounds_used", 0)),
                detail=f"{len(copied)} acceptance files",
            )
            ctx.log_event(
                state,
                "xv_clean",
                "cross-validation CLEAN: blind acceptance suite fully passes",
                stage=ctx.VERIFY_STAGE,
                files=len(copied),
                rounds=int(state.get("xv_rounds_used", 0)),
                decision=record["id"],
            )
            _promote_acceptance_command(ctx, state)
            remove_blind_clone(ctx, feature)
            return {"action": "clean"}

        rounds_used = int(state.get("xv_rounds_used", 0))
        if rounds_used >= max_rounds:
            reason = _quarantine_reason(
                [], failures, f"adjudication budget exhausted ({rounds_used}/{max_rounds})"
            )
            _record_decision(
                ctx, state, verdict="EXHAUSTED", round_index=rounds_used, failures=failures
            )
            return {"action": "block", "reason": reason}

        classifications, arbiter_error = _run_arbiter(ctx, state, failures)
        if arbiter_error:
            reason = _quarantine_reason([], failures, f"arbiter unavailable: {arbiter_error}")
            _record_decision(
                ctx, state, verdict="ARBITER-FAILED", round_index=rounds_used, failures=failures,
                detail=arbiter_error,
            )
            return {"action": "block", "reason": reason}

        verdicts = {item["verdict"] for item in classifications}
        ctx.log_event(
            state,
            "xv_arbiter_verdict",
            "arbiter classified the CONFLICT",
            stage=ctx.VERIFY_STAGE,
            verdicts=",".join(sorted(verdicts)),
            failing=len(failures),
        )

        if VERDICT_SPEC in verdicts or VERDICT_INVALID in verdicts:
            headline = (
                "spec ambiguity surfaced -- both derivations are defensible"
                if VERDICT_SPEC in verdicts
                else "arbiter verdict lacked a grounding citation (invalid)"
            )
            _record_decision(
                ctx,
                state,
                verdict="SPEC-AMBIGUOUS" if VERDICT_SPEC in verdicts else "ARBITER-INVALID",
                round_index=rounds_used,
                classifications=classifications,
                failures=failures,
            )
            return {
                "action": "block",
                "reason": _quarantine_reason(classifications, failures, headline),
            }

        state["xv_rounds_used"] = rounds_used + 1
        if VERDICT_IMPL in verdicts:
            _record_decision(
                ctx,
                state,
                verdict="CONFLICT-IMPL",
                round_index=state["xv_rounds_used"],
                classifications=classifications,
                failures=failures,
            )
            _route_fix(ctx, state, result, failures, classifications)
            ctx.log_event(
                state,
                "xv_routed_fix",
                "arbiter: implementation at fault; routing to fix",
                stage=ctx.VERIFY_STAGE,
                round=state["xv_rounds_used"],
            )
            ctx.save_state(state)
            return {"action": "fix"}

        # Only test faults remain: rewrite blind, re-join in this same call.
        findings = [item for item in classifications if item["verdict"] == VERDICT_TEST]
        _record_decision(
            ctx,
            state,
            verdict="CONFLICT-TEST",
            round_index=state["xv_rounds_used"],
            classifications=classifications,
            failures=failures,
        )
        ctx.log_event(
            state,
            "xv_routed_test_rewrite",
            "arbiter: tests over-specified; rewriting blind tests",
            stage=ctx.VERIFY_STAGE,
            round=state["xv_rounds_used"],
        )
        ctx.save_state(state)
        rewrite_error = _rewrite_tests(ctx, state, findings)
        if rewrite_error:
            reason = _quarantine_reason(
                classifications, failures, f"blind test rewrite failed: {rewrite_error}"
            )
            return {"action": "block", "reason": reason}


def _promote_acceptance_command(ctx: HarnessRuntime, state: dict[str, Any]) -> None:
    """CLEAN aftermath: the acceptance suite becomes a permanent regression
    gate -- promote `python -m pytest tests/acceptance` into the project
    verification config (same machinery dynamic verify commands use)."""
    from . import verification as verification_core

    feature = str(state["feature_name"])
    spec, rejection = verification_core._coerce_dynamic_command(  # noqa: SLF001 - same-package reuse
        ctx,
        feature,
        {
            "name": "acceptance_tests",
            "command": ["python", "-m", "pytest", ACCEPTANCE_DIR],
            "persist": True,
        },
        "cross_validation",
        1,
        int(ctx.DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS or 600),
    )
    if rejection or spec is None:
        ctx.log_event(
            state,
            "xv_promotion_skipped",
            f"could not promote acceptance command: {rejection}",
            stage=ctx.VERIFY_STAGE,
            console=False,
        )
        return
    promoted = verification_core.promote_dynamic_verification_commands(ctx, feature, [spec])
    if promoted:
        ctx.log_event(
            state,
            "xv_acceptance_promoted",
            "promoted acceptance suite to project verification commands",
            stage=ctx.VERIFY_STAGE,
            config=ctx.rel(ctx.project_config_path()),
        )


# ---------------------------------------------------------------------------
# Tree-partition enforcement for the impl track (flag-gated, preset-invisible)
# ---------------------------------------------------------------------------


def _expand_acceptance_entry(ctx: HarnessRuntime, normalized: str) -> list[str]:
    """git status collapses a wholly-untracked directory to one entry
    ("tests/"). Expand such entries to the concrete acceptance files they
    contain so the partition guard cannot be blinded by the collapse."""
    trimmed = normalized.rstrip("/")
    if trimmed == ACCEPTANCE_DIR or normalized.startswith(ACCEPTANCE_DIR + "/"):
        if normalized.endswith("/") or trimmed == ACCEPTANCE_DIR:
            base = ctx.ROOT.joinpath(*trimmed.split("/"))
            if base.is_dir():
                return [
                    f"{ACCEPTANCE_DIR}/" + p.relative_to(ctx.ROOT / "tests" / "acceptance").as_posix()
                    for p in base.rglob("*")
                    if p.is_file()
                ]
        return [normalized]
    if trimmed == "tests":
        acceptance_root = ctx.ROOT / "tests" / "acceptance"
        if acceptance_root.is_dir():
            return [
                f"{ACCEPTANCE_DIR}/" + p.relative_to(acceptance_root).as_posix()
                for p in acceptance_root.rglob("*")
                if p.is_file()
            ]
    return []


def partition_violations(ctx: HarnessRuntime, state: dict[str, Any], stage: str) -> list[str]:
    """When cross-validation is on, the impl track must never write
    tests/acceptance -- that is the blind track's exclusive territory. Enforced
    here (workflow level) instead of preset frontmatter so the flag-off
    pipeline stays byte-identical (사전 결정 10)."""
    if not enabled(state):
        return []
    if stage == ctx.PLAN_STAGE or stage == ctx.START_STAGE:
        return []
    copied = {str(item) for item in state.get("xv_copied_files", []) or []}
    violations: list[str] = []
    for path in ctx.filtered_changed_paths(state, stage):
        normalized = str(path).replace("\\", "/")
        for candidate in _expand_acceptance_entry(ctx, normalized):
            if candidate in copied:
                continue  # the harness itself copied this file at join
            violations.append(
                f"{candidate} is reserved for the blind acceptance track "
                "(tree partition; cross-validation is enabled)"
            )
    return violations
