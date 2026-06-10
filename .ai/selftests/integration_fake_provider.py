#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


PIPELINES = {
    "fast": {
        "stages": ("00_specify", "01_develop", "02_verify"),
        "develop_stage": "01_develop",
        "verify_stage": "02_verify",
        "verify_output": "02_verify.md",
        "verify_retry_target": "01_develop",
        "verify_pass_next": "done",
        "document_stage": None,
    },
    "standard": {
        "stages": ("00_specify", "01_develop", "02_review", "03_fix", "04_verify"),
        "develop_stage": "01_develop",
        "verify_stage": "04_verify",
        "verify_output": "04_verify.md",
        "verify_retry_target": "03_fix",
        "verify_pass_next": "done",
        "document_stage": None,
    },
    "full": {
        "stages": (
            "00_specify",
            "01_plan",
            "02_develop",
            "03_review",
            "04_fix",
            "05_verify",
            "06_document",
        ),
        "develop_stage": "02_develop",
        "verify_stage": "05_verify",
        "verify_output": "05_verify.md",
        "verify_retry_target": "04_fix",
        "verify_pass_next": "06_document",
        "document_stage": "06_document",
    },
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


def infer_pipeline_mode(prompt: str, stage: str) -> str:
    mode = prompt_value(prompt, "pipeline_mode").strip().lower()
    if mode in PIPELINES:
        return mode
    for candidate, config in PIPELINES.items():
        if stage in config["stages"]:
            return candidate
    return "standard"


def next_stage_for(config: dict[str, Any], stage: str) -> str:
    stages = list(config["stages"])
    if stage == config["verify_stage"]:
        return str(config["verify_pass_next"])
    try:
        index = stages.index(stage)
    except ValueError:
        return "done"
    if index + 1 >= len(stages):
        return "done"
    return str(stages[index + 1])


def prior_verify_result(feature: str, config: dict[str, Any]) -> dict[str, Any]:
    output_name = str(config["verify_output"])
    result_name = output_name.replace(".md", ".result.json")
    return read_json(Path(".project") / "features" / feature / result_name)


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


def write_minimal_docx(feature: str) -> Path:
    path = Path(".project") / "docs" / f"{feature}_\uba85\uc138\uc11c.docx"
    path.parent.mkdir(parents=True, exist_ok=True)
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:t>Harness integration selftest document.</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("word/document.xml", document_xml)
    return path


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
    pipeline_mode = infer_pipeline_mode(prompt, stage)
    config = PIPELINES[pipeline_mode]
    verify_stage = str(config["verify_stage"])
    verify_retry_target = str(config["verify_retry_target"])
    develop_stage = str(config["develop_stage"])
    document_stage = str(config.get("document_stage") or "")

    if mode == "provider-nonzero" and stage == "00_specify":
        print("fake provider intentional non-zero exit", file=sys.stderr)
        return 7

    if mode == "provider-silent" and stage == "00_specify":
        return 0

    if stage == develop_stage:
        prior_verify = prior_verify_result(feature, config)
        retrying_after_verify_fail = str(prior_verify.get("status") or "").upper() == "FAIL"
        fixed = retrying_after_verify_fail and mode != "verify-always-fail"
        write_app(fixed=fixed)
        result = stage_result(stage, "PASS", next_stage_for(config, stage))
        result["changed_files"] = ["src/app.py"]
        if fixed:
            result["history_notes"]["implemented"] = [{"title": "Applied retry fix after verify failure"}]
    elif stage == verify_retry_target:
        prior_verify = prior_verify_result(feature, config)
        if str(prior_verify.get("status") or "").upper() == "FAIL" and mode != "verify-always-fail":
            write_app(fixed=True)
            result = stage_result(stage, "PASS", next_stage_for(config, stage))
            result["changed_files"] = ["src/app.py"]
            result["history_notes"]["implemented"] = [{"title": "Applied retry fix after verify failure"}]
        else:
            result = stage_result(stage, "PASS", next_stage_for(config, stage))
            result["changed_files"] = []
    elif stage == verify_stage:
        fixed = "FIXED = True" in (Path("src") / "app.py").read_text(encoding="utf-8", errors="replace")
        if fixed and mode != "verify-always-fail":
            result = stage_result(stage, "PASS", next_stage_for(config, stage))
            result["verification_summary"] = {"status": "PASS", "checked": ["src/app.py"]}
        else:
            result = stage_result(stage, "FAIL", verify_retry_target, "Selftest app is intentionally not fixed yet.")
            result["harness_commit_required"] = False
            result["verification_summary"] = {"status": "FAIL", "failed": ["src/app.py"]}
            result["fix_inputs"] = {"items": ["Set FIXED = True in src/app.py"]}
    elif stage == document_stage:
        docx_path = write_minimal_docx(feature)
        result = stage_result(stage, "PASS", next_stage_for(config, stage))
        result["produced_files"] = [docx_path.as_posix()]
        result["changed_files"] = [docx_path.as_posix()]
    else:
        result = stage_result(stage, "PASS", next_stage_for(config, stage))
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
