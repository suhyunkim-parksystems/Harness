from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from support import ensure_ai_path


AI_DIR = ensure_ai_path()
SOURCE_ROOT = AI_DIR.parent
TEMP_PARENT = AI_DIR / ".selftest_tmp"

STANDARD_STAGE_OUTPUTS = {
    "00_specify": "00_spec.md",
    "01_develop": "01_dev.md",
    "02_review": "02_review.md",
    "03_fix": "03_fix.md",
    "04_verify": "04_verify.md",
}


def announce(message: str) -> None:
    print(f"\n[selftest] {message}", flush=True)


def run(
    command: list[str],
    cwd: Path,
    *,
    timeout: int = 60,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=env,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            "Command failed:\n"
            f"cwd: {cwd}\n"
            f"command: {' '.join(command)}\n"
            f"returncode: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"JSON file is not an object: {path}")
    return parsed


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )


def provider_command(provider: str) -> list[str]:
    return [
        sys.executable,
        ".ai\\selftests\\integration_fake_provider.py",
        "--provider",
        provider,
    ]


def write_fixture_config(fixture_root: Path) -> None:
    config = {
        "providers": {
            provider: {
                "enabled": True,
                "command": provider_command(provider),
            }
            for provider in ("codex", "claude", "agy")
        },
        "model_policy": {
            "min_distinct_agents": 1,
            "no_adjacent_same_provider": False,
            "on_independence_violation": "allow",
            "code_write_allowed": ["codex", "claude"],
            "code_write_denied": ["agy"],
            "code_write_order": ["codex", "claude"],
            "non_code_order": ["codex", "agy", "claude"],
            "role_orders": {
                "plan": ["codex", "agy", "claude"],
                "review": ["codex", "agy", "claude"],
                "verify": ["codex", "agy", "claude"],
                "document": ["codex", "agy", "claude"],
                "pc_extract": ["codex", "agy", "claude"],
            },
            "avoid_reusing_recent_code_writer_for_review": False,
            "reserve_code_writers_for_code_stages": False,
        },
        "verification": {
            "enabled": True,
            "required": True,
            "timeout_seconds": 30,
            "commands": [
                {
                    "name": "fixture_py_compile",
                    "command": [sys.executable, "-m", "py_compile", "src\\app.py"],
                    "cwd": ".",
                }
            ],
        },
    }
    path = fixture_root / ".ai" / "harness.config.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_harness_into_fixture(fixture_root: Path) -> None:
    fixture_ai = fixture_root / ".ai"
    fixture_ai.mkdir(parents=True, exist_ok=True)
    for name in ("harness.py", "harness_fast.py", "harness_standard.py", "project_contract.md"):
        shutil.copy2(AI_DIR / name, fixture_ai / name)
    for dirname in ("harness_core", "templates"):
        copy_tree(AI_DIR / dirname, fixture_ai / dirname)

    fake_provider_dir = fixture_ai / "selftests"
    fake_provider_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(AI_DIR / "selftests" / "integration_fake_provider.py", fake_provider_dir / "integration_fake_provider.py")

    presets_dir = fixture_root / "presets"
    presets_dir.mkdir(parents=True, exist_ok=True)
    copy_tree(SOURCE_ROOT / "presets" / "standard", presets_dir / "standard")
    write_fixture_config(fixture_root)


def write_fixture_project(fixture_root: Path) -> None:
    (fixture_root / "src").mkdir(parents=True, exist_ok=True)
    (fixture_root / "src" / "app.py").write_text(
        "FIXED = False\n\n"
        "def answer() -> str:\n"
        "    return 'needs-fix'\n",
        encoding="utf-8",
    )
    (fixture_root / ".gitignore").write_text(
        "__pycache__/\n"
        "*.pyc\n",
        encoding="utf-8",
    )
    (fixture_root / "README.md").write_text("# Harness selftest fixture\n", encoding="utf-8")


def init_git_repo(fixture_root: Path) -> None:
    run(["git", "init"], fixture_root)
    run(["git", "config", "user.email", "harness-selftest@example.local"], fixture_root)
    run(["git", "config", "user.name", "Harness Selftest"], fixture_root)
    run(["git", "add", "."], fixture_root)
    run(["git", "commit", "-m", "initial fixture"], fixture_root)


def setup_fixture() -> Path:
    TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    fixture_root = Path(tempfile.mkdtemp(prefix="integration-", dir=TEMP_PARENT))
    copy_harness_into_fixture(fixture_root)
    write_fixture_project(fixture_root)
    init_git_repo(fixture_root)
    return fixture_root


def keep_temp_enabled() -> bool:
    return os.environ.get("HARNESS_SELFTEST_KEEP_TEMP") == "1"


def safe_rmtree(path: Path) -> None:
    parent = TEMP_PARENT.resolve()
    target = path.resolve()
    if parent != target and parent not in target.parents:
        raise AssertionError(f"Refusing to remove path outside selftest temp root: {target}")

    def remove_readonly(func: Any, failed_path: str, _exc_info: Any) -> None:
        os.chmod(failed_path, 0o700)
        func(failed_path)

    shutil.rmtree(target, onerror=remove_readonly)
    try:
        parent.rmdir()
    except OSError:
        pass


def cleanup_fixture(fixture_root: Path, success: bool) -> None:
    if keep_temp_enabled() or not success:
        print(f"\nselftest integration fixture: {fixture_root}", flush=True)
    else:
        safe_rmtree(fixture_root)


@contextmanager
def fixture_workspace() -> Iterator[Path]:
    fixture_root = setup_fixture()
    success = False
    try:
        yield fixture_root
        success = True
    finally:
        cleanup_fixture(fixture_root, success)


def fixture_env(mode: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    if mode:
        env["HARNESS_FAKE_PROVIDER_MODE"] = mode
    else:
        env.pop("HARNESS_FAKE_PROVIDER_MODE", None)
    return env


def run_standard_pipeline(
    fixture_root: Path,
    *,
    feature: str = "selftest-demo",
    mode: str | None = None,
    max_steps: int = 20,
    max_verify_fix_retries: int = 2,
    timeout_seconds: int = 30,
    command_timeout: int = 90,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            ".ai\\harness_standard.py",
            "run",
            "Exercise the standard pipeline with a deterministic fake provider.",
            "--feature",
            feature,
            "--yes",
            "--defaults",
            "--timeout",
            str(timeout_seconds),
            "--max-steps",
            str(max_steps),
            "--max-verify-fix-retries",
            str(max_verify_fix_retries),
            "--performance",
            "lite",
        ],
        fixture_root,
        timeout=command_timeout,
        env=fixture_env(mode),
        check=check,
    )
