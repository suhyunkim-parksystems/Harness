from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import HarnessRuntime

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

from . import pipeline
from .errors import HarnessError
from .json_io import read_json_value_file


PROVIDER_EXECUTABLE_ENV_VARS = {
    "codex": ("HARNESS_CODEX_EXECUTABLE", "CODEX_EXECUTABLE", "CODEX_BIN", "CODEX_EXE"),
    "claude": ("HARNESS_CLAUDE_EXECUTABLE", "CLAUDE_EXECUTABLE", "CLAUDE_BIN", "CLAUDE_EXE"),
    "agy": ("HARNESS_AGY_EXECUTABLE", "AGY_EXECUTABLE", "AGY_BIN", "AGY_EXE"),
}

PROVIDER_EXECUTABLE_NAMES = {
    "codex": ("codex.cmd", "codex.exe", "codex"),
    "claude": ("claude", "claude.cmd", "claude.exe"),
    "agy": ("agy.exe", "agy.cmd", "agy"),
}


def load_config(ctx: HarnessRuntime) -> dict[str, Any]:
    base = _read_config_file(ctx.config_path())
    project = _read_config_file(ctx.project_config_path())
    return merge_config(base, project)


def config_path(ctx: HarnessRuntime) -> Path:
    return ctx.HARNESS_CONFIG_PATH or (ctx.AI_DIR / "harness.config.json")


def project_config_path(ctx: HarnessRuntime) -> Path:
    return ctx.PROJECT_CONFIG_PATH or (ctx.PROJECT_DIR / "harness.config.json")


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = read_json_value_file(path)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HarnessError(f"harness config must be an object: {path}")
    return value


def load_project_config(ctx: HarnessRuntime) -> dict[str, Any]:
    return _read_config_file(ctx.project_config_path())


def _command_config_identity(item: Any) -> str:
    if isinstance(item, dict):
        command = item.get("command")
        cwd = item.get("cwd", ".")
        timeout_seconds = item.get("timeout_seconds")
    else:
        command = item
        cwd = "."
        timeout_seconds = None
    return json.dumps(
        {
            "command": command,
            "cwd": cwd,
            "timeout_seconds": timeout_seconds,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _merge_command_lists(base: list[Any], override: list[Any]) -> list[Any]:
    merged = [copy.deepcopy(item) for item in base]
    seen = {_command_config_identity(item) for item in merged}
    for item in override:
        identity = _command_config_identity(item)
        if identity in seen:
            continue
        merged.append(copy.deepcopy(item))
        seen.add(identity)
    return merged


def merge_config(base: dict[str, Any], override: dict[str, Any], path: tuple[str, ...] = ()) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        next_path = (*path, str(key))
        if next_path == ("verification", "commands") and isinstance(merged.get(key), list) and isinstance(value, list):
            merged[key] = _merge_command_lists(merged[key], value)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value, next_path)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def write_config(ctx: HarnessRuntime, config: dict[str, Any]) -> None:
    ctx.write_json_file(ctx.config_path(), config)


def write_project_config(ctx: HarnessRuntime, config: dict[str, Any]) -> None:
    ctx.write_json_file(ctx.project_config_path(), config)


def raw_provider_command(ctx: HarnessRuntime, provider: str) -> list[str]:
    config = ctx.load_config()
    configured = config.get("providers", {}).get(provider, {}).get("command")
    command = configured or ctx.DEFAULT_PROVIDER_COMMANDS.get(provider)
    if not command:
        raise HarnessError(f"No provider command configured for {provider}")
    return [str(part) for part in command]


def normalize_performance(ctx: HarnessRuntime, value: Any | None) -> str:
    if value is None or str(value).strip() == "":
        return ctx.DEFAULT_PERFORMANCE
    performance = str(value).strip().lower()
    if performance not in ctx.PERFORMANCE_PROFILES:
        allowed = ", ".join(ctx.PERFORMANCE_PROFILES)
        raise HarnessError(f"Unknown performance profile {value!r}. Expected one of: {allowed}.")
    return performance


def performance_profile(ctx: HarnessRuntime, value: Any | None) -> dict[str, dict[str, str]]:
    return ctx.PERFORMANCE_PROFILES[ctx.normalize_performance(value)]


def provider_performance_settings(ctx: HarnessRuntime, provider: str, performance: Any | None) -> dict[str, str]:
    return dict(ctx.performance_profile(performance).get(provider, {}))


def command_has_option(command: list[str], *options: str) -> bool:
    for part in command:
        if part in options:
            return True
        for option in options:
            if option.startswith("--") and part.startswith(f"{option}="):
                return True
    return False


def command_has_config_key(command: list[str], key: str) -> bool:
    return any(key in part for part in command)


def append_before_stdin_prompt(command: list[str], extra: list[str]) -> list[str]:
    if command and command[-1] == "-":
        return command[:-1] + extra + ["-"]
    return command + extra


def _normalize_executable_candidate(value: Any) -> str:
    candidate = str(value or "").strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {"'", '"'}:
        candidate = candidate[1:-1].strip()
    return candidate


def _dedupe_executable_candidates(candidates: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_executable_candidate(candidate)
        if not normalized:
            continue
        key = normalized.lower() if os.name == "nt" else normalized
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def provider_executable_candidates(provider: str, command: list[str]) -> list[str]:
    candidates: list[str] = []
    env_vars = PROVIDER_EXECUTABLE_ENV_VARS.get(provider, ())
    candidates.extend(os.environ.get(name, "") for name in env_vars)
    if command:
        candidates.append(command[0])
    candidates.extend(PROVIDER_EXECUTABLE_NAMES.get(provider, ()))
    return _dedupe_executable_candidates(candidates)


def resolve_provider_executable(provider: str, command: list[str]) -> str | None:
    for candidate in provider_executable_candidates(provider, command):
        executable = shutil.which(candidate)
        if executable:
            return executable
    return None


def resolve_provider_command(provider: str, command: list[str]) -> list[str]:
    if not command:
        return command
    executable = resolve_provider_executable(provider, command)
    if not executable:
        return command
    return [executable, *command[1:]]


def apply_performance_to_command(
    ctx: HarnessRuntime,
    provider: str,
    command: list[str],
    performance: Any | None,
) -> list[str]:
    settings = ctx.provider_performance_settings(provider, performance)
    if provider == "codex":
        extra: list[str] = []
        model = settings.get("model")
        effort = settings.get("model_reasoning_effort")
        if model and not command_has_option(command, "--model", "-m"):
            extra.extend(["--model", model])
        if effort and not command_has_config_key(command, "model_reasoning_effort"):
            extra.extend(["-c", f'model_reasoning_effort="{effort}"'])
        return append_before_stdin_prompt(command, extra) if extra else command
    if provider == "claude":
        extra = []
        model = settings.get("model")
        effort = settings.get("effort")
        if model and not command_has_option(command, "--model"):
            extra.extend(["--model", model])
        if effort and not command_has_option(command, "--effort"):
            extra.extend(["--effort", effort])
        return append_before_stdin_prompt(command, extra) if extra else command
    return command


def prepare_provider_command(
    ctx: HarnessRuntime,
    provider: str,
    prompt_text: str | None = None,
    prompt_file: Path | None = None,
    log_file: Path | None = None,
    performance: Any | None = None,
) -> tuple[list[str], bool]:
    uses_prompt_placeholder = False
    command: list[str] = []
    root = ctx.ROOT
    for part in ctx.raw_provider_command(provider):
        rendered = part.replace("{cwd}", str(root))
        if "{log_file}" in rendered:
            rendered = rendered.replace("{log_file}", str(log_file) if log_file is not None else "<log_file>")
        if "{prompt_file}" in rendered and prompt_file is not None:
            rendered = rendered.replace("{prompt_file}", str(prompt_file))
        if "{prompt_file_instruction}" in rendered:
            uses_prompt_placeholder = True
            if prompt_file is None:
                instruction = "<prompt>"
            else:
                instruction = (
                    "Read the harness prompt file at "
                    f"{prompt_file} and execute every instruction in it. "
                    "Write the required repository files exactly as specified. "
                    "Do not summarize only; perform the task."
                )
            rendered = rendered.replace("{prompt_file_instruction}", instruction)
        if "{prompt}" in rendered:
            uses_prompt_placeholder = True
            rendered = rendered.replace("{prompt}", prompt_text if prompt_text is not None else "<prompt>")
        command.append(rendered)
    command = ctx.apply_performance_to_command(provider, command, performance)
    command = resolve_provider_command(provider, command)
    return command, uses_prompt_placeholder


def provider_command(ctx: HarnessRuntime, provider: str) -> list[str]:
    command, _ = ctx.prepare_provider_command(provider)
    return command


def redact_prompt_command(command: list[str], prompt_text: str | None) -> list[str]:
    if not prompt_text:
        return command
    return ["<prompt>" if part == prompt_text else part.replace(prompt_text, "<prompt>") for part in command]


def preset_provider_for_stage(ctx: HarnessRuntime, stage: str) -> str | None:
    if stage == ctx.PC_REVIEW_STAGE:
        return None
    meta, _, _ = ctx.read_preset(stage)
    preferred = str(meta.get("preferred_model", ""))
    provider = ctx.PROVIDER_BY_MODEL.get(preferred)
    if not provider:
        raise HarnessError(f"No provider mapped for preferred_model={preferred!r} stage={stage}")
    return provider


def resolve_executable(command: list[str]) -> str | None:
    if not command:
        return None
    return shutil.which(command[0])


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def model_policy(ctx: HarnessRuntime) -> dict[str, Any]:
    config = ctx.load_config()
    raw = config.get("model_policy", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise HarnessError("model_policy config must be an object.")
    return merge_dicts(ctx.DEFAULT_MODEL_POLICY, raw)


def ordered_unique(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip().lower()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def known_provider_names(ctx: HarnessRuntime) -> list[str]:
    config = ctx.load_config()
    configured = []
    providers = config.get("providers", {})
    if isinstance(providers, dict):
        configured = [str(provider) for provider in providers]
    return ordered_unique([*ctx.PROVIDERS, *configured])


def provider_config(ctx: HarnessRuntime, provider: str) -> dict[str, Any]:
    config = ctx.load_config()
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        return {}
    provider_config = providers.get(provider, {})
    return provider_config if isinstance(provider_config, dict) else {}


def provider_enabled(ctx: HarnessRuntime, provider: str) -> bool:
    return ctx.provider_config(provider).get("enabled", True) is not False


def provider_capabilities(ctx: HarnessRuntime, provider: str) -> set[str]:
    configured = ctx.provider_config(provider).get("capabilities")
    if isinstance(configured, list):
        return {str(item).strip() for item in configured if str(item).strip()}
    return set(ctx.DEFAULT_PROVIDER_CAPABILITIES.get(provider, []))


def provider_available(ctx: HarnessRuntime, provider: str) -> bool:
    if not ctx.provider_enabled(provider):
        return False
    try:
        command = ctx.provider_command(provider)
    except HarnessError:
        return False
    return ctx.resolve_executable(command) is not None


def available_providers(ctx: HarnessRuntime) -> list[str]:
    return [provider for provider in ctx.known_provider_names() if ctx.provider_available(provider)]


def pipeline_extracts_pc_candidates(ctx: HarnessRuntime, pipeline_mode: Any) -> bool:
    return pipeline.extracts_pc_candidates(pipeline_mode or ctx.PIPELINE_MODE)


def provider_schedule_stages(ctx: HarnessRuntime, state: dict[str, Any]) -> list[str]:
    stages = list(ctx.STAGES)
    if ctx.pipeline_extracts_pc_candidates(state.get("pipeline_mode") or ctx.PIPELINE_MODE):
        stages.append(ctx.PC_REVIEW_STAGE)
    return stages


def stage_role(ctx: HarnessRuntime, stage: str) -> str:
    if stage == ctx.PC_REVIEW_STAGE:
        return "pc_extract"
    lowered = stage.lower()
    if "develop" in lowered or "fix" in lowered:
        return "code_write"
    if "review" in lowered:
        return "review"
    if "verify" in lowered:
        return "verify"
    if "document" in lowered:
        return "document"
    if "spec" in lowered or "plan" in lowered:
        return "plan"
    return "plan"


def provider_order_for_role(ctx: HarnessRuntime, stage: str, role: str, policy: dict[str, Any]) -> list[str]:
    preferred: list[str] = []
    preset_provider = ctx.preset_provider_for_stage(stage) if stage in ctx.STAGES else None
    if preset_provider:
        preferred.append(preset_provider)

    if role == "code_write":
        preferred.extend(str(item) for item in policy.get("code_write_order", []))
    else:
        role_orders = policy.get("role_orders", {})
        if isinstance(role_orders, dict) and isinstance(role_orders.get(role), list):
            preferred.extend(str(item) for item in role_orders[role])
        else:
            preferred.extend(str(item) for item in policy.get("non_code_order", []))
    preferred.extend(ctx.known_provider_names())
    return ordered_unique(preferred)


def candidate_providers_for_stage(
    ctx: HarnessRuntime,
    stage: str,
    policy: dict[str, Any],
    available: list[str],
) -> list[str]:
    role = ctx.stage_role(stage)
    available_set = set(available)
    denied = {str(item).strip().lower() for item in policy.get("code_write_denied", [])}
    allowed = {str(item).strip().lower() for item in policy.get("code_write_allowed", [])}
    candidates: list[str] = []
    for provider in ctx.provider_order_for_role(stage, role, policy):
        if provider not in available_set:
            continue
        caps = ctx.provider_capabilities(provider)
        if role not in caps:
            continue
        if role == "code_write":
            if provider in denied:
                continue
            if allowed and provider not in allowed:
                continue
        candidates.append(provider)
    return ordered_unique(candidates)


def latest_code_writer(ctx: HarnessRuntime, assignments: dict[str, str], stages: list[str]) -> str | None:
    for stage in reversed(stages):
        provider = assignments.get(stage)
        if provider and ctx.stage_role(stage) == "code_write":
            return provider
    return None


def stage_provider_score(
    ctx: HarnessRuntime,
    stage: str,
    provider: str,
    candidates: list[str],
    assignments: dict[str, str],
    ordered_stages: list[str],
    policy: dict[str, Any],
) -> int:
    role = ctx.stage_role(stage)
    score = candidates.index(provider) * 100
    if role != "code_write" and policy.get("reserve_code_writers_for_code_stages", True):
        code_order = ordered_unique([str(item) for item in policy.get("code_write_order", [])])
        non_code_candidates = [
            item for item in candidates if "code_write" not in ctx.provider_capabilities(item)
        ]
        if provider in code_order and non_code_candidates:
            score += 30
    if (
        role in {"review", "verify", "pc_extract"}
        and policy.get("avoid_reusing_recent_code_writer_for_review", True)
        and ctx.latest_code_writer(assignments, ordered_stages) == provider
        and len(candidates) > 1
    ):
        score += 80
    return score


def compute_provider_schedule(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    *,
    strict_independence: bool,
) -> dict[str, str] | None:
    policy = ctx.model_policy()
    available = ctx.available_providers()
    min_distinct = int(policy.get("min_distinct_agents", 2) or 0)
    if len(available) < min_distinct:
        available_text = ", ".join(available) if available else "none"
        raise HarnessError(
            f"At least {min_distinct} distinct available providers are required by model_policy. "
            f"Available providers: {available_text}."
        )

    stages = ctx.provider_schedule_stages(state)
    states: list[tuple[int, dict[str, str]]] = [(0, {})]
    for stage in stages:
        candidates = ctx.candidate_providers_for_stage(stage, policy, available)
        if not candidates:
            raise HarnessError(
                f"No available provider can run stage {stage} with role={ctx.stage_role(stage)}. "
                "Check model_policy providers, capabilities, and installed CLIs."
            )
        next_states: list[tuple[int, dict[str, str]]] = []
        for cost, assignments in states:
            previous_provider = assignments.get(stages[len(assignments) - 1]) if assignments else None
            for provider in candidates:
                if strict_independence and previous_provider == provider:
                    continue
                next_assignments = dict(assignments)
                add = ctx.stage_provider_score(
                    stage,
                    provider,
                    candidates,
                    assignments,
                    stages[: len(assignments)],
                    policy,
                )
                next_assignments[stage] = provider
                next_states.append((cost + add, next_assignments))
        if not next_states:
            return None
        next_states.sort(key=lambda item: (item[0], [item[1].get(stage, "") for stage in stages]))
        states = next_states[:200]

    cost, schedule = min(states, key=lambda item: (item[0], [item[1].get(stage, "") for stage in stages]))
    if len(set(schedule.values())) < min_distinct:
        raise HarnessError(
            f"Provider schedule uses fewer than {min_distinct} distinct providers: {schedule}"
        )
    return schedule


def build_provider_schedule(ctx: HarnessRuntime, state: dict[str, Any]) -> dict[str, str]:
    policy = ctx.model_policy()
    strict = bool(policy.get("no_adjacent_same_provider", True))
    schedule = ctx.compute_provider_schedule(state, strict_independence=strict)
    if schedule is not None:
        return schedule
    mode = str(policy.get("on_independence_violation", "block")).strip().lower()
    if mode == "allow":
        fallback = ctx.compute_provider_schedule(state, strict_independence=False)
        if fallback is not None:
            return fallback
    raise HarnessError(
        "Cannot build a provider schedule that preserves model independence. "
        "Add another available provider or relax model_policy.on_independence_violation."
    )


def ensure_provider_schedule(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    *,
    persist: bool = True,
    console: bool = False,
    record_event: bool = True,
) -> dict[str, str]:
    stages = ctx.provider_schedule_stages(state)
    existing = state.get("provider_schedule")
    if isinstance(existing, dict) and all(str(existing.get(stage) or "") for stage in stages):
        return {stage: str(existing[stage]) for stage in stages}

    schedule = ctx.build_provider_schedule(state)
    state["provider_schedule"] = schedule
    state["provider_policy"] = {
        "min_distinct_agents": int(ctx.model_policy().get("min_distinct_agents", 2) or 0),
        "no_adjacent_same_provider": bool(ctx.model_policy().get("no_adjacent_same_provider", True)),
        "code_write_allowed": ctx.model_policy().get("code_write_allowed", []),
        "code_write_denied": ctx.model_policy().get("code_write_denied", []),
    }
    if record_event and state.get("events") is not None:
        ctx.log_event(
            state,
            "provider_schedule_created",
            "created provider schedule",
            console=console,
            schedule=json.dumps(schedule, ensure_ascii=False),
        )
    if persist and ctx.state_path(state["feature_name"]).exists():
        ctx.save_state(state)
    return schedule


def provider_for_stage(ctx: HarnessRuntime, stage: str, state: dict[str, Any] | None = None) -> str:
    if state is not None:
        schedule = ctx.ensure_provider_schedule(state, record_event=False)
        provider = str(schedule.get(stage) or "")
        if provider:
            return provider
    provider = ctx.preset_provider_for_stage(stage)
    if provider:
        return provider
    policy = ctx.model_policy()
    available = ctx.available_providers()
    candidates = ctx.candidate_providers_for_stage(stage, policy, available)
    if not candidates:
        raise HarnessError(f"No provider available for stage {stage}.")
    return candidates[0]

