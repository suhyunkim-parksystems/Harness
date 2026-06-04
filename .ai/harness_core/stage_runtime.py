from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import pipeline
from .errors import HarnessError
from .status import ResultStatus, RunStatus


def find_stage_result(ctx, text: str) -> dict[str, Any]:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "## 단계 결과":
            start = i + 1
    if start is None:
        return {}

    section_lines: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        section_lines.append(line)
    section = "\n".join(section_lines).strip()

    json_result = parse_result_json_from_text(ctx, section)
    if json_result:
        return json_result

    result: dict[str, Any] = {}
    current_key: str | None = None
    for line in section_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            item = stripped[2:]
            if ":" in item:
                key, value = item.split(":", 1)
                key = key.strip()
                value = value.strip()
                if value == "":
                    result[key] = []
                    current_key = key
                else:
                    result[key] = parse_result_scalar(ctx, value)
                    current_key = key
            elif current_key and isinstance(result.get(current_key), list):
                result[current_key].append(item.strip())
        elif stripped.startswith("-") and current_key and isinstance(result.get(current_key), list):
            result[current_key].append(stripped[1:].strip())
        elif line.startswith("  - ") and current_key and isinstance(result.get(current_key), list):
            result[current_key].append(line[4:].strip())
    return result


def parse_result_json_from_text(ctx, text: str) -> dict[str, Any]:
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
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def read_stage_result_json(ctx, path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"Invalid stage result JSON in {ctx.rel(path)}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HarnessError(f"Stage result JSON must be an object: {ctx.rel(path)}")
    return parsed


def parse_result_scalar(ctx, value: str) -> Any:
    value = value.strip()
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "없음":
        return ""
    return value


def stage_default_next(ctx, stage: str) -> str | None:
    meta, _, _ = ctx.read_preset(stage)
    if stage == ctx.VERIFY_STAGE:
        return str(meta.get("default_next_stage_on_pass", ctx.DOCUMENT_STAGE or "done"))
    if ctx.DOCUMENT_STAGE and stage == ctx.DOCUMENT_STAGE:
        return "done"
    return meta.get("default_next_stage")  # type: ignore[return-value]


def stage_status(ctx, result: dict[str, Any]) -> str:
    return str(result.get("status", "")).strip().upper()


def prompt_path(ctx, state: dict[str, Any], stage: str) -> Path:
    attempts = state.setdefault("attempts", {})
    attempt = int(attempts.get(stage, 0)) + 1
    attempts[stage] = attempt
    prompt_dir = ctx.run_dir(state["feature_name"]) / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    return prompt_dir / f"{stage}_attempt{attempt}.md"


def generate_prompt(ctx, state: dict[str, Any], stage: str, retry_context: str | None = None) -> Path:
    feature = state["feature_name"]
    meta, body, raw = ctx.read_preset(stage)
    scheduled_provider = ctx.provider_for_stage(stage, state)
    preset_text = raw.replace("[기능명]", feature)
    output = ctx.stage_output_path(feature, stage)
    result_json = ctx.stage_result_json_path(feature, stage)
    ctx.ensure_project_contract_file()
    state.setdefault("stage_file_snapshots", {})[stage] = ctx.file_policy_snapshot(feature)
    defaults_mode = bool(state.get("defaults_mode"))
    interactive_mode = bool(state.get("interactive_mode"))
    if defaults_mode and interactive_mode:
        raise HarnessError("Run cannot use both defaults_mode and interactive_mode.")
    if defaults_mode:
        decision_policy = (
            "Use recommended defaults for ambiguous decisions. Do not return NEEDS_USER unless the task is impossible, unsafe, "
            "requires credentials/secrets that are not available, or would perform destructive/non-reversible actions. "
            "Record all default decisions and their rationale in the stage output."
        )
    elif interactive_mode:
        decision_policy = (
            "When user input is needed, return NEEDS_USER and include a structured `questions` array in the result JSON. "
            "Use `type: \"choice\"` with an `options` array for multiple choices, `type: \"yes_no\"` for yes/no questions, "
            "or `type: \"text\"` for free-form answers. Keep questions concise and actionable."
        )
    else:
        decision_policy = (
            "Ask for user input when the preset's question criteria require it. Return NEEDS_USER for unresolved decisions."
        )

    previous_outputs: list[str] = []
    for prev in ctx.STAGES:
        if prev == stage:
            break
        prev_path = ctx.stage_output_path(feature, prev)
        if prev_path.exists():
            previous_outputs.append(f"- {ctx.rel(prev_path)}")
        prev_result_json = ctx.stage_result_json_path(feature, prev)
        if prev_result_json.exists():
            previous_outputs.append(f"- {ctx.rel(prev_result_json)}")

    additional_inputs: list[str] = []
    if stage == ctx.VERIFY_RETRY_TARGET_STAGE:
        verify_path = ctx.stage_output_path(feature, ctx.VERIFY_STAGE)
        if verify_path.exists():
            additional_inputs.append(f"- {ctx.rel(verify_path)}")
        verify_result_json = ctx.stage_result_json_path(feature, ctx.VERIFY_STAGE)
        if verify_result_json.exists():
            additional_inputs.append(f"- {ctx.rel(verify_result_json)}")
        latest_verify_path = ctx.latest_verification_result_path(feature)
        if latest_verify_path.exists():
            additional_inputs.append(f"- {ctx.rel(latest_verify_path)}")

    project_contract = ctx.project_contract_prompt_text()
    answer_history: list[str] = []
    for item in state.get("interactive_answers", [])[-10:]:
        if not isinstance(item, dict):
            continue
        stage_name = str(item.get("stage") or "-")
        summary = str(item.get("summary") or "").strip()
        answer_path = str(item.get("answer_path") or "").strip()
        line = f"- {stage_name}: {summary or '(no summary)'}"
        if answer_path:
            line += f" ({answer_path})"
        answer_history.append(line)

    stages = list(ctx.STAGES)
    final_stage = str(stages[-1]) if stages else stage
    default_next = stage_default_next(ctx, stage)
    if stage == final_stage:
        next_stage_contract = (
            '- next_stage: next stage id or "done". This is the final pipeline stage; '
            'use "done" only when the run is complete.'
        )
    else:
        next_hint = f"`{default_next}`" if default_next else "a valid next stage"
        next_stage_contract = (
            "- next_stage: next stage id. This is not the final pipeline stage; "
            f'do not use "done". Use {next_hint} unless the preset explicitly routes to another valid stage.'
        )

    instruction = f"""# Local Harness Prompt

## Harness Context
- feature_name: {feature}
- pipeline_mode: {ctx.PIPELINE_MODE}
- stage: {stage}
- preferred_model: {meta.get("preferred_model", "")}
- scheduled_provider: {scheduled_provider}
- performance: {ctx.normalize_performance(state.get("performance"))}
- output_file: {ctx.rel(output)}
- result_json_file: {ctx.rel(result_json)}
- run_state: {ctx.rel(ctx.state_path(feature))}
- generated_at: {ctx.iso_now()}
- defaults_mode: {str(defaults_mode).lower()}
- interactive_mode: {str(interactive_mode).lower()}
- feature_name_locked: {str(bool(state.get("feature_name_locked"))).lower()}

## Decision Policy
{decision_policy}

## Manual Provider Instructions
1. The local harness is executing this prompt with the preferred model when possible.
2. Make the requested file changes directly in the repository.
3. Write the human-readable stage output file exactly at `{ctx.rel(output)}`.
4. Also write the machine-readable stage result JSON exactly at `{ctx.rel(result_json)}`.
5. Do not run `git commit`, `git reset`, `git checkout`, `git rebase`, or `git push`. The local harness owns Git history.
6. This Git ownership rule overrides any preset text that appears to ask the model to create, amend, or push commits.
7. For every successful stage, leave the working tree commit-ready and record commit intent in the stage output; the harness will create or amend the commit.
8. If `defaults_mode: true`, prefer recommended defaults over `NEEDS_USER` unless blocked by missing credentials, safety, destructive operations, or impossibility.
9. If the stage needs user input under the decision policy, write both outputs with `status: NEEDS_USER`.
10. If the stage fails, write both outputs with `status: FAIL` and a concrete blocking reason.
11. If `feature_name_locked: true`, keep the existing `feature_name` exactly as provided by the harness. Do not rename or invent a different feature slug.
12. End with a concise summary; the harness will inspect files, not your final message.

## Machine Result JSON Contract
The harness reads `{ctx.rel(result_json)}` first. Keep the `## 단계 결과` section in `{ctx.rel(output)}` for humans, but write this JSON file for the harness.

Required JSON keys:
- status: "PASS", "FAIL", "SKIPPED", or "NEEDS_USER"
{next_stage_contract}
- human_gate_required: true or false
- blocking_reason: string, use "" when there is no blocker

For NEEDS_USER in interactive_mode, also include `questions`: an array of question objects.
Each question object must include:
- id: stable snake_case identifier
- type: "choice", "yes_no", or "text"
- question: user-facing question text
- options: for "choice" only, either strings or objects with `id`, `label`, and optional `description`
- default: optional default option/value

Include any extra stage fields that the preset asks for, such as `risk_level`, `harness_commit_required`, `changed_files`, `verification_summary`, or `fix_inputs`.
For PASS or FAIL stages, also include `history_notes` with these arrays when known: `implemented`, `risks`, `future_improvements`, `decisions`, and `unresolved_items`. Use empty arrays for categories with nothing to record. Prefer Korean text for human-facing titles, descriptions, reasons, risks, and decisions when the project context is Korean.

{project_contract}

## Original User Request
{state.get("request", "")}

## Previous Stage Outputs
{chr(10).join(previous_outputs) if previous_outputs else "- none"}

## Additional Stage Inputs
{chr(10).join(additional_inputs) if additional_inputs else "- none"}

## Retry Context
{retry_context if retry_context else "- none"}

## Interactive Answer History
{chr(10).join(answer_history) if answer_history else "- none"}

## Current Git Hints
- current_head: {ctx.safe_git_head()}
- changed_paths_excluding_runs: {json.dumps(ctx.filtered_changed_paths(state, stage), ensure_ascii=False)}
- latest_harness_verification: {ctx.rel(ctx.latest_verification_result_path(feature)) if ctx.latest_verification_result_path(feature).exists() else "none"}

---

"""
    full_prompt = instruction + preset_text
    path = prompt_path(ctx, state, stage)
    path.write_text(full_prompt, encoding="utf-8")
    state["current_stage"] = stage
    state["current_prompt"] = ctx.rel(path)
    state["status"] = RunStatus.WAITING_FOR_MODEL
    ctx.log_event(state, "prompt_generated", "generated prompt", stage=stage, path=ctx.rel(path))
    ctx.save_state(state)
    return path


def print_provider_heartbeat(ctx,
    *,
    stage: str,
    provider: str,
    started: float,
    stdout_path: Path,
    stderr_path: Path,
    last_stdout_size: int,
    last_stderr_size: int,
) -> tuple[int, int]:
    stdout_size = ctx.file_size(stdout_path)
    stderr_size = ctx.file_size(stderr_path)
    stdout_delta = stdout_size - last_stdout_size
    stderr_delta = stderr_size - last_stderr_size
    parts = [
        ctx.color_text(f"[{datetime.now().strftime('%H:%M:%S')}]", "dim"),
        ctx.color_text("[진행중]", "cyan", "bold"),
        f"{ctx.color_text(provider, 'magenta', 'bold')} 실행 중",
        f"stage={stage}",
        f"elapsed={ctx.format_duration(time.time() - started)}",
        f"stdout +{ctx.format_bytes(max(0, stdout_delta))}",
        f"stderr +{ctx.format_bytes(max(0, stderr_delta))}",
    ]
    print(" | ".join(parts), flush=True)
    return stdout_size, stderr_size


def harness_script_for_pipeline_mode(ctx, pipeline_mode: Any) -> str:
    return pipeline.harness_script(pipeline_mode or ctx.PIPELINE_MODE)


def suggested_retry_command(ctx, state: dict[str, Any], *, auto: bool = True) -> str:
    script = harness_script_for_pipeline_mode(ctx, state.get("pipeline_mode"))
    feature = str(state.get("feature_name") or "<feature>")
    parts = ["python", script, "retry", feature]
    if auto:
        parts.extend(["--auto", "--yes"])
    if state.get("defaults_mode"):
        parts.append("--defaults")
    elif state.get("interactive_mode"):
        parts.append("--interactive")
    performance = ctx.normalize_performance(state.get("performance"))
    if performance != ctx.DEFAULT_PERFORMANCE:
        parts.extend(["--performance", performance])
    return " ".join(parts)


def provider_log_hint(ctx, stdout_path: Path, stderr_path: Path, provider_log_path: Path) -> str:
    return (
        f"stdout={ctx.rel(stdout_path)} "
        f"stderr={ctx.rel(stderr_path)} "
        f"provider_log={ctx.rel(provider_log_path)}"
    )


def log_tail(ctx, path: Path, lines: int = 2, max_chars: int = 500) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tail_lines = [line.strip() for line in text.splitlines() if line.strip()][-lines:]
    if not tail_lines:
        return None
    tail = " | ".join(tail_lines)
    if len(tail) > max_chars:
        return tail[: max_chars - 3] + "..."
    return tail


def provider_output_tails(ctx, stdout_path: Path, stderr_path: Path) -> dict[str, str]:
    tails: dict[str, str] = {}
    stdout_tail = log_tail(ctx, stdout_path)
    stderr_tail = log_tail(ctx, stderr_path)
    if stdout_tail:
        tails["stdout_tail"] = stdout_tail
    if stderr_tail:
        tails["stderr_tail"] = stderr_tail
    return tails


def provider_failure_reason(
    ctx, state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    failure: str,
    stdout_path: Path,
    stderr_path: Path,
    provider_log_path: Path,
) -> str:
    retry_command = suggested_retry_command(ctx, state)
    return (
        f"Provider {provider} {failure} while running stage {stage}. "
        f"Inspect logs: {provider_log_hint(ctx, stdout_path, stderr_path, provider_log_path)}. "
        f"Retry current stage: {retry_command}"
    )


def stage_artifact_signature(ctx, paths: list[Path]) -> tuple[tuple[str, int, int], ...] | None:
    signature: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            return None
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        signature.append((ctx.rel(path), stat.st_size, int(mtime_ns)))
    return tuple(signature)


def read_live_stage_result(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def stage_artifact_completion_candidate(
    ctx, feature: str,
    stage: str,
    baseline_signature: tuple[tuple[str, int, int], ...] | None,
) -> dict[str, Any] | None:
    output = ctx.stage_output_path(feature, stage)
    result_json = ctx.stage_result_json_path(feature, stage)
    paths = [output, result_json]
    signature = stage_artifact_signature(ctx, paths)
    if signature is None or signature == baseline_signature:
        return None
    if any(ctx.file_size(path) <= 0 for path in paths):
        return None

    result = read_live_stage_result(result_json)
    if result is None:
        return None
    required = {"status", "next_stage", "human_gate_required", "blocking_reason"}
    if any(key not in result for key in required):
        return None

    status = stage_status(ctx, result)
    if status not in {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.SKIPPED, ResultStatus.NEEDS_USER}:
        return None
    next_stage = str(result.get("next_stage") or stage_default_next(ctx, stage) or "").strip()
    if not next_stage:
        return None
    if next_stage != "done" and next_stage not in ctx.STAGES:
        return None

    return {
        "status": status,
        "next_stage": next_stage,
        "output": ctx.rel(output),
        "result_json": ctx.rel(result_json),
        "signature": signature,
    }


def stop_provider_after_artifact_completion(proc: subprocess.Popen[str]) -> int | None:
    if proc.poll() is not None:
        return proc.returncode
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait()
    return proc.returncode


def git_head_changed(ctx, before_head: str, after_head: str) -> bool:
    return bool(before_head and after_head and before_head != after_head)


def _block_provider_changed_head(
    ctx, state: dict[str, Any], *, stage: str, before_head: str, after_head: str
) -> dict[str, Any]:
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": "Provider changed Git HEAD. The harness owns commits; inspect history before continuing.",
    }
    ctx.write_handoff(
        state,
        str(state["blocked"]["reason"]),
        stage=stage,
        next_action="Git history를 점검한 뒤 수동으로 정리하고 resume 또는 retry 하세요.",
    )
    ctx.log_event(
        state,
        "blocked_provider_changed_head",
        "provider changed Git HEAD",
        stage=stage,
        before_head=before_head,
        after_head=after_head,
    )
    ctx.save_state(state)
    return state


def _finalize_artifact_salvage(
    ctx,
    state: dict[str, Any],
    proc: "subprocess.Popen[str]",
    *,
    stage: str,
    provider: str,
    performance: Any,
    command: list[str],
    prompt_text: str,
    before_head: str,
    completion: dict[str, Any],
    meta_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    cli_log_path: Path,
    started: float,
) -> dict[str, Any]:
    returncode = stop_provider_after_artifact_completion(proc)
    elapsed = round(time.time() - started, 2)
    after_head = ctx.safe_git_head()
    meta_path.write_text(
        json.dumps(
            {
                "stage": stage,
                "provider": provider,
                "performance": performance,
                "performance_settings": ctx.provider_performance_settings(provider, performance),
                "command": ctx.redact_prompt_command(command, prompt_text),
                "returncode": returncode,
                "before_head": before_head,
                "after_head": after_head,
                "stdout": ctx.rel(stdout_path),
                "stderr": ctx.rel(stderr_path),
                "provider_log": ctx.rel(cli_log_path),
                "artifact_salvaged": True,
                "artifact_status": completion["status"],
                "artifact_next_stage": completion["next_stage"],
                "finished_at": ctx.iso_now(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if git_head_changed(ctx, before_head, after_head):
        return _block_provider_changed_head(
            ctx,
            state,
            stage=stage,
            before_head=before_head,
            after_head=after_head,
        )

    state["status"] = RunStatus.MODEL_COMPLETED
    ctx.log_event(
        state,
        "provider_artifact_completed",
        f"{provider} produced stable stage outputs",
        stage=stage,
        provider=provider,
        stdout=ctx.rel(stdout_path),
        stderr=ctx.rel(stderr_path),
        provider_log=ctx.rel(cli_log_path),
        output=completion["output"],
        result_json=completion["result_json"],
        artifact_status=completion["status"],
        artifact_next_stage=completion["next_stage"],
        elapsed_seconds=elapsed,
    )
    ctx.save_state(state)
    return state


def _handle_provider_timeout(
    ctx,
    state: dict[str, Any],
    proc: "subprocess.Popen[str]",
    *,
    stage: str,
    provider: str,
    timeout_seconds: int,
    started: float,
    stdout_path: Path,
    stderr_path: Path,
    cli_log_path: Path,
) -> dict[str, Any]:
    proc.kill()
    proc.wait()
    elapsed = round(time.time() - started, 2)
    reason = provider_failure_reason(
        ctx,
        state,
        stage=stage,
        provider=provider,
        failure=f"timed out after {timeout_seconds} seconds",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        provider_log_path=cli_log_path,
    )
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": reason,
        "stdout": ctx.rel(stdout_path),
        "stderr": ctx.rel(stderr_path),
        "provider_log": ctx.rel(cli_log_path),
        "retry_command": suggested_retry_command(ctx, state),
    }
    ctx.write_handoff(
        state,
        reason,
        stage=stage,
        next_action=f"로그를 확인한 뒤 현재 단계를 다시 실행하세요: {suggested_retry_command(ctx, state)}",
    )
    ctx.log_event(
        state,
        "provider_failed",
        f"{provider} timed out",
        stage=stage,
        provider=provider,
        stdout=ctx.rel(stdout_path),
        stderr=ctx.rel(stderr_path),
        provider_log=ctx.rel(cli_log_path),
        retry_command=suggested_retry_command(ctx, state),
        elapsed_seconds=elapsed,
        **provider_output_tails(ctx, stdout_path, stderr_path),
    )
    ctx.save_state(state)
    return state


def _write_provider_run_meta(
    ctx,
    meta_path: Path,
    *,
    stage: str,
    provider: str,
    performance: Any,
    command: list[str],
    prompt_text: str,
    returncode: Any,
    before_head: str,
    after_head: str,
    stdout_path: Path,
    stderr_path: Path,
    cli_log_path: Path,
) -> None:
    meta_path.write_text(
        json.dumps(
            {
                "stage": stage,
                "provider": provider,
                "performance": performance,
                "performance_settings": ctx.provider_performance_settings(provider, performance),
                "command": ctx.redact_prompt_command(command, prompt_text),
                "returncode": returncode,
                "before_head": before_head,
                "after_head": after_head,
                "stdout": ctx.rel(stdout_path),
                "stderr": ctx.rel(stderr_path),
                "provider_log": ctx.rel(cli_log_path),
                "finished_at": ctx.iso_now(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _handle_provider_nonzero_exit(
    ctx,
    state: dict[str, Any],
    proc: "subprocess.Popen[str]",
    *,
    stage: str,
    provider: str,
    elapsed: float,
    stdout_path: Path,
    stderr_path: Path,
    cli_log_path: Path,
) -> dict[str, Any]:
    reason = provider_failure_reason(
        ctx,
        state,
        stage=stage,
        provider=provider,
        failure=f"exited with code {proc.returncode}",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        provider_log_path=cli_log_path,
    )
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": reason,
        "stdout": ctx.rel(stdout_path),
        "stderr": ctx.rel(stderr_path),
        "provider_log": ctx.rel(cli_log_path),
        "retry_command": suggested_retry_command(ctx, state),
    }
    ctx.write_handoff(
        state,
        reason,
        stage=stage,
        next_action=f"로그를 확인한 뒤 현재 단계를 다시 실행하세요: {suggested_retry_command(ctx, state)}",
    )
    ctx.log_event(
        state,
        "provider_failed",
        f"{provider} exited with {proc.returncode}",
        stage=stage,
        provider=provider,
        returncode=proc.returncode,
        stdout=ctx.rel(stdout_path),
        stderr=ctx.rel(stderr_path),
        provider_log=ctx.rel(cli_log_path),
        retry_command=suggested_retry_command(ctx, state),
        elapsed_seconds=elapsed,
        **provider_output_tails(ctx, stdout_path, stderr_path),
    )
    ctx.save_state(state)
    return state


def _handle_provider_no_output(
    ctx,
    state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    elapsed: float,
    stdout_path: Path,
    stderr_path: Path,
    cli_log_path: Path,
) -> dict[str, Any]:
    reason = provider_failure_reason(
        ctx,
        state,
        stage=stage,
        provider=provider,
        failure="exited with code 0 but produced no stdout, no stderr, and no required outputs",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        provider_log_path=cli_log_path,
    )
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": reason,
        "next_stage": stage,
        "stdout": ctx.rel(stdout_path),
        "stderr": ctx.rel(stderr_path),
        "provider_log": ctx.rel(cli_log_path),
        "retry_command": suggested_retry_command(ctx, state),
    }
    ctx.write_handoff(
        state,
        reason,
        stage=stage,
        next_action=f"provider 설정 또는 인증 상태를 고친 뒤 현재 단계를 다시 실행하세요: {suggested_retry_command(ctx, state)}",
    )
    ctx.log_event(
        state,
        "provider_no_output",
        f"{provider} exited without output",
        stage=stage,
        provider=provider,
        stdout=ctx.rel(stdout_path),
        stderr=ctx.rel(stderr_path),
        provider_log=ctx.rel(cli_log_path),
        retry_command=suggested_retry_command(ctx, state),
        elapsed_seconds=elapsed,
    )
    ctx.save_state(state)
    return state


def _finalize_provider_success(
    ctx,
    state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    elapsed: float,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    state["status"] = RunStatus.MODEL_COMPLETED
    ctx.log_event(
        state,
        "provider_completed",
        f"{provider} completed",
        stage=stage,
        provider=provider,
        stdout=ctx.rel(stdout_path),
        stderr=ctx.rel(stderr_path),
        elapsed_seconds=elapsed,
    )
    ctx.save_state(state)
    return state


def execute_current_prompt(ctx, state: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    feature = state["feature_name"]
    stage = state["current_stage"]
    prompt_rel = state.get("current_prompt")
    if not prompt_rel:
        raise HarnessError("No current prompt to execute.")
    prompt_file = ctx.ROOT / prompt_rel
    if not prompt_file.exists():
        raise HarnessError(f"Prompt file does not exist: {prompt_file}")

    provider = ctx.provider_for_stage(stage, state)
    prompt_text = prompt_file.read_text(encoding="utf-8")
    logs_dir = ctx.run_dir(feature) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    attempt = state.get("attempts", {}).get(stage, 1)
    stdout_path = logs_dir / f"{stage}_attempt{attempt}_{provider}.out.txt"
    stderr_path = logs_dir / f"{stage}_attempt{attempt}_{provider}.err.txt"
    meta_path = logs_dir / f"{stage}_attempt{attempt}_{provider}.json"
    cli_log_path = logs_dir / f"{stage}_attempt{attempt}_{provider}.cli.log"
    performance = ctx.normalize_performance(state.get("performance"))

    command, prompt_in_command = ctx.prepare_provider_command(
        provider,
        prompt_text,
        prompt_file=prompt_file.resolve(),
        log_file=cli_log_path.resolve(),
        performance=performance,
    )
    executable = ctx.resolve_executable(command)
    if not executable:
        raise HarnessError(f"Provider executable not found for {provider}: {command[0]}")

    before_head = ctx.safe_git_head()
    state["status"] = RunStatus.MODEL_RUNNING
    ctx.log_event(
        state,
        "provider_started",
        f"running {provider}",
        stage=stage,
        provider=provider,
        performance=performance,
        timeout_seconds=timeout_seconds,
    )
    ctx.save_state(state)

    started = time.time()
    expected_output = ctx.stage_output_path(feature, stage)
    expected_result_json = ctx.stage_result_json_path(feature, stage)
    initial_artifact_signature = stage_artifact_signature(ctx, [expected_output, expected_result_json])
    output_check_seconds = max(1, int(globals().get("DEFAULT_PROVIDER_OUTPUT_CHECK_SECONDS", 60)))
    stable_checks_required = max(1, int(globals().get("DEFAULT_PROVIDER_OUTPUT_STABLE_CHECKS", 2)))
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_fh, stderr_path.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr_fh:
        proc = subprocess.Popen(
            command,
            cwd=ctx.ROOT,
            stdin=subprocess.PIPE,
            stdout=stdout_fh,
            stderr=stderr_fh,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.stdin and not prompt_in_command:
            proc.stdin.write(prompt_text)
            proc.stdin.close()
        elif proc.stdin:
            proc.stdin.close()

        last_heartbeat = started
        last_stdout_size = 0
        last_stderr_size = 0
        last_output_check = started
        last_completion_signature: tuple[tuple[str, int, int], ...] | None = None
        stable_completion_checks = 0
        while proc.poll() is None:
            now = time.time()
            if now - last_output_check >= output_check_seconds:
                last_output_check = now
                completion = stage_artifact_completion_candidate(ctx,
                    feature,
                    stage,
                    initial_artifact_signature,
                )
                if completion:
                    signature = completion["signature"]
                    if signature == last_completion_signature:
                        stable_completion_checks += 1
                    else:
                        last_completion_signature = signature
                        stable_completion_checks = 1
                    if stable_completion_checks >= stable_checks_required:
                        return _finalize_artifact_salvage(
                            ctx,
                            state,
                            proc,
                            stage=stage,
                            provider=provider,
                            performance=performance,
                            command=command,
                            prompt_text=prompt_text,
                            before_head=before_head,
                            completion=completion,
                            meta_path=meta_path,
                            stdout_path=stdout_path,
                            stderr_path=stderr_path,
                            cli_log_path=cli_log_path,
                            started=started,
                        )
            if timeout_seconds > 0 and now - started > timeout_seconds:
                return _handle_provider_timeout(
                    ctx,
                    state,
                    proc,
                    stage=stage,
                    provider=provider,
                    timeout_seconds=timeout_seconds,
                    started=started,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    cli_log_path=cli_log_path,
                )
            if now - last_heartbeat >= ctx.DEFAULT_PROVIDER_HEARTBEAT_SECONDS:
                last_stdout_size, last_stderr_size = print_provider_heartbeat(ctx,
                    stage=stage,
                    provider=provider,
                    started=started,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    last_stdout_size=last_stdout_size,
                    last_stderr_size=last_stderr_size,
                )
                last_heartbeat = now
            time.sleep(1)

    elapsed = round(time.time() - started, 2)
    after_head = ctx.safe_git_head()
    _write_provider_run_meta(
        ctx,
        meta_path,
        stage=stage,
        provider=provider,
        performance=performance,
        command=command,
        prompt_text=prompt_text,
        returncode=proc.returncode,
        before_head=before_head,
        after_head=after_head,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        cli_log_path=cli_log_path,
    )

    if git_head_changed(ctx, before_head, after_head):
        return _block_provider_changed_head(ctx,
            state,
            stage=stage,
            before_head=before_head,
            after_head=after_head,
        )

    if proc.returncode != 0:
        return _handle_provider_nonzero_exit(
            ctx,
            state,
            proc,
            stage=stage,
            provider=provider,
            elapsed=elapsed,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            cli_log_path=cli_log_path,
        )

    if (
        not expected_output.exists()
        and not expected_result_json.exists()
        and ctx.file_size(stdout_path) == 0
        and ctx.file_size(stderr_path) == 0
    ):
        return _handle_provider_no_output(
            ctx,
            state,
            stage=stage,
            provider=provider,
            elapsed=elapsed,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            cli_log_path=cli_log_path,
        )

    return _finalize_provider_success(
        ctx,
        state,
        stage=stage,
        provider=provider,
        elapsed=elapsed,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


