#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from harness_core.docx_validation import validate_docx_file as core_validate_docx_file
from harness_core.schemas_validation import validate_schemas_file as core_validate_schemas_file
from harness_core.schemas_validation import (
    validate_schemas_conformance_file as core_validate_schemas_conformance_file,
)
from harness_core.console import (
    color_text,
    event_line_for_console,
    format_bytes,  # re-exported into ctx
    format_duration,  # re-exported into ctx
    status_style,
)
from harness_core.context import HarnessContext, HarnessRuntime
from harness_core.errors import HarnessError
from harness_core.frontmatter import parse_frontmatter, parse_scalar
from harness_core.json_io import (
    read_json_file,
    read_json_value_file,
    replace_with_retry,
    write_json_file,
)
from harness_core.status import RunStatus
from harness_core import cross_validation as cross_validation_core
from harness_core import deep_thinking as deep_thinking_core
from harness_core import history as history_core
from harness_core import pipeline as pipeline_core
from harness_core import policy as policy_core
from harness_core import process as process_core
from harness_core import providers as provider_core
from harness_core import stage_runtime as stage_runtime_core
from harness_core import verification as verification_core
from harness_core import workflow as workflow_core
from harness_core.text import (
    boolish,
    compact_history_text,
    history_list,
    history_object_list,
    markdown_section_items,
    markdown_sections,
    norm_repo_path,
    section_matches,
    slugify,
    validate_slug,
)


def _ctx() -> HarnessRuntime:
    """Build the typed HarnessRuntime passed into harness_core from this module's
    current namespace (constants + facade functions). Rebuilt per call so it
    always reflects the active pipeline's rebound constants. The concrete carrier
    is HarnessContext; the contract callers see is the HarnessRuntime Protocol."""
    return HarnessContext.from_namespace(globals())


ROOT = Path(__file__).resolve().parents[1]
AI_DIR = ROOT / ".ai"
PROJECT_DIR = ROOT / ".project"
HARNESS_CONFIG_PATH = AI_DIR / "harness.config.json"
PROJECT_CONFIG_PATH = PROJECT_DIR / "harness.config.json"
RUNS_DIR = PROJECT_DIR / "runs"
FEATURES_DIR = PROJECT_DIR / "features"
DOCS_DIR = PROJECT_DIR / "docs"
HISTORY_DIR = PROJECT_DIR / "history"
PROJECT_CONTRACT_PATH = PROJECT_DIR / "project_contract.md"
PC_CANDIDATES_PATH = HISTORY_DIR / "pc_candidates.json"
HISTORY_SCHEMA_VERSION = 1
PC_CANDIDATES_SCHEMA_VERSION = 1
PC_PENDING_STATUS = "미정"
PC_APPROVED_STATUS = "승인"
PC_REJECTED_STATUS = "기각"
PC_REVIEW_STAGE = "pc_candidates"
PC_PROJECT_WIDE_SCOPE = "project_wide"

DEFAULT_MAX_VERIFY_FIX_RETRIES = 3
DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS = 600
DEFAULT_PROVIDER_HEARTBEAT_SECONDS = 30
DEFAULT_PROVIDER_OUTPUT_CHECK_SECONDS = 60
DEFAULT_PROVIDER_OUTPUT_STABLE_CHECKS = 2
DEFAULT_DOCTOR_DEEP_TIMEOUT_SECONDS = 60


# Per-pipeline-mode constants (PIPELINE_MODE, PRESETS_DIR, STAGES,
# STAGE_OUTPUTS, COMMIT_STAGES and the named stage roles) are bound from the
# PipelineConfig registry by apply_pipeline(). harness.py runs as the "full"
# pipeline; the fast/standard entrypoints re-bind these by calling
# base.apply_pipeline(...) right after importing this module.
def apply_pipeline(mode: str) -> None:
    config = pipeline_core.PIPELINES[mode]
    g = globals()
    g["PIPELINE_MODE"] = config.mode
    g["PRESETS_DIR"] = AI_DIR / "presets" / config.presets_subdir
    g["STAGES"] = list(config.stages)
    g["STAGE_OUTPUTS"] = dict(config.stage_outputs)
    g["COMMIT_STAGES"] = set(config.stages)
    g["NO_COMMIT_STAGES"] = set()
    g["START_STAGE"] = config.start_stage
    g["DEVELOP_STAGE"] = config.develop_stage
    g["VERIFY_STAGE"] = config.verify_stage
    g["VERIFY_RETRY_TARGET_STAGE"] = config.verify_retry_target_stage
    g["FIX_STAGE"] = config.fix_stage
    g["DOCUMENT_STAGE"] = config.document_stage
    g["PLAN_STAGE"] = config.plan_stage
    g["PLAN_SCHEMAS_REQUIRED"] = config.plan_schemas_required
    g["SCHEMAS_CONFORMANCE_REQUIRED"] = config.schemas_conformance_required


apply_pipeline("full")

PROVIDER_BY_MODEL = {
    "Codex": "codex",
    "Claude": "claude",
    "Antigravity": "agy",
}
PROVIDERS = ("codex", "claude", "agy")

DEFAULT_PROVIDER_COMMANDS = {
    "codex": [
        "codex.cmd",
        "exec",
        "--cd",
        "{cwd}",
        "--sandbox",
        "workspace-write",
        "--dangerously-bypass-approvals-and-sandbox",
        "-",
    ],
    "claude": [
        "claude",
        "-p",
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "text",
    ],
    "agy": [
        "agy.exe",
        "--add-dir",
        "{cwd}",
        "--log-file",
        "{log_file}",
        "--print",
        "--print-timeout",
        "30m",
        "--dangerously-skip-permissions",
    ],
}

DEFAULT_PERFORMANCE = "medium"

DEFAULT_PROVIDER_CAPABILITIES = {
    "codex": ["plan", "code_write", "review", "verify", "document", "pc_extract"],
    "claude": ["plan", "code_write", "review", "verify", "document", "pc_extract"],
    "agy": ["plan", "review", "verify", "document", "pc_extract"],
}

DEFAULT_MODEL_POLICY = {
    "min_distinct_agents": 2,
    "no_adjacent_same_provider": True,
    "on_independence_violation": "block",
    "code_write_allowed": ["claude", "codex"],
    "code_write_denied": ["agy"],
    "code_write_order": ["claude", "codex"],
    "non_code_order": ["agy", "codex", "claude"],
    "role_orders": {
        "plan": ["agy", "codex", "claude"],
        "review": ["agy", "codex", "claude"],
        "verify": ["codex", "agy", "claude"],
        "document": ["agy", "codex", "claude"],
        "pc_extract": ["claude", "codex", "agy"],
    },
    "avoid_reusing_recent_code_writer_for_review": True,
    "reserve_code_writers_for_code_stages": True,
}

PERFORMANCE_PROFILES = {
    "high": {
        "codex": {
            "model": "gpt-5.5",
            "model_reasoning_effort": "xhigh",
        },
        "claude": {
            "model": "claude-opus-4-8",
            "effort": "xhigh",
        },
        "agy": {
            "model": "agy-high",
        },
    },
    "medium": {
        "codex": {
            "model": "gpt-5.5",
            "model_reasoning_effort": "xhigh",
        },
        "claude": {
            "model": "claude-sonnet-4-6",
            "effort": "xhigh",
        },
        "agy": {
            "model": "agy-medium",
        },
    },
    "lite": {
        "codex": {
            "model": "gpt-5.5",
            "model_reasoning_effort": "medium",
        },
        "claude": {
            "model": "claude-sonnet-4-6",
            "effort": "high",
        },
        "agy": {
            "model": "agy-lite",
        },
    },
}


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def ensure_dirs() -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


def git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return process_core.git(ROOT, args, check)


def git_output(args: list[str]) -> str:
    return process_core.git_output(ROOT, args)


def unmerged_run_branches() -> list[dict[str, str]]:
    """Completed runs whose per-run branch still exists and is NOT yet merged
    into its base. A branch counts as handled when it is merged (its tip is an
    ancestor of base) OR deleted -- the squash-or-delete completion rule. This
    is the run-per-branch successor to the old unpushed-commit interlock."""
    if not RUNS_DIR.exists():
        return []
    pending: list[dict[str, str]] = []
    for path in sorted(RUNS_DIR.glob("*/run.json")):
        try:
            parsed = read_json_value_file(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        if str(parsed.get("status") or "") != RunStatus.COMPLETE:
            continue
        run_branch = str(parsed.get("run_branch") or "")
        base_branch = str(parsed.get("base_branch") or "")
        if not run_branch or not base_branch:
            continue  # linear run (no branch created) -> nothing to merge
        if not process_core.branch_exists(ROOT, run_branch):
            continue  # branch deleted -> handled (covers squash-then-delete)
        if not process_core.branch_exists(ROOT, base_branch):
            continue  # base gone -> cannot determine; fail open, do not block
        if process_core.branch_is_merged(ROOT, run_branch, base_branch):
            continue  # already merged into base
        pending.append(
            {
                "feature": str(parsed.get("feature_name") or path.parent.name),
                "run_branch": run_branch,
                "base_branch": base_branch,
            }
        )
    return pending


def format_unmerged_run_branches_message(runs: list[dict[str, str]]) -> str:
    lines = [
        color_text("새 파이프라인을 시작할 수 없습니다.", "red", "bold"),
        "",
        (
            f"아직 base 브랜치에 merge되지 않은 완료된 run이 "
            f"{color_text(str(len(runs)), 'yellow', 'bold')}개 있습니다."
        ),
        "하네스는 한 번의 새 파이프라인을 하나의 기능 단위로 취급합니다.",
        "이전 run의 브랜치를 base에 merge(또는 삭제)한 뒤 다시 시작하세요.",
        "",
        color_text("미-merge run 브랜치:", "yellow", "bold"),
    ]
    for run in runs:
        lines.append(f"  - {run['feature']}: {run['run_branch']} -> {run['base_branch']}")
    lines.extend(
        [
            "",
            (
                f"{color_text('권장 조치:', 'green', 'bold')} "
                "git checkout <base> && git merge --no-ff <run-branch>"
            ),
        ]
    )
    return "\n".join(lines)


def assert_prev_run_branch_merged() -> None:
    pending = unmerged_run_branches()
    if pending:
        raise HarnessError(format_unmerged_run_branches_message(pending))


def incomplete_run_summaries() -> list[dict[str, str]]:
    if not RUNS_DIR.exists():
        return []
    summaries: list[dict[str, str]] = []
    for path in sorted(RUNS_DIR.glob("*/run.json")):
        try:
            parsed = read_json_value_file(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            summaries.append(
                {
                    "feature": path.parent.name,
                    "status": "unreadable",
                    "stage": "-",
                    "reason": str(exc),
                }
            )
            continue
        if not isinstance(parsed, dict):
            summaries.append(
                {
                    "feature": path.parent.name,
                    "status": "invalid",
                    "stage": "-",
                    "reason": "run.json is not an object",
                }
            )
            continue
        status = str(parsed.get("status") or "unknown")
        if status == RunStatus.COMPLETE:
            continue
        blocked = parsed.get("blocked")
        reason = str(blocked.get("reason") or "") if isinstance(blocked, dict) else ""
        summaries.append(
            {
                "feature": str(parsed.get("feature_name") or path.parent.name),
                "status": status,
                "stage": str(parsed.get("current_stage") or "-"),
                "reason": reason,
            }
        )
    return summaries


def format_incomplete_runs_message(runs: list[dict[str, str]]) -> str:
    lines = [
        color_text("새 파이프라인을 시작할 수 없습니다.", "red", "bold"),
        "",
        f"완료되지 않은 하네스 run이 {color_text(str(len(runs)), 'yellow', 'bold')}개 있습니다.",
        "하네스는 한 번의 새 파이프라인을 하나의 기능 단위로 취급합니다.",
        "기존 run을 먼저 정리한 뒤 다시 시작하세요.",
        "",
        color_text("미완료 run:", "yellow", "bold"),
    ]
    for run in runs:
        lines.append(f"  - {run['feature']}: {run['status']} at {run['stage']}")
        reason = run.get("reason", "")
        if reason:
            lines.append(f"    reason: {reason[:200]}")
    lines.extend(
        [
            "",
            f"{color_text('권장 조치:', 'green', 'bold')} resume / retry / cleanup",
        ]
    )
    return "\n".join(lines)


def assert_no_incomplete_runs_for_new_run() -> None:
    runs = incomplete_run_summaries()
    if runs:
        raise HarnessError(format_incomplete_runs_message(runs))


def git_changed_paths() -> list[str]:
    return process_core.git_changed_paths(ROOT)


def git_show_file(ref: str, rel_path: str) -> bytes | None:
    return process_core.git_show_file(ROOT, ref, rel_path)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_harness_internal_path(path: str, feature: str) -> bool:
    return policy_core.is_harness_internal_path(path, feature)


def is_snapshot_generated_path(path: str) -> bool:
    return policy_core.is_snapshot_generated_path(path)


def git_ignored_paths(paths: list[str]) -> set[str]:
    return policy_core.git_ignored_paths(_ctx(), paths)


def snapshot_excluded_paths(paths: list[str]) -> set[str]:
    return policy_core.snapshot_excluded_paths(_ctx(), paths)


def repo_child_path(parent: Path, name: str) -> str:
    return policy_core.repo_child_path(_ctx(), parent, name)


def file_policy_snapshot(feature: str) -> dict[str, str]:
    return policy_core.file_policy_snapshot(_ctx(), feature)


def changed_since_snapshot(before: dict[str, str], feature: str) -> list[str]:
    return policy_core.changed_since_snapshot(_ctx(), before, feature)


def git_head() -> str:
    return process_core.git_head(ROOT)


def git_add(paths: list[str]) -> None:
    return process_core.git_add(ROOT, paths)


def git_commit(message: str, amend: bool = False) -> str:
    return process_core.git_commit(ROOT, message, amend)


def current_branch() -> str:
    return process_core.current_branch(ROOT)


def branch_exists(name: str) -> bool:
    return process_core.branch_exists(ROOT, name)


def checkout_new_branch(name: str) -> None:
    return process_core.checkout_new_branch(ROOT, name)


def branch_is_merged(branch: str, base: str) -> bool:
    return process_core.branch_is_merged(ROOT, branch, base)


def merge_tree_conflicts(base: str, branch: str) -> "list[str] | None":
    return process_core.merge_tree_conflicts(ROOT, base, branch)


def read_preset(stage: str) -> tuple[dict[str, Any], str, str]:
    path = PRESETS_DIR / f"{stage}.md"
    if not path.exists():
        raise HarnessError(f"Missing preset: {path}")
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    return meta, body, text


def load_config() -> dict[str, Any]:
    return provider_core.load_config(_ctx())


def config_path() -> Path:
    return provider_core.config_path(_ctx())


def project_config_path() -> Path:
    return provider_core.project_config_path(_ctx())


def write_config(config: dict[str, Any]) -> None:
    return provider_core.write_config(_ctx(), config)


def load_project_config() -> dict[str, Any]:
    return provider_core.load_project_config(_ctx())


def write_project_config(config: dict[str, Any]) -> None:
    return provider_core.write_project_config(_ctx(), config)


def raw_provider_command(provider: str) -> list[str]:
    return provider_core.raw_provider_command(_ctx(), provider)


def normalize_performance(value: Any | None) -> str:
    return provider_core.normalize_performance(_ctx(), value)


def performance_profile(value: Any | None) -> dict[str, dict[str, str]]:
    return provider_core.performance_profile(_ctx(), value)


def provider_performance_settings(provider: str, performance: Any | None) -> dict[str, str]:
    return provider_core.provider_performance_settings(_ctx(), provider, performance)


def command_has_option(command: list[str], *options: str) -> bool:
    return provider_core.command_has_option(command, *options)


def command_has_config_key(command: list[str], key: str) -> bool:
    return provider_core.command_has_config_key(command, key)


def append_before_stdin_prompt(command: list[str], extra: list[str]) -> list[str]:
    return provider_core.append_before_stdin_prompt(command, extra)


def apply_performance_to_command(
    provider: str,
    command: list[str],
    performance: Any | None,
) -> list[str]:
    return provider_core.apply_performance_to_command(_ctx(), provider, command, performance)


def prepare_provider_command(
    provider: str,
    prompt_text: str | None = None,
    prompt_file: Path | None = None,
    log_file: Path | None = None,
    performance: Any | None = None,
) -> tuple[list[str], bool]:
    return provider_core.prepare_provider_command(
        _ctx(),
        provider,
        prompt_text,
        prompt_file,
        log_file,
        performance,
    )


def provider_command(provider: str) -> list[str]:
    return provider_core.provider_command(_ctx(), provider)


def redact_prompt_command(command: list[str], prompt_text: str | None) -> list[str]:
    return provider_core.redact_prompt_command(command, prompt_text)


def run_text_provider_prompt(
    provider: str,
    prompt_text: str,
    *,
    logs_dir: Path,
    log_prefix: str,
    timeout_seconds: int = 3600,
    performance: Any | None = None,
) -> dict[str, Any]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    safe_prefix = re.sub(r"[^a-zA-Z0-9_.-]+", "-", log_prefix).strip("-") or "provider"
    stdout_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.out.txt"
    stderr_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.err.txt"
    meta_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.json"
    cli_log_path = logs_dir / f"{safe_prefix}_{provider}_{stamp}.cli.log"

    command, prompt_in_command = prepare_provider_command(
        provider,
        prompt_text,
        log_file=cli_log_path.resolve(),
        performance=performance,
    )
    executable = resolve_executable(command)
    if not executable:
        raise HarnessError(f"Provider executable not found for {provider}: {command[0]}")

    started = time.time()
    # Popen (not subprocess.run) so a timeout can kill the whole process tree
    # before reading remaining output. subprocess.run's internal timeout handling
    # kills only the direct child then calls communicate() with no timeout; on
    # Windows the surviving grandchild (node behind a .cmd shim) holds the pipe
    # handles open, so that recovery read blocks forever -- turning the timeout
    # into an unbounded hang.
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
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
        elapsed = round(time.time() - started, 2)
        stdout_text = stdout_text or ""
        stderr_text = stderr_text or ""
        timed_out = False
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        process_core.kill_process_tree(proc)
        try:
            stdout_text, stderr_text = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            stdout_text, stderr_text = "", ""
        elapsed = round(time.time() - started, 2)
        stdout_text = stdout_text or ""
        stderr_text = (stderr_text or "") + f"\nTimed out after {timeout_seconds} seconds.\n"
        timed_out = True
        returncode = None

    stdout_path.write_text(str(stdout_text), encoding="utf-8")
    stderr_path.write_text(str(stderr_text), encoding="utf-8")
    result = {
        "provider": provider,
        "command": redact_prompt_command(command, prompt_text),
        "returncode": returncode,
        "timed_out": timed_out,
        "elapsed_seconds": elapsed,
        "stdout": rel(stdout_path),
        "stderr": rel(stderr_path),
        "meta": rel(meta_path),
        "provider_log": rel(cli_log_path),
        "finished_at": iso_now(),
    }
    meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result | {"stdout_text": str(stdout_text), "stderr_text": str(stderr_text)}


def expand_runtime_placeholders(value: Any, feature: str) -> str:
    return (
        str(value)
        .replace("{root}", str(ROOT))
        .replace("{cwd}", str(ROOT))
        .replace("{feature}", feature)
    )


def configured_verification_commands(feature: str) -> tuple[list[dict[str, Any]], bool]:
    return verification_core.configured_verification_commands(_ctx(), feature)


def preset_provider_for_stage(stage: str) -> str | None:
    return provider_core.preset_provider_for_stage(_ctx(), stage)


def resolve_executable(command: list[str]) -> str | None:
    return provider_core.resolve_executable(command)


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    return provider_core.merge_dicts(base, override)


def model_policy() -> dict[str, Any]:
    return provider_core.model_policy(_ctx())


def ordered_unique(values: list[str] | tuple[str, ...]) -> list[str]:
    return provider_core.ordered_unique(values)


def known_provider_names() -> list[str]:
    return provider_core.known_provider_names(_ctx())


def provider_config(provider: str) -> dict[str, Any]:
    return provider_core.provider_config(_ctx(), provider)


def provider_enabled(provider: str) -> bool:
    return provider_core.provider_enabled(_ctx(), provider)


def provider_capabilities(provider: str) -> set[str]:
    return provider_core.provider_capabilities(_ctx(), provider)


def provider_available(provider: str) -> bool:
    return provider_core.provider_available(_ctx(), provider)


def available_providers() -> list[str]:
    return provider_core.available_providers(_ctx())


def pipeline_extracts_pc_candidates(pipeline_mode: Any) -> bool:
    return provider_core.pipeline_extracts_pc_candidates(_ctx(), pipeline_mode)


def provider_schedule_stages(state: dict[str, Any]) -> list[str]:
    return provider_core.provider_schedule_stages(_ctx(), state)


def stage_role(stage: str) -> str:
    return provider_core.stage_role(_ctx(), stage)


def provider_order_for_role(stage: str, role: str, policy: dict[str, Any]) -> list[str]:
    return provider_core.provider_order_for_role(_ctx(), stage, role, policy)


def candidate_providers_for_stage(
    stage: str,
    policy: dict[str, Any],
    available: list[str],
) -> list[str]:
    return provider_core.candidate_providers_for_stage(_ctx(), stage, policy, available)


def latest_code_writer(assignments: dict[str, str], stages: list[str]) -> str | None:
    return provider_core.latest_code_writer(_ctx(), assignments, stages)


def stage_provider_score(
    stage: str,
    provider: str,
    candidates: list[str],
    assignments: dict[str, str],
    ordered_stages: list[str],
    policy: dict[str, Any],
) -> int:
    return provider_core.stage_provider_score(
        _ctx(),
        stage,
        provider,
        candidates,
        assignments,
        ordered_stages,
        policy,
    )


def compute_provider_schedule(
    state: dict[str, Any],
    *,
    strict_independence: bool,
) -> dict[str, str] | None:
    return provider_core.compute_provider_schedule(
        _ctx(),
        state,
        strict_independence=strict_independence,
    )


def build_provider_schedule(state: dict[str, Any]) -> dict[str, str]:
    return provider_core.build_provider_schedule(_ctx(), state)


def ensure_provider_schedule(
    state: dict[str, Any],
    *,
    persist: bool = True,
    console: bool = False,
    record_event: bool = True,
) -> dict[str, str]:
    return provider_core.ensure_provider_schedule(
        _ctx(),
        state,
        persist=persist,
        console=console,
        record_event=record_event,
    )


def provider_for_stage(stage: str, state: dict[str, Any] | None = None) -> str:
    return provider_core.provider_for_stage(_ctx(), stage, state)


def feature_dir(feature: str) -> Path:
    return FEATURES_DIR / feature


def run_dir(feature: str) -> Path:
    return RUNS_DIR / feature


def state_path(feature: str) -> Path:
    return run_dir(feature) / "run.json"


def stage_output_path(feature: str, stage: str) -> Path:
    return feature_dir(feature) / STAGE_OUTPUTS[stage]


def stage_result_json_path(feature: str, stage: str) -> Path:
    output = stage_output_path(feature, stage)
    return output.with_name(f"{output.stem}.result.json")


def pipeline_config_for_state(state: dict[str, Any]):
    config = pipeline_core.get(state.get("pipeline_mode"))
    if config:
        return config
    return pipeline_core.get(PIPELINE_MODE) or pipeline_core.PIPELINES[pipeline_core.DEFAULT_MODE]


def pipeline_stages_for_state(state: dict[str, Any]) -> list[str]:
    return list(pipeline_config_for_state(state).stages)


def stage_output_path_for_state(feature: str, stage: str, state: dict[str, Any]) -> Path | None:
    output_name = pipeline_config_for_state(state).stage_outputs.get(stage)
    if not output_name:
        return None
    return feature_dir(feature) / output_name


def stage_result_json_path_for_state(feature: str, stage: str, state: dict[str, Any]) -> Path | None:
    output = stage_output_path_for_state(feature, stage, state)
    if output is None:
        return None
    return output.with_name(f"{output.stem}.result.json")


def load_state(feature: str) -> dict[str, Any]:
    path = state_path(feature)
    if not path.exists():
        raise HarnessError(f"Run not found: {feature}")
    return read_json_value_file(path)


def save_state(state: dict[str, Any]) -> None:
    feature = state["feature_name"]
    path = state_path(feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = iso_now()
    # Write to a sibling temp file first, then atomically replace the target.
    # os.replace is atomic on both POSIX and Windows, so a crash, power loss,
    # or disk-full condition can never leave a half-written run.json behind:
    # either the old file survives intact or the new one fully takes its place.
    # replace_with_retry absorbs transient Windows EACCES (antivirus/indexer
    # briefly holding the file) without giving up atomicity.
    tmp = path.parent / (path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        replace_with_retry(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def run_log_path(feature: str) -> Path:
    return run_dir(feature) / "harness.log"


def verification_dir(feature: str) -> Path:
    return run_dir(feature) / "verification"


def latest_verification_result_path(feature: str) -> Path:
    return verification_dir(feature) / "latest.json"


def history_summary_path() -> Path:
    return history_core.history_summary_path(_ctx())


def history_index_path() -> Path:
    return history_core.history_index_path(_ctx())


def pc_candidates_path() -> Path:
    return history_core.pc_candidates_path(_ctx())


def project_contract_path() -> Path:
    return history_core.project_contract_path(_ctx())


def empty_pc_candidates_store() -> dict[str, Any]:
    return history_core.empty_pc_candidates_store(_ctx())


def read_pc_candidates_store() -> dict[str, Any]:
    return history_core.read_pc_candidates_store(_ctx())


def write_pc_candidates_store(store: dict[str, Any]) -> None:
    return history_core.write_pc_candidates_store(_ctx(), store)


def pending_pc_candidates() -> list[dict[str, Any]]:
    return history_core.pending_pc_candidates(_ctx())


def ensure_project_contract_file() -> None:
    return history_core.ensure_project_contract_file(_ctx())


def project_contract_prompt_text() -> str:
    return history_core.project_contract_prompt_text(_ctx())


def warn_pending_pc_candidates_for_new_run() -> None:
    return history_core.warn_pending_pc_candidates_for_new_run(_ctx())


def ensure_history_store() -> bool:
    return history_core.ensure_history_store(_ctx())


def history_timestamp_id(value: Any) -> str:
    return history_core.history_timestamp_id(_ctx(), value)


def history_event_id(state: dict[str, Any]) -> str:
    return history_core.history_event_id(_ctx(), state)


def safe_stage_text(feature: str, stage: str) -> str:
    return history_core.safe_stage_text(_ctx(), feature, stage)


def load_history_stage_results(feature: str) -> dict[str, dict[str, Any]]:
    return history_core.load_history_stage_results(_ctx(), feature)


def history_source_artifacts(feature: str) -> list[str]:
    return history_core.history_source_artifacts(_ctx(), feature)


def split_event_paths(value: Any) -> list[str]:
    return history_core.split_event_paths(_ctx(), value)


def collect_history_changed_files(
    state: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    return history_core.collect_history_changed_files(_ctx(), state, stage_results)


def load_history_verification(feature: str, stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return history_core.load_history_verification(_ctx(), feature, stage_results)


def collect_history_notes(
    feature: str,
    stage_results: dict[str, dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    return history_core.collect_history_notes(_ctx(), feature, stage_results)


def normalize_unresolved_source_item(
    item: Any,
    *,
    item_type: str,
    status: str,
    disposition: str,
    source_stage: str,
    source_artifact: str,
    default_severity: str = "info",
) -> dict[str, Any] | None:
    return history_core.normalize_unresolved_source_item(_ctx(), item, item_type=item_type, status=status, disposition=disposition, source_stage=source_stage, source_artifact=source_artifact, default_severity=default_severity)


def unresolved_items_from_value(
    value: Any,
    *,
    item_type: str,
    status: str,
    disposition: str,
    source_stage: str,
    source_artifact: str,
    default_severity: str = "info",
) -> list[dict[str, Any]]:
    return history_core.unresolved_items_from_value(_ctx(), value, item_type=item_type, status=status, disposition=disposition, source_stage=source_stage, source_artifact=source_artifact, default_severity=default_severity)


def collect_history_unresolved_items(
    feature: str,
    stage_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return history_core.collect_history_unresolved_items(_ctx(), feature, stage_results)


def stable_history_id(prefix: str, *parts: Any) -> str:
    return history_core.stable_history_id(_ctx(), prefix, *parts)


def read_history_index() -> dict[str, Any]:
    return history_core.read_history_index(_ctx())


def write_history_index(index: dict[str, Any]) -> None:
    return history_core.write_history_index(_ctx(), index)


def compact_history_titles(items: list[Any], max_items: int = 5, max_len: int = 180) -> list[str]:
    return history_core.compact_history_titles(_ctx(), items, max_items, max_len)


def history_document_path(feature: str) -> str:
    return history_core.history_document_path(_ctx(), feature)


def upsert_history_index_entry(entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    return history_core.upsert_history_index_entry(_ctx(), entry)


def render_history_summary(index: dict[str, Any]) -> None:
    return history_core.render_history_summary(_ctx(), index)


def record_project_history(state: dict[str, Any]) -> dict[str, Any]:
    return history_core.record_project_history(_ctx(), state)


def should_extract_pc_candidates(state: dict[str, Any]) -> bool:
    return history_core.should_extract_pc_candidates(_ctx(), state)


def pc_candidate_source_artifact_text(feature: str, max_chars_per_file: int = 8000) -> str:
    return history_core.pc_candidate_source_artifact_text(_ctx(), feature, max_chars_per_file)


def build_pc_candidate_extraction_prompt(state: dict[str, Any]) -> str:
    return history_core.build_pc_candidate_extraction_prompt(_ctx(), state)


def normalize_pc_candidate(
    raw: dict[str, Any],
    state: dict[str, Any],
    created_at: str,
    provider: str,
) -> dict[str, Any] | None:
    return history_core.normalize_pc_candidate(_ctx(), raw, state, created_at, provider)


def append_pc_candidates(candidates: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    return history_core.append_pc_candidates(_ctx(), candidates, state)


def extract_project_contract_candidates(state: dict[str, Any]) -> dict[str, Any]:
    return history_core.extract_project_contract_candidates(_ctx(), state)


def complete_run(state: dict[str, Any], stage: str) -> dict[str, Any]:
    return workflow_core.complete_run(_ctx(), state, stage)


def finish_pc_candidate_extraction(state: dict[str, Any]) -> dict[str, Any]:
    return workflow_core.finish_pc_candidate_extraction(_ctx(), state)


def log_event(
    state: dict[str, Any],
    event: str,
    message: str,
    *,
    stage: str | None = None,
    console: bool = True,
    **fields: Any,
) -> None:
    feature = state["feature_name"]
    timestamp = iso_now()
    stage = stage or state.get("current_stage")
    provider_schedule = state.get("provider_schedule")
    scheduled_provider = (
        provider_schedule.get(str(stage))
        if isinstance(provider_schedule, dict) and stage
        else None
    )
    agent = str(fields.get("agent") or fields.get("provider") or scheduled_provider or "harness")
    line = f"[{timestamp}] [{feature}]"
    if stage:
        line += f" [{stage}]"
    line += f" [{agent}]"
    line += f" {event}: {message}"
    if fields:
        compact = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
        if compact:
            line += f" ({compact})"

    path = run_log_path(feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    state.setdefault("events", []).append(
        {"at": timestamp, "event": event, "stage": stage, "agent": agent, "message": message, **fields}
    )
    if console:
        print(event_line_for_console(line, event), flush=True)


def find_stage_result(text: str) -> dict[str, Any]:
    return stage_runtime_core.find_stage_result(_ctx(), text)


def parse_result_json_from_text(text: str) -> dict[str, Any]:
    return stage_runtime_core.parse_result_json_from_text(_ctx(), text)


def read_stage_result_json(path: Path) -> dict[str, Any]:
    return stage_runtime_core.read_stage_result_json(_ctx(), path)


def parse_result_scalar(value: str) -> Any:
    return stage_runtime_core.parse_result_scalar(_ctx(), value)


def extract_feature_name(spec_text: str) -> str | None:
    match = re.search(r"^\s*-\s*feature_name:\s*([a-z0-9][a-z0-9-]*)\s*$", spec_text, re.M)
    if match:
        return match.group(1)
    return None


def maybe_rename_feature(state: dict[str, Any]) -> dict[str, Any]:
    return workflow_core.maybe_rename_feature(_ctx(), state)


def stage_default_next(stage: str) -> str | None:
    return stage_runtime_core.stage_default_next(_ctx(), stage)


def expand_policy_item(item: Any, feature: str) -> str:
    return policy_core.expand_policy_item(item, feature)


def is_test_path(path: str) -> bool:
    return policy_core.is_test_path(path)


def is_production_code_path(path: str) -> bool:
    return policy_core.is_production_code_path(path)


def direct_policy_match(path: str, policy_path: str) -> bool:
    return policy_core.direct_policy_match(path, policy_path)


def policy_item_matches(path: str, item: str, before_snapshot: dict[str, str]) -> bool:
    return policy_core.policy_item_matches(path, item, before_snapshot)


def write_policy_violations(state: dict[str, Any], stage: str) -> list[str]:
    return policy_core.write_policy_violations(_ctx(), state, stage)


def stage_status(result: dict[str, Any]) -> str:
    return stage_runtime_core.stage_status(_ctx(), result)


def run_status_line(state: dict[str, Any]) -> str:
    return (
        f"{state['feature_name']}: status={state.get('status')} "
        f"stage={state.get('current_stage')} performance={normalize_performance(state.get('performance'))} "
        f"decision_mode={decision_mode_label(state)} prompt={state.get('current_prompt')}"
    )


def decision_mode_label(state: dict[str, Any]) -> str:
    if state.get("defaults_mode"):
        return "defaults"
    if state.get("interactive_mode"):
        return "interactive"
    return "manual"


def print_status_field(label: str, value: str, *styles: str) -> None:
    label_text = color_text(f"{label:<14}", "dim")
    value_text = color_text(value, *styles) if styles else value
    print(f"{label_text} {value_text}")


def last_event_summary(state: dict[str, Any]) -> str:
    events = state.get("events", [])
    if not events:
        return "없음"
    event = events[-1]
    stage = event.get("stage") or "-"
    name = event.get("event") or "-"
    message = event.get("message") or ""
    at = event.get("at") or ""
    return f"{at} [{stage}] {name}: {message}"


def next_action_hint(state: dict[str, Any], expected_output: Path | None) -> tuple[str, tuple[str, ...]]:
    status = str(state.get("status") or "")
    if status == RunStatus.COMPLETE:
        return "완료되었습니다.", ("green", "bold")
    if status == RunStatus.BLOCKED:
        return "blocked 이유를 확인한 뒤 수정하거나 승인/재실행하세요.", ("red", "bold")
    if expected_output and not expected_output.exists() and status in {RunStatus.MODEL_COMPLETED, RunStatus.WAITING_FOR_MODEL}:
        return "필수 산출물이 없으면 로그를 확인하고 현재 stage를 다시 실행하세요.", ("yellow", "bold")
    if status == RunStatus.WAITING_FOR_MODEL:
        return "현재 prompt를 provider가 실행해야 합니다.", ("cyan", "bold")
    if status == RunStatus.MODEL_RUNNING:
        return "provider가 실행 중입니다. heartbeat 로그를 기다리세요.", ("cyan", "bold")
    return "현재 상태를 기준으로 다음 하네스 명령을 실행하세요.", ("cyan", "bold")


def read_only_provider_for_state_stage(state: dict[str, Any], stage: str) -> str:
    schedule = state.get("provider_schedule")
    if isinstance(schedule, dict):
        provider = str(schedule.get(stage) or "")
        if provider:
            return provider

    if stage == PC_REVIEW_STAGE:
        return "-"

    config = pipeline_config_for_state(state)
    if stage not in config.stages:
        return "-"

    preset = AI_DIR / "presets" / config.presets_subdir / f"{stage}.md"
    try:
        meta, _ = parse_frontmatter(preset.read_text(encoding="utf-8"))
    except OSError:
        return "-"
    preferred = str(meta.get("preferred_model", ""))
    return PROVIDER_BY_MODEL.get(preferred) or "-"


def print_detailed_status(state: dict[str, Any]) -> None:
    feature = state["feature_name"]
    stage = str(state.get("current_stage") or "")
    status = str(state.get("status") or "")
    expected_output: Path | None = None
    expected_result_json: Path | None = None
    provider = "-"
    attempt = "-"
    if stage in pipeline_stages_for_state(state):
        expected_output = stage_output_path_for_state(feature, stage, state)
        expected_result_json = stage_result_json_path_for_state(feature, stage, state)
        attempt = str(state.get("attempts", {}).get(stage, 0) or 0)
        provider = read_only_provider_for_state_stage(state, stage)

    print(color_text(feature, "bold"))
    print_status_field("performance", normalize_performance(state.get("performance")), "cyan")
    print_status_field("모드", str(state.get("pipeline_mode") or PIPELINE_MODE))
    print_status_field("결정 모드", decision_mode_label(state), "cyan")
    print_status_field("상태", status, *status_style(status))
    print_status_field("단계", stage or "-")
    print_status_field("담당", provider, "magenta", "bold" if provider != "-" else "dim")
    print_status_field("시도", attempt)
    if state.get("current_prompt"):
        print_status_field("프롬프트", str(state["current_prompt"]), "cyan")
    if expected_output:
        exists = expected_output.exists()
        print_status_field("예상 산출물", rel(expected_output), "cyan")
        print_status_field("산출물 상태", "있음" if exists else "없음", "green" if exists else "red", "bold")
    if expected_result_json:
        exists = expected_result_json.exists()
        print_status_field("result JSON", rel(expected_result_json), "cyan")
        print_status_field("JSON 상태", "있음" if exists else "없음", "green" if exists else "yellow", "bold")
    if state.get("last_harness_verification"):
        print_status_field("최근 검증", str(state["last_harness_verification"]), "cyan")
    if state.get("last_handoff"):
        print_status_field("handoff", str(state["last_handoff"]), "yellow")
    if state.get("interactive_answers"):
        print_status_field("interactive 답변", str(len(state.get("interactive_answers", []))), "cyan")
    print_status_field("마지막 이벤트", last_event_summary(state))
    hint, styles = next_action_hint(state, expected_output)
    print_status_field("다음 조치", hint, *styles)

    if state.get("blocked"):
        print()
        print(color_text("blocked 상세:", "red", "bold"))
        print(json.dumps(state["blocked"], ensure_ascii=False, indent=2))
    if state.get("commits"):
        print()
        print_status_field("commits", json.dumps(state.get("commits", {}), ensure_ascii=False))


def prompt_path(state: dict[str, Any], stage: str) -> Path:
    return stage_runtime_core.prompt_path(_ctx(), state, stage)


def generate_prompt(state: dict[str, Any], stage: str, retry_context: str | None = None) -> Path:
    return stage_runtime_core.generate_prompt(_ctx(), state, stage, retry_context)


def print_provider_heartbeat(
    *,
    stage: str,
    provider: str,
    started: float,
    stdout_path: Path,
    stderr_path: Path,
    last_stdout_size: int,
    last_stderr_size: int,
) -> tuple[int, int]:
    return stage_runtime_core.print_provider_heartbeat(_ctx(), stage=stage, provider=provider, started=started, stdout_path=stdout_path, stderr_path=stderr_path, last_stdout_size=last_stdout_size, last_stderr_size=last_stderr_size)


def harness_script_for_pipeline_mode(pipeline_mode: Any) -> str:
    return stage_runtime_core.harness_script_for_pipeline_mode(_ctx(), pipeline_mode)


def suggested_retry_command(state: dict[str, Any], *, auto: bool = True) -> str:
    return stage_runtime_core.suggested_retry_command(_ctx(), state, auto=auto)


def provider_log_hint(stdout_path: Path, stderr_path: Path, provider_log_path: Path) -> str:
    return stage_runtime_core.provider_log_hint(_ctx(), stdout_path, stderr_path, provider_log_path)


def provider_failure_reason(
    state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    failure: str,
    stdout_path: Path,
    stderr_path: Path,
    provider_log_path: Path,
) -> str:
    return stage_runtime_core.provider_failure_reason(_ctx(), state, stage=stage, provider=provider, failure=failure, stdout_path=stdout_path, stderr_path=stderr_path, provider_log_path=provider_log_path)


def execute_current_prompt(state: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    if should_execute_deep_thinking_plan(state):
        return deep_thinking_core.execute_plan(_ctx(), state, timeout_seconds)
    return stage_runtime_core.execute_current_prompt(_ctx(), state, timeout_seconds)


def should_execute_deep_thinking_plan(state: dict[str, Any]) -> bool:
    return deep_thinking_core.should_execute_plan(_ctx(), state)


def validate_deep_thinking_ready(state: dict[str, Any] | None = None) -> dict[str, Any]:
    return deep_thinking_core.validate_config_for_state(_ctx(), state)


def display_cwd(path: Path) -> str:
    return verification_core.display_cwd(_ctx(), path)


def run_harness_verification(
    state: dict[str, Any],
    stage_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return verification_core.run_harness_verification(_ctx(), state, stage_result)


def enforce_harness_verify_result(
    state: dict[str, Any],
    result: dict[str, Any],
    status: str,
    next_stage: str,
) -> tuple[str, str]:
    return verification_core.enforce_harness_verify_result(
        _ctx(),
        state,
        result,
        status,
        next_stage,
    )


def auto_drive(
    state: dict[str, Any],
    yes: bool,
    timeout_seconds: int,
    max_steps: int,
    max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES,
) -> dict[str, Any]:
    return workflow_core.auto_drive(_ctx(), state, yes, timeout_seconds, max_steps, max_verify_fix_retries)


def apply_decision_mode(
    state: dict[str, Any],
    *,
    defaults: bool = False,
    interactive: bool = False,
    reason: str = "decision mode updated",
) -> dict[str, Any]:
    return workflow_core.apply_decision_mode(_ctx(),
        state,
        defaults=defaults,
        interactive=interactive,
        reason=reason,
    )


def step_run(
    feature: str,
    yes: bool,
    defaults: bool,
    interactive: bool,
    timeout_seconds: int,
    max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES,
) -> dict[str, Any]:
    return workflow_core.step_run(_ctx(),
        feature,
        yes,
        defaults,
        interactive,
        timeout_seconds,
        max_verify_fix_retries,
    )


def safe_git_head() -> str:
    return workflow_core.safe_git_head(_ctx())


def filtered_changed_paths(state: dict[str, Any], stage: str) -> list[str]:
    return workflow_core.filtered_changed_paths(_ctx(), state, stage)


def commit_for_stage(state: dict[str, Any], stage: str, result: dict[str, Any]) -> None:
    return workflow_core.commit_for_stage(_ctx(), state, stage, result)


def create_run(
    request: str,
    feature: str | None,
    defaults_mode: bool = False,
    interactive_mode: bool = False,
    deep_thinking: bool = False,
    performance: Any | None = None,
    strategy: Any | None = None,
    cross_validation: bool = False,
) -> dict[str, Any]:
    return workflow_core.create_run(_ctx(),
        request,
        feature,
        defaults_mode,
        interactive_mode,
        deep_thinking,
        performance,
        strategy,
        cross_validation,
    )


def apply_runtime_performance(state: dict[str, Any], performance: Any | None) -> dict[str, Any]:
    return workflow_core.apply_runtime_performance(_ctx(), state, performance)


def latest_provider_artifacts(
    feature: str,
    stage: str,
    state: dict[str, Any] | None = None,
) -> dict[str, str]:
    return workflow_core.latest_provider_artifacts(_ctx(), feature, stage, state)


def handoff_path(feature: str) -> Path:
    return workflow_core.handoff_path(_ctx(), feature)


def safe_read_tail(path: Path, lines: int = 40, max_chars: int = 6000) -> str:
    return workflow_core.safe_read_tail(_ctx(), path, lines, max_chars)


def latest_verification_summary(feature: str) -> dict[str, Any] | None:
    return workflow_core.latest_verification_summary(_ctx(), feature)


def recent_events(state: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    return workflow_core.recent_events(_ctx(), state, limit)


def write_handoff(
    state: dict[str, Any],
    reason: str,
    *,
    stage: str | None = None,
    next_action: str | None = None,
    result: dict[str, Any] | None = None,
) -> Path:
    return workflow_core.write_handoff(_ctx(), state, reason, stage=stage, next_action=next_action, result=result)


def missing_stage_output_message(
    feature: str,
    stage: str,
    output: Path,
    state: dict[str, Any] | None = None,
) -> str:
    return workflow_core.missing_stage_output_message(_ctx(), feature, stage, output, state)


def load_stage_result(
    feature: str,
    stage: str,
    state: dict[str, Any] | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    return workflow_core.load_stage_result(_ctx(), feature, stage, state)


def expected_docx_path(feature: str) -> Path:
    return workflow_core.expected_docx_path(_ctx(), feature)


def validate_docx_file(path: Path) -> str | None:
    return core_validate_docx_file(path, rel(path))


def validate_document_stage_artifacts(feature: str) -> str | None:
    return workflow_core.validate_document_stage_artifacts(_ctx(), feature)


def feature_schemas_path(feature: str) -> Path:
    return feature_dir(feature) / "schemas.json"


def validate_feature_schemas(feature: str) -> str | None:
    path = feature_schemas_path(feature)
    return core_validate_schemas_file(path, feature=feature, display_path=rel(path))


def validate_feature_schemas_conformance(feature: str) -> tuple[str | None, list[str]]:
    path = feature_schemas_path(feature)
    return core_validate_schemas_conformance_file(
        path, ROOT, feature=feature, display_path=rel(path)
    )


def block_state(state: dict[str, Any], stage: str, reason: str, next_stage: str | None = None) -> None:
    return workflow_core.block_state(_ctx(), state, stage, reason, next_stage)


def resume_run(feature: str, max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES) -> dict[str, Any]:
    return workflow_core.resume_run(_ctx(), feature, max_verify_fix_retries)


def approve_run(feature: str, max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES) -> dict[str, Any]:
    return workflow_core.approve_run(_ctx(), feature, max_verify_fix_retries)


def build_retry_context(state: dict[str, Any], stage: str) -> str:
    return workflow_core.build_retry_context(_ctx(), state, stage)


def copy_same_prompt_for_retry(state: dict[str, Any], stage: str) -> Path:
    return workflow_core.copy_same_prompt_for_retry(_ctx(), state, stage)


def archive_stage_outputs_for_retry(state: dict[str, Any], stage: str) -> None:
    return workflow_core.archive_stage_outputs_for_retry(_ctx(), state, stage)


def retry_run(
    feature: str,
    *,
    same: bool,
    prompt_only: bool,
    auto: bool,
    yes: bool,
    defaults: bool,
    interactive: bool,
    timeout_seconds: int,
    max_steps: int,
    max_verify_fix_retries: int,
) -> dict[str, Any]:
    return workflow_core.retry_run(_ctx(), feature, same=same, prompt_only=prompt_only, auto=auto, yes=yes, defaults=defaults, interactive=interactive, timeout_seconds=timeout_seconds, max_steps=max_steps, max_verify_fix_retries=max_verify_fix_retries)


def print_providers() -> None:
    for provider in known_provider_names():
        try:
            command = provider_command(provider)
            executable = resolve_executable(command)
        except HarnessError as exc:
            command = []
            executable = None
            print(f"{provider}: error ({exc})")
            continue
        status = "ok" if provider_enabled(provider) and executable else "missing"
        if not provider_enabled(provider):
            status = "disabled"
        print(f"{provider}: {status}")
        print(f"  capabilities: {', '.join(sorted(provider_capabilities(provider))) or '-'}")
        print(f"  command: {' '.join(command)}")
        if executable:
            print(f"  executable: {executable}")


def print_provider_schedule_preview() -> None:
    state = {
        "feature_name": "_doctor",
        "pipeline_mode": PIPELINE_MODE,
        "events": [],
    }
    try:
        schedule = build_provider_schedule(state)
    except HarnessError as exc:
        print(color_text(f"provider_schedule: ERROR {exc}", "red", "bold"))
        return
    print("provider_schedule:")
    for stage in provider_schedule_stages(state):
        print(f"  {stage}: {schedule.get(stage)}")


def harness_script_for_state(state: dict[str, Any]) -> str:
    return harness_script_for_pipeline_mode(state.get("pipeline_mode"))


def decision_mode_args_for_state(state: dict[str, Any]) -> str:
    if state.get("defaults_mode"):
        return " --defaults"
    if state.get("interactive_mode"):
        return " --interactive"
    return ""


def compact_todo_text(text: str, max_chars: int = 180) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def todo_relevant_stage_for_state(state: dict[str, Any]) -> str:
    stage = str(state.get("current_stage") or "")
    stages = pipeline_stages_for_state(state)
    if stage in stages or stage == PC_REVIEW_STAGE:
        return stage
    blocked = state.get("blocked") if isinstance(state.get("blocked"), dict) else {}
    blocked_stage = str(blocked.get("stage") or "") if isinstance(blocked, dict) else ""
    if blocked_stage in stages or blocked_stage == PC_REVIEW_STAGE:
        return blocked_stage
    if str(state.get("status") or "") == RunStatus.COMPLETE and stages:
        return stages[-1]
    return ""


def todo_provider_for_state(state: dict[str, Any]) -> str:
    stage = todo_relevant_stage_for_state(state)
    if stage not in pipeline_stages_for_state(state) and stage != PC_REVIEW_STAGE:
        return "-"
    return read_only_provider_for_state_stage(state, stage)


def todo_attempt_for_state(state: dict[str, Any]) -> str:
    stage = todo_relevant_stage_for_state(state)
    if stage not in pipeline_stages_for_state(state):
        return "-"
    return str(state.get("attempts", {}).get(stage, 0) or 0)


def todo_artifact_state(path: Path) -> str:
    return f"{rel(path)} ({'exists' if path.exists() else 'missing'})"


def todo_stage_artifacts_for_state(state: dict[str, Any]) -> tuple[str, str]:
    feature = str(state.get("feature_name") or "")
    stage = todo_relevant_stage_for_state(state)
    if not feature or stage not in pipeline_stages_for_state(state):
        return "-", "-"
    output = stage_output_path_for_state(feature, stage, state)
    result_json = stage_result_json_path_for_state(feature, stage, state)
    if output is None or result_json is None:
        return "-", "-"
    return todo_artifact_state(output), todo_artifact_state(result_json)


def todo_provider_artifacts(feature: str, stage: str, state: dict[str, Any]) -> dict[str, str]:
    provider = read_only_provider_for_state_stage(state, stage)
    if provider == "-":
        provider = "unknown"
    attempt = int(state.get("attempts", {}).get(stage, 1) or 1)
    logs_dir = run_dir(feature) / "logs"
    return {
        "provider": provider,
        "stdout": rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.out.txt"),
        "stderr": rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.err.txt"),
        "meta": rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.json"),
        "provider_log": rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.cli.log"),
    }


def todo_next_action(state: dict[str, Any]) -> str:
    feature = str(state.get("feature_name") or "<feature>")
    stage = str(state.get("current_stage") or "")
    status = str(state.get("status") or "")
    script = harness_script_for_state(state)
    mode_args = decision_mode_args_for_state(state)
    if status == RunStatus.COMPLETE:
        return "done"
    if status == RunStatus.BLOCKED:
        blocked = state.get("blocked") if isinstance(state.get("blocked"), dict) else {}
        reason = str(blocked.get("reason") or "") if isinstance(blocked, dict) else ""
        if "Human gate approval required" in reason:
            return f"python {script} approve {feature} --auto --yes{mode_args}"
        stage = todo_relevant_stage_for_state(state) or stage
        if stage in pipeline_stages_for_state(state):
            output = stage_output_path_for_state(feature, stage, state)
            result_json = stage_result_json_path_for_state(feature, stage, state)
            if output and result_json and output.exists() and result_json.exists():
                if state.get("interactive_mode"):
                    return f"python {script} resume {feature} --auto --yes{mode_args}"
                return f"python {script} resume {feature}{mode_args}"
        if isinstance(blocked, dict) and blocked.get("retry_command"):
            return str(blocked["retry_command"])
        return f"python {script} retry {feature} --auto --yes{mode_args}"
    if status == RunStatus.MODEL_COMPLETED:
        return f"python {script} resume {feature}{mode_args}"
    if status in {RunStatus.CREATED, RunStatus.WAITING_FOR_MODEL}:
        return f"python {script} auto {feature} --yes{mode_args}"
    if status == RunStatus.MODEL_RUNNING:
        return f"python {script} todo {feature}"
    return f"python {script} todo {feature}"


def todo_items() -> list[dict[str, str]]:
    if not RUNS_DIR.exists():
        return []
    items: list[dict[str, str]] = []
    for path in sorted(RUNS_DIR.glob("*/run.json")):
        try:
            state = read_json_value_file(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            items.append(
                {
                    "feature": path.parent.name,
                    "status": "unreadable",
                    "stage": "-",
                    "mode": "-",
                    "performance": "-",
                    "provider": "-",
                    "attempt": "-",
                    "prompt": "",
                    "output": "-",
                    "result_json": "-",
                    "handoff": "",
                    "last_event": "",
                    "next": f"inspect {rel(path)}",
                    "reason": compact_todo_text(str(exc)),
                }
            )
            continue
        if not isinstance(state, dict):
            items.append(
                {
                    "feature": path.parent.name,
                    "status": "invalid",
                    "stage": "-",
                    "mode": "-",
                    "performance": "-",
                    "provider": "-",
                    "attempt": "-",
                    "prompt": "",
                    "output": "-",
                    "result_json": "-",
                    "handoff": "",
                    "last_event": "",
                    "next": f"inspect {rel(path)}",
                    "reason": "run.json is not an object",
                }
            )
            continue
        blocked = state.get("blocked")
        reason = str(blocked.get("reason") or "") if isinstance(blocked, dict) else ""
        output_state, result_json_state = todo_stage_artifacts_for_state(state)
        items.append(
            {
                "feature": str(state.get("feature_name") or path.parent.name),
                "status": str(state.get("status") or "unknown"),
                "stage": str(state.get("current_stage") or "-"),
                "mode": decision_mode_label(state),
                "performance": normalize_performance(state.get("performance")),
                "provider": todo_provider_for_state(state),
                "attempt": todo_attempt_for_state(state),
                "prompt": str(state.get("current_prompt") or ""),
                "output": output_state,
                "result_json": result_json_state,
                "handoff": str(state.get("last_handoff") or ""),
                "last_event": compact_todo_text(last_event_summary(state), max_chars=220),
                "next": todo_next_action(state),
                "reason": compact_todo_text(reason) if reason else "",
            }
        )
    return sorted(
        items,
        key=lambda item: (
            item["status"] == RunStatus.COMPLETE,
            item["feature"],
        ),
    )


def print_todo_detail(feature: str) -> None:
    state = load_state(feature)
    print_status_field("NEXT COMMAND", todo_next_action(state), "green", "bold")
    print()
    print_detailed_status(state)
    log_path = run_log_path(feature)
    if log_path.exists():
        print_status_field("harness log", str(log_path), "cyan")

    relevant_stage = todo_relevant_stage_for_state(state)
    current_stage = str(state.get("current_stage") or "")
    if relevant_stage and relevant_stage != current_stage:
        output_state, result_json_state = todo_stage_artifacts_for_state(state)
        print_status_field("last stage", relevant_stage, "cyan")
        print_status_field("last provider", todo_provider_for_state(state), "magenta")
        print_status_field("last attempt", todo_attempt_for_state(state))
        print_status_field("last output", output_state, "cyan")
        print_status_field("last result", result_json_state, "cyan")

    if relevant_stage in pipeline_stages_for_state(state) or relevant_stage == PC_REVIEW_STAGE:
        artifacts = todo_provider_artifacts(feature, relevant_stage, state)
        print()
        print(color_text("provider artifacts:", "cyan", "bold"))
        print_status_field("stdout", artifacts["stdout"], "cyan")
        print_status_field("stderr", artifacts["stderr"], "cyan")
        print_status_field("meta", artifacts["meta"], "cyan")
        print_status_field("provider log", artifacts["provider_log"], "cyan")

    events = recent_events(state, limit=6)
    if events:
        print()
        print(color_text("recent events:", "cyan", "bold"))
        for event in events:
            print(
                f"- {event.get('at', '')} [{event.get('stage') or '-'}] "
                f"{event.get('event')}: {event.get('message', '')}"
            )


def print_todo(feature: str | None = None) -> None:
    if feature:
        print_todo_detail(feature)
        return
    items = todo_items()
    if not items:
        print("todo: no runs")
        return
    active_count = sum(1 for item in items if item["status"] != RunStatus.COMPLETE)
    complete_count = len(items) - active_count
    header = (
        f"todo: {color_text(str(active_count), 'yellow', 'bold')} active, "
        f"{color_text(str(complete_count), 'green', 'bold')} complete"
    )
    print(header)
    print()
    for item in items:
        status = item["status"]
        status_label = color_text(status.upper(), *status_style(status))
        feature_label = color_text(item["feature"], "bold")
        print(
            f"- {feature_label} [{status_label}] "
            f"stage={item['stage']} provider={item['provider']} "
            f"mode={item.get('mode', 'manual')} performance={item.get('performance', '-')} "
            f"attempt={item.get('attempt', '-')}"
        )
        print(f"  next command: {color_text(item['next'], 'green', 'bold')}")
        if item["reason"]:
            print(f"  reason: {item['reason']}")
        if item.get("prompt"):
            print(f"  prompt: {item['prompt']}")
        print(f"  output: {item.get('output', '-')}")
        print(f"  result_json: {item.get('result_json', '-')}")
        if item.get("handoff"):
            print(f"  handoff: {item['handoff']}")
        if item.get("last_event"):
            print(f"  last_event: {item['last_event']}")


def cleanup_run(feature: str, keep_feature: bool = False) -> None:
    # The feature must be a plain slug. Without this, "cleanup .." resolves to
    # .project and "cleanup ../.." to the repo root, and the old guard below
    # (which permitted resolved == root) would rmtree the entire repository.
    if not validate_slug(feature):
        raise HarnessError(
            f"Invalid feature name for cleanup: {feature!r}. "
            "Expected a slug like 'my-feature' (no path separators or '..')."
        )
    root = ROOT.resolve()
    runs_root = RUNS_DIR.resolve()
    features_root = FEATURES_DIR.resolve()
    targets = [(run_dir(feature), runs_root)]
    if not keep_feature:
        targets.append((feature_dir(feature), features_root))
    for target, expected_parent in targets:
        if not target.exists():
            continue
        resolved = target.resolve()
        # Only ever delete a direct child of the runs/features directory, and
        # never those directories themselves or anything at/above the root.
        if resolved == root or resolved == expected_parent or resolved.parent != expected_parent:
            raise HarnessError(f"Refusing to remove unexpected path: {resolved}")
        # rmtree_robust: a cross-validation run leaves a blind git clone under
        # the run dir whose object files are read-only on Windows.
        cross_validation_core.rmtree_robust(resolved)
        print(f"removed: {resolved}")


def doctor_provider_smoke(provider: str, timeout_seconds: int) -> None:
    prompt = (
        "You are running a harness doctor smoke test. "
        "Do not edit files. Reply with exactly HARNESS_DOCTOR_OK."
    )
    ensure_dirs()
    logs_dir = RUNS_DIR / "_doctor" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    stdout_path = logs_dir / f"{provider}_{stamp}.out.txt"
    stderr_path = logs_dir / f"{provider}_{stamp}.err.txt"
    cli_log_path = logs_dir / f"{provider}_{stamp}.cli.log"
    command, prompt_in_command = prepare_provider_command(
        provider,
        prompt,
        log_file=cli_log_path.resolve(),
    )
    executable = resolve_executable(command)
    if not executable:
        print(color_text(f"{provider}: missing executable", "red", "bold"))
        return
    before_paths = set(git_changed_paths())
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            input=None if prompt_in_command else prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stdout_path.write_text(str(stdout), encoding="utf-8")
        stderr_path.write_text(str(stderr) + f"\nTimed out after {timeout_seconds} seconds.\n", encoding="utf-8")
        print(
            color_text(f"{provider}: timeout after {timeout_seconds}s", "red", "bold")
            + f" stdout={rel(stdout_path)} stderr={rel(stderr_path)} provider_log={rel(cli_log_path)}"
        )
        return

    elapsed = round(time.time() - started, 2)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    after_paths = set(git_changed_paths())
    new_changes = sorted(
        path for path in after_paths - before_paths if not path.startswith(".project/runs/_doctor/")
    )
    ok = proc.returncode == 0 and "HARNESS_DOCTOR_OK" in (proc.stdout or "")
    style = ("green", "bold") if ok else ("red", "bold")
    print(
        color_text(f"{provider}: {'ok' if ok else 'failed'}", *style)
        + f" returncode={proc.returncode} elapsed={elapsed}s stdout={rel(stdout_path)} stderr={rel(stderr_path)} provider_log={rel(cli_log_path)}"
    )
    if new_changes:
        print(color_text(f"  warning: provider changed files: {', '.join(new_changes)}", "yellow", "bold"))


def doctor(deep: bool = False, deep_timeout_seconds: int = DEFAULT_DOCTOR_DEEP_TIMEOUT_SECONDS) -> None:
    print(f"root: {ROOT}")
    try:
        print(f"git_head: {git_head()}")
    except Exception as exc:
        print(f"git_head: ERROR {exc}")
    for stage in STAGES:
        path = PRESETS_DIR / f"{stage}.md"
        print(f"preset {stage}: {'ok' if path.exists() else 'missing'}")
    print("providers:")
    print_providers()
    print_provider_schedule_preview()
    ensure_dirs()
    print(f"project_dir: {PROJECT_DIR}")
    print(f"runs_dir: {RUNS_DIR}")
    print(f"features_dir: {FEATURES_DIR}")
    print("changed_paths:")
    for path in git_changed_paths():
        print(f"  {path}")
    if deep:
        print("deep provider smoke tests:")
        for provider in known_provider_names():
            if not provider_enabled(provider):
                continue
            doctor_provider_smoke(provider, deep_timeout_seconds)


def run_selftest(
    pattern: str = "test*.py",
    failfast: bool = False,
    verbose: bool = False,
    keep_temp: bool = False,
) -> bool:
    import unittest

    selftest_dir = AI_DIR / "selftests"
    if not selftest_dir.exists():
        raise HarnessError(f"Selftest directory does not exist: {selftest_dir}")

    for path in (AI_DIR, selftest_dir):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)

    old_keep_temp = os.environ.get("HARNESS_SELFTEST_KEEP_TEMP")
    if keep_temp:
        os.environ["HARNESS_SELFTEST_KEEP_TEMP"] = "1"
    try:
        print(f"selftest_dir: {selftest_dir}")
        loader = unittest.TestLoader()
        suite = loader.discover(
            start_dir=str(selftest_dir),
            pattern=pattern,
            top_level_dir=str(selftest_dir),
        )
        runner = unittest.TextTestRunner(verbosity=2 if verbose else 1, failfast=failfast)
        return runner.run(suite).wasSuccessful()
    finally:
        if old_keep_temp is None:
            os.environ.pop("HARNESS_SELFTEST_KEEP_TEMP", None)
        else:
            os.environ["HARNESS_SELFTEST_KEEP_TEMP"] = old_keep_temp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local orchestrator for staged AI development presets.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_retry_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--max-verify-fix-retries",
            type=int,
            default=DEFAULT_MAX_VERIFY_FIX_RETRIES,
            help=(
                f"Maximum number of failed {VERIFY_STAGE} -> {VERIFY_RETRY_TARGET_STAGE} retry cycles "
                f"(default: {DEFAULT_MAX_VERIFY_FIX_RETRIES})."
            ),
        )

    def add_performance_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--performance",
            choices=list(PERFORMANCE_PROFILES),
            default=None,
            help=(
                "Performance profile for provider model settings. "
                f"Defaults to {DEFAULT_PERFORMANCE}. "
                "Applied to codex/claude only; agy is recorded but not passed to the CLI yet."
            ),
        )

    def add_decision_mode_args(
        command: argparse.ArgumentParser,
        *,
        defaults_help: str,
        interactive_help: str,
    ) -> None:
        group = command.add_mutually_exclusive_group()
        group.add_argument("--defaults", action="store_true", help=defaults_help)
        group.add_argument("--interactive", action="store_true", help=interactive_help)

    run = sub.add_parser("run", help="Start a new feature run and execute it automatically.")
    run.add_argument("request", help="User request for the feature.")
    run.add_argument("--feature", help="Optional feature slug.")
    run.add_argument("--yes", action="store_true", help="Auto-approve human gates.")
    if pipeline_core.supports_deep_thinking(PIPELINE_MODE):
        run.add_argument(
            "--deep-thinking",
            dest="deep_thinking",
            action="store_true",
            help="Run the 01_plan stage with private multi-provider internal planning.",
        )
        run.add_argument(
            "--heavy-thinking",
            dest="deep_thinking",
            action="store_true",
            help=argparse.SUPPRESS,
        )
        run.add_argument(
            "--strategy",
            choices=["parallel", "sequential", "max"],
            default=None,
            help=(
                "Deep-thinking planning strategy (requires --deep-thinking). "
                "'parallel': independent blind drafts synthesized into one plan (default). "
                "'sequential': iterative relay refinement. "
                "'max': parallel breadth then a grounded sequential relay (select -> ground -> pre-mortem); "
                "highest cost, for the heaviest work."
            ),
        )
    if pipeline_core.supports_cross_validation(PIPELINE_MODE):
        run.add_argument(
            "--cross-validation",
            dest="cross_validation",
            action="store_true",
            help=(
                "Run a blind acceptance-test track (independent provider, isolated "
                "from the implementation) in parallel and only auto-pass when the "
                "tracks converge CLEAN. Requires three distinct available providers."
            ),
        )
    add_decision_mode_args(
        run,
        defaults_help="Use model-recommended defaults for ambiguous decisions instead of stopping for user input.",
        interactive_help="Ask NEEDS_USER questions in the terminal and retry the same stage with your answers.",
    )
    run.add_argument("--timeout", type=int, default=3600, help="Provider timeout in seconds.")
    run.add_argument("--max-steps", type=int, default=30, help="Maximum automatic stage transitions.")
    add_performance_arg(run)
    add_retry_arg(run)

    resume = sub.add_parser("resume", help="Resume the current stage after the model wrote its output.")
    resume.add_argument("feature", help="Feature slug.")
    resume.add_argument("--auto", action="store_true", help="Continue executing stages with local providers.")
    resume.add_argument("--yes", action="store_true", help="Auto-approve human gates while running with --auto.")
    add_decision_mode_args(
        resume,
        defaults_help="Switch this run to defaults mode before resuming.",
        interactive_help="Switch this run to interactive mode before resuming.",
    )
    resume.add_argument("--timeout", type=int, default=3600, help="Provider timeout in seconds.")
    resume.add_argument("--max-steps", type=int, default=30, help="Maximum automatic stage transitions.")
    add_performance_arg(resume)
    add_retry_arg(resume)

    auto = sub.add_parser("auto", help="Execute the current and following stages with local providers.")
    auto.add_argument("feature", help="Feature slug.")
    auto.add_argument("--yes", action="store_true", help="Auto-approve human gates.")
    add_decision_mode_args(
        auto,
        defaults_help="Switch this run to defaults mode before continuing.",
        interactive_help="Switch this run to interactive mode before continuing.",
    )
    auto.add_argument("--timeout", type=int, default=3600, help="Provider timeout in seconds.")
    auto.add_argument("--max-steps", type=int, default=30, help="Maximum automatic stage transitions.")
    add_performance_arg(auto)
    add_retry_arg(auto)

    step = sub.add_parser("step", help="Execute exactly one current stage and stop.")
    step.add_argument("feature", help="Feature slug.")
    step.add_argument("--yes", action="store_true", help="Approve the current human gate before running one stage.")
    add_decision_mode_args(
        step,
        defaults_help="Switch this run to defaults mode before running one stage.",
        interactive_help="Switch this run to interactive mode before running one stage.",
    )
    step.add_argument("--timeout", type=int, default=3600, help="Provider timeout in seconds.")
    add_performance_arg(step)
    add_retry_arg(step)

    approve = sub.add_parser("approve", help="Approve a blocked human gate and continue.")
    approve.add_argument("feature", help="Feature slug.")
    approve.add_argument("--auto", action="store_true", help="Continue executing stages with local providers after approval.")
    approve.add_argument("--yes", action="store_true", help="Auto-approve later human gates while running with --auto.")
    add_decision_mode_args(
        approve,
        defaults_help="Switch this run to defaults mode before continuing.",
        interactive_help="Switch this run to interactive mode before continuing.",
    )
    approve.add_argument("--timeout", type=int, default=3600, help="Provider timeout in seconds.")
    approve.add_argument("--max-steps", type=int, default=30, help="Maximum automatic stage transitions.")
    add_performance_arg(approve)
    add_retry_arg(approve)

    todo = sub.add_parser("todo", help="Show run status, artifacts, recent events, and next actions.")
    todo.add_argument("feature", nargs="?", help="Feature slug. Omit to list all runs.")

    retry = sub.add_parser("retry", help="Retry the current stage.")
    retry.add_argument("feature", help="Feature slug.")
    retry.add_argument("--same", action="store_true", help="Retry with the same prompt content instead of adding failure context.")
    retry.add_argument("--prompt-only", action="store_true", help="Only generate the retry prompt; do not execute the provider.")
    retry.add_argument("--auto", action="store_true", help="Continue executing following stages after this retry succeeds.")
    retry.add_argument("--yes", action="store_true", help="Auto-approve human gates while continuing with --auto.")
    add_decision_mode_args(
        retry,
        defaults_help="Switch this run to defaults mode before retrying.",
        interactive_help="Switch this run to interactive mode before retrying.",
    )
    retry.add_argument("--timeout", type=int, default=3600, help="Provider timeout in seconds.")
    retry.add_argument("--max-steps", type=int, default=30, help="Maximum automatic stage transitions after retry.")
    add_performance_arg(retry)
    add_retry_arg(retry)

    cleanup = sub.add_parser("cleanup", help="Remove a local run directory and optionally its feature dir.")
    cleanup.add_argument("feature", help="Feature slug.")
    cleanup.add_argument(
        "--keep-feature",
        action="store_true",
        help="Only remove .project/runs/<feature>, preserving .project/features/<feature>.",
    )

    doctor_parser = sub.add_parser("doctor", help="Check local harness prerequisites.")
    doctor_parser.add_argument("--deep", action="store_true", help="Run provider smoke tests, not just path checks.")
    doctor_parser.add_argument(
        "--deep-timeout",
        type=int,
        default=DEFAULT_DOCTOR_DEEP_TIMEOUT_SECONDS,
        help="Timeout in seconds for each --deep provider smoke test.",
    )

    selftest_parser = sub.add_parser("selftest", help="Run harness engine selftests without project verify.")
    selftest_parser.add_argument(
        "--pattern",
        default="test*.py",
        help="unittest discovery pattern under .ai/selftests (default: test*.py).",
    )
    selftest_parser.add_argument("--failfast", action="store_true", help="Stop on the first selftest failure.")
    selftest_parser.add_argument("--verbose", action="store_true", help="Print each selftest name.")
    selftest_parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary integration fixture repos for inspection.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            if getattr(args, "strategy", None) and not getattr(args, "deep_thinking", False):
                raise HarnessError("--strategy requires --deep-thinking.")
            state = create_run(
                args.request,
                args.feature,
                defaults_mode=args.defaults,
                interactive_mode=args.interactive,
                deep_thinking=bool(getattr(args, "deep_thinking", False)),
                performance=args.performance,
                strategy=getattr(args, "strategy", None),
                cross_validation=bool(getattr(args, "cross_validation", False)),
            )
            state = auto_drive(
                state,
                yes=args.yes,
                timeout_seconds=args.timeout,
                max_steps=args.max_steps,
                max_verify_fix_retries=args.max_verify_fix_retries,
            )
            print(run_status_line(state))
            if state.get("current_prompt"):
                print(f"prompt: {ROOT / state['current_prompt']}")
            return 0
        if args.command == "resume":
            state = apply_runtime_performance(load_state(args.feature), args.performance)
            state = apply_decision_mode(
                state,
                defaults=args.defaults,
                interactive=args.interactive,
                reason="decision mode enabled before resume",
            )
            if args.auto:
                state = auto_drive(
                    state,
                    yes=args.yes,
                    timeout_seconds=args.timeout,
                    max_steps=args.max_steps,
                    max_verify_fix_retries=args.max_verify_fix_retries,
                )
            else:
                state = resume_run(args.feature, max_verify_fix_retries=args.max_verify_fix_retries)
            print(run_status_line(state))
            if state.get("current_prompt"):
                print(f"prompt: {ROOT / state['current_prompt']}")
            return 0
        if args.command == "auto":
            state = apply_runtime_performance(load_state(args.feature), args.performance)
            state = apply_decision_mode(
                state,
                defaults=args.defaults,
                interactive=args.interactive,
                reason="decision mode enabled for existing run",
            )
            state = auto_drive(
                state,
                yes=args.yes,
                timeout_seconds=args.timeout,
                max_steps=args.max_steps,
                max_verify_fix_retries=args.max_verify_fix_retries,
            )
            print(run_status_line(state))
            if state.get("current_prompt"):
                print(f"prompt: {ROOT / state['current_prompt']}")
            return 0
        if args.command == "step":
            apply_runtime_performance(load_state(args.feature), args.performance)
            state = step_run(
                args.feature,
                yes=args.yes,
                defaults=args.defaults,
                interactive=args.interactive,
                timeout_seconds=args.timeout,
                max_verify_fix_retries=args.max_verify_fix_retries,
            )
            print(run_status_line(state))
            if state.get("current_prompt"):
                print(f"prompt: {ROOT / state['current_prompt']}")
            return 0
        if args.command == "approve":
            state = apply_runtime_performance(load_state(args.feature), args.performance)
            state = apply_decision_mode(
                state,
                defaults=args.defaults,
                interactive=args.interactive,
                reason="decision mode enabled before approval",
            )
            state = approve_run(args.feature, max_verify_fix_retries=args.max_verify_fix_retries)
            if args.auto:
                state = auto_drive(
                    state,
                    yes=args.yes,
                    timeout_seconds=args.timeout,
                    max_steps=args.max_steps,
                    max_verify_fix_retries=args.max_verify_fix_retries,
                )
            print(run_status_line(state))
            if state.get("current_prompt"):
                print(f"prompt: {ROOT / state['current_prompt']}")
            return 0
        if args.command == "todo":
            print_todo(args.feature)
            return 0
        if args.command == "retry":
            apply_runtime_performance(load_state(args.feature), args.performance)
            state = retry_run(
                args.feature,
                same=args.same,
                prompt_only=args.prompt_only,
                auto=args.auto,
                yes=args.yes,
                defaults=args.defaults,
                interactive=args.interactive,
                timeout_seconds=args.timeout,
                max_steps=args.max_steps,
                max_verify_fix_retries=args.max_verify_fix_retries,
            )
            print(run_status_line(state))
            if state.get("current_prompt"):
                print(f"prompt: {ROOT / state['current_prompt']}")
            return 0
        if args.command == "cleanup":
            cleanup_run(args.feature, keep_feature=args.keep_feature)
            return 0
        if args.command == "doctor":
            doctor(deep=args.deep, deep_timeout_seconds=args.deep_timeout)
            return 0
        if args.command == "selftest":
            return 0 if run_selftest(
                pattern=args.pattern,
                failfast=args.failfast,
                verbose=args.verbose,
                keep_temp=args.keep_temp,
            ) else 1
        parser.error("Unknown command")
        return 2
    except HarnessError as exc:
        print(f"{color_text('ERROR:', 'red', 'bold')} {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print("ERROR: command failed", file=sys.stderr)
        print(" ".join(exc.cmd), file=sys.stderr)
        if exc.stdout:
            print(exc.stdout, file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
