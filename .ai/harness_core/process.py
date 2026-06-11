"""Low-level git/subprocess primitives, parameterized by the repository root.

Extracted from harness.py. These helpers take an explicit ``root`` so they have
no dependency on harness module state; harness.py keeps thin wrappers that bind
the active ROOT and re-expose them (also into the HarnessContext).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .text import norm_repo_path


def kill_process_tree(proc: "subprocess.Popen[Any]", *, wait_timeout: float = 10.0) -> None:
    """Terminate a child process *and all its descendants*.

    On Windows, ``proc.kill()`` (TerminateProcess) only kills the direct child.
    The default providers are ``.cmd`` shims, so the direct child is ``cmd.exe``
    and the real agent (``node.exe``) is a grandchild that survives -- it keeps
    editing the repo and holding the inherited stdout/stderr pipe handles (which
    makes a follow-up ``communicate()`` block forever). ``taskkill /T`` walks the
    whole tree. On POSIX, fall back to ``proc.kill()``.
    """
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            _best_effort_kill(proc)
    else:
        _best_effort_kill(proc)
    try:
        proc.wait(timeout=wait_timeout)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _best_effort_kill(proc: "subprocess.Popen[Any]") -> None:
    try:
        proc.kill()
    except OSError:
        pass


def git(root: Path, args: list[str], check: bool = True) -> "subprocess.CompletedProcess[str]":
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


def git_output(root: Path, args: list[str]) -> str:
    return git(root, args).stdout.strip()


def git_show_file(root: Path, ref: str, rel_path: str) -> bytes | None:
    """Return the blob bytes of ``rel_path`` (posix-style) at ``ref``, or None.

    Bytes (not text) so callers can hash the content exactly as stored."""
    if not ref or not rel_path:
        return None
    cmd = [
        "git",
        "-c",
        f"safe.directory={root.as_posix()}",
        "show",
        f"{ref}:{rel_path}",
    ]
    try:
        proc = subprocess.run(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def git_changed_paths(root: Path) -> list[str]:
    out = git_output(root, ["status", "--porcelain=v1"])
    paths: list[str] = []
    for line in out.splitlines():
        if not line:
            continue
        raw = line[2:].lstrip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        paths.append(norm_repo_path(raw.strip('"')))
    return sorted(set(paths))


def git_head(root: Path) -> str:
    return git_output(root, ["rev-parse", "HEAD"])


def git_add(root: Path, paths: list[str]) -> None:
    if not paths:
        return
    git(root, ["add", "--"] + paths)


def git_commit(root: Path, message: str, amend: bool = False) -> str:
    if amend:
        git(root, ["commit", "--amend", "--no-edit"])
    else:
        git(root, ["commit", "-m", message])
    return git_head(root)


def current_branch(root: Path) -> str:
    """Active branch name, or "HEAD" when detached, or "" on error."""
    proc = git(root, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    return proc.stdout.strip()


def branch_exists(root: Path, name: str) -> bool:
    proc = git(root, ["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], check=False)
    return proc.returncode == 0


def checkout_new_branch(root: Path, name: str) -> None:
    """Create and check out a new branch at the current HEAD. Same SHA, so this
    does not trip the provider HEAD-change guard."""
    git(root, ["checkout", "-b", name])


def branch_is_merged(root: Path, branch: str, base: str) -> bool:
    """True when ``branch``'s tip is already contained in ``base`` (a normal
    merge makes the tip an ancestor of base). Squash merges are NOT detected
    here; the deleted-branch signal covers that case at the call site."""
    proc = git(root, ["merge-base", "--is-ancestor", branch, base], check=False)
    return proc.returncode == 0


def merge_tree_conflicts(root: Path, base: str, branch: str) -> "list[str] | None":
    """Predict whether merging ``branch`` into ``base`` conflicts, WITHOUT
    touching the working tree (a pure tree computation).

    Returns the sorted list of conflicting paths ([] when the merge is clean),
    or ``None`` when the result cannot be determined (e.g. git < 2.38 lacking
    ``merge-tree --write-tree``, or unrelated histories). Callers treat ``None``
    as "unknown" and never block on it."""
    proc = git(root, ["merge-tree", "--write-tree", base, branch], check=False)
    if proc.returncode == 0:
        return []
    if proc.returncode != 1:
        return None  # undeterminable (old git / unrelated histories / bad ref)
    # --write-tree output: first line is the merged tree OID; if conflicts exist,
    # the lines up to the first blank list "<mode> <oid> <stage>\t<path>".
    paths: set[str] = set()
    lines = proc.stdout.splitlines()
    for line in lines[1:]:
        if not line.strip():
            break
        if "\t" in line:
            paths.add(line.split("\t", 1)[1].strip())
    return sorted(paths)
