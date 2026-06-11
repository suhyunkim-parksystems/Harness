from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

from support import ensure_ai_path

ensure_ai_path()

import harness  # noqa: E402
import pc_review  # noqa: E402


# pc_review does `import harness as base`, so pc_review's `base` is the same
# module object as `harness`. Rebinding path constants on `harness` therefore
# redirects every `base.*` filesystem call inside pc_review to a temp dir.
_PATCHED_PATH_NAMES = (
    "ROOT",
    "AI_DIR",
    "PROJECT_DIR",
    "HARNESS_CONFIG_PATH",
    "PROJECT_CONFIG_PATH",
    "RUNS_DIR",
    "FEATURES_DIR",
    "DOCS_DIR",
    "HISTORY_DIR",
    "PROJECT_CONTRACT_PATH",
    "PC_CANDIDATES_PATH",
)

CONTRACT_HEADER = "# Project Contract"
BASE_CONTRACT = "# Project Contract\n\n## Reliability\n- 기존 규칙은 유지한다.\n"


def _candidate(candidate_id: str, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": candidate_id,
        "status": harness.PC_PENDING_STATUS,
        "category": "process",
        "rule_candidate": f"rule candidate for {candidate_id}",
        "rationale": "rationale",
        "evidence": "evidence",
        "recommended_contract_section": "Reliability",
        "source_feature": "feat-x",
        "source_artifacts": [],
    }
    item.update(overrides)
    return item


def _rule(
    rule_text: str,
    covered: list[str],
    *,
    section: str = "Reliability",
    reason: str = "프로젝트 전반에 유용",
) -> dict[str, Any]:
    return {
        "target_section": section,
        "rule_text": rule_text,
        "covered_candidate_ids": covered,
        "reason": reason,
    }


def _rejection(candidate_id: str, *, reason_code: str = "too_specific", reason: str = "사유") -> dict[str, Any]:
    return {"candidate_id": candidate_id, "reason_code": reason_code, "reason": reason}


def _proposal(
    *,
    rules: list[dict[str, Any]] | None = None,
    rejected: list[dict[str, Any]] | None = None,
    contract: str = BASE_CONTRACT,
    summary: str = "요약",
) -> dict[str, Any]:
    return {
        "summary": summary,
        "proposed_rules": [] if rules is None else rules,
        "rejected_candidates": [] if rejected is None else rejected,
        "project_contract_markdown": contract,
    }


class IsolatedPcReviewTest(unittest.TestCase):
    """Base class that redirects all harness .project/ paths to a temp dir."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-review-selftest-"))
        self._orig = {name: getattr(harness, name) for name in _PATCHED_PATH_NAMES}
        harness.ROOT = self.tmp
        harness.AI_DIR = self.tmp / ".ai"
        harness.PROJECT_DIR = self.tmp / ".project"
        harness.HARNESS_CONFIG_PATH = harness.AI_DIR / "harness.config.json"
        harness.PROJECT_CONFIG_PATH = harness.PROJECT_DIR / "harness.config.json"
        harness.RUNS_DIR = harness.PROJECT_DIR / "runs"
        harness.FEATURES_DIR = harness.PROJECT_DIR / "features"
        harness.DOCS_DIR = harness.PROJECT_DIR / "docs"
        harness.HISTORY_DIR = harness.PROJECT_DIR / "history"
        harness.PROJECT_CONTRACT_PATH = harness.PROJECT_DIR / "project_contract.md"
        harness.PC_CANDIDATES_PATH = harness.HISTORY_DIR / "pc_candidates.json"
        harness.HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for name, value in self._orig.items():
            setattr(harness, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seed_store(self, candidates: list[dict[str, Any]]) -> None:
        harness.write_pc_candidates_store({"version": 1, "candidates": candidates})

    def seed_contract(self, text: str = BASE_CONTRACT) -> None:
        harness.PROJECT_CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        harness.PROJECT_CONTRACT_PATH.write_text(text, encoding="utf-8")

    def statuses(self) -> dict[str, str]:
        store = harness.read_pc_candidates_store()
        return {str(item.get("id")): str(item.get("status")) for item in store["candidates"]}


# --------------------------------------------------------------------------- #
# Pure helpers: payload, prompt, _string_list, parse_batch_proposal
# --------------------------------------------------------------------------- #
class PendingCandidatesPayloadTests(unittest.TestCase):
    def test_payload_is_compact_json_with_expected_fields(self) -> None:
        payload = pc_review.pending_candidates_payload(
            [_candidate("pc-1", rule_candidate="규칙 후보", category="testing")]
        )
        parsed = json.loads(payload)
        self.assertEqual(len(parsed), 1)
        entry = parsed[0]
        self.assertEqual(entry["id"], "pc-1")
        self.assertEqual(entry["category"], "testing")
        self.assertEqual(entry["rule_candidate"], "규칙 후보")
        for key in ("rationale", "evidence", "recommended_contract_section", "source_feature", "source_artifacts"):
            self.assertIn(key, entry)
        # Internal store fields must not leak into the reviewer payload.
        self.assertNotIn("status", entry)

    def test_payload_falls_back_to_summary_when_rule_candidate_missing(self) -> None:
        candidate = _candidate("pc-2")
        candidate.pop("rule_candidate")
        candidate["summary"] = "요약 문장"
        parsed = json.loads(pc_review.pending_candidates_payload([candidate]))
        self.assertEqual(parsed[0]["rule_candidate"], "요약 문장")


class BuildBatchReviewPromptTests(unittest.TestCase):
    def test_prompt_contains_key_sections_and_inputs(self) -> None:
        prompt = pc_review.build_batch_review_prompt(
            [_candidate("pc-77")], "# Project Contract\n- 기존 규칙\n", "codex"
        )
        # Key structural sections (loose match, not exact wording).
        self.assertIn("Project Contract Batch Review", prompt)
        self.assertIn("## Pending Candidates", prompt)
        self.assertIn("## Decision Rules", prompt)
        self.assertIn("## Required JSON Output", prompt)
        # Inputs are embedded.
        self.assertIn("- 기존 규칙", prompt)
        self.assertIn("pc-77", prompt)
        self.assertIn("reviewer_agent: codex", prompt)
        # The required output schema keys are spelled out for the agent.
        for key in ("proposed_rules", "rejected_candidates", "project_contract_markdown", "covered_candidate_ids"):
            self.assertIn(key, prompt)


class StringListTests(unittest.TestCase):
    def test_non_list_returns_empty(self) -> None:
        self.assertEqual(pc_review._string_list(None), [])
        self.assertEqual(pc_review._string_list("pc-1"), [])
        self.assertEqual(pc_review._string_list({"a": 1}), [])

    def test_strips_and_drops_blank_entries(self) -> None:
        self.assertEqual(pc_review._string_list([" pc-1 ", "", "  ", "pc-2", 3]), ["pc-1", "pc-2", "3"])


class ParseBatchProposalTests(unittest.TestCase):
    def test_parses_json_object_from_stdout(self) -> None:
        text = "noise before\n" + json.dumps({"summary": "ok", "proposed_rules": []}) + "\nnoise after"
        proposal = pc_review.parse_batch_proposal(text)
        self.assertEqual(proposal["summary"], "ok")

    def test_parses_fenced_json_block(self) -> None:
        text = "```json\n{\"summary\": \"fenced\"}\n```"
        self.assertEqual(pc_review.parse_batch_proposal(text)["summary"], "fenced")

    def test_non_json_output_raises(self) -> None:
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.parse_batch_proposal("no json here")
        self.assertIn("did not return a valid JSON object", str(ctx.exception))


# --------------------------------------------------------------------------- #
# validate_batch_proposal: strict validator rejection paths + happy path
# --------------------------------------------------------------------------- #
class ValidateBatchProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pending = [_candidate("pc-1"), _candidate("pc-2")]
        self.contract = BASE_CONTRACT

    def _assert_rejected(self, proposal: dict[str, Any], substring: str, pending: list[dict[str, Any]] | None = None) -> None:
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.validate_batch_proposal(
                proposal, self.pending if pending is None else pending, self.contract
            )
        self.assertIn(substring, str(ctx.exception))

    def test_happy_path_passes(self) -> None:
        rule_text = "모든 변경은 셀프테스트를 통과해야 한다."
        proposal = _proposal(
            rules=[_rule(rule_text, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=BASE_CONTRACT + f"- {rule_text}\n",
        )
        # No exception means the proposal is accepted.
        pc_review.validate_batch_proposal(proposal, self.pending, self.contract)

    def test_pending_candidates_must_have_unique_ids(self) -> None:
        pending = [_candidate("pc-1"), _candidate("pc-1")]
        self._assert_rejected(_proposal(), "unique non-empty ids", pending=pending)

    def test_proposed_rules_must_be_a_list(self) -> None:
        proposal = _proposal()
        proposal["proposed_rules"] = "not-a-list"
        self._assert_rejected(proposal, "proposed_rules as a list")

    def test_rejected_candidates_must_be_a_list(self) -> None:
        proposal = _proposal()
        proposal["rejected_candidates"] = None
        self._assert_rejected(proposal, "rejected_candidates as a list")

    def test_rule_missing_rule_text_rejected(self) -> None:
        proposal = _proposal(rules=[_rule("   ", ["pc-1"])], rejected=[_rejection("pc-2")])
        self._assert_rejected(proposal, "missing rule_text")

    def test_rule_text_over_220_chars_rejected(self) -> None:
        long_text = "r" * 221
        proposal = _proposal(
            rules=[_rule(long_text, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=BASE_CONTRACT + long_text + "\n",
        )
        self._assert_rejected(proposal, "too long")

    def test_rule_text_at_220_chars_allowed(self) -> None:
        edge_text = "r" * 220
        proposal = _proposal(
            rules=[_rule(edge_text, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=BASE_CONTRACT + edge_text + "\n",
        )
        pc_review.validate_batch_proposal(proposal, self.pending, self.contract)

    def test_rule_without_covered_candidates_rejected(self) -> None:
        proposal = _proposal(rules=[_rule("규칙", [])], rejected=[_rejection("pc-1"), _rejection("pc-2")])
        self._assert_rejected(proposal, "must cover at least one candidate id")

    def test_rejected_entry_missing_candidate_id(self) -> None:
        proposal = _proposal(rejected=[{"reason_code": "duplicate", "reason": "사유"}])
        self._assert_rejected(proposal, "missing candidate_id")

    def test_duplicate_candidate_id_across_decisions_rejected(self) -> None:
        rule_text = "중복 검증 규칙."
        proposal = _proposal(
            rules=[_rule(rule_text, ["pc-1"])],
            rejected=[_rejection("pc-1"), _rejection("pc-2")],
            contract=BASE_CONTRACT + f"- {rule_text}\n",
        )
        self._assert_rejected(proposal, "appear more than once")
        self._assert_rejected(proposal, "pc-1")

    def test_unknown_candidate_id_rejected(self) -> None:
        proposal = _proposal(rejected=[_rejection("pc-1"), _rejection("pc-2"), _rejection("pc-9")])
        self._assert_rejected(proposal, "unknown candidate ids")
        self._assert_rejected(proposal, "pc-9")

    def test_undecided_pending_candidate_rejected(self) -> None:
        proposal = _proposal(rejected=[_rejection("pc-1")])
        self._assert_rejected(proposal, "did not decide candidate ids")
        self._assert_rejected(proposal, "pc-2")

    def test_rules_with_empty_contract_markdown_rejected(self) -> None:
        proposal = _proposal(
            rules=[_rule("규칙 문장.", ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract="",
        )
        self._assert_rejected(proposal, "project_contract_markdown is empty")

    def test_contract_must_start_with_project_contract_header(self) -> None:
        rule_text = "헤더 검증 규칙."
        proposal = _proposal(
            rules=[_rule(rule_text, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=f"## Rules\n- {rule_text}\n",
        )
        self._assert_rejected(proposal, "must start with '# Project Contract'")

    def test_approved_rule_text_must_appear_in_contract(self) -> None:
        proposal = _proposal(
            rules=[_rule("계약에 없는 규칙 문장.", ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=BASE_CONTRACT,
        )
        self._assert_rejected(proposal, "does not contain proposed_rules[1].rule_text")

    def test_empty_markdown_with_no_rules_falls_back_to_current_contract(self) -> None:
        proposal = _proposal(rejected=[_rejection("pc-1"), _rejection("pc-2")], contract="")
        pc_review.validate_batch_proposal(proposal, self.pending, self.contract)
        self.assertEqual(proposal["project_contract_markdown"], self.contract.rstrip() + "\n")

    def test_empty_markdown_no_rules_empty_current_contract_uses_default_header(self) -> None:
        proposal = _proposal(rejected=[_rejection("pc-1"), _rejection("pc-2")], contract="")
        pc_review.validate_batch_proposal(proposal, self.pending, "")
        self.assertEqual(proposal["project_contract_markdown"], "# Project Contract\n")

    def test_duplicate_rule_text_rejected(self) -> None:
        rule_text = "동일한 규칙 문장."
        proposal = _proposal(
            rules=[_rule(rule_text, ["pc-1"]), _rule(rule_text, ["pc-2"])],
            contract=BASE_CONTRACT + f"- {rule_text}\n",
        )
        self._assert_rejected(proposal, "duplicates an earlier rule_text")

    def test_rule_text_must_be_its_own_line_not_substring(self) -> None:
        # A rule_text appearing only as a fragment of a longer line was never
        # actually added as a rule; the validator must reject it.
        rule_text = "짧은 규칙"
        proposal = _proposal(
            rules=[_rule(rule_text, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=BASE_CONTRACT + "- 짧은 규칙이라는 표현이 들어간 다른 문장.\n",
        )
        self._assert_rejected(proposal, "as its own line")

    def test_contract_must_retain_existing_rules(self) -> None:
        rule_text = "새 규칙."
        proposal = _proposal(
            rules=[_rule(rule_text, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=f"# Project Contract\n\n- {rule_text}\n",  # drops 기존 규칙
        )
        self._assert_rejected(proposal, "append-only")

    def test_contract_retention_allows_pure_additions(self) -> None:
        rule_text = "기존 내용을 유지한 채 추가만 한다."
        proposal = _proposal(
            rules=[_rule(rule_text, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=BASE_CONTRACT + f"\n## Process\n- {rule_text}\n",
        )
        pc_review.validate_batch_proposal(proposal, self.pending, self.contract)


# --------------------------------------------------------------------------- #
# Snapshot / change detection / restore helpers
# --------------------------------------------------------------------------- #
class SnapshotRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-review-snap-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_modified_file_detected_and_restored(self) -> None:
        path = self._file("contract.md", "original\n")
        snapshot = pc_review._snapshot([path])
        path.write_text("tampered\n", encoding="utf-8")
        self.assertEqual(pc_review._changed(snapshot), [path])
        pc_review._restore(snapshot)
        self.assertEqual(path.read_text(encoding="utf-8"), "original\n")
        self.assertEqual(pc_review._changed(snapshot), [])

    def test_deleted_file_detected_and_restored(self) -> None:
        path = self._file("store.json", "{\"candidates\": []}\n")
        snapshot = pc_review._snapshot([path])
        path.unlink()
        self.assertEqual(pc_review._changed(snapshot), [path])
        pc_review._restore(snapshot)
        self.assertEqual(path.read_text(encoding="utf-8"), "{\"candidates\": []}\n")

    def test_identical_content_rewrite_is_not_detected(self) -> None:
        # NOTE: change detection compares file CONTENT, by design. Rewriting a
        # protected file with byte-identical content (touching mtime only) is
        # intentionally not flagged as a modification.
        path = self._file("contract.md", "same\n")
        snapshot = pc_review._snapshot([path])
        path.write_text("same\n", encoding="utf-8")
        self.assertEqual(pc_review._changed(snapshot), [])

    def test_missing_file_snapshots_as_empty_and_creation_is_detected(self) -> None:
        missing = self.tmp / "not-yet.md"
        self.assertEqual(pc_review._read_text(missing), "")
        snapshot = pc_review._snapshot([missing])
        self.assertEqual(snapshot[missing], "")
        # File created during the "read-only" review is detected as a change.
        missing.write_text("agent wrote this\n", encoding="utf-8")
        self.assertEqual(pc_review._changed(snapshot), [missing])
        # NOTE: _restore writes the snapshot text back, so a path that was
        # missing pre-review is materialized as an EMPTY file rather than being
        # deleted. In practice main() calls ensure_pc_files() before
        # snapshotting, so protected paths always exist; not asserted as the
        # desired contract for truly-missing paths.


# --------------------------------------------------------------------------- #
# proposal_*_candidate_ids extraction
# --------------------------------------------------------------------------- #
class ProposalIdExtractionTests(unittest.TestCase):
    def test_approved_ids_collected_from_rules(self) -> None:
        proposal = _proposal(rules=[_rule("a", ["pc-1", "pc-2"]), _rule("b", ["pc-3"]), "garbage"])
        self.assertEqual(pc_review.proposal_approved_candidate_ids(proposal), {"pc-1", "pc-2", "pc-3"})

    def test_rejected_ids_collected_and_blank_skipped(self) -> None:
        proposal = _proposal(rejected=[_rejection("pc-4"), {"candidate_id": "  "}, "garbage"])
        self.assertEqual(pc_review.proposal_rejected_candidate_ids(proposal), {"pc-4"})

    def test_empty_proposal_yields_empty_sets(self) -> None:
        self.assertEqual(pc_review.proposal_approved_candidate_ids({}), set())
        self.assertEqual(pc_review.proposal_rejected_candidate_ids({}), set())


# --------------------------------------------------------------------------- #
# Candidate store decision updates (temp-dir isolated)
# --------------------------------------------------------------------------- #
class UpdateCandidateDecisionsTests(IsolatedPcReviewTest):
    def test_decisions_update_status_reason_and_timestamp(self) -> None:
        self.seed_store([_candidate("pc-1"), _candidate("pc-2")])
        pc_review.update_candidate_decisions(
            {"pc-1": harness.PC_APPROVED_STATUS, "pc-2": harness.PC_REJECTED_STATUS},
            {"pc-1": "approve reason", "pc-2": "reject reason"},
        )
        store = harness.read_pc_candidates_store()
        by_id = {item["id"]: item for item in store["candidates"]}
        self.assertEqual(by_id["pc-1"]["status"], harness.PC_APPROVED_STATUS)
        self.assertEqual(by_id["pc-1"]["decision_reason"], "approve reason")
        self.assertTrue(by_id["pc-1"]["decided_at"])
        self.assertEqual(by_id["pc-2"]["status"], harness.PC_REJECTED_STATUS)
        self.assertEqual(by_id["pc-2"]["decision_reason"], "reject reason")

    def test_untouched_candidates_keep_their_status(self) -> None:
        self.seed_store([_candidate("pc-1"), _candidate("pc-2")])
        pc_review.update_candidate_decisions({"pc-1": harness.PC_APPROVED_STATUS}, {})
        self.assertEqual(self.statuses()["pc-2"], harness.PC_PENDING_STATUS)

    def test_unsupported_status_rejected(self) -> None:
        self.seed_store([_candidate("pc-1")])
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.update_candidate_decisions({"pc-1": "보류"}, {})
        self.assertIn("Unsupported PC decision status", str(ctx.exception))

    def test_unknown_candidate_id_rejected(self) -> None:
        self.seed_store([_candidate("pc-1")])
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.update_candidate_decisions({"pc-404": harness.PC_APPROVED_STATUS}, {})
        self.assertIn("PC candidate not found", str(ctx.exception))
        self.assertIn("pc-404", str(ctx.exception))


class RejectAllPendingTests(IsolatedPcReviewTest):
    def test_all_pending_marked_rejected_with_reason(self) -> None:
        pending = [_candidate("pc-1"), _candidate("pc-2")]
        self.seed_store(pending)
        pc_review.reject_all_pending(pending, "일괄 기각 사유")
        store = harness.read_pc_candidates_store()
        for item in store["candidates"]:
            self.assertEqual(item["status"], harness.PC_REJECTED_STATUS)
            self.assertEqual(item["decision_reason"], "일괄 기각 사유")
        self.assertEqual(harness.pending_pc_candidates(), [])


# --------------------------------------------------------------------------- #
# apply_accepted_proposal
# --------------------------------------------------------------------------- #
class ApplyAcceptedProposalTests(IsolatedPcReviewTest):
    def setUp(self) -> None:
        super().setUp()
        self.pending = [_candidate("pc-1"), _candidate("pc-2")]
        self.seed_store(self.pending)
        self.seed_contract(BASE_CONTRACT)
        self.rule_text = "새로 추가되는 프로젝트 규칙."
        self.new_contract = BASE_CONTRACT + f"- {self.rule_text}\n"
        self.proposal = _proposal(
            rules=[_rule(self.rule_text, ["pc-1"])],
            rejected=[_rejection("pc-2", reason_code="too_specific", reason="좁은 범위")],
            contract=self.new_contract,
        )

    def test_apply_updates_statuses_and_contract(self) -> None:
        pc_review.apply_accepted_proposal(self.proposal, self.pending, "codex")
        statuses = self.statuses()
        self.assertEqual(statuses["pc-1"], harness.PC_APPROVED_STATUS)
        self.assertEqual(statuses["pc-2"], harness.PC_REJECTED_STATUS)
        written = harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8")
        self.assertEqual(written, self.new_contract.rstrip() + "\n")
        # The pre-existing contract content survives (append-only is also
        # enforced upstream by validate_batch_proposal).
        self.assertIn("기존 규칙은 유지한다.", written)
        self.assertIn(self.rule_text, written)
        self.assertEqual(harness.pending_pc_candidates(), [])

    def test_decision_reasons_mention_agent_and_rule(self) -> None:
        pc_review.apply_accepted_proposal(self.proposal, self.pending, "codex")
        store = harness.read_pc_candidates_store()
        by_id = {item["id"]: item for item in store["candidates"]}
        self.assertIn("codex", by_id["pc-1"]["decision_reason"])
        self.assertIn(self.rule_text, by_id["pc-1"]["decision_reason"])
        self.assertIn("too_specific", by_id["pc-2"]["decision_reason"])

    def test_decision_mismatch_raises(self) -> None:
        proposal = _proposal(rejected=[_rejection("pc-1")], contract=BASE_CONTRACT)
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.apply_accepted_proposal(proposal, self.pending, "codex")
        self.assertIn("Internal decision mismatch", str(ctx.exception))
        self.assertIn("pc-2", str(ctx.exception))

    def test_decision_overlap_raises(self) -> None:
        proposal = _proposal(
            rules=[_rule(self.rule_text, ["pc-1"])],
            rejected=[_rejection("pc-1"), _rejection("pc-2")],
            contract=self.new_contract,
        )
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.apply_accepted_proposal(proposal, self.pending, "codex")
        self.assertIn("Internal decision overlap", str(ctx.exception))


# --------------------------------------------------------------------------- #
# validate_after_apply / ensure_pc_files
# --------------------------------------------------------------------------- #
class ValidateAfterApplyTests(IsolatedPcReviewTest):
    def test_invalid_status_detected(self) -> None:
        self.seed_store([_candidate("pc-1", status="이상한값")])
        self.seed_contract()
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.validate_after_apply()
        self.assertIn("Invalid PC candidate status after apply", str(ctx.exception))
        self.assertIn("pc-1", str(ctx.exception))

    def test_missing_contract_detected(self) -> None:
        self.seed_store([_candidate("pc-1", status=harness.PC_APPROVED_STATUS)])
        with self.assertRaises(harness.HarnessError) as ctx:
            pc_review.validate_after_apply()
        self.assertIn("Project contract file is missing after apply", str(ctx.exception))

    def test_returns_remaining_pending_candidates(self) -> None:
        self.seed_store([_candidate("pc-1", status=harness.PC_APPROVED_STATUS), _candidate("pc-2")])
        self.seed_contract()
        remaining = pc_review.validate_after_apply()
        self.assertEqual([item["id"] for item in remaining], ["pc-2"])


class EnsurePcFilesTests(IsolatedPcReviewTest):
    def test_creates_missing_store_and_contract(self) -> None:
        self.assertFalse(harness.PC_CANDIDATES_PATH.exists())
        self.assertFalse(harness.PROJECT_CONTRACT_PATH.exists())
        pc_review.ensure_pc_files()
        store = harness.read_pc_candidates_store()
        self.assertEqual(store["candidates"], [])
        contract = harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8")
        self.assertTrue(contract.startswith(CONTRACT_HEADER))

    def test_preserves_existing_files(self) -> None:
        self.seed_store([_candidate("pc-1")])
        self.seed_contract("# Project Contract\n\n- 사용자 규칙\n")
        pc_review.ensure_pc_files()
        self.assertEqual(self.statuses(), {"pc-1": harness.PC_PENDING_STATUS})
        self.assertIn("사용자 규칙", harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# display_batch_proposal (smoke: structure, not exact wording)
# --------------------------------------------------------------------------- #
class DisplayBatchProposalTests(unittest.TestCase):
    def test_display_lists_rules_and_rejections(self) -> None:
        pending = [_candidate("pc-1"), _candidate("pc-2", rule_candidate="기각될 후보 문장")]
        proposal = _proposal(
            rules=[_rule("표시할 규칙.", ["pc-1"])],
            rejected=[_rejection("pc-2", reason_code="duplicate", reason="중복임")],
        )
        out = io.StringIO()
        with redirect_stdout(out):
            pc_review.display_batch_proposal(proposal, pending)
        text = out.getvalue()
        self.assertIn("표시할 규칙.", text)
        self.assertIn("pc-1", text)
        self.assertIn("pc-2", text)
        self.assertIn("duplicate", text)
        self.assertIn("기각될 후보 문장", text)


# --------------------------------------------------------------------------- #
# main() end-to-end with a fake reviewer agent (offline, no provider CLI)
# --------------------------------------------------------------------------- #
class MainFlowTests(IsolatedPcReviewTest):
    RULE_TEXT = "메인 흐름에서 추가되는 규칙."

    def setUp(self) -> None:
        super().setUp()
        self.seed_store([_candidate("pc-1"), _candidate("pc-2")])
        self.seed_contract(BASE_CONTRACT)
        self.new_contract = BASE_CONTRACT + f"- {self.RULE_TEXT}\n"
        self.proposal = _proposal(
            rules=[_rule(self.RULE_TEXT, ["pc-1"])],
            rejected=[_rejection("pc-2")],
            contract=self.new_contract,
        )

    def _fake_run_agent(self, proposal: dict[str, Any]):
        def fake(agent: str, prompt: str, prefix: str, label: str) -> dict[str, Any]:
            return {"stdout_text": json.dumps(proposal, ensure_ascii=False), "returncode": 0}

        return fake

    def _failing_run_agent(self):
        def fake(agent: str, prompt: str, prefix: str, label: str) -> dict[str, Any]:
            raise AssertionError("run_agent must not be called in this scenario")

        return fake

    def _run_main(self, argv: list[str]) -> int:
        with redirect_stdout(io.StringIO()):
            return pc_review.main(argv)

    def test_no_pending_candidates_returns_zero_without_review(self) -> None:
        self.seed_store([])
        with mock.patch.object(pc_review, "run_agent", self._failing_run_agent()):
            self.assertEqual(self._run_main(["--yes"]), 0)

    def test_yes_mode_applies_proposal_end_to_end(self) -> None:
        with mock.patch.object(pc_review, "run_agent", self._fake_run_agent(self.proposal)):
            self.assertEqual(self._run_main(["--yes"]), 0)
        statuses = self.statuses()
        self.assertEqual(statuses["pc-1"], harness.PC_APPROVED_STATUS)
        self.assertEqual(statuses["pc-2"], harness.PC_REJECTED_STATUS)
        self.assertEqual(
            harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8"),
            self.new_contract.rstrip() + "\n",
        )
        self.assertEqual(harness.pending_pc_candidates(), [])

    def test_yes_mode_rerun_after_apply_is_noop(self) -> None:
        # First run decides every pending candidate; a re-run finds no pending
        # candidates, returns 0 immediately, and never invokes the reviewer.
        with mock.patch.object(pc_review, "run_agent", self._fake_run_agent(self.proposal)):
            self.assertEqual(self._run_main(["--yes"]), 0)
        contract_after_first = harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8")
        store_after_first = harness.PC_CANDIDATES_PATH.read_text(encoding="utf-8")
        with mock.patch.object(pc_review, "run_agent", self._failing_run_agent()):
            self.assertEqual(self._run_main(["--yes"]), 0)
        self.assertEqual(harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8"), contract_after_first)
        self.assertEqual(harness.PC_CANDIDATES_PATH.read_text(encoding="utf-8"), store_after_first)

    def test_files_modified_during_review_are_restored_and_error_raised(self) -> None:
        original_contract = harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8")
        original_store = harness.PC_CANDIDATES_PATH.read_text(encoding="utf-8")

        def tampering_agent(agent: str, prompt: str, prefix: str, label: str) -> dict[str, Any]:
            harness.PROJECT_CONTRACT_PATH.write_text("# hacked\n", encoding="utf-8")
            harness.PC_CANDIDATES_PATH.write_text("{}", encoding="utf-8")
            return {"stdout_text": json.dumps(self.proposal, ensure_ascii=False)}

        with mock.patch.object(pc_review, "run_agent", tampering_agent):
            with self.assertRaises(harness.HarnessError) as ctx:
                self._run_main(["--yes"])
        self.assertIn("modified files during the read-only batch review", str(ctx.exception))
        self.assertEqual(harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8"), original_contract)
        self.assertEqual(harness.PC_CANDIDATES_PATH.read_text(encoding="utf-8"), original_store)
        # Candidates are untouched: still pending.
        self.assertEqual(
            self.statuses(),
            {"pc-1": harness.PC_PENDING_STATUS, "pc-2": harness.PC_PENDING_STATUS},
        )

    def test_apply_failure_rolls_back_contract_and_store(self) -> None:
        original_contract = harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8")
        original_store = harness.PC_CANDIDATES_PATH.read_text(encoding="utf-8")

        def exploding_write(store: dict[str, Any]) -> None:
            raise RuntimeError("disk on fire")

        # apply_accepted_proposal writes the contract BEFORE updating the
        # candidate store; failing the store write proves the pre-apply
        # snapshot restores the already-mutated contract too.
        with mock.patch.object(pc_review, "run_agent", self._fake_run_agent(self.proposal)):
            with mock.patch.object(harness, "write_pc_candidates_store", exploding_write):
                with self.assertRaises(RuntimeError):
                    self._run_main(["--yes"])
        self.assertEqual(harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8"), original_contract)
        self.assertEqual(harness.PC_CANDIDATES_PATH.read_text(encoding="utf-8"), original_store)
        self.assertEqual(
            self.statuses(),
            {"pc-1": harness.PC_PENDING_STATUS, "pc-2": harness.PC_PENDING_STATUS},
        )

    def test_interactive_no_rejects_all_pending_and_keeps_contract(self) -> None:
        original_contract = harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8")
        with mock.patch.object(pc_review, "run_agent", self._fake_run_agent(self.proposal)):
            with mock.patch.object(pc_review, "ask_yes_no", lambda prompt: False):
                self.assertEqual(self._run_main([]), 0)
        statuses = self.statuses()
        self.assertEqual(statuses["pc-1"], harness.PC_REJECTED_STATUS)
        self.assertEqual(statuses["pc-2"], harness.PC_REJECTED_STATUS)
        self.assertEqual(harness.PROJECT_CONTRACT_PATH.read_text(encoding="utf-8"), original_contract)

    def test_invalid_proposal_from_agent_fails_before_apply(self) -> None:
        # Reviewer decides only pc-1; the strict validator must fail the run
        # and leave both candidates pending and the contract untouched.
        bad = _proposal(rejected=[_rejection("pc-1")], contract=BASE_CONTRACT)
        with mock.patch.object(pc_review, "run_agent", self._fake_run_agent(bad)):
            with self.assertRaises(harness.HarnessError) as ctx:
                self._run_main(["--yes"])
        self.assertIn("did not decide candidate ids", str(ctx.exception))
        self.assertEqual(
            self.statuses(),
            {"pc-1": harness.PC_PENDING_STATUS, "pc-2": harness.PC_PENDING_STATUS},
        )


if __name__ == "__main__":
    unittest.main()
