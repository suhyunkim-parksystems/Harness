from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import HarnessRuntime

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .errors import HarnessError
from .status import ResultStatus

from .text import boolish, slugify


DYNAMIC_VERIFICATION_FIELDS = ("test_commands", "recommended_verification_commands")
SHELL_WRAPPER_EXECUTABLES = {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "bash", "sh", "wsl"}
DANGEROUS_EXECUTABLES = {
    "curl",
    "curl.exe",
    "wget",
    "wget.exe",
    "rm",
    "del",
    "erase",
    "remove-item",
    "rmdir",
    "rd",
}
DANGEROUS_GIT_SUBCOMMANDS = {"push", "reset", "clean", "checkout", "restore", "rebase"}
SHELL_CONTROL_TOKENS = {"|", "||", "&&", "&", ";", "<", ">", ">>", "2>", "2>>"}


def _is_pytest_command(command: list[str]) -> bool:
    executable = _executable_name(command)
    if executable in {"pytest", "pytest.exe"}:
        return True
    return (
        executable in {"python", "python.exe", "py", "py.exe"}
        and len(command) >= 3
        and command[1] == "-m"
        and command[2] == "pytest"
    )


def _without_pytest_basetemp(command: list[str]) -> list[str]:
    cleaned: list[str] = []
    skip_next = False
    for part in command:
        text = str(part)
        if skip_next:
            skip_next = False
            continue
        if text == "--basetemp":
            skip_next = True
            continue
        if text.startswith("--basetemp="):
            continue
        cleaned.append(text)
    return cleaned


def _verification_scratch_root(out_dir: Path) -> Path:
    run_dir = out_dir.parent
    runs_dir = run_dir.parent
    feature = slugify(run_dir.name) or "unknown"
    return runs_dir / ".tmp" / "verification" / feature


def _verification_temp_dir(out_dir: Path, verify_stage: str, attempt: int, name: str) -> Path:
    stamp = int(time.time() * 1000)
    return _verification_scratch_root(out_dir) / f"{verify_stage}_attempt{attempt}_{slugify(name)}_{os.getpid()}_{stamp}"


def _verification_command_env(temp_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    temp_value = str(temp_dir)
    env["TMP"] = temp_value
    env["TEMP"] = temp_value
    env["TMPDIR"] = temp_value
    return env


def _verification_command_with_temp(command: list[str], temp_dir: Path) -> list[str]:
    command = [str(part) for part in command]
    if _is_pytest_command(command):
        command = _without_pytest_basetemp(command)
        command.append(f"--basetemp={temp_dir / 'pytest'}")
    return command


def _unique_command_specs(command_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    unique_specs: list[dict[str, Any]] = []
    for command_spec in command_specs:
        spec = dict(command_spec)
        base_name = slugify(str(spec.get("name") or "command")) or "command"
        count = seen.get(base_name, 0) + 1
        seen[base_name] = count
        if count == 1:
            spec["name"] = base_name
        else:
            spec["base_name"] = base_name
            spec["name"] = f"{base_name}-{count}"
        unique_specs.append(spec)
    return unique_specs


def configured_verification_commands(ctx: HarnessRuntime, feature: str) -> tuple[list[dict[str, Any]], bool]:
    config = ctx.load_config()
    verification = config.get("verification")
    if verification is None:
        return [], False
    if verification is False:
        return [], False
    if not isinstance(verification, dict):
        raise HarnessError("verification config must be an object.")
    if verification.get("enabled", True) is False:
        return [], False

    required = boolish(verification.get("required", True))
    timeout_default = int(
        verification.get("timeout_seconds", ctx.DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS)
    )
    raw_commands = verification.get("commands", [])
    if not isinstance(raw_commands, list):
        raise HarnessError("verification.commands must be a list.")

    root = ctx.ROOT
    commands: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_commands, start=1):
        if isinstance(item, list):
            name = f"command_{idx}"
            command = item
            cwd = root
            timeout_seconds = timeout_default
        elif isinstance(item, dict):
            name = str(item.get("name") or f"command_{idx}")
            command = item.get("command")
            if not isinstance(command, list):
                raise HarnessError(f"verification command {name!r} must have a list command.")
            raw_cwd = item.get("cwd")
            cwd = Path(ctx.expand_runtime_placeholders(raw_cwd, feature)) if raw_cwd else root
            if not cwd.is_absolute():
                cwd = root / cwd
            timeout_seconds = int(item.get("timeout_seconds", timeout_default))
        else:
            raise HarnessError("verification.commands entries must be objects or lists.")

        command_parts = [ctx.expand_runtime_placeholders(part, feature) for part in command]
        if not command_parts or not command_parts[0]:
            raise HarnessError(f"verification command {name!r} is empty.")
        if timeout_seconds <= 0:
            raise HarnessError(f"verification command {name!r} has invalid timeout.")

        commands.append(
            {
                "name": slugify(name),
                "command": command_parts,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
            }
        )
    return commands, required


def display_cwd(ctx: HarnessRuntime, path: Path) -> str:
    try:
        resolved = path.resolve()
        root = ctx.ROOT.resolve()
        if resolved == root or root in resolved.parents:
            return ctx.rel(resolved)
    except Exception:
        pass
    return str(path)


def _path_identity(path: Path) -> str:
    try:
        value = str(path.resolve())
    except OSError:
        value = str(path.absolute())
    return os.path.normcase(value)


def _command_identity(command: list[str], cwd: Path) -> tuple[str, tuple[str, ...]]:
    return (_path_identity(cwd), tuple(str(part) for part in command))


def _executable_name(command: list[str]) -> str:
    if not command:
        return ""
    return Path(str(command[0])).name.lower()


def _is_inside_repo(ctx: HarnessRuntime, path: Path) -> bool:
    try:
        resolved = path.resolve()
        root = ctx.ROOT.resolve()
        return resolved == root or root in resolved.parents
    except OSError:
        return False


def _resolve_dynamic_cwd(ctx: HarnessRuntime, feature: str, raw_cwd: Any) -> tuple[Path | None, str | None]:
    root = ctx.ROOT
    if raw_cwd is None or str(raw_cwd).strip() == "":
        return root, None
    rendered = ctx.expand_runtime_placeholders(raw_cwd, feature)
    cwd = Path(rendered)
    if not cwd.is_absolute():
        cwd = root / cwd
    return cwd, str(raw_cwd)


def _looks_like_path_arg(value: str) -> bool:
    if not value or value.startswith("-"):
        return False
    return (
        value in {".", ".."}
        or value.startswith(".\\")
        or value.startswith("./")
        or "\\" in value
        or "/" in value
        or Path(value).is_absolute()
    )


def _validate_dynamic_command_safety(
    ctx: HarnessRuntime,
    command: list[str],
    cwd: Path,
) -> str | None:
    if not _is_inside_repo(ctx, cwd):
        return f"cwd is outside the repository: {cwd}"
    if not cwd.exists() or not cwd.is_dir():
        return f"cwd does not exist or is not a directory: {cwd}"

    executable = _executable_name(command)
    if executable in SHELL_WRAPPER_EXECUTABLES:
        return f"shell wrapper commands are not allowed: {command[0]}"
    if executable in DANGEROUS_EXECUTABLES:
        return f"destructive or network command is not allowed: {command[0]}"
    if executable in {"npm", "npm.exe"}:
        return "use npm.cmd for promoted verification commands on Windows"
    if any(str(part).strip() in SHELL_CONTROL_TOKENS for part in command):
        return "shell control operators are not allowed in command arrays"

    lowered = [str(part).lower() for part in command]
    if executable == "git" and len(lowered) > 1 and lowered[1] in DANGEROUS_GIT_SUBCOMMANDS:
        return f"git {lowered[1]} is not allowed in promoted verification commands"
    if any(part in DANGEROUS_EXECUTABLES for part in lowered[1:]):
        return "destructive or network command token is not allowed"

    allowed = False
    if executable in {"python", "python.exe", "py", "py.exe"}:
        allowed = len(command) >= 3 and command[1] == "-m" and command[2] == "pytest"
    elif executable == "npm.cmd":
        allowed = len(command) >= 2 and (
            command[1] == "test"
            or (len(command) >= 3 and command[1] == "run" and command[2] == "build")
        )
    elif executable in {"dotnet", "dotnet.exe"}:
        allowed = len(command) >= 2 and command[1] in {"test", "build"}
    if not allowed:
        return (
            "command is not in the dynamic verification allowlist "
            "(python -m pytest, npm.cmd test, npm.cmd run build, dotnet test, dotnet build)"
        )

    root = ctx.ROOT.resolve()
    for part in command[1:]:
        if not _looks_like_path_arg(str(part)):
            continue
        arg_path = Path(str(part))
        candidate = arg_path if arg_path.is_absolute() else cwd / arg_path
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        if resolved != root and root not in resolved.parents:
            return f"command path argument points outside the repository: {part}"
    return None


def _dynamic_command_rejection(source: str, index: int, reason: str, item: Any = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source": source,
        "index": index,
        "reason": reason,
    }
    if item is not None:
        entry["item"] = item
    return entry


def _coerce_dynamic_command(
    ctx: HarnessRuntime,
    feature: str,
    item: Any,
    source: str,
    index: int,
    timeout_default: int,
    *,
    validate_safety: bool = True,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    raw_cwd: Any = None
    persist = True
    raw_name = f"{source}_{index}"
    timeout_seconds = timeout_default

    if isinstance(item, list):
        raw_command = item
    elif isinstance(item, dict):
        raw_name = str(item.get("name") or raw_name)
        raw_command = item.get("command")
        raw_cwd = item.get("cwd")
        persist = boolish(item.get("persist", True))
        raw_timeout = item.get("timeout_seconds")
        if raw_timeout is not None:
            try:
                timeout_seconds = int(raw_timeout)
            except (TypeError, ValueError):
                return None, _dynamic_command_rejection(source, index, "timeout_seconds must be an integer", item)
    else:
        return None, _dynamic_command_rejection(source, index, "entry must be an object or command array", item)

    if not isinstance(raw_command, list):
        return None, _dynamic_command_rejection(source, index, "command must be an array, not a shell string", item)
    if not raw_command:
        return None, _dynamic_command_rejection(source, index, "command array is empty", item)
    if len(raw_command) > 64:
        return None, _dynamic_command_rejection(source, index, "command array is too long", item)
    if timeout_seconds <= 0:
        return None, _dynamic_command_rejection(source, index, "timeout_seconds must be greater than zero", item)

    command = [ctx.expand_runtime_placeholders(part, feature) for part in raw_command]
    if any(str(part).strip() == "" for part in command):
        return None, _dynamic_command_rejection(source, index, "command contains an empty argument", item)

    cwd, config_cwd = _resolve_dynamic_cwd(ctx, feature, raw_cwd)
    if cwd is None:
        return None, _dynamic_command_rejection(source, index, "cwd is invalid", item)

    if validate_safety:
        safety_error = _validate_dynamic_command_safety(ctx, command, cwd)
        if safety_error:
            return None, _dynamic_command_rejection(source, index, safety_error, item)

    name = slugify(raw_name)
    spec = {
        "name": name,
        "command": command,
        "raw_command": [str(part) for part in raw_command],
        "cwd": cwd,
        "config_cwd": config_cwd,
        "timeout_seconds": timeout_seconds,
        "persist": persist,
        "source": source,
        "identity": _command_identity(command, cwd),
    }
    return spec, None


def dynamic_verification_commands(
    ctx: HarnessRuntime,
    feature: str,
    result: dict[str, Any] | None,
    configured_commands: list[dict[str, Any]],
) -> dict[str, Any]:
    timeout_default = int(ctx.DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS)
    try:
        config = ctx.load_config()
        verification = config.get("verification", {})
        if isinstance(verification, dict):
            timeout_default = int(verification.get("timeout_seconds", timeout_default))
    except Exception:
        pass

    plan: dict[str, Any] = {
        "commands": [],
        "rejected": [],
        "skipped": [],
        "fields": [],
    }
    if not isinstance(result, dict):
        return plan

    known_identities = {
        _command_identity(command_spec["command"], Path(command_spec["cwd"]))
        for command_spec in configured_commands
    }
    seen_dynamic: set[tuple[str, tuple[str, ...]]] = set()

    for field in DYNAMIC_VERIFICATION_FIELDS:
        if field not in result:
            continue
        plan["fields"].append(field)
        raw_items = result.get(field)
        if raw_items in (None, ""):
            continue
        if not isinstance(raw_items, list):
            plan["rejected"].append(
                _dynamic_command_rejection(field, 0, f"{field} must be a list", raw_items)
            )
            continue
        for index, item in enumerate(raw_items, start=1):
            spec, rejection = _coerce_dynamic_command(
                ctx,
                feature,
                item,
                field,
                index,
                timeout_default,
                validate_safety=False,
            )
            if rejection:
                plan["rejected"].append(rejection)
                continue
            assert spec is not None
            identity = spec["identity"]
            if identity in known_identities:
                plan["skipped"].append(
                    {
                        "source": field,
                        "index": index,
                        "name": spec["name"],
                        "reason": "already configured",
                        "command": spec["command"],
                        "cwd": ctx.display_cwd(Path(spec["cwd"])),
                    }
                )
                continue
            safety_error = _validate_dynamic_command_safety(ctx, spec["command"], Path(spec["cwd"]))
            if safety_error:
                plan["rejected"].append(_dynamic_command_rejection(field, index, safety_error, item))
                continue
            if identity in seen_dynamic:
                plan["skipped"].append(
                    {
                        "source": field,
                        "index": index,
                        "name": spec["name"],
                        "reason": "duplicate dynamic command in verify result",
                        "command": spec["command"],
                        "cwd": ctx.display_cwd(Path(spec["cwd"])),
                    }
                )
                continue
            seen_dynamic.add(identity)
            plan["commands"].append(spec)
    return plan


def _promotable_config_entry(ctx: HarnessRuntime, command_spec: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": command_spec["name"],
        "command": command_spec["raw_command"],
    }
    config_cwd = command_spec.get("config_cwd")
    if config_cwd:
        entry["cwd"] = config_cwd
    timeout_seconds = int(command_spec.get("timeout_seconds", 0) or 0)
    default_timeout = int(ctx.DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS)
    try:
        verification = ctx.load_config().get("verification", {})
        if isinstance(verification, dict):
            default_timeout = int(verification.get("timeout_seconds", default_timeout))
    except Exception:
        pass
    if timeout_seconds and timeout_seconds != default_timeout:
        entry["timeout_seconds"] = timeout_seconds
    return entry


def _configured_command_identities(ctx: HarnessRuntime, feature: str) -> set[tuple[str, tuple[str, ...]]]:
    commands, _ = ctx.configured_verification_commands(feature)
    return {_command_identity(item["command"], Path(item["cwd"])) for item in commands}


def promote_dynamic_verification_commands(
    ctx: HarnessRuntime,
    feature: str,
    command_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    promotable = [item for item in command_specs if item.get("persist", True)]
    if not promotable:
        return []

    config = ctx.load_project_config()
    if not isinstance(config, dict):
        raise HarnessError("project harness config must be an object.")
    verification = config.get("verification")
    if verification is None or verification is False:
        verification = {"commands": []}
        config["verification"] = verification
    if not isinstance(verification, dict):
        raise HarnessError("project verification config must be an object before promotion.")
    commands = verification.setdefault("commands", [])
    if not isinstance(commands, list):
        raise HarnessError("verification.commands must be a list before promotion.")

    known = _configured_command_identities(ctx, feature)
    promoted: list[dict[str, Any]] = []
    for command_spec in promotable:
        identity = command_spec["identity"]
        if identity in known:
            continue
        entry = _promotable_config_entry(ctx, command_spec)
        commands.append(entry)
        known.add(identity)
        promoted.append(
            {
                "name": entry["name"],
                "command": entry["command"],
                "cwd": entry.get("cwd", "."),
            }
        )

    if promoted:
        ctx.write_project_config(config)
    return promoted


def run_verification_command(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    out_dir: Path,
    verify_stage: str,
    attempt: int,
    command_spec: dict[str, Any],
) -> dict[str, Any]:
    name = command_spec["name"]
    configured_command = command_spec["command"]
    cwd = Path(command_spec["cwd"])
    timeout_seconds = int(command_spec["timeout_seconds"])
    stdout_path = out_dir / f"{verify_stage}_attempt{attempt}_{name}.out.txt"
    stderr_path = out_dir / f"{verify_stage}_attempt{attempt}_{name}.err.txt"
    temp_dir = _verification_temp_dir(out_dir, verify_stage, attempt, name)
    command = _verification_command_with_temp(configured_command, temp_dir)
    entry: dict[str, Any] = {
        "name": name,
        "source": command_spec.get("source", "configured"),
        "command": command,
        "cwd": ctx.display_cwd(cwd),
        "temp_dir": ctx.rel(temp_dir),
        "timeout_seconds": timeout_seconds,
        "returncode": None,
        "elapsed_seconds": None,
        "passed": False,
        "timed_out": False,
        "stdout": ctx.rel(stdout_path),
        "stderr": ctx.rel(stderr_path),
    }
    if command_spec.get("base_name"):
        entry["base_name"] = command_spec["base_name"]

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        entry["error"] = f"Could not create verification temp directory: {exc}"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(entry["error"] + "\n", encoding="utf-8")
        ctx.log_event(
            state,
            "harness_verification_command_failed",
            entry["error"],
            stage=verify_stage,
            command=name,
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
        return entry

    executable = ctx.resolve_executable(command)
    if not executable:
        entry["error"] = f"Executable not found: {command[0]}"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(entry["error"] + "\n", encoding="utf-8")
        ctx.log_event(
            state,
            "harness_verification_command_failed",
            entry["error"],
            stage=verify_stage,
            command=name,
        )
        return entry

    started = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
            env=_verification_command_env(temp_dir),
        )
        elapsed = round(time.time() - started, 2)
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        entry["returncode"] = proc.returncode
        entry["elapsed_seconds"] = elapsed
        entry["passed"] = proc.returncode == 0
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - started, 2)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stdout_path.write_text(str(stdout), encoding="utf-8")
        stderr_path.write_text(
            str(stderr) + f"\nTimed out after {timeout_seconds} seconds.\n",
            encoding="utf-8",
        )
        entry["elapsed_seconds"] = elapsed
        entry["timed_out"] = True
        entry["error"] = f"Timed out after {timeout_seconds} seconds."
    except OSError as exc:
        elapsed = round(time.time() - started, 2)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
        entry["elapsed_seconds"] = elapsed
        entry["error"] = str(exc)

    shutil.rmtree(temp_dir, ignore_errors=True)

    if not entry["passed"]:
        ctx.log_event(
            state,
            "harness_verification_command_failed",
            "verification command failed",
            stage=verify_stage,
            command=name,
            returncode=entry.get("returncode"),
            timed_out=entry.get("timed_out"),
            stderr=entry.get("stderr"),
        )
    return entry


def run_harness_verification(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    stage_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feature = state["feature_name"]
    verify_stage = ctx.VERIFY_STAGE
    stage = state.get("current_stage", verify_stage)
    attempt = int(state.get("attempts", {}).get(verify_stage, 1))
    commands, required = ctx.configured_verification_commands(feature)
    verification_enabled = True
    try:
        verification_config = ctx.load_config().get("verification")
        if verification_config is False:
            verification_enabled = False
        elif isinstance(verification_config, dict) and verification_config.get("enabled", True) is False:
            verification_enabled = False
    except Exception:
        verification_enabled = True
    out_dir = ctx.verification_dir(feature)
    out_dir.mkdir(parents=True, exist_ok=True)
    started_at = ctx.iso_now()
    result_path = out_dir / f"{verify_stage}_attempt{attempt}_{ctx.now_stamp()}.json"
    latest_path = ctx.latest_verification_result_path(feature)

    summary: dict[str, Any] = {
        "feature_name": feature,
        "stage": stage,
        "attempt": attempt,
        "result_path": ctx.rel(result_path),
        "latest_path": ctx.rel(latest_path),
        "started_at": started_at,
        "finished_at": None,
        "required": required,
        "passed": True,
        "status": ResultStatus.PASS,
        "commands": [],
        "failed_commands": [],
        "configured_command_count": len(commands),
        "dynamic_command_fields": [],
        "dynamic_commands": [],
        "skipped_dynamic_commands": [],
        "rejected_dynamic_commands": [],
        "promoted_commands": [],
    }

    for command_spec in commands:
        command_spec.setdefault("source", "configured")

    dynamic_plan = (
        dynamic_verification_commands(ctx, feature, stage_result, commands)
        if verification_enabled
        else {"commands": [], "rejected": [], "skipped": [], "fields": []}
    )
    dynamic_commands = list(dynamic_plan["commands"])
    summary["dynamic_command_fields"] = dynamic_plan["fields"]
    summary["dynamic_commands"] = [
        {
            "name": item["name"],
            "source": item["source"],
            "command": item["command"],
            "cwd": ctx.display_cwd(Path(item["cwd"])),
            "persist": item.get("persist", True),
        }
        for item in dynamic_commands
    ]
    summary["skipped_dynamic_commands"] = dynamic_plan["skipped"]
    summary["rejected_dynamic_commands"] = dynamic_plan["rejected"]

    all_commands = _unique_command_specs(commands + dynamic_commands)
    if dynamic_plan["rejected"]:
        summary["failed_commands"].append("rejected_dynamic_verification_commands")

    if not all_commands:
        summary["passed"] = not required
        summary["status"] = ResultStatus.FAIL if required else ResultStatus.SKIPPED
        summary["failure_reason"] = (
            "No harness verification commands configured."
            if required
            else "Harness verification is not configured."
        )
        summary["finished_at"] = ctx.iso_now()
        result_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copyfile(result_path, latest_path)
        state["last_harness_verification"] = ctx.rel(latest_path)
        ctx.log_event(
            state,
            "harness_verification_skipped" if not required else "harness_verification_failed",
            str(summary["failure_reason"]),
            stage=verify_stage,
            result=ctx.rel(latest_path),
        )
        ctx.save_state(state)
        return summary | {"path": ctx.rel(latest_path)}

    ctx.log_event(
        state,
        "harness_verification_started",
        "running verification commands",
        stage=verify_stage,
        configured_count=len(commands),
        dynamic_count=len(dynamic_commands),
        rejected_dynamic_count=len(dynamic_plan["rejected"]),
    )

    for command_spec in all_commands:
        name = command_spec["name"]
        entry = run_verification_command(ctx, state, out_dir, verify_stage, attempt, command_spec)
        summary["commands"].append(entry)
        if not entry["passed"]:
            summary["failed_commands"].append(name)

    summary["passed"] = not summary["failed_commands"]
    summary["status"] = ResultStatus.PASS if summary["passed"] else ResultStatus.FAIL
    if summary["passed"] and dynamic_commands:
        promoted = promote_dynamic_verification_commands(ctx, feature, dynamic_commands)
        summary["promoted_commands"] = promoted
        if promoted:
            ctx.log_event(
                state,
                "harness_verification_commands_promoted",
                "promoted passed dynamic verification commands to project harness config",
                stage=verify_stage,
                count=len(promoted),
                config=ctx.rel(ctx.project_config_path()),
            )
    summary["finished_at"] = ctx.iso_now()
    result_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(result_path, latest_path)
    state["last_harness_verification"] = ctx.rel(latest_path)
    ctx.log_event(
        state,
        "harness_verification_completed",
        "harness verification completed",
        stage=verify_stage,
        status=summary["status"],
        result=ctx.rel(latest_path),
        failed=",".join(summary["failed_commands"]),
    )
    ctx.save_state(state)
    return summary | {"path": ctx.rel(latest_path)}


def enforce_harness_verify_result(
    ctx: HarnessRuntime,
    state: dict[str, Any],
    result: dict[str, Any],
    status: str,
    next_stage: str,
) -> tuple[str, str]:
    if state.get("current_stage") != ctx.VERIFY_STAGE or status != ResultStatus.PASS:
        return status, next_stage

    verification = ctx.run_harness_verification(state, result)
    result["harness_verification_status"] = verification["status"]
    result["harness_verification_path"] = verification["path"]
    if verification["passed"]:
        return status, next_stage

    result["status"] = ResultStatus.FAIL
    result["next_stage"] = ctx.VERIFY_RETRY_TARGET_STAGE
    result["harness_commit_required"] = False
    result["blocking_reason"] = (
        "Harness verification failed. See "
        f"{verification['path']} for command results."
    )
    return ResultStatus.FAIL, ctx.VERIFY_RETRY_TARGET_STAGE

