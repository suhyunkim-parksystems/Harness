#!/usr/bin/env python
"""Batch supervisor for harness feature runs.

`orchestrate` drives a queue of `run` jobs (a ``batch.json``) on top of the
existing harness CLI. It does NOT re-implement the pipeline: it shells out to
``harness_fast.py`` / ``harness_standard.py`` / ``harness.py`` and reads each
run's ``.project/runs/<feature>/run.json`` to decide what happened.

Core job: when a run ends ``blocked``, classify the block as

  - transient (provider failure, incl. token/quota/rate)  -> wait & retry
  - unknown  (unexpected error)                           -> bounded retry
  - gate     (human gate)                                 -> auto-approve
  - manual   (verify-limit / NEEDS_USER / policy / guard) -> stop the line

Transient/unknown failures are retried in place (``retry --auto``) after a
cooldown, up to a per-run attempt budget. Anything needing a human stops the
whole batch (stop-the-line) - which the harness's own incomplete-run guard
enforces anyway. On success, pending Project Contract candidates are batch-reviewed
(``pc_review.py --yes``) and any contract update is committed - best-effort, so a
review hiccup never blocks feature delivery - then the run's branch is merged
(--no-ff) into its base.

Two commands:
  run [batch.json]     start/resume the batch; long-running, sleeps through
                       cooldowns; re-reads the batch file every cycle so new
                       jobs appended while it runs are picked up.
  status [batch.json]  print a read-only board.

State for each run lives in that run's ``state`` object inside the batch file;
every other field is user input. The batch file is gitignored (runtime
artifact); copy ``batch.example.json`` to start.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

HARNESS_DIR = Path(__file__).resolve().parent
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from harness_core.console import color_text  # noqa: E402
from harness_core.json_io import read_json_file, read_json_value_file  # noqa: E402
from harness_core.process import git  # noqa: E402

ROOT = HARNESS_DIR.parent
RUNS_DIR = ROOT / ".project" / "runs"
DEFAULT_BATCH_PATH = ROOT / "batch.json"

# Between feature runs the supervisor batch-reviews accumulated Project Contract
# candidates so later features inherit earlier learnings (the feedback loop is
# otherwise dead in an unattended batch). pc_review.py touches only these two
# files and never runs git, so orchestrate commits the result itself.
PC_REVIEW_SCRIPT = HARNESS_DIR / "pc_review.py"
PC_REVIEW_PATHS = (".project/project_contract.md", ".project/history/pc_candidates.json")

PIPELINE_SCRIPTS = {
    "fast": HARNESS_DIR / "harness_fast.py",
    "standard": HARNESS_DIR / "harness_standard.py",
    "full": HARNESS_DIR / "harness.py",
}
VALID_PIPELINES = tuple(PIPELINE_SCRIPTS)
VALID_PERFORMANCE = ("high", "medium", "lite")
VALID_DECISION_MODES = ("defaults", "interactive", "manual")
VALID_STRATEGIES = ("parallel", "sequential", "max")

DEFAULT_COOLDOWN_SECONDS = 900
DEFAULT_MAX_ATTEMPTS = 3
UNKNOWN_MAX_ATTEMPTS = 2
# A provider rate/quota limit (5h / weekly / monthly) is time-based, not a flaky
# failure: it WILL reset on its own. So we poll on a short cooldown and bound the
# wait by wall-clock from first occurrence, never by an attempt count.
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 300        # poll every 5 min while limited
DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS = 6 * 3600   # after 6h still limited -> manual

# Hard fallbacks so a minimal batch (only feature+request per run) still runs.
HARD_DEFAULTS: dict[str, Any] = {
    "pipeline": "standard",
    "performance": "medium",
    "decision_mode": "defaults",
    "yes": True,
    "deep_thinking": False,
    "strategy": "parallel",
    "timeout": 3600,
    "max_steps": 30,
    "max_verify_fix_retries": 3,
    "max_attempts": DEFAULT_MAX_ATTEMPTS,
}
INPUT_FIELDS = tuple(HARD_DEFAULTS) + ("feature", "request")

# Run lifecycle states (orchestrate-owned, stored in run["state"]["status"]).
ST_PENDING = "pending"
ST_RUNNING = "running"
ST_WAITING_RETRY = "waiting_retry"
ST_SUCCESS = "success"
ST_FAILED = "failed"
ST_MANUAL = "manual_required"
TERMINAL_BAD = {ST_FAILED, ST_MANUAL}

# Failure categories derived from a blocked run's reason text.
CAT_SUCCESS = "success"
CAT_TRANSIENT = "transient"
CAT_RATE_LIMIT = "rate_limit"
CAT_AUTH = "auth"
CAT_UNKNOWN = "unknown"
CAT_GATE = "gate"
CAT_MANUAL = "manual"

# Reason-string markers. Classification order (see classify_reason) is significant:
#   manual > gate > auth > rate-limit > transient > unknown
# so a more specific terminal signal always wins. Both an auth failure and a quota
# limit also "exited with code 1", so they MUST be matched before transient or
# they'd be misread as a flaky provider exit. Auth/billing is matched before
# rate-limit because it does NOT self-heal (a credit/quota *limit* resets on a
# time window; an empty *balance* or expired login needs a human).
MANUAL_MARKERS = (
    "Verify/Fix retry limit reached",
    "Stage requested user input",
    "Write policy violation",
    "새 파이프라인을 시작할 수 없습니다",  # harness new-run guard (unmerged-branch/incomplete)
)
GATE_MARKERS = ("Human gate approval required",)
# Provider access is blocked and will NOT self-heal: a human must re-auth or top up
# billing. Retrying just burns cooldowns, so this escalates to manual immediately
# (the harness's own no-output handoff points here: "인증 상태를 고친 뒤"). Matched
# case-insensitively; keep phrases specific so feature code that merely mentions
# "credentials"/"token" doesn't trip a false manual stop.
AUTH_MARKERS = (
    "not logged in",
    "please log in",
    "please login",
    "login required",
    "authentication required",
    "run /login",
    "authentication failed",
    "failed to authenticate",
    "authentication error",
    "unauthorized",
    "401 unauthorized",
    "invalid api key",
    "incorrect api key",
    "missing api key",
    "no api key",
    "invalid credentials",
    "token has expired",
    "token expired",
    "expired token",
    "session expired",
    "re-authenticate",
    "reauthenticate",
    "credit balance",       # "credit balance is too low" - empty wallet, not a window
    "out of credit",
    "insufficient credit",
    "add credits",
)
# Provider quota/limit signals, matched case-insensitively (these phrases usually
# land in the provider's stdout, not in blocked.reason - see classify_outcome).
# These are TIME-WINDOWED and self-heal; extend to teach a new limit phrasing.
RATE_LIMIT_MARKERS = (
    "spend limit",
    "usage limit",
    "rate limit",
    "rate-limit",
    "rate_limit",
    "monthly limit",
    "weekly limit",
    "hour limit",          # "5-hour limit", "5 hour limit"
    "quota",
    "too many requests",
    "429",
)
TRANSIENT_MARKERS = (
    "timed out",
    "exited with code",
    "produced no stdout",
    "no required outputs",
)


@dataclass(frozen=True)
class RetryPolicy:
    """How the supervisor reacts to one failure category.

    kind:
      "attempts" - bounded by a retry COUNT (flaky / unknown failures).
      "deadline" - bounded by WALL-CLOCK from first occurrence (time-based resets
                   such as a provider rate/quota limit).
      "none"     - no retry; escalate immediately.
    on_exhausted   - terminal state once the bound is hit (ST_FAILED or ST_MANUAL).
    max_attempts   - cap for kind="attempts"; None means "use the run's max_attempts".
    cooldown_seconds / max_wait_seconds - wait knobs (None -> batch override or default).

    To handle a NEW error type differently, add a category + its markers + one row
    in RETRY_POLICIES. The engine dispatches off this table; its loop never changes.
    """

    kind: str
    on_exhausted: str
    max_attempts: Optional[int] = None
    cooldown_seconds: Optional[int] = None
    max_wait_seconds: Optional[int] = None


# Category -> policy. The dispatcher (apply_policy) reads only this table, so a new
# error class is a data change here, not a control-flow change in the engine.
RETRY_POLICIES: dict[str, RetryPolicy] = {
    CAT_TRANSIENT: RetryPolicy(kind="attempts", on_exhausted=ST_FAILED),
    CAT_UNKNOWN: RetryPolicy(kind="attempts", on_exhausted=ST_FAILED, max_attempts=UNKNOWN_MAX_ATTEMPTS),
    CAT_RATE_LIMIT: RetryPolicy(
        kind="deadline",
        on_exhausted=ST_MANUAL,
        cooldown_seconds=DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
        max_wait_seconds=DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS,
    ),
    CAT_AUTH: RetryPolicy(kind="none", on_exhausted=ST_MANUAL),  # never self-heals
    CAT_MANUAL: RetryPolicy(kind="none", on_exhausted=ST_MANUAL),
    CAT_GATE: RetryPolicy(kind="none", on_exhausted=ST_MANUAL),
}


class OrchestrateError(Exception):
    """User-facing configuration or batch-structure error."""


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Batch IO
# --------------------------------------------------------------------------- #
def load_batch(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise OrchestrateError(f"배치 파일이 없습니다: {path}")
    try:
        data = read_json_value_file(path)
    except Exception as exc:  # noqa: BLE001 - surface any parse/IO error verbatim
        raise OrchestrateError(f"배치 파일을 읽을 수 없습니다 ({path}): {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        raise OrchestrateError("배치 파일은 'runs' 배열을 가진 객체여야 합니다.")
    validate_batch(data)
    return data


def validate_batch(batch: dict[str, Any]) -> None:
    seen: set[str] = set()
    for index, run in enumerate(batch.get("runs", [])):
        if not isinstance(run, dict):
            raise OrchestrateError(f"runs[{index}]가 객체가 아닙니다.")
        feature = run.get("feature")
        if not feature or not isinstance(feature, str):
            raise OrchestrateError(f"runs[{index}]에 'feature'가 없습니다.")
        if feature in seen:
            raise OrchestrateError(f"feature가 중복되었습니다(머지 키는 유일해야 함): {feature}")
        seen.add(feature)
        eff = effective_config(batch, run)
        if not eff.get("request"):
            raise OrchestrateError(f"{feature}: 'request'가 없습니다.")
        if eff["pipeline"] not in VALID_PIPELINES:
            raise OrchestrateError(f"{feature}: pipeline은 {VALID_PIPELINES} 중 하나여야 합니다.")
        if eff["performance"] not in VALID_PERFORMANCE:
            raise OrchestrateError(f"{feature}: performance는 {VALID_PERFORMANCE} 중 하나여야 합니다.")
        if eff["decision_mode"] not in VALID_DECISION_MODES:
            raise OrchestrateError(f"{feature}: decision_mode는 {VALID_DECISION_MODES} 중 하나여야 합니다.")
        if eff.get("deep_thinking") and eff["strategy"] not in VALID_STRATEGIES:
            raise OrchestrateError(f"{feature}: strategy는 {VALID_STRATEGIES} 중 하나여야 합니다.")


def effective_config(batch: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """Merge hard defaults <- batch.defaults <- run input fields (excluding state)."""
    merged = dict(HARD_DEFAULTS)
    batch_defaults = batch.get("defaults")
    if isinstance(batch_defaults, dict):
        merged.update({k: v for k, v in batch_defaults.items() if k != "state"})
    merged.update({k: v for k, v in run.items() if k != "state"})
    return merged


def save_batch(path: Path, batch: dict[str, Any]) -> None:
    """Write batch state back, merging onto the current on-disk file.

    Only each run's ``state`` is orchestrate-owned: we re-read the disk file
    (which may have user-appended runs or edited input fields since we loaded
    it) and copy our ``state`` onto the matching feature, preserving disk input
    fields and any runs we don't know about. Atomic via os.replace.
    """
    disk = read_json_file(path, batch)
    if not isinstance(disk, dict) or not isinstance(disk.get("runs"), list):
        disk = batch
    state_by_feature = {
        r.get("feature"): r.get("state")
        for r in batch.get("runs", [])
        if isinstance(r, dict) and r.get("state") is not None
    }
    for run in disk.get("runs", []):
        if isinstance(run, dict) and run.get("feature") in state_by_feature:
            run["state"] = state_by_feature[run["feature"]]
    disk["updated_at"] = iso_now()
    _write_json_atomic(path, disk)


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def run_state(run: dict[str, Any]) -> dict[str, Any]:
    state = run.get("state")
    if not isinstance(state, dict):
        state = {"status": ST_PENDING, "attempts": 0}
        run["state"] = state
    state.setdefault("status", ST_PENDING)
    state.setdefault("attempts", 0)
    return state


# --------------------------------------------------------------------------- #
# Harness invocation
# --------------------------------------------------------------------------- #
def _decision_mode_args(eff: dict[str, Any]) -> list[str]:
    mode = eff.get("decision_mode")
    if mode == "defaults":
        return ["--defaults"]
    if mode == "interactive":
        return ["--interactive"]
    return []


def build_start_command(eff: dict[str, Any]) -> list[str]:
    script = PIPELINE_SCRIPTS[eff["pipeline"]]
    cmd = [
        sys.executable,
        str(script),
        "run",
        str(eff["request"]),
        "--feature",
        str(eff["feature"]),
        "--timeout",
        str(eff["timeout"]),
        "--max-steps",
        str(eff["max_steps"]),
        "--max-verify-fix-retries",
        str(eff["max_verify_fix_retries"]),
        "--performance",
        str(eff["performance"]),
    ]
    if eff.get("yes"):
        cmd.append("--yes")
    cmd += _decision_mode_args(eff)
    if eff["pipeline"] == "full" and eff.get("deep_thinking"):
        cmd.append("--deep-thinking")
        if eff.get("strategy"):
            cmd += ["--strategy", str(eff["strategy"])]
    return cmd


def build_retry_command(eff: dict[str, Any]) -> list[str]:
    script = PIPELINE_SCRIPTS[eff["pipeline"]]
    cmd = [
        sys.executable,
        str(script),
        "retry",
        str(eff["feature"]),
        "--auto",
        "--yes",
        "--timeout",
        str(eff["timeout"]),
        "--max-steps",
        str(eff["max_steps"]),
        "--max-verify-fix-retries",
        str(eff["max_verify_fix_retries"]),
        "--performance",
        str(eff["performance"]),
    ]
    cmd += _decision_mode_args(eff)
    return cmd


def build_approve_command(eff: dict[str, Any]) -> list[str]:
    script = PIPELINE_SCRIPTS[eff["pipeline"]]
    return [
        sys.executable,
        str(script),
        "approve",
        str(eff["feature"]),
        "--auto",
        "--yes",
        "--timeout",
        str(eff["timeout"]),
        "--max-steps",
        str(eff["max_steps"]),
        "--max-verify-fix-retries",
        str(eff["max_verify_fix_retries"]),
        "--performance",
        str(eff["performance"]),
    ]


def invoke_harness(cmd: list[str]) -> tuple[int, str]:
    """Run a harness command. stdout is inherited (live progress for the user);
    stderr is captured so a guard/crash message is available for classification.
    Returns (returncode, stderr_text)."""
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stderr or ""


def read_run_json(feature: str) -> Optional[dict[str, Any]]:
    path = RUNS_DIR / feature / "run.json"
    if not path.exists():
        return None
    try:
        data = read_json_value_file(path)
    except Exception:  # noqa: BLE001 - a half-written/corrupt run.json is just "unknown"
        return None
    return data if isinstance(data, dict) else None


def _read_tail(path_str: Optional[str], limit: int = 4000) -> str:
    """Best-effort tail of a provider log file. The harness writes a quota/limit
    message to the run's stdout but NOT into blocked.reason, so the classifier
    must peek at the stdout file to see it. A missing/locked log is just no signal."""
    if not path_str:
        return ""
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT / path
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    return text[-limit:]


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def classify_reason(text: str) -> str:
    blob = text or ""
    for marker in MANUAL_MARKERS:
        if marker in blob:
            return CAT_MANUAL
    for marker in GATE_MARKERS:
        if marker in blob:
            return CAT_GATE
    blob_low = blob.lower()
    for marker in AUTH_MARKERS:
        if marker in blob_low:  # before rate-limit: blocked access doesn't self-heal
            return CAT_AUTH
    for marker in RATE_LIMIT_MARKERS:
        if marker in blob_low:  # before transient: a limit also "exited with code 1"
            return CAT_RATE_LIMIT
    for marker in TRANSIENT_MARKERS:
        if marker in blob:
            return CAT_TRANSIENT
    return CAT_UNKNOWN


def classify_outcome(run_json: Optional[dict[str, Any]], stderr: str) -> tuple[str, str]:
    """Return (category, reason_text) from the harness outcome."""
    if isinstance(run_json, dict):
        status = str(run_json.get("status") or "")
        if status == "complete":
            return CAT_SUCCESS, ""
        if status == "blocked":
            blocked = run_json.get("blocked")
            if isinstance(blocked, dict):
                reason = str(blocked.get("reason") or "")
                stdout_tail = _read_tail(blocked.get("stdout"))
            else:
                reason = ""
                stdout_tail = ""
            # Classify on reason + stderr + the provider stdout tail so a limit
            # message that only landed in stdout still surfaces as rate_limit.
            blob = "\n".join(part for part in (reason, stderr, stdout_tail) if part)
            return classify_reason(blob), reason or stderr.strip()
    # No terminal run.json (e.g. new-run guard rejected before creation, or crash):
    # fall back to the captured stderr.
    reason = stderr.strip()
    return classify_reason(reason), reason


# --------------------------------------------------------------------------- #
# Git integration: merge a completed run branch into its base (push is optional)
# --------------------------------------------------------------------------- #
def _git(args: list[str], check: bool = False) -> "subprocess.CompletedProcess[str]":
    return git(ROOT, args, check=check)


def current_branch() -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def upstream_ref() -> Optional[str]:
    proc = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def has_remote() -> bool:
    return bool(_git(["remote"]).stdout.strip())


def push_current_branch() -> tuple[bool, str]:
    """Push the current branch's commits. Does NOT create a new branch.
    If no upstream, set tracking on the SAME branch name via -u origin <branch>.
    If no remote at all, skip (publishing is optional in the merge model)."""
    if upstream_ref():
        proc = _git(["push"])
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()
    if not has_remote():
        return False, "원격이 없어 push를 생략합니다."
    branch = current_branch()
    if not branch or branch == "HEAD":
        return False, "현재 브랜치를 확인할 수 없어 push를 생략합니다(detached HEAD)."
    proc = _git(["push", "-u", "origin", branch])
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def merge_tree_has_conflicts(base: str, branch: str) -> Optional[bool]:
    """True/False if the merge of branch into base conflicts; None when it can't
    be determined (git < 2.38, unrelated histories, bad ref). Pure prediction --
    no working-tree mutation."""
    proc = _git(["merge-tree", "--write-tree", base, branch])
    if proc.returncode == 0:
        return False
    if proc.returncode == 1:
        return True
    return None


def merge_run_branch(run_json: Optional[dict[str, Any]]) -> tuple[bool, str]:
    """Integrate a completed run's branch into its base with a --no-ff merge,
    then best-effort publish the base. Batch mode is unattended, so a clean merge
    is performed automatically; a conflicting merge is left for the human
    (stop-the-line). Linear runs that never created a branch fall back to the
    old push-current-branch behavior."""
    base = str((run_json or {}).get("base_branch") or "")
    branch = str((run_json or {}).get("run_branch") or "")
    if not base or not branch:
        return push_current_branch()  # linear fallback (no run branch)
    conflicts = merge_tree_has_conflicts(base, branch)
    if conflicts:
        return False, f"merge 충돌로 {branch} -> {base} 보류(수동 해결 필요)."
    checkout = _git(["checkout", base])
    if checkout.returncode != 0:
        return False, f"base 체크아웃 실패: {(checkout.stderr or checkout.stdout).strip()}"
    merged = _git(["merge", "--no-ff", branch, "-m", f"merge {branch} into {base}"])
    if merged.returncode != 0:
        return False, f"merge 실패: {(merged.stderr or merged.stdout).strip()}"
    if has_remote():
        pushed, push_msg = push_current_branch()
        suffix = " (push 완료)" if pushed else f" (push 보류: {push_msg})"
    else:
        suffix = ""
    return True, f"{branch} -> {base} merge 완료.{suffix}"


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def _emit(text: str) -> None:
    """Print a line without ever crashing on a non-UTF-8 console (e.g. Windows
    cp949): a long-running supervisor must not die on a single log line."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write((text + "\n").encode(encoding, errors="replace"))
            sys.stdout.flush()


def log(message: str, *styles: str) -> None:
    _emit(color_text(f"[orchestrate] {message}", *styles))


def first_active_run(batch: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The frontline run = the first run that is not already a success.

    Because of the harness's incomplete-run guard the batch is strictly serial,
    so the first non-success run is the only one we may act on. Everything before
    it is success; nothing after it can start until it finishes.
    """
    for run in batch.get("runs", []):
        if not isinstance(run, dict):
            continue
        if run_state(run).get("status") != ST_SUCCESS:
            return run
    return None


def truncate(text: str, limit: int = 200) -> str:
    compact = " ".join(str(text).split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def _pc_review_config(batch: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Resolve the between-runs pc_review setting. Returns None when disabled.

    batch["pc_review"]: omitted/True -> enabled (default agent); False -> off;
    {"enabled": bool, "agent": "codex|claude|agy"} -> explicit.
    """
    cfg = batch.get("pc_review", True)
    if cfg is False:
        return None
    if isinstance(cfg, dict):
        if not cfg.get("enabled", True):
            return None
        return {"agent": cfg.get("agent")}
    return {"agent": None}


def _run_pc_review(batch: dict[str, Any], feature: str) -> None:
    """Batch-review pending Project Contract candidates and commit the update.

    Best-effort: a non-zero exit (provider rate-limit/auth/flake, validation, etc.)
    is logged and skipped - candidates stay pending and get reviewed at the next
    gap. A contract polish must never stop feature delivery.
    """
    cfg = _pc_review_config(batch)
    if cfg is None:
        return
    cmd = [sys.executable, str(PC_REVIEW_SCRIPT), "--yes"]
    if cfg.get("agent"):
        cmd += ["--agent", str(cfg["agent"])]
    log(f"{feature}: pc_review --yes 실행 (프로젝트 계약 갱신)", "cyan")
    returncode, stderr = invoke_harness(cmd)
    if returncode != 0:
        log(f"{feature}: pc_review 스킵 (비치명적 실패 rc={returncode}) {truncate(stderr, 160)}", "yellow")
        return
    _commit_pc_review_changes(feature)


def _commit_pc_review_changes(feature: str) -> None:
    """Commit the contract/candidates files pc_review just wrote, so the next run
    starts clean and the change rides along with this run's push. No-op when the
    review added/decided nothing."""
    paths = [p for p in PC_REVIEW_PATHS if (ROOT / p).exists()]
    if not paths:
        return
    _git(["add", "--"] + paths)
    staged = _git(["diff", "--cached", "--name-only", "--"] + paths).stdout.strip()
    if not staged:
        return  # reviewer proposed no rule and changed no candidate status
    commit = _git(["commit", "-m", f"[orchestrate][pc_review] {feature} 이후 프로젝트 계약 갱신", "--"] + paths)
    if commit.returncode == 0:
        log(f"{feature}: 프로젝트 계약 갱신 커밋 완료", "green")
    else:
        log(f"{feature}: 계약 커밋 실패(무시) - {truncate(commit.stderr or commit.stdout, 160)}", "yellow")


def mark_success(
    run: dict[str, Any],
    run_json: Optional[dict[str, Any]],
    batch: Optional[dict[str, Any]] = None,
) -> None:
    state = run_state(run)
    state["status"] = ST_SUCCESS
    state["finished_at"] = iso_now()
    state["next_retry_at"] = None
    state["rate_limit_since"] = None
    state["last_reason"] = ""
    if isinstance(run_json, dict) and run_json.get("current_stage"):
        state["stage"] = run_json["current_stage"]
    feature = run["feature"]
    # Review/commit the contract BEFORE merging so the update rides this run's
    # branch into base - the orchestrator is still on the run branch here, so the
    # contract commit is part of the very merge that integrates this feature.
    if batch is not None:
        _run_pc_review(batch, feature)
    merged, message = merge_run_branch(run_json)
    state["merged"] = merged
    if merged:
        log(f"{feature}: 성공 -> {message}", "green", "bold")
    else:
        log(f"{feature}: 성공했으나 merge 보류 - {message}", "yellow", "bold")


def mark_failed(run: dict[str, Any], category: str, detail: str) -> None:
    state = run_state(run)
    state["status"] = ST_FAILED
    state["finished_at"] = iso_now()
    state["next_retry_at"] = None
    log(f"{run['feature']}: {category} 실패 - {detail} -> failed (정지)", "red", "bold")


def _finalize_exhausted(run: dict[str, Any], category: str, policy: RetryPolicy, detail: str) -> None:
    """Move a run to its policy's terminal state once a retry bound is exhausted."""
    if policy.on_exhausted == ST_MANUAL:
        mark_manual(run, f"{category}: {detail}")
    else:
        mark_failed(run, category, detail)


def apply_policy(
    run: dict[str, Any],
    category: str,
    reason: str,
    eff: dict[str, Any],
    batch: dict[str, Any],
) -> None:
    """Dispatch a non-success failure to its category's RetryPolicy.

    This is the only place that reads RETRY_POLICIES; the engine loop never
    branches on category, so adding a new error class is purely a table edit.
    """
    policy = RETRY_POLICIES.get(category)
    if policy is None:  # unmapped category -> a human should look
        mark_manual(run, reason)
        return
    if policy.kind == "attempts":
        _apply_attempts_policy(run, category, reason, policy, eff, batch)
    elif policy.kind == "deadline":
        _apply_deadline_policy(run, category, reason, policy, batch)
    elif policy.on_exhausted == ST_MANUAL:  # kind == "none"
        mark_manual(run, reason)
    else:  # kind == "none", escalate to failed (defensive; no category uses this today)
        run_state(run)["last_reason"] = truncate(reason)
        mark_failed(run, category, truncate(reason, 120))


def _apply_attempts_policy(
    run: dict[str, Any],
    category: str,
    reason: str,
    policy: RetryPolicy,
    eff: dict[str, Any],
    batch: dict[str, Any],
) -> None:
    """Count-bounded retry: wait a cooldown until the attempt budget is spent."""
    state = run_state(run)
    state["rate_limit_since"] = None  # any prior limit window is over
    attempts = int(state.get("attempts", 0))
    eff_max = int(eff["max_attempts"])
    budget = eff_max if policy.max_attempts is None else min(int(policy.max_attempts), eff_max)
    cooldown = int(batch.get("cooldown_seconds") or DEFAULT_COOLDOWN_SECONDS)
    state["last_reason"] = truncate(reason)
    if attempts >= budget:
        _finalize_exhausted(run, category, policy, f"재시도 예산 {attempts}/{budget} 소진")
        return
    next_at = (datetime.now() + timedelta(seconds=cooldown)).isoformat(timespec="seconds")
    state["status"] = ST_WAITING_RETRY
    state["next_retry_at"] = next_at
    log(
        f"{run['feature']}: {category} -> {cooldown}s 후 재시도 (attempt {attempts}/{budget}) at {next_at}",
        "yellow",
    )


def _apply_deadline_policy(
    run: dict[str, Any],
    category: str,
    reason: str,
    policy: RetryPolicy,
    batch: dict[str, Any],
) -> None:
    """Time-bounded retry for a self-healing limit: poll on a short cooldown until
    the limit resets, giving up only when wall-clock since the FIRST occurrence
    exceeds max_wait. The reset is time-based, so the attempt count is irrelevant -
    and the poll itself is rejected before doing real work, so it must not erode
    the run's real attempt budget (execute_run pre-increments; we roll that back)."""
    state = run_state(run)
    state["attempts"] = max(0, int(state.get("attempts", 0)) - 1)
    state["last_reason"] = truncate(reason)
    now = datetime.now()
    since = parse_iso(state.get("rate_limit_since")) or now
    state["rate_limit_since"] = since.isoformat(timespec="seconds")
    cooldown = int(
        batch.get("rate_limit_cooldown_seconds")
        or policy.cooldown_seconds
        or DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS
    )
    max_wait = int(
        batch.get("rate_limit_max_wait_seconds")
        or policy.max_wait_seconds
        or DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS
    )
    waited = (now - since).total_seconds()
    if waited >= max_wait:
        state["rate_limit_since"] = None
        _finalize_exhausted(
            run,
            category,
            policy,
            f"리밋 대기 상한 {max_wait // 60}분 초과 (총 {int(waited // 60)}분 대기) - 한도 상향/리셋 필요",
        )
        return
    next_at = (now + timedelta(seconds=cooldown)).isoformat(timespec="seconds")
    state["status"] = ST_WAITING_RETRY
    state["next_retry_at"] = next_at
    remaining_min = int((max_wait - waited) // 60)
    log(
        f"{run['feature']}: {category} -> {cooldown}s 후 재시도 "
        f"(리밋 리셋 대기, 상한까지 ~{remaining_min}분 남음) at {next_at}",
        "yellow",
    )


def mark_manual(run: dict[str, Any], reason: str) -> None:
    state = run_state(run)
    state["status"] = ST_MANUAL
    state["finished_at"] = iso_now()
    state["next_retry_at"] = None
    state["last_reason"] = truncate(reason)
    log(f"{run['feature']}: 사람이 확인해야 함 -> manual_required (정지): {truncate(reason, 120)}", "red", "bold")


def execute_run(batch: dict[str, Any], run: dict[str, Any], path: Path) -> None:
    """Run one harness invocation for the frontline run and record the outcome."""
    eff = effective_config(batch, run)
    feature = str(eff["feature"])
    state = run_state(run)

    # Decide start vs retry by the actual run.json, not our status: this resumes a
    # leftover "running" (orchestrate crashed mid-run) instead of re-spec'ing it,
    # and short-circuits a feature that was already completed out-of-band.
    existing = read_run_json(feature)
    if isinstance(existing, dict) and str(existing.get("status")) == "complete":
        mark_success(run, existing, batch)
        save_batch(path, batch)
        return
    if existing is not None:
        cmd = build_retry_command(eff)
        verb = "retry"
    else:
        cmd = build_start_command(eff)
        verb = "run"

    state["attempts"] = int(state.get("attempts", 0)) + 1
    state["status"] = ST_RUNNING
    if not state.get("started_at"):
        state["started_at"] = iso_now()
    save_batch(path, batch)
    log(f"{feature}: {verb} 시작 (attempt {state['attempts']}, pipeline={eff['pipeline']})", "cyan")

    returncode, stderr = invoke_harness(cmd)
    run_json = read_run_json(feature)
    if isinstance(run_json, dict) and run_json.get("current_stage"):
        state["stage"] = run_json["current_stage"]

    category, reason = classify_outcome(run_json, stderr)

    if category == CAT_GATE:
        # Human gate slipped through despite --yes: auto-approve and re-evaluate once.
        log(f"{feature}: human gate 감지 -> 자동 승인", "yellow")
        invoke_harness(build_approve_command(eff))
        run_json = read_run_json(feature)
        category, reason = classify_outcome(run_json, "")
        if category == CAT_GATE and not reason:
            reason = "human gate가 자동 승인 후에도 해소되지 않았습니다."

    if category == CAT_SUCCESS:
        mark_success(run, run_json, batch)
    else:
        apply_policy(run, category, reason, eff, batch)

    save_batch(path, batch)


def run_batch(path: Path) -> int:
    log(f"배치 시작: {path}", "bold")
    while True:
        batch = load_batch(path)
        run = first_active_run(batch)
        if run is None:
            log("모든 run이 success입니다. 배치 완료.", "green", "bold")
            return 0

        state = run_state(run)
        status = state.get("status")

        if status in TERMINAL_BAD:
            log(
                f"정지(stop-the-line): {run['feature']} 가 {status} 입니다. "
                f"원인 확인 후 batch.json을 수정하고 다시 실행하세요.",
                "red",
                "bold",
            )
            print_board(batch)
            return 1

        if status == ST_WAITING_RETRY:
            due = parse_iso(state.get("next_retry_at"))
            if due and datetime.now() < due:
                _sleep_until(due, run["feature"])
                continue
            # due reached (or unparseable timestamp) -> retry now
            execute_run(batch, run, path)
            continue

        # pending / running(leftover) -> execute
        execute_run(batch, run, path)


def _sleep_until(due: datetime, feature: str) -> None:
    remaining = int((due - datetime.now()).total_seconds())
    if remaining <= 0:
        return
    log(f"{feature}: 재시도까지 {remaining}s 대기...", "dim")
    # Sleep in short chunks so Ctrl-C stays responsive and an edited batch is
    # re-read promptly on wake.
    while datetime.now() < due:
        time.sleep(min(30, max(1, int((due - datetime.now()).total_seconds()))))


# --------------------------------------------------------------------------- #
# Status board
# --------------------------------------------------------------------------- #
STATUS_STYLES = {
    ST_PENDING: ("dim",),
    ST_RUNNING: ("cyan", "bold"),
    ST_WAITING_RETRY: ("yellow", "bold"),
    ST_SUCCESS: ("green", "bold"),
    ST_FAILED: ("red", "bold"),
    ST_MANUAL: ("red", "bold"),
}


def print_board(batch: dict[str, Any]) -> None:
    runs = [r for r in batch.get("runs", []) if isinstance(r, dict)]
    counts: dict[str, int] = {}
    for run in runs:
        st = str(run_state(run).get("status"))
        counts[st] = counts.get(st, 0) + 1
    header = "  ".join(f"{name}={n}" for name, n in sorted(counts.items()))
    _emit(color_text(f"batch: {batch.get('name') or '-'}  ({header})", "bold"))
    _emit(color_text(f"updated_at: {batch.get('updated_at') or '-'}", "dim"))
    _emit("")
    for run in runs:
        eff = effective_config(batch, run)
        state = run_state(run)
        status = str(state.get("status"))
        status_label = color_text(status.upper(), *STATUS_STYLES.get(status, ("bold",)))
        feature = color_text(str(run.get("feature")), "bold")
        _emit(
            f"- {feature} [{status_label}] "
            f"pipeline={eff['pipeline']} stage={state.get('stage') or '-'} "
            f"attempts={state.get('attempts', 0)}/{eff['max_attempts']}"
        )
        if state.get("next_retry_at"):
            _emit(f"    next_retry_at: {state['next_retry_at']}")
        if state.get("merged") is True:
            _emit(color_text("    merged: yes", "green"))
        if state.get("last_reason"):
            _emit(f"    last_reason: {truncate(str(state['last_reason']), 200)}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch supervisor for harness feature runs (retry-on-transient, stop-on-human)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Start/resume the batch and drive it to completion.")
    run_cmd.add_argument("batch", nargs="?", default=str(DEFAULT_BATCH_PATH), help="Batch JSON path (default: batch.json).")

    status_cmd = sub.add_parser("status", help="Print the batch board (read-only).")
    status_cmd.add_argument("batch", nargs="?", default=str(DEFAULT_BATCH_PATH), help="Batch JSON path (default: batch.json).")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.batch)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    try:
        if args.command == "run":
            return run_batch(path)
        if args.command == "status":
            print_board(load_batch(path))
            return 0
    except OrchestrateError as exc:
        print(f"{color_text('ERROR:', 'red', 'bold')} {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(color_text("\n중단됨. 상태는 batch.json에 저장되어 있어 다시 run으로 이어갑니다.", "yellow"), file=sys.stderr)
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
