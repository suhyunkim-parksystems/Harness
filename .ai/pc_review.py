#!/usr/bin/env python
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

import harness as base


DEFAULT_AGENT = "codex"
AGENT_CHOICES = ("codex", "claude", "agy")
REVIEW_TIMEOUT_SECONDS = 3600
PROGRESS_INTERVAL_SECONDS = 15
COLOR_RESET = "\033[0m"
COLOR_DIM = "\033[2m"
COLOR_BOLD = "\033[1m"
COLOR_BLUE = "\033[34m"
COLOR_CYAN = "\033[36m"
COLOR_GREEN = "\033[32m"
COLOR_MAGENTA = "\033[35m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        return


_enable_windows_ansi()


def _color_enabled() -> bool:
    return not os.environ.get("NO_COLOR") and sys.stdout.isatty()


def _style(text: str, *codes: str) -> str:
    if not _color_enabled() or not codes:
        return text
    return "".join(codes) + text + COLOR_RESET


def _print_rule(title: str, color: str = COLOR_CYAN) -> None:
    line = f"========== {title} =========="
    print(_style(line, COLOR_BOLD, color), flush=True)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _snapshot(paths: list[Path]) -> dict[Path, str]:
    return {path: _read_text(path) for path in paths}


def _restore(snapshot: dict[Path, str]) -> None:
    for path, text in snapshot.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _changed(snapshot: dict[Path, str]) -> list[Path]:
    return [path for path, text in snapshot.items() if _read_text(path) != text]


def _now_label() -> str:
    return datetime.now().strftime("%H:%M:%S")


def pending_candidates_payload(candidates: list[dict]) -> str:
    compact: list[dict] = []
    for item in candidates:
        compact.append(
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "rule_candidate": item.get("rule_candidate") or item.get("summary"),
                "rationale": item.get("rationale"),
                "evidence": item.get("evidence"),
                "recommended_contract_section": item.get("recommended_contract_section"),
                "source_feature": item.get("source_feature"),
                "source_artifacts": item.get("source_artifacts"),
            }
        )
    return json.dumps(compact, ensure_ascii=False, indent=2)


def build_batch_review_prompt(candidates: list[dict], contract_text: str, agent: str) -> str:
    return f"""# Project Contract Batch Review

You are reviewing all pending Project Contract candidates for a local AI development harness.

Do not edit files. Return one JSON object only.

## Existing Project Contract
If this contract is empty or minimal, treat it as the current set of project-wide constraints.

```markdown
{contract_text}
```

## Pending Candidates
```json
{pending_candidates_payload(candidates)}
```

## Goal
Propose only useful project-wide rules to add to `.project/project_contract.md`.

Rules must be concise, clear, and reusable across future pipeline prompts.
Do not add evidence, long rationale, implementation history, feature-specific detail, or provider-specific detail to the contract.
If several candidates mean the same thing, merge them into one short rule.

## Decision Rules
- There is no ambiguous status.
- If a candidate is already covered, too specific, weakly supported, duplicated, or only an implementation detail, reject it.
- If a candidate becomes part of a proposed project-wide rule, mark it covered by that rule.
- Every pending candidate id must appear exactly once, either in `proposed_rules[].covered_candidate_ids` or `rejected_candidates[].candidate_id`.
- Do not propose a rule that duplicates the existing Project Contract.
- `project_contract_markdown` is append-only: keep every existing line of the current contract unchanged and only add new lines. Never drop, merge, or rewrite existing rules.
- Each `rule_text` must appear verbatim as its own line (typically a `- ` bullet) in `project_contract_markdown`, and `rule_text` values must not duplicate each other.
- Keep each `rule_text` short. Prefer one sentence under 160 Korean characters.
- The final `project_contract_markdown` must be concise and rule-focused.

## Required JSON Output
Return a single JSON object with this shape:

```json
{{
  "summary": "짧은 한국어 요약",
  "proposed_rules": [
    {{
      "target_section": "Reliability",
      "rule_text": "추가할 최종 규칙 문장",
      "covered_candidate_ids": ["pc-..."],
      "reason": "왜 프로젝트 전체 규칙으로 가치가 있는지 짧게"
    }}
  ],
  "rejected_candidates": [
    {{
      "candidate_id": "pc-...",
      "reason_code": "already_covered | too_specific | implementation_detail | duplicate | weak_project_value",
      "reason": "짧은 한국어 사유"
    }}
  ],
  "project_contract_markdown": "# Project Contract\\n\\n..."
}}
```

`project_contract_markdown` must be the full final file content after applying `proposed_rules`.
If there are no rules to add, return the existing contract unchanged and put all candidates in `rejected_candidates`.

reviewer_agent: {agent}
"""


def _progress_until_done(stop: threading.Event, label: str) -> None:
    while not stop.wait(PROGRESS_INTERVAL_SECONDS):
        print(_style(f"[{_now_label()}] {label} 진행 중...", COLOR_DIM, COLOR_BLUE), flush=True)


def run_agent(agent: str, prompt: str, prefix: str, label: str) -> dict:
    print(_style(f"[{_now_label()}] {label} 시작 (agent={agent})", COLOR_BOLD, COLOR_BLUE), flush=True)
    stop = threading.Event()
    heartbeat = threading.Thread(target=_progress_until_done, args=(stop, label), daemon=True)
    heartbeat.start()
    try:
        result = base.run_text_provider_prompt(
            agent,
            prompt,
            logs_dir=base.RUNS_DIR / "_pc_review" / "logs",
            log_prefix=prefix,
            timeout_seconds=REVIEW_TIMEOUT_SECONDS,
            performance="medium",
        )
    finally:
        stop.set()
        heartbeat.join(timeout=1)

    print(
        _style(
            f"[{_now_label()}] {label} 완료 "
            f"(stdout={result.get('stdout')} stderr={result.get('stderr')})",
            COLOR_GREEN,
        ),
        flush=True,
    )
    if result.get("returncode") != 0 or result.get("timed_out"):
        raise base.HarnessError(
            f"{agent} PC review failed. "
            f"stdout={result.get('stdout')} stderr={result.get('stderr')}"
        )
    return result


def parse_batch_proposal(stdout_text: str) -> dict:
    proposal = base.parse_result_json_from_text(stdout_text)
    if not proposal:
        raise base.HarnessError("Agent did not return a valid JSON object for the batch PC proposal.")
    return proposal


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def validate_batch_proposal(proposal: dict, pending: list[dict], current_contract: str) -> None:
    pending_ids = {str(item.get("id") or "").strip() for item in pending}
    pending_ids.discard("")
    if len(pending_ids) != len(pending):
        raise base.HarnessError("Pending PC candidates must all have unique non-empty ids.")

    proposed_rules = proposal.get("proposed_rules")
    rejected_candidates = proposal.get("rejected_candidates")
    if not isinstance(proposed_rules, list):
        raise base.HarnessError("Batch PC proposal must include proposed_rules as a list.")
    if not isinstance(rejected_candidates, list):
        raise base.HarnessError("Batch PC proposal must include rejected_candidates as a list.")

    approved_ids: list[str] = []
    rejected_ids: list[str] = []
    seen_rule_texts: set[str] = set()
    for index, rule in enumerate(proposed_rules, start=1):
        if not isinstance(rule, dict):
            raise base.HarnessError(f"proposed_rules[{index}] must be an object.")
        rule_text = str(rule.get("rule_text") or "").strip()
        if not rule_text:
            raise base.HarnessError(f"proposed_rules[{index}] is missing rule_text.")
        if len(rule_text) > 220:
            raise base.HarnessError(
                f"proposed_rules[{index}] is too long. Keep Project Contract rules concise."
            )
        if rule_text in seen_rule_texts:
            raise base.HarnessError(
                f"proposed_rules[{index}] duplicates an earlier rule_text: {rule_text}"
            )
        seen_rule_texts.add(rule_text)
        covered = _string_list(rule.get("covered_candidate_ids"))
        if not covered:
            raise base.HarnessError(f"proposed_rules[{index}] must cover at least one candidate id.")
        approved_ids.extend(covered)

    for index, item in enumerate(rejected_candidates, start=1):
        if not isinstance(item, dict):
            raise base.HarnessError(f"rejected_candidates[{index}] must be an object.")
        candidate_id = str(item.get("candidate_id") or "").strip()
        if not candidate_id:
            raise base.HarnessError(f"rejected_candidates[{index}] is missing candidate_id.")
        rejected_ids.append(candidate_id)

    all_seen = approved_ids + rejected_ids
    duplicates = sorted({candidate_id for candidate_id in all_seen if all_seen.count(candidate_id) > 1})
    if duplicates:
        raise base.HarnessError(f"Candidate ids appear more than once in proposal: {', '.join(duplicates)}")

    seen = set(all_seen)
    unknown = sorted(seen - pending_ids)
    missing = sorted(pending_ids - seen)
    if unknown:
        raise base.HarnessError(f"Proposal references unknown candidate ids: {', '.join(unknown)}")
    if missing:
        raise base.HarnessError(f"Proposal did not decide candidate ids: {', '.join(missing)}")

    proposed_contract = str(proposal.get("project_contract_markdown") or "").strip()
    if proposed_rules and not proposed_contract:
        raise base.HarnessError("Proposal adds rules but project_contract_markdown is empty.")
    if not proposed_contract:
        fallback_contract = current_contract.rstrip() or "# Project Contract"
        proposal["project_contract_markdown"] = fallback_contract + "\n"
        proposed_contract = str(proposal["project_contract_markdown"]).strip()
    if not proposed_contract.startswith("# Project Contract"):
        raise base.HarnessError("project_contract_markdown must start with '# Project Contract'.")

    proposed_lines = {line.strip() for line in proposed_contract.splitlines()}
    # The contract is append-only: a reviewer proposal may add rules but must
    # never drop or rewrite lines that are already part of the approved
    # contract (project_planning enforces the same invariant on its path).
    missing_existing = [
        line.strip()
        for line in current_contract.splitlines()
        if line.strip() and line.strip() not in proposed_lines
    ]
    if missing_existing:
        preview = " | ".join(missing_existing[:3])
        raise base.HarnessError(
            "project_contract_markdown drops existing contract lines "
            f"(the contract is append-only): {preview}"
        )

    # Each approved rule must exist as its own (optionally bulleted) line, not
    # merely as a substring of some unrelated longer line.
    rule_lines = set(proposed_lines)
    for line in proposed_lines:
        if line.startswith(("- ", "* ")):
            rule_lines.add(line[2:].strip())
    for index, rule in enumerate(proposed_rules, start=1):
        rule_text = str(rule.get("rule_text") or "").strip()
        if rule_text not in rule_lines:
            raise base.HarnessError(
                f"project_contract_markdown does not contain proposed_rules[{index}].rule_text "
                "as its own line."
            )


def display_batch_proposal(proposal: dict, pending: list[dict]) -> None:
    candidates_by_id = {str(item.get("id") or ""): item for item in pending}
    proposed_rules = proposal.get("proposed_rules") if isinstance(proposal.get("proposed_rules"), list) else []
    rejected = proposal.get("rejected_candidates") if isinstance(proposal.get("rejected_candidates"), list) else []

    print()
    _print_rule("PC 일괄 검토 결과", COLOR_CYAN)
    summary = str(proposal.get("summary") or "").strip()
    if summary:
        print(summary)
    print(_style(f"추가 제안: {len(proposed_rules)}개 / 기각 예정: {len(rejected)}개", COLOR_BOLD, COLOR_CYAN))

    print()
    _print_rule("추가될 Project Contract 문장", COLOR_GREEN)
    if not proposed_rules:
        print("추가할 문장이 없습니다.")
    for index, rule in enumerate(proposed_rules, start=1):
        section = str(rule.get("target_section") or "Unspecified").strip()
        text = str(rule.get("rule_text") or "").strip()
        covered = ", ".join(_string_list(rule.get("covered_candidate_ids")))
        reason = str(rule.get("reason") or "").strip()
        print(f"{index}. [{section}] {text}")
        print(f"   후보: {covered}")
        if reason:
            print(f"   이유: {reason}")

    print()
    _print_rule("기각될 후보", COLOR_YELLOW)
    if not rejected:
        print("기각될 후보가 없습니다.")
    for item in rejected:
        candidate_id = str(item.get("candidate_id") or "").strip()
        candidate = candidates_by_id.get(candidate_id, {})
        candidate_text = str(candidate.get("rule_candidate") or candidate.get("summary") or "").strip()
        reason_code = str(item.get("reason_code") or "-").strip()
        reason = str(item.get("reason") or "").strip()
        print(f"- {candidate_id} ({reason_code})")
        if candidate_text:
            print(f"  후보: {candidate_text}")
        if reason:
            print(f"  사유: {reason}")


def proposal_approved_candidate_ids(proposal: dict) -> set[str]:
    approved: set[str] = set()
    for rule in proposal.get("proposed_rules", []):
        if isinstance(rule, dict):
            approved.update(_string_list(rule.get("covered_candidate_ids")))
    return approved


def proposal_rejected_candidate_ids(proposal: dict) -> set[str]:
    rejected: set[str] = set()
    for item in proposal.get("rejected_candidates", []):
        if isinstance(item, dict):
            candidate_id = str(item.get("candidate_id") or "").strip()
            if candidate_id:
                rejected.add(candidate_id)
    return rejected


def update_candidate_decisions(decisions: dict[str, str], reasons: dict[str, str]) -> None:
    allowed = {base.PC_APPROVED_STATUS, base.PC_REJECTED_STATUS}
    store = base.read_pc_candidates_store()
    seen: set[str] = set()
    for item in store.get("candidates", []):
        candidate_id = str(item.get("id") or "")
        if candidate_id not in decisions:
            continue
        status = decisions[candidate_id]
        if status not in allowed:
            raise base.HarnessError(f"Unsupported PC decision status: {status}")
        item["status"] = status
        item["decided_at"] = base.iso_now()
        item["decision_reason"] = reasons.get(candidate_id, "")
        seen.add(candidate_id)
    missing = sorted(set(decisions) - seen)
    if missing:
        raise base.HarnessError(f"PC candidate not found: {', '.join(missing)}")
    base.write_pc_candidates_store(store)


def apply_accepted_proposal(proposal: dict, pending: list[dict], agent: str) -> None:
    approved_ids = proposal_approved_candidate_ids(proposal)
    rejected_ids = proposal_rejected_candidate_ids(proposal)
    decisions: dict[str, str] = {}
    reasons: dict[str, str] = {}

    for rule in proposal.get("proposed_rules", []):
        if not isinstance(rule, dict):
            continue
        rule_text = str(rule.get("rule_text") or "").strip()
        for candidate_id in _string_list(rule.get("covered_candidate_ids")):
            decisions[candidate_id] = base.PC_APPROVED_STATUS
            reasons[candidate_id] = (
                f"사용자가 pc_review 일괄 제안을 승인함. "
                f"{agent} 제안 규칙: {rule_text}"
            )

    rejected_by_id = {
        str(item.get("candidate_id") or "").strip(): item
        for item in proposal.get("rejected_candidates", [])
        if isinstance(item, dict)
    }
    for candidate_id in rejected_ids:
        item = rejected_by_id.get(candidate_id, {})
        reason_code = str(item.get("reason_code") or "rejected").strip()
        reason = str(item.get("reason") or "").strip()
        decisions[candidate_id] = base.PC_REJECTED_STATUS
        reasons[candidate_id] = (
            f"사용자가 pc_review 일괄 제안을 승인했으며, "
            f"{agent}가 후보를 기각 대상으로 분류함({reason_code}). {reason}"
        ).strip()

    pending_ids = {str(item.get("id") or "").strip() for item in pending}
    if set(decisions) != pending_ids:
        missing = sorted(pending_ids - set(decisions))
        extra = sorted(set(decisions) - pending_ids)
        raise base.HarnessError(f"Internal decision mismatch. missing={missing} extra={extra}")
    if approved_ids & rejected_ids:
        overlap = ", ".join(sorted(approved_ids & rejected_ids))
        raise base.HarnessError(f"Internal decision overlap: {overlap}")

    proposed_contract = str(proposal.get("project_contract_markdown") or "").rstrip() + "\n"
    base.project_contract_path().write_text(proposed_contract, encoding="utf-8")
    update_candidate_decisions(decisions, reasons)


def reject_all_pending(pending: list[dict], reason: str) -> None:
    decisions = {
        str(item.get("id") or "").strip(): base.PC_REJECTED_STATUS
        for item in pending
        if str(item.get("id") or "").strip()
    }
    update_candidate_decisions(decisions, {candidate_id: reason for candidate_id in decisions})


def ask_yes_no(prompt: str) -> bool:
    while True:
        answer = input(_style(prompt, COLOR_BOLD, COLOR_YELLOW)).strip().lower()
        if answer in {"yes", "y"}:
            return True
        if answer in {"no", "n"}:
            return False
        print(_style("Yes 또는 No로 답해주세요. 예: y / n", COLOR_RED))


def validate_after_apply() -> list[dict]:
    store = base.read_pc_candidates_store()
    allowed = {base.PC_PENDING_STATUS, base.PC_APPROVED_STATUS, base.PC_REJECTED_STATUS}
    invalid = [
        item
        for item in store.get("candidates", [])
        if str(item.get("status") or "") not in allowed
    ]
    if invalid:
        ids = ", ".join(str(item.get("id") or "-") for item in invalid)
        raise base.HarnessError(f"Invalid PC candidate status after apply: {ids}")
    if not base.project_contract_path().exists():
        raise base.HarnessError("Project contract file is missing after apply.")
    return base.pending_pc_candidates()


def ensure_pc_files() -> None:
    if not base.pc_candidates_path().exists():
        base.write_pc_candidates_store(base.empty_pc_candidates_store())
    base.ensure_project_contract_file()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch review pending Project Contract candidates.")
    parser.add_argument(
        "--agent",
        choices=AGENT_CHOICES,
        default=DEFAULT_AGENT,
        help=f"Agent used to review Project Contract candidates. Default: {DEFAULT_AGENT}.",
    )
    parser.add_argument(
        "--yes",
        "--auto",
        dest="yes",
        action="store_true",
        help=(
            "Non-interactive: apply the reviewer's proposal without the y/n prompt "
            "(trusts the reviewer agent's judgment). Used by orchestrate between runs. "
            "Note: this always APPLIES the proposal; it never takes the interactive "
            "No path (which rejects all pending)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)
    agent = args.agent

    ensure_pc_files()
    pending = base.pending_pc_candidates()
    if not pending:
        print("미정 Project Contract 후보가 없습니다.")
        return 0

    candidates_path = base.pc_candidates_path()
    contract_path = base.project_contract_path()
    protected = [candidates_path, contract_path]

    print(_style(f"미정 PC 후보 {len(pending)}개를 {agent}가 한 번에 검토합니다.", COLOR_BOLD, COLOR_CYAN))
    if args.yes:
        print(_style("--yes 모드: 리뷰어 제안을 자동 적용합니다(전체 기각 경로 없음).", COLOR_CYAN))
    else:
        print(_style("추가할 최종 Project Contract 문장을 제안받고, 사용자는 전체 제안에 대해 한 번만 y/n을 선택합니다.", COLOR_CYAN))

    current_contract = _read_text(contract_path)
    before_review = _snapshot(protected)
    review = run_agent(
        agent,
        build_batch_review_prompt(pending, current_contract, agent),
        "pc_review_batch",
        f"PC 후보 {len(pending)}개 일괄 검토",
    )

    changed = _changed(before_review)
    if changed:
        _restore(before_review)
        changed_paths = ", ".join(str(path) for path in changed)
        raise base.HarnessError(
            f"{agent} modified files during the read-only batch review; changes were restored. "
            f"Changed files: {changed_paths}"
        )

    review_text = str(review.get("stdout_text") or "").strip()
    proposal = parse_batch_proposal(review_text)
    validate_batch_proposal(proposal, pending, current_contract)
    display_batch_proposal(proposal, pending)

    print()
    if args.yes:
        accepted = True
        print(_style("[--yes] 사용자 확인 없이 리뷰어 제안을 자동 적용합니다.", COLOR_BOLD, COLOR_GREEN))
    else:
        accepted = ask_yes_no("이 Project Contract 갱신 제안을 적용할까요? (Yes=적용 / No=전체 기각): ")
    if accepted:
        before_apply = _snapshot(protected)
        try:
            apply_accepted_proposal(proposal, pending, agent)
        except Exception:
            _restore(before_apply)
            raise
        approved_count = len(proposal_approved_candidate_ids(proposal))
        rejected_count = len(proposal_rejected_candidate_ids(proposal))
        print(
            _style(
                f"[{_now_label()}] 적용 완료: 승인 후보 {approved_count}개 / 기각 후보 {rejected_count}개",
                COLOR_BOLD,
                COLOR_GREEN,
            )
        )
    else:
        reject_all_pending(
            pending,
            "사용자가 pc_review 일괄 제안을 적용하지 않아 미정 후보 전체를 기각함.",
        )
        print(_style(f"[{_now_label()}] 미정 PC 후보 {len(pending)}개 전체 기각 완료", COLOR_BOLD, COLOR_RED))

    remaining = validate_after_apply()
    print()
    if remaining:
        print(f"아직 미정 PC 후보가 {len(remaining)}개 남아 있습니다. pc_review가 정상 완료되면 미정 후보가 남지 않아야 합니다.")
        return 1
    print("모든 PC 후보가 승인 또는 기각되었습니다.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except base.HarnessError as exc:
        print(f"[PC review failed] {exc}", file=sys.stderr)
        raise SystemExit(1)
