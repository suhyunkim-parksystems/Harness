#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


NEXT_STAGE = {
    "00_specify": "01_develop",
    "01_develop": "02_review",
    "02_review": "03_fix",
    "03_fix": "04_verify",
}


def prompt_value(prompt: str, key: str) -> str:
    match = re.search(rf"^- {re.escape(key)}:\s*(.+?)\s*$", prompt, re.M)
    return match.group(1).strip() if match else ""


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def history_notes(stage: str) -> dict[str, list[dict[str, str]]]:
    return {
        "implemented": [{"title": f"{stage} completed by fake provider"}],
        "risks": [],
        "future_improvements": [],
        "decisions": [{"title": "Used deterministic fake provider for harness selftest"}],
        "unresolved_items": [],
    }


def stage_result(stage: str, status: str, next_stage: str, blocking_reason: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "next_stage": next_stage,
        "human_gate_required": False,
        "blocking_reason": blocking_reason,
        "risk_level": "low",
        "harness_commit_required": status == "PASS",
        "changed_files": [],
        "history_notes": history_notes(stage),
    }


def write_stage_output(path: Path, stage: str, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"# {stage}",
        "",
        "Deterministic harness selftest output from fake provider.",
        "",
        "## 단계 결과",
        "```json",
        json.dumps(result, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")


def write_app(fixed: bool) -> None:
    path = Path("src") / "app.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "FIXED = " + ("True" if fixed else "False") + "\n\n"
        "def answer() -> str:\n"
        "    return 'fixed' if FIXED else 'needs-fix'\n",
        encoding="utf-8",
    )


def commit_provider_changes() -> bool:
    try:
        subprocess.run(["git", "add", "."], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            ["git", "commit", "-m", "provider changed head"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        print(f"fake provider git commit failed: {exc}", file=sys.stderr)
        return False
    return True


def handle_pc_candidate_prompt(prompt: str) -> int:
    result = {"candidates": []}
    capture_abs = prompt_value(prompt, "absolute_path")
    capture_rel = prompt_value(prompt, "relative_path")
    if capture_abs:
        write_json(Path(capture_abs), result)
    elif capture_rel:
        write_json(Path(capture_rel), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def run_stage(prompt: str) -> int:
    mode = os.environ.get("HARNESS_FAKE_PROVIDER_MODE", "").strip().lower()
    feature = prompt_value(prompt, "feature_name") or "selftest-demo"
    stage = prompt_value(prompt, "stage")
    output_file = prompt_value(prompt, "output_file")
    result_json_file = prompt_value(prompt, "result_json_file")
    if not stage or not output_file or not result_json_file:
        print("fake provider could not find stage output paths in prompt", file=sys.stderr)
        return 2

    if mode == "provider-nonzero" and stage == "00_specify":
        print("fake provider intentional non-zero exit", file=sys.stderr)
        return 7

    if mode == "provider-silent" and stage == "00_specify":
        return 0

    if stage == "01_develop":
        write_app(fixed=False)
        result = stage_result(stage, "PASS", NEXT_STAGE[stage])
        result["changed_files"] = ["src/app.py"]
    elif stage == "03_fix":
        prior_verify = read_json(Path(".ai") / "features" / feature / "04_verify.result.json")
        if str(prior_verify.get("status") or "").upper() == "FAIL" and mode != "verify-always-fail":
            write_app(fixed=True)
            result = stage_result(stage, "PASS", NEXT_STAGE[stage])
            result["changed_files"] = ["src/app.py"]
            result["history_notes"]["implemented"] = [{"title": "Applied retry fix after verify failure"}]
        else:
            result = stage_result(stage, "PASS", NEXT_STAGE[stage])
            result["changed_files"] = []
    elif stage == "04_verify":
        fixed = "FIXED = True" in (Path("src") / "app.py").read_text(encoding="utf-8", errors="replace")
        if fixed and mode != "verify-always-fail":
            result = stage_result(stage, "PASS", "done")
            result["verification_summary"] = {"status": "PASS", "checked": ["src/app.py"]}
        else:
            result = stage_result(stage, "FAIL", "03_fix", "Selftest app is intentionally not fixed yet.")
            result["harness_commit_required"] = False
            result["verification_summary"] = {"status": "FAIL", "failed": ["src/app.py"]}
            result["fix_inputs"] = {"items": ["Set FIXED = True in src/app.py"]}
    else:
        result = stage_result(stage, "PASS", NEXT_STAGE.get(stage, "done"))
        if stage == "00_specify":
            result["feature_name"] = feature

    if mode == "write-policy-violation" and stage == "00_specify":
        violation_path = Path("src") / "policy_violation.py"
        violation_path.parent.mkdir(parents=True, exist_ok=True)
        violation_path.write_text("VALUE = 'forbidden during specify'\n", encoding="utf-8")
        result["changed_files"] = ["src/policy_violation.py"]

    write_stage_output(Path(output_file), stage, result)

    if mode == "malformed-json" and stage == "00_specify":
        Path(result_json_file).parent.mkdir(parents=True, exist_ok=True)
        Path(result_json_file).write_text("{ this is not valid json\n", encoding="utf-8")
        print(f"HARNESS_FAKE_PROVIDER_OK {stage}")
        return 0

    write_json(Path(result_json_file), result)

    if mode == "git-head-change" and stage == "00_specify":
        if not commit_provider_changes():
            return 3

    print(f"HARNESS_FAKE_PROVIDER_OK {stage}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="fake")
    parser.parse_known_args()
    prompt = sys.stdin.read()
    if "Project Contract Candidate Extraction" in prompt:
        return handle_pc_candidate_prompt(prompt)
    return run_stage(prompt)


if __name__ == "__main__":
    raise SystemExit(main())
