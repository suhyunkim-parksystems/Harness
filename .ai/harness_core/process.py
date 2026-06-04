"""Low-level git/subprocess primitives, parameterized by the repository root.

Extracted from harness.py. These helpers take an explicit ``root`` so they have
no dependency on harness module state; harness.py keeps thin wrappers that bind
the active ROOT and re-expose them (also into the HarnessContext).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .text import norm_repo_path


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
