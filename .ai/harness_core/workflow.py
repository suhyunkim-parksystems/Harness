from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from harness_core import pipeline
from harness_core.errors import HarnessError
from harness_core.status import ResultStatus, RunStatus

from harness_core.questions import (
    QuestionInputError,
    answers_markdown,
    collect_answers,
    normalize_questions,
    summarize_answers,
)

DEFAULT_MAX_VERIFY_FIX_RETRIES = 3


def complete_run(ctx, state: dict[str, Any], stage: str) -> dict[str, Any]:
    state["status"] = RunStatus.COMPLETE
    state["current_stage"] = "done"
    state.pop("blocked", None)
    ctx.log_event(state, "complete", "run complete", stage=stage)
    ctx.save_state(state)
    try:
        history_result = ctx.record_project_history(state)
    except Exception as exc:
        ctx.log_event(
            state,
            "history_failed",
            f"project history update failed: {exc}",
            stage=stage,
        )
    else:
        ctx.log_event(
            state,
            "history_recorded",
            "project history updated",
            stage=stage,
            status=history_result.get("status"),
            event_id=history_result.get("event_id"),
            index=history_result.get("index"),
        )
    ctx.save_state(state)
    return state


def finish_pc_candidate_extraction(ctx, state: dict[str, Any]) -> dict[str, Any]:
    source_stage = str(state.get("pc_candidate_source_stage") or ctx.VERIFY_STAGE)
    try:
        extraction = ctx.extract_project_contract_candidates(state)
    except Exception as exc:
        extraction = {
            "status": "WARN",
            "provider": "unknown",
            "attempts": 0,
            "raw_candidate_count": 0,
            "candidate_count": 0,
            "filtered_out_count": 0,
            "recorded_count": 0,
            "candidate_ids": [],
            "candidates_path": ctx.rel(ctx.pc_candidates_path()),
            "warning": "Project Contract candidate extraction failed before retries completed.",
            "failures": [{"attempt": 0, "reason": str(exc)}],
        }
        state["pc_candidate_extraction"] = extraction
        state.pop("blocked", None)
        state.pop("pc_candidate_source_stage", None)
        ctx.log_event(
            state,
            "pc_candidate_extraction_warning",
            "project contract candidate extraction failed unexpectedly; continuing run",
            stage=ctx.PC_REVIEW_STAGE,
            error=str(exc),
        )
        ctx.save_state(state)
        return complete_run(ctx, state, source_stage)

    state["pc_candidate_extraction"] = extraction
    state.pop("blocked", None)
    state.pop("pc_candidate_source_stage", None)
    ctx.save_state(state)
    return complete_run(ctx, state, source_stage)


def maybe_rename_feature(ctx, state: dict[str, Any]) -> dict[str, Any]:
    old = state["feature_name"]
    if state.get("feature_name_locked"):
        return state
    spec_path = ctx.stage_output_path(old, ctx.START_STAGE)
    if not spec_path.exists():
        return state
    feature_name = ctx.extract_feature_name(spec_path.read_text(encoding="utf-8"))
    if not feature_name:
        result_json = ctx.stage_result_json_path(old, ctx.START_STAGE)
        if result_json.exists():
            try:
                json_feature = ctx.read_stage_result_json(result_json).get("feature_name")
            except HarnessError:
                json_feature = None
            if isinstance(json_feature, str):
                feature_name = json_feature
    if not feature_name or feature_name == old:
        return state
    if not ctx.validate_slug(feature_name):
        state["status"] = RunStatus.BLOCKED
        state["blocked"] = {
            "reason": f"Invalid feature_name in 00_spec.md: {feature_name}",
            "stage": ctx.START_STAGE,
        }
        ctx.save_state(state)
        return state

    old_feature_dir = ctx.feature_dir(old)
    new_feature_dir = ctx.feature_dir(feature_name)
    old_run_dir = ctx.run_dir(old)
    new_run_dir = ctx.run_dir(feature_name)
    if new_feature_dir.exists() or new_run_dir.exists():
        state["status"] = RunStatus.BLOCKED
        state["blocked"] = {
            "reason": f"Cannot rename feature to existing run or feature: {feature_name}",
            "stage": ctx.START_STAGE,
        }
        ctx.save_state(state)
        return state

    if old_feature_dir.exists():
        shutil.move(str(old_feature_dir), str(new_feature_dir))
    state["feature_name"] = feature_name
    state.setdefault("events", []).append(
        {"at": ctx.iso_now(), "event": "feature_renamed", "from": old, "to": feature_name}
    )
    if old_run_dir.exists():
        shutil.move(str(old_run_dir), str(new_run_dir))
    ctx.save_state(state)
    return state


def apply_decision_mode(
    ctx, state: dict[str, Any],
    *,
    defaults: bool = False,
    interactive: bool = False,
    reason: str = "decision mode updated",
) -> dict[str, Any]:
    if defaults and interactive:
        raise HarnessError("--defaults and --interactive cannot be used together.")

    state.setdefault("defaults_mode", False)
    state.setdefault("interactive_mode", False)
    state.setdefault("interactive_answers", [])

    if state.get("defaults_mode") and state.get("interactive_mode"):
        raise HarnessError("Run state is invalid: defaults_mode and interactive_mode are both true.")
    if interactive and state.get("defaults_mode"):
        raise HarnessError("Cannot enable --interactive because this run is already in defaults_mode.")
    if defaults and state.get("interactive_mode"):
        raise HarnessError("Cannot enable --defaults because this run is already in interactive_mode.")

    changed = False
    if defaults and not state.get("defaults_mode"):
        state["defaults_mode"] = True
        state["interactive_mode"] = False
        ctx.log_event(state, "defaults_mode_enabled", reason)
        changed = True
    if interactive and not state.get("interactive_mode"):
        state["interactive_mode"] = True
        state["defaults_mode"] = False
        ctx.log_event(state, "interactive_mode_enabled", reason)
        changed = True
    if changed:
        ctx.save_state(state)
    return state


def _stage_result_status_from_files(ctx, feature: str, stage: str) -> str:
    try:
        result_json = ctx.stage_result_json_path(feature, stage)
        if result_json.exists():
            return ctx.stage_status(ctx.read_stage_result_json(result_json))
        output = ctx.stage_output_path(feature, stage)
        if output.exists():
            return ctx.stage_status(ctx.find_stage_result(output.read_text(encoding="utf-8")))
    except Exception:
        return ""
    return ""


def auto_drive(
    ctx, state: dict[str, Any],
    yes: bool,
    timeout_seconds: int,
    max_steps: int,
    max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES,
) -> dict[str, Any]:
    steps = 0
    ctx.log_event(
        state,
        "auto_started",
        "automatic execution started",
        yes=yes,
        interactive=bool(state.get("interactive_mode")),
        timeout_seconds=timeout_seconds,
        max_steps=max_steps,
        max_verify_fix_retries=max_verify_fix_retries,
    )
    while steps < max_steps:
        steps += 1
        status = state.get("status")
        ctx.log_event(state, "auto_step", "evaluating run state", step=steps, status=status)
        if status == RunStatus.COMPLETE:
            ctx.log_event(state, "auto_complete", "automatic execution complete")
            return state
        if status == RunStatus.BLOCKED:
            blocked = state.get("blocked", {})
            reason = str(blocked.get("reason", ""))
            if yes and "Human gate approval required" in reason:
                ctx.log_event(state, "auto_approving_gate", "auto-approving human gate", reason=reason)
                state = approve_run(ctx, 
                    state["feature_name"],
                    max_verify_fix_retries=max_verify_fix_retries,
                )
                continue
            blocked_stage = str(blocked.get("stage") or state.get("current_stage") or "")
            if (
                state.get("interactive_mode")
                and "requires a TTY" not in reason
                and blocked_stage in ctx.STAGES
                and _stage_result_status_from_files(ctx, state["feature_name"], blocked_stage) == ResultStatus.NEEDS_USER
            ):
                ctx.log_event(
                    state,
                    "auto_resuming_interactive_question",
                    "resuming blocked NEEDS_USER stage in interactive mode",
                    stage=blocked_stage,
                )
                state = resume_run(ctx, 
                    state["feature_name"],
                    max_verify_fix_retries=max_verify_fix_retries,
                )
                continue
            ctx.log_event(state, "auto_blocked", "automatic execution blocked", reason=reason)
            return state
        if status in {RunStatus.CREATED}:
            ctx.generate_prompt(state, state["current_stage"])
            continue
        if status in {RunStatus.WAITING_FOR_MODEL, RunStatus.MODEL_COMPLETED}:
            if status == RunStatus.WAITING_FOR_MODEL:
                state = ctx.execute_current_prompt(state, timeout_seconds)
                if state.get("status") == RunStatus.BLOCKED:
                    return state
            state = resume_run(ctx, state["feature_name"], max_verify_fix_retries=max_verify_fix_retries)
            continue
        raise HarnessError(f"Cannot auto-drive run in status={status!r}")
    raise HarnessError(f"Reached max auto steps ({max_steps}) without completion.")


def step_run(
    ctx, feature: str,
    yes: bool,
    defaults: bool,
    interactive: bool,
    timeout_seconds: int,
    max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES,
) -> dict[str, Any]:
    state = ctx.load_state(feature)
    state = apply_decision_mode(ctx, 
        state,
        defaults=defaults,
        interactive=interactive,
        reason="decision mode enabled for one-stage step",
    )

    ctx.log_event(
        state,
        "step_started",
        "executing one stage only",
        yes=yes,
        interactive=interactive or bool(state.get("interactive_mode")),
        timeout_seconds=timeout_seconds,
        max_verify_fix_retries=max_verify_fix_retries,
    )

    if state.get("status") == RunStatus.COMPLETE:
        ctx.log_event(state, "step_complete", "run is already complete")
        return state

    if state.get("current_stage") == ctx.PC_REVIEW_STAGE:
        return finish_pc_candidate_extraction(ctx, state)

    if state.get("status") == RunStatus.CREATED:
        ctx.generate_prompt(state, state["current_stage"])

    if state.get("status") == RunStatus.BLOCKED:
        blocked = state.get("blocked", {})
        reason = str(blocked.get("reason", ""))
        if yes and "Human gate approval required" in reason:
            ctx.log_event(state, "step_approving_gate", "approving current human gate", reason=reason)
            state = approve_run(ctx, 
                state["feature_name"],
                max_verify_fix_retries=max_verify_fix_retries,
            )
        else:
            ctx.log_event(state, "step_blocked", "one-stage step stopped at blocked state", reason=reason)
            ctx.save_state(state)
            return state

    if state.get("status") == RunStatus.WAITING_FOR_MODEL:
        state = ctx.execute_current_prompt(state, timeout_seconds)
        if state.get("status") == RunStatus.BLOCKED:
            return state

    if state.get("status") == RunStatus.MODEL_COMPLETED:
        return resume_run(ctx, state["feature_name"], max_verify_fix_retries=max_verify_fix_retries)

    if state.get("status") in {RunStatus.WAITING_FOR_MODEL, RunStatus.BLOCKED, RunStatus.COMPLETE}:
        return state

    raise HarnessError(f"Cannot step run in status={state.get('status')!r}")


def safe_git_head(ctx) -> str:
    try:
        return ctx.git_head()
    except Exception:
        return ""


def filtered_changed_paths(ctx, state: dict[str, Any], stage: str) -> list[str]:
    baseline = set(state.get("baseline_dirty", []))
    feature = state["feature_name"]
    paths = []
    for path in ctx.git_changed_paths():
        if path in baseline:
            continue
        if path.startswith(".ai/runs/"):
            continue
        if stage == ctx.VERIFY_RETRY_TARGET_STAGE and path == f".ai/features/{feature}/{ctx.STAGE_OUTPUTS[ctx.VERIFY_STAGE]}":
            continue
        if path.startswith(".ai/docs/") and stage != ctx.DOCUMENT_STAGE:
            continue
        paths.append(path)
    return sorted(set(paths))


def _run_start_dirty_paths(ctx) -> list[str]:
    paths: list[str] = []
    for path in ctx.git_changed_paths():
        normalized = str(path).replace("\\", "/")
        if normalized == "src" or normalized.startswith("src/"):
            paths.append(normalized)
        elif normalized == "tests" or normalized.startswith("tests/"):
            paths.append(normalized)
    return sorted(set(paths))


def _format_run_start_dirty_message(paths: list[str]) -> str:
    lines = [
        "Cannot start a new harness run because implementation paths are already dirty.",
        "",
        "The harness creates local commits for successful stages and treats run start as",
        "the clean baseline. Starting with dirty src/ or tests/ paths can make a later",
        "stage commit exclude real changes.",
        "",
        "Dirty implementation paths:",
    ]
    max_paths = 40
    for path in paths[:max_paths]:
        lines.append(f"  - {path}")
    if len(paths) > max_paths:
        lines.append(f"  - ... and {len(paths) - max_paths} more")
    lines.extend(
        [
            "",
            "What to do next:",
            "  1. Inspect the existing implementation changes:",
            "     git status --short src tests",
            "     git diff -- src tests",
            "  2. If these changes should be kept as current work, commit them yourself first:",
            "     git add src tests",
            "     git commit -m \"save existing implementation changes\"",
            "  3. If you want to set them aside temporarily, stash them yourself:",
            "     git stash push -u -- src tests",
            "  4. If these changes belong to an incomplete harness run, finish that run with resume/retry",
            "     instead of starting a new run:",
            "     python .ai\\harness.py todo",
            "     python .ai\\harness.py resume <feature> --auto --yes --defaults",
            "  5. If the changes are disposable, clean them up explicitly, then start the run again.",
            "",
            "After one of the above actions, rerun your original harness command.",
            "Allowed actions are explicit user choices such as commit, stash, or intentional cleanup.",
            "The harness did not commit, stash, reset, or delete anything.",
        ]
    )
    return "\n".join(lines)


def assert_clean_run_start_paths(ctx) -> None:
    paths = _run_start_dirty_paths(ctx)
    if paths:
        raise HarnessError(_format_run_start_dirty_message(paths))


def commit_for_stage(ctx, state: dict[str, Any], stage: str, result: dict[str, Any]) -> None:
    if stage in ctx.NO_COMMIT_STAGES:
        ctx.log_event(state, "commit_skipped", "stage does not commit", stage=stage)
        return

    status = ctx.stage_status(result)
    if status != ResultStatus.PASS:
        ctx.log_event(
            state,
            "commit_skipped_non_pass",
            "stage did not pass; leaving changes uncommitted",
            stage=stage,
            status=status,
        )
        return

    paths = filtered_changed_paths(ctx, state, stage)
    if not paths:
        raise HarnessError(f"No changed files to commit for {stage}.")

    feature = state["feature_name"]
    commits = state.setdefault("commits", {})
    stage_width = max((len(str(item)) for item in ctx.STAGES), default=len(stage))
    stage_label = stage.ljust(stage_width)
    message = f"[{feature}][{ctx.now_stamp()}][{stage_label}]"

    amend = False
    if stage == ctx.VERIFY_RETRY_TARGET_STAGE and commits.get(ctx.VERIFY_RETRY_TARGET_STAGE):
        head = ctx.git_head()
        if head != commits[ctx.VERIFY_RETRY_TARGET_STAGE]:
            raise HarnessError(
                f"Cannot amend {ctx.VERIFY_RETRY_TARGET_STAGE}: current HEAD is not the recorded "
                f"{ctx.VERIFY_RETRY_TARGET_STAGE} commit. "
                "Stop and inspect git history."
            )
        amend = True

    ctx.log_event(
        state,
        "commit_start",
        "creating stage commit" if not amend else "amending stage commit",
        stage=stage,
        amend=amend,
        paths=",".join(paths),
    )
    ctx.git_add(paths)
    sha = ctx.git_commit(message, amend=amend)
    commits[stage] = sha
    ctx.log_event(
        state,
        "commit_amended" if amend else "commit_created",
        "stage commit recorded",
        stage=stage,
        sha=sha,
        paths=",".join(paths),
    )
    ctx.save_state(state)


def create_run(
    ctx, request: str,
    feature: str | None,
    defaults_mode: bool = False,
    interactive_mode: bool = False,
    deep_thinking: bool = False,
    performance: Any | None = None,
    strategy: Any | None = None,
) -> dict[str, Any]:
    if defaults_mode and interactive_mode:
        raise HarnessError("--defaults and --interactive cannot be used together.")
    strategy_name = str(strategy).strip().lower() if strategy else None
    if deep_thinking:
        ctx.validate_deep_thinking_ready()
    ctx.warn_pending_pc_candidates_for_new_run()
    ctx.assert_no_unpushed_commits_for_new_run()
    ctx.assert_no_incomplete_runs_for_new_run()
    assert_clean_run_start_paths(ctx)
    ctx.ensure_dirs()
    performance_name = ctx.normalize_performance(performance)
    feature_name_locked = feature is not None
    if feature is None:
        feature = ctx.slugify(request)
    if not ctx.validate_slug(feature):
        raise HarnessError("Feature name must use lowercase letters, numbers, and hyphens.")
    if ctx.state_path(feature).exists():
        raise HarnessError(f"Run already exists: {feature}")

    ctx.feature_dir(feature).mkdir(parents=True, exist_ok=True)
    state = {
        "feature_name": feature,
        "feature_name_locked": feature_name_locked,
        "request": request,
        "pipeline_mode": ctx.PIPELINE_MODE,
        "performance": performance_name,
        "defaults_mode": defaults_mode,
        "interactive_mode": interactive_mode,
        "deep_thinking": bool(deep_thinking),
        "strategy": strategy_name,
        "interactive_answers": [],
        "current_stage": ctx.START_STAGE,
        "status": RunStatus.CREATED,
        "created_at": ctx.iso_now(),
        "updated_at": ctx.iso_now(),
        "baseline_dirty": ctx.git_changed_paths(),
        "attempts": {},
        "commits": {},
        "approved_stages": [],
        "events": [],
    }
    ctx.ensure_provider_schedule(state, persist=False, console=False, record_event=False)
    ctx.save_state(state)
    ctx.log_event(
        state,
        "run_created",
        "created feature run",
        request=request,
        feature=feature,
        performance=performance_name,
        defaults_mode=defaults_mode,
        interactive_mode=interactive_mode,
        deep_thinking=bool(deep_thinking),
    )
    ctx.log_event(
        state,
        "provider_schedule_created",
        "created provider schedule",
        schedule=json.dumps(state.get("provider_schedule", {}), ensure_ascii=False),
    )
    ctx.generate_prompt(state, ctx.START_STAGE)
    return state


def apply_runtime_performance(ctx, state: dict[str, Any], performance: Any | None) -> dict[str, Any]:
    if performance is None:
        return state
    performance_name = ctx.normalize_performance(performance)
    previous = state.get("performance")
    state["performance"] = performance_name
    if previous != performance_name:
        ctx.log_event(
            state,
            "performance_updated",
            "performance profile updated",
            performance=performance_name,
            previous_performance=previous,
        )
    ctx.save_state(state)
    return state


def latest_provider_artifacts(
    ctx, feature: str,
    stage: str,
    state: dict[str, Any] | None = None,
) -> dict[str, str]:
    try:
        provider = ctx.provider_for_stage(stage, state)
    except Exception:
        provider = "unknown"
    attempt = 1
    if state:
        attempt = int(state.get("attempts", {}).get(stage, 1))
    logs_dir = ctx.run_dir(feature) / "logs"
    artifacts = {
        "provider": provider,
        "stdout": ctx.rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.out.txt"),
        "stderr": ctx.rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.err.txt"),
        "meta": ctx.rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.json"),
        "provider_log": ctx.rel(logs_dir / f"{stage}_attempt{attempt}_{provider}.cli.log"),
    }
    return artifacts


def handoff_path(ctx, feature: str) -> Path:
    return ctx.run_dir(feature) / "handoff.md"


def safe_read_tail(ctx, path: Path, lines: int = 40, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    text = "\n".join(content[-lines:])
    if len(text) > max_chars:
        return text[-max_chars:]
    return text


def latest_verification_summary(ctx, feature: str) -> dict[str, Any] | None:
    path = ctx.latest_verification_result_path(feature)
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return parsed if isinstance(parsed, dict) else None


def recent_events(ctx, state: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    events = state.get("events", [])
    if not isinstance(events, list):
        return []
    return [event for event in events[-limit:] if isinstance(event, dict)]


def write_handoff(
    ctx, state: dict[str, Any],
    reason: str,
    *,
    stage: str | None = None,
    next_action: str | None = None,
    result: dict[str, Any] | None = None,
) -> Path:
    feature = state["feature_name"]
    stage = stage or str(state.get("current_stage") or "")
    path = handoff_path(ctx, feature)
    path.parent.mkdir(parents=True, exist_ok=True)

    expected_md = ctx.stage_output_path(feature, stage) if stage in ctx.STAGES else None
    expected_json = ctx.stage_result_json_path(feature, stage) if stage in ctx.STAGES else None
    artifacts = latest_provider_artifacts(ctx, feature, stage, state) if stage in ctx.STAGES else {}
    verification = latest_verification_summary(ctx, feature)

    lines = [
        "# 실패 인수인계",
        "",
        f"- feature: {feature}",
        f"- pipeline_mode: {state.get('pipeline_mode') or ctx.PIPELINE_MODE}",
        f"- stage: {stage or '-'}",
        f"- status: {state.get('status') or '-'}",
        f"- generated_at: {ctx.iso_now()}",
        f"- reason: {reason}",
    ]
    if next_action:
        lines.append(f"- next_action: {next_action}")
    if expected_md:
        lines.append(f"- expected_md: {ctx.rel(expected_md)}")
    if expected_json:
        lines.append(f"- expected_json: {ctx.rel(expected_json)}")
    if state.get("current_prompt"):
        lines.append(f"- current_prompt: {state['current_prompt']}")
    if state.get("last_harness_verification"):
        lines.append(f"- latest_harness_verification: {state['last_harness_verification']}")

    lines.extend(["", "## 확인할 로그"])
    if artifacts:
        lines.extend(
            [
                f"- provider: {artifacts.get('provider')}",
                f"- stdout: {artifacts.get('stdout')}",
                f"- stderr: {artifacts.get('stderr')}",
                f"- meta: {artifacts.get('meta')}",
                f"- provider_log: {artifacts.get('provider_log')}",
            ]
        )
    else:
        lines.append("- provider log: 없음")

    if result:
        lines.extend(["", "## 단계 결과"])
        lines.append("```json")
        lines.append(json.dumps(result, ensure_ascii=False, indent=2))
        lines.append("```")

    if verification:
        lines.extend(["", "## 최근 하네스 검증"])
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "status": verification.get("status"),
                    "failed_commands": verification.get("failed_commands", []),
                    "latest_path": verification.get("latest_path"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        lines.append("```")

    events = recent_events(ctx, state)
    if events:
        lines.extend(["", "## 최근 이벤트"])
        for event in events:
            lines.append(
                f"- {event.get('at', '')} [{event.get('stage') or '-'}] "
                f"{event.get('event')}: {event.get('message', '')}"
            )

    if artifacts:
        stdout_tail = safe_read_tail(ctx, ctx.ROOT / artifacts["stdout"], lines=20)
        stderr_tail = safe_read_tail(ctx, ctx.ROOT / artifacts["stderr"], lines=20)
        provider_log_tail = safe_read_tail(ctx, ctx.ROOT / artifacts["provider_log"], lines=30)
        if stdout_tail:
            lines.extend(["", "## stdout 마지막 부분", "```text", stdout_tail, "```"])
        if stderr_tail:
            lines.extend(["", "## stderr 마지막 부분", "```text", stderr_tail, "```"])
        if provider_log_tail:
            lines.extend(["", "## provider log 마지막 부분", "```text", provider_log_tail, "```"])

    lines.extend(
        [
            "",
            "## 다음 모델에게",
            "- 위 reason을 먼저 해결한다.",
            "- 사람이 읽는 md 산출물과 하네스가 읽는 result.json을 둘 다 작성한다.",
            "- Git 커밋은 하지 않는다. 하네스가 커밋을 소유한다.",
        ]
    )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    state["last_handoff"] = ctx.rel(path)
    return path


def missing_stage_output_message(
    ctx, feature: str,
    stage: str,
    output: Path,
    state: dict[str, Any] | None = None,
) -> str:
    artifacts = latest_provider_artifacts(ctx, feature, stage, state)
    provider = artifacts["provider"]
    harness_script = pipeline.harness_script(state.get("pipeline_mode") if state else None)
    return "\n".join(
        [
            ctx.color_text("[실패] 필수 단계 산출물이 없습니다.", "red", "bold"),
            "",
            ctx.color_text("예상 파일:", "yellow", "bold"),
            f"  {ctx.rel(output)}",
            "",
            ctx.color_text("무슨 일이 있었나:", "cyan", "bold"),
            (
                f"  {provider} provider는 종료됐지만, 하네스가 요구한 stage output 파일을 "
                "현재 저장소 안에 만들지 않았습니다."
            ),
            "",
            ctx.color_text("가능한 원인:", "yellow", "bold"),
            "  1. provider가 다른 workspace를 작업 대상으로 잡았습니다.",
            "  2. 모델이 필수 출력 경로 지시를 따르지 않았습니다.",
            "  3. 파일 생성 권한 또는 경로 문제가 있었습니다.",
            "",
            ctx.color_text("확인할 로그:", "cyan", "bold"),
            f"  stdout: {artifacts['stdout']}",
            f"  stderr: {artifacts['stderr']}",
            f"  meta:   {artifacts['meta']}",
            f"  provider_log: {artifacts['provider_log']}",
            "",
            ctx.color_text("다음 조치:", "green", "bold"),
            f"  python {harness_script} todo {feature}",
            "  필요하면 cleanup 후 같은 요청으로 다시 실행하세요.",
        ]
    )


def load_stage_result(
    ctx, feature: str,
    stage: str,
    state: dict[str, Any] | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    output = ctx.stage_output_path(feature, stage)
    if not output.exists():
        if state is not None:
            state["status"] = RunStatus.BLOCKED
            state["blocked"] = {
                "stage": stage,
                "reason": f"Missing stage output: {ctx.rel(output)}",
                "next_stage": stage,
            }
            write_handoff(ctx, 
                state,
                f"Missing stage output: {ctx.rel(output)}",
                stage=stage,
                next_action="retry 명령으로 현재 단계를 다시 실행하거나 provider 로그를 확인하세요.",
            )
            ctx.save_state(state)
        raise HarnessError(missing_stage_output_message(ctx, feature, stage, output, state))
    text = output.read_text(encoding="utf-8")
    result_json = ctx.stage_result_json_path(feature, stage)
    if result_json.exists():
        try:
            result = ctx.read_stage_result_json(result_json)
        except HarnessError as exc:
            if state is not None:
                state["status"] = RunStatus.BLOCKED
                state["blocked"] = {
                    "stage": stage,
                    "reason": str(exc),
                    "next_stage": stage,
                }
                write_handoff(ctx, 
                    state,
                    str(exc),
                    stage=stage,
                    next_action="result.json 형식을 고치거나 retry 명령으로 현재 단계를 다시 실행하세요.",
                )
                ctx.save_state(state)
            raise
    else:
        result = ctx.find_stage_result(text)
    if not result:
        if state is not None:
            state["status"] = RunStatus.BLOCKED
            state["blocked"] = {
                "stage": stage,
                "reason": (
                    f"Missing stage result. Expected {ctx.rel(result_json)} or "
                    f"'## 단계 결과' block in {ctx.rel(output)}"
                ),
                "next_stage": stage,
            }
            write_handoff(ctx, 
                state,
                str(state["blocked"]["reason"]),
                stage=stage,
                next_action="result.json을 보강하거나 retry 명령으로 현재 단계를 다시 실행하세요.",
            )
            ctx.save_state(state)
        raise HarnessError(
            f"Missing stage result. Expected {ctx.rel(result_json)} or '## 단계 결과' block in {ctx.rel(output)}"
        )
    return output, text, result


def expected_docx_path(ctx, feature: str) -> Path:
    return ctx.DOCS_DIR / f"{feature}_명세서.docx"


def validate_document_stage_artifacts(ctx, feature: str) -> str | None:
    return ctx.validate_docx_file(expected_docx_path(ctx, feature))


def block_state(ctx, state: dict[str, Any], stage: str, reason: str, next_stage: str | None = None) -> None:
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {"stage": stage, "reason": reason, "next_stage": next_stage}
    write_handoff(ctx, 
        state,
        reason,
        stage=stage,
        next_action="원인을 확인한 뒤 approve, retry, resume 중 맞는 명령으로 이어가세요.",
    )
    ctx.log_event(state, "blocked", reason, stage=stage, next_stage=next_stage)
    ctx.save_state(state)


def _interactive_answer_path(ctx, feature: str, stage: str, attempt: int) -> Path:
    return ctx.run_dir(feature) / "questions" / f"{stage}_attempt{attempt}_{ctx.now_stamp()}.json"


def _record_interactive_answers(
    ctx, state: dict[str, Any],
    stage: str,
    result: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: list[dict[str, Any]],
) -> tuple[dict[str, Any], Path]:
    feature = state["feature_name"]
    attempt = int(state.get("attempts", {}).get(stage, 0) or 0)
    output = ctx.stage_output_path(feature, stage)
    result_json = ctx.stage_result_json_path(feature, stage)
    record = {
        "feature": feature,
        "stage": stage,
        "attempt": attempt,
        "at": ctx.iso_now(),
        "blocking_reason": str(result.get("blocking_reason") or "Stage requested user input."),
        "source_output": ctx.rel(output),
        "source_result_json": ctx.rel(result_json),
        "questions": questions,
        "answers": answers,
    }
    path = _interactive_answer_path(ctx, feature, stage, attempt)
    ctx.write_json_file(path, record)
    state.setdefault("interactive_answers", []).append(
        {
            "at": record["at"],
            "stage": stage,
            "attempt": attempt,
            "answer_path": ctx.rel(path),
            "summary": summarize_answers(answers),
        }
    )
    return record, path


def _interactive_retry_context(ctx, record: dict[str, Any], answer_path: Path) -> str:
    return "\n".join(
        [
            "This is an interactive retry of the current stage.",
            f"- answers_file: {ctx.rel(answer_path)}",
            "",
            answers_markdown(record),
        ]
    )


def _handle_interactive_needs_user(
    ctx, state: dict[str, Any],
    stage: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    try:
        questions = normalize_questions(result)
        answers = collect_answers(questions, feature=state["feature_name"], stage=stage)
    except QuestionInputError as exc:
        block_state(ctx, state, stage, str(exc), stage)
        return state

    record, answer_path = _record_interactive_answers(ctx, state, stage, result, questions, answers)
    ctx.log_event(
        state,
        "interactive_answers_recorded",
        "recorded interactive answers",
        stage=stage,
        answers=summarize_answers(answers),
        path=ctx.rel(answer_path),
    )
    retry_context = _interactive_retry_context(ctx, record, answer_path)
    archive_stage_outputs_for_retry(ctx, state, stage)
    state.pop("blocked", None)
    ctx.generate_prompt(state, stage, retry_context=retry_context)
    return state


def failed_verification_checks(ctx, result: dict[str, Any]) -> str | None:
    checks: list[str] = []
    verification_summary = result.get("verification_summary")
    if isinstance(verification_summary, dict):
        commands = verification_summary.get("commands")
        if isinstance(commands, list):
            for command in commands:
                if not isinstance(command, dict):
                    continue
                status = str(command.get("status", "")).strip().upper()
                if status != ResultStatus.FAIL:
                    continue
                name = str(command.get("name") or command.get("command") or "").strip()
                summary = str(command.get("summary") or "").strip()
                if name and summary:
                    checks.append(f"{name}: {summary}")
                elif name:
                    checks.append(name)
    return "; ".join(checks) if checks else None


def _final_pipeline_stage(ctx) -> str:
    stages = list(ctx.STAGES)
    return str(stages[-1]) if stages else ""


def _sequential_next_stage(ctx, stage: str) -> str | None:
    stages = list(ctx.STAGES)
    try:
        index = stages.index(stage)
    except ValueError:
        return None
    if index + 1 >= len(stages):
        return None
    return str(stages[index + 1])


def _correct_non_final_done_next_stage(
    ctx,
    state: dict[str, Any],
    stage: str,
    next_stage: str,
) -> str:
    if next_stage != "done":
        return next_stage
    if stage == _final_pipeline_stage(ctx):
        return next_stage

    corrected_next_stage = str(ctx.stage_default_next(stage) or "").strip()
    if not corrected_next_stage or corrected_next_stage == "done":
        corrected_next_stage = str(_sequential_next_stage(ctx, stage) or "").strip()
    if not corrected_next_stage or corrected_next_stage == "done":
        return next_stage

    ctx.log_event(
        state,
        "stage_next_stage_corrected_warning",
        "model returned done for non-final stage; continuing with default next stage",
        stage=stage,
        model_next_stage="done",
        corrected_next_stage=corrected_next_stage,
    )
    return corrected_next_stage


def resume_run(ctx, feature: str, max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES) -> dict[str, Any]:
    state = ctx.load_state(feature)
    if max_verify_fix_retries < 0:
        raise HarnessError("max_verify_fix_retries must be zero or greater.")
    stage = state["current_stage"]
    if stage == ctx.PC_REVIEW_STAGE:
        return finish_pc_candidate_extraction(ctx, state)
    if stage not in ctx.STAGES:
        raise HarnessError(f"Unknown current stage: {stage}")

    output, text, result = load_stage_result(ctx, state["feature_name"], stage, state)
    if stage == ctx.START_STAGE:
        state = maybe_rename_feature(ctx, state)
        feature = state["feature_name"]
        output, text, result = load_stage_result(ctx, feature, stage, state)

    status = ctx.stage_status(result)
    next_stage = str(result.get("next_stage") or ctx.stage_default_next(stage) or "")
    ctx.log_event(state, "stage_result", "parsed stage result", stage=stage, status=status, next_stage=next_stage)
    if stage == ctx.VERIFY_STAGE and status == ResultStatus.FAIL:
        next_stage = ctx.VERIFY_RETRY_TARGET_STAGE
    if status not in {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.SKIPPED, ResultStatus.NEEDS_USER}:
        raise HarnessError(f"Invalid or missing status in {ctx.rel(output)}: {status!r}")

    violations = ctx.write_policy_violations(state, stage)
    if violations:
        block_state(ctx, 
            state,
            stage,
            "Write policy violation: " + "; ".join(violations),
            stage,
        )
        return state

    if status == ResultStatus.NEEDS_USER and state.get("interactive_mode"):
        return _handle_interactive_needs_user(ctx, state, stage, result)

    if status == ResultStatus.NEEDS_USER:
        block_state(ctx, state, stage, result.get("blocking_reason") or "Stage requested user input.", stage)
        return state

    if status == ResultStatus.FAIL and stage != ctx.VERIFY_STAGE:
        block_state(ctx, state, stage, result.get("blocking_reason") or "Stage failed.", next_stage)
        return state

    if ctx.DOCUMENT_STAGE and status == ResultStatus.PASS and stage == ctx.DOCUMENT_STAGE:
        artifact_error = validate_document_stage_artifacts(ctx, state["feature_name"])
        if artifact_error:
            block_state(ctx, state, stage, artifact_error, stage)
            return state

    next_stage = _correct_non_final_done_next_stage(ctx, state, stage, next_stage)

    human_gate = ctx.boolish(result.get("human_gate_required"))
    approved = stage in state.get("approved_stages", [])
    if status == ResultStatus.PASS and human_gate and not approved:
        block_state(ctx, state, stage, "Human gate approval required.", next_stage)
        return state

    if stage == ctx.VERIFY_STAGE:
        status, next_stage = ctx.enforce_harness_verify_result(state, result, status, next_stage)

    if stage == ctx.VERIFY_STAGE and status == ResultStatus.FAIL:
        retries_used = int(state.get("verify_fix_retries_used", 0))
        if retries_used >= max_verify_fix_retries:
            block_state(ctx,
                state,
                stage,
                (
                    "Verify/Fix retry limit reached "
                    f"({retries_used}/{max_verify_fix_retries}). "
                    "Resume with a higher --max-verify-fix-retries value if this feature needs more iterations."
                ),
                stage,
            )
            return state

    commit_for_stage(ctx, state, stage, result)

    if stage == ctx.VERIFY_STAGE and status == ResultStatus.FAIL:
        write_handoff(ctx,
            state,
            result.get("blocking_reason") or "Verify stage failed.",
            stage=stage,
            next_action=f"{ctx.VERIFY_RETRY_TARGET_STAGE} 단계가 이 실패를 수정해야 합니다.",
            result=result,
        )
        # Increment the retry counter together with the stage transition so a
        # single save (generate_prompt below) persists both atomically.
        # Persisting the counter while current_stage was still the verify stage
        # left a crash window where resume would re-count the same failure and
        # double-spend the retry budget. write_handoff does not save run.json,
        # so nothing persists the incremented counter before this point.
        state["verify_fix_retries_used"] = int(state.get("verify_fix_retries_used", 0)) + 1
        state["current_stage"] = ctx.VERIFY_RETRY_TARGET_STAGE
        state["status"] = RunStatus.WAITING_FOR_MODEL
        ctx.log_event(
            state,
            "verify_fix_retry_recorded",
            "recorded verify/fix retry",
            stage=stage,
            retries_used=state["verify_fix_retries_used"],
            max_verify_fix_retries=max_verify_fix_retries,
        )
        ctx.log_event(
            state,
            "verify_failed_returning_to_development",
            f"returning to {ctx.VERIFY_RETRY_TARGET_STAGE} after failed verify",
            stage=stage,
            blocking_reason=result.get("blocking_reason") or "Verify stage failed.",
            failed_checks=failed_verification_checks(ctx, result),
        )
        ctx.generate_prompt(state, ctx.VERIFY_RETRY_TARGET_STAGE)
        return state

    if (ctx.DOCUMENT_STAGE and stage == ctx.DOCUMENT_STAGE) or next_stage == "done":
        if ctx.should_extract_pc_candidates(state):
            state["status"] = RunStatus.PC_CANDIDATES_PENDING
            state["current_stage"] = ctx.PC_REVIEW_STAGE
            state["pc_candidate_source_stage"] = stage
            ctx.log_event(
                state,
                "pc_candidate_extraction_queued",
                "queued project contract candidate extraction",
                stage=stage,
            )
            ctx.save_state(state)
            return finish_pc_candidate_extraction(ctx, state)
        return complete_run(ctx, state, stage)

    if next_stage not in ctx.STAGES:
        raise HarnessError(f"Invalid next_stage: {next_stage}")

    state["current_stage"] = next_stage
    state["status"] = RunStatus.WAITING_FOR_MODEL
    state.pop("blocked", None)
    ctx.log_event(state, "stage_advanced", "advanced to next stage", stage=stage, next_stage=next_stage)
    ctx.save_state(state)
    ctx.generate_prompt(state, next_stage)
    return state


def approve_run(ctx, feature: str, max_verify_fix_retries: int = DEFAULT_MAX_VERIFY_FIX_RETRIES) -> dict[str, Any]:
    state = ctx.load_state(feature)
    blocked = state.get("blocked")
    if not blocked:
        raise HarnessError("Run is not blocked.")
    stage = blocked.get("stage")
    if not stage:
        raise HarnessError("Blocked state has no stage.")
    approved_stages = state.setdefault("approved_stages", [])
    if stage not in approved_stages:
        approved_stages.append(stage)
    ctx.log_event(state, "approved", "human gate approved", stage=stage)
    state["current_stage"] = stage
    state["status"] = RunStatus.MODEL_COMPLETED
    state.pop("blocked", None)
    ctx.save_state(state)

    return resume_run(ctx, state["feature_name"], max_verify_fix_retries=max_verify_fix_retries)


def build_retry_context(ctx, state: dict[str, Any], stage: str) -> str:
    feature = state["feature_name"]
    blocked = state.get("blocked") if isinstance(state.get("blocked"), dict) else {}
    reason = str(blocked.get("reason") or "Manual retry requested.")
    handoff = write_handoff(ctx, 
        state,
        reason,
        stage=stage,
        next_action="retry가 현재 단계를 보강 프롬프트로 다시 실행합니다.",
    )
    artifacts = latest_provider_artifacts(ctx, feature, stage, state)
    output = ctx.stage_output_path(feature, stage)
    result_json = ctx.stage_result_json_path(feature, stage)
    parts = [
        "This is a retry of the current stage. Fix the previous failure and overwrite both required outputs.",
        "",
        f"- retry_stage: {stage}",
        f"- failure_reason: {reason}",
        f"- handoff_file: {ctx.rel(handoff)}",
        f"- required_md_output: {ctx.rel(output)}",
        f"- required_result_json: {ctx.rel(result_json)}",
        f"- provider_stdout: {artifacts['stdout']}",
        f"- provider_stderr: {artifacts['stderr']}",
        f"- provider_meta: {artifacts['meta']}",
        "",
        "Retry checklist:",
        "1. Work in the repository root shown by the harness context.",
        "2. Do not reuse stale stage results. Overwrite the md output and result.json for this stage.",
        "3. If the prior failure was a missing output, create the exact paths above.",
        "4. If verification failed, read the latest verification JSON and fix the failed commands.",
        "5. Do not commit. The harness owns Git history.",
    ]
    verification = ctx.latest_verification_result_path(feature)
    if verification.exists():
        parts.append(f"- latest_harness_verification: {ctx.rel(verification)}")
    handoff_tail = safe_read_tail(ctx, handoff, lines=80)
    if handoff_tail:
        parts.extend(["", "Latest handoff.md:", "```md", handoff_tail, "```"])
    return "\n".join(parts)


def copy_same_prompt_for_retry(ctx, state: dict[str, Any], stage: str) -> Path:
    current_prompt = state.get("current_prompt")
    if not current_prompt:
        return ctx.generate_prompt(state, stage)
    source = ctx.ROOT / current_prompt
    if not source.exists():
        return ctx.generate_prompt(state, stage)

    state.setdefault("stage_file_snapshots", {})[stage] = ctx.file_policy_snapshot(state["feature_name"])
    path = ctx.prompt_path(state, stage)
    path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    state["current_stage"] = stage
    state["current_prompt"] = ctx.rel(path)
    state["status"] = RunStatus.WAITING_FOR_MODEL
    state.pop("blocked", None)
    ctx.log_event(state, "retry_prompt_generated", "copied same prompt for retry", stage=stage, path=ctx.rel(path))
    ctx.save_state(state)
    return path


def archive_stage_outputs_for_retry(ctx, state: dict[str, Any], stage: str) -> None:
    feature = state["feature_name"]
    archive_dir = ctx.run_dir(feature) / "retry_archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    attempt = int(state.get("attempts", {}).get(stage, 0) or 0)
    stamp = ctx.now_stamp()
    archived: list[str] = []
    for path in [ctx.stage_output_path(feature, stage), ctx.stage_result_json_path(feature, stage)]:
        if not path.exists():
            continue
        target = archive_dir / f"{stage}_attempt{attempt}_{stamp}_{path.name}"
        shutil.copyfile(path, target)
        path.unlink()
        archived.append(ctx.rel(target))
    if archived:
        state.setdefault("retry_archives", []).append(
            {"stage": stage, "at": ctx.iso_now(), "files": archived}
        )
        ctx.log_event(
            state,
            "retry_outputs_archived",
            "archived stale stage outputs before retry",
            stage=stage,
            files=",".join(archived),
        )


def retry_run(
    ctx, feature: str,
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
    state = ctx.load_state(feature)
    state = apply_decision_mode(ctx, 
        state,
        defaults=defaults,
        interactive=interactive,
        reason="decision mode enabled before retry",
    )
    blocked = state.get("blocked") if isinstance(state.get("blocked"), dict) else {}
    stage = str(blocked.get("stage") or state.get("current_stage") or "")
    if stage not in ctx.STAGES:
        raise HarnessError(f"Cannot retry stage: {stage!r}")
    if state.get("status") == RunStatus.COMPLETE or stage == "done":
        raise HarnessError("Run is already complete; there is no current stage to retry.")

    state["current_stage"] = stage
    if same:
        archive_stage_outputs_for_retry(ctx, state, stage)
        copy_same_prompt_for_retry(ctx, state, stage)
        state = ctx.load_state(feature)
    else:
        retry_context = build_retry_context(ctx, state, stage)
        archive_stage_outputs_for_retry(ctx, state, stage)
        state.pop("blocked", None)
        ctx.generate_prompt(state, stage, retry_context=retry_context)
        state = ctx.load_state(feature)
        ctx.log_event(state, "retry_prompt_generated", "generated enriched retry prompt", stage=stage)
        ctx.save_state(state)

    if prompt_only:
        return state

    state = ctx.execute_current_prompt(state, timeout_seconds)
    if state.get("status") == RunStatus.BLOCKED:
        return state
    state = resume_run(ctx, state["feature_name"], max_verify_fix_retries=max_verify_fix_retries)
    if auto and state.get("status") not in {RunStatus.COMPLETE, RunStatus.BLOCKED}:
        state = auto_drive(ctx, 
            state,
            yes=yes,
            timeout_seconds=timeout_seconds,
            max_steps=max_steps,
            max_verify_fix_retries=max_verify_fix_retries,
        )
    return state


