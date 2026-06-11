from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from support import ensure_ai_path

ensure_ai_path()

import orchestrate  # noqa: E402
from harness_core.json_io import read_json_value_file  # noqa: E402


class ClassifyReasonTests(unittest.TestCase):
    def test_verify_limit_is_manual(self) -> None:
        reason = "Verify/Fix retry limit reached (3/3). Resume with a higher value."
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_MANUAL)

    def test_needs_user_is_manual(self) -> None:
        self.assertEqual(
            orchestrate.classify_reason("Stage requested user input."),
            orchestrate.CAT_MANUAL,
        )

    def test_policy_violation_is_manual(self) -> None:
        self.assertEqual(
            orchestrate.classify_reason("Write policy violation: src/x.py edited in review"),
            orchestrate.CAT_MANUAL,
        )

    def test_new_run_guard_is_manual(self) -> None:
        self.assertEqual(
            orchestrate.classify_reason("새 파이프라인을 시작할 수 없습니다."),
            orchestrate.CAT_MANUAL,
        )

    def test_human_gate_is_gate(self) -> None:
        self.assertEqual(
            orchestrate.classify_reason("Human gate approval required."),
            orchestrate.CAT_GATE,
        )

    def test_provider_exit_is_transient(self) -> None:
        reason = "Provider codex exited with code 1 while running stage 02_develop. Inspect logs: ..."
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_TRANSIENT)

    def test_provider_timeout_is_transient(self) -> None:
        reason = "Provider claude timed out after 3600 seconds while running stage 05_verify."
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_TRANSIENT)

    def test_no_output_is_transient(self) -> None:
        reason = (
            "Provider agy exited with code 0 but produced no stdout, no stderr, "
            "and no required outputs while running stage 03_review."
        )
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_TRANSIENT)

    def test_unknown_reason_is_unknown(self) -> None:
        self.assertEqual(
            orchestrate.classify_reason("Invalid or missing status in 02_dev.md"),
            orchestrate.CAT_UNKNOWN,
        )

    def test_manual_wins_over_transient_when_both_present(self) -> None:
        # A verify-limit block whose text also mentions an exit code must stay manual.
        reason = "Verify/Fix retry limit reached (3/3). last provider exited with code 1."
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_MANUAL)

    def test_spend_limit_is_rate_limit(self) -> None:
        reason = "You've hit your monthly spend limit · raise it at claude.ai/settings/usage"
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_RATE_LIMIT)

    def test_rate_limit_wins_over_transient_when_both_present(self) -> None:
        # The real-world block: generic exit text in reason, the limit in stdout.
        reason = "Provider claude exited with code 1. You've hit your monthly spend limit."
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_RATE_LIMIT)

    def test_quota_and_429_are_rate_limit(self) -> None:
        self.assertEqual(orchestrate.classify_reason("HTTP 429 Too Many Requests"), orchestrate.CAT_RATE_LIMIT)
        self.assertEqual(orchestrate.classify_reason("quota exceeded for this period"), orchestrate.CAT_RATE_LIMIT)

    def test_verify_limit_still_manual_not_rate_limit(self) -> None:
        # "retry limit reached" must stay manual even though "limit" is limit-ish.
        self.assertEqual(
            orchestrate.classify_reason("Verify/Fix retry limit reached (3/3)."),
            orchestrate.CAT_MANUAL,
        )

    def test_login_failure_is_auth(self) -> None:
        self.assertEqual(orchestrate.classify_reason("Not logged in. Please run /login"), orchestrate.CAT_AUTH)

    def test_invalid_api_key_is_auth(self) -> None:
        self.assertEqual(orchestrate.classify_reason("401 Unauthorized: invalid API key"), orchestrate.CAT_AUTH)

    def test_auth_wins_over_transient(self) -> None:
        # The real shape: generic exit text, with the auth cause in the same blob.
        reason = "Provider claude exited with code 1. Authentication failed; please log in."
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_AUTH)

    def test_credit_balance_is_auth_not_rate_limit(self) -> None:
        # An empty balance needs a human top-up; it does NOT reset on a time window,
        # so it must escalate (auth), never wait like a rate limit.
        self.assertEqual(
            orchestrate.classify_reason("Your credit balance is too low to run this request."),
            orchestrate.CAT_AUTH,
        )

    def test_spend_limit_stays_rate_limit_not_auth(self) -> None:
        # A spend/usage *limit* is time-windowed and self-heals -> still rate_limit.
        self.assertEqual(
            orchestrate.classify_reason("You've hit your monthly spend limit"),
            orchestrate.CAT_RATE_LIMIT,
        )

    def test_codex_usage_limit_is_rate_limit(self) -> None:
        # The exact codex usage-limit error. "purchase more credits" must NOT trip
        # auth/manual ("add credits" != "more credits"); "usage limit" -> rate_limit.
        reason = (
            "ERROR: You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
            "to purchase more credits or try again at Jun 11th, 2026 9:37 AM."
        )
        self.assertEqual(orchestrate.classify_reason(reason), orchestrate.CAT_RATE_LIMIT)


class ClassifyOutcomeTests(unittest.TestCase):
    def test_complete_run_json_is_success(self) -> None:
        category, _ = orchestrate.classify_outcome({"status": "complete"}, "")
        self.assertEqual(category, orchestrate.CAT_SUCCESS)

    def test_blocked_uses_reason(self) -> None:
        run_json = {"status": "blocked", "blocked": {"reason": "Provider codex exited with code 1."}}
        category, reason = orchestrate.classify_outcome(run_json, "")
        self.assertEqual(category, orchestrate.CAT_TRANSIENT)
        self.assertIn("exited with code", reason)

    def test_missing_run_json_falls_back_to_stderr(self) -> None:
        category, reason = orchestrate.classify_outcome(None, "새 파이프라인을 시작할 수 없습니다.")
        self.assertEqual(category, orchestrate.CAT_MANUAL)
        self.assertIn("파이프라인", reason)

    def test_missing_run_json_empty_stderr_is_unknown(self) -> None:
        category, _ = orchestrate.classify_outcome(None, "")
        self.assertEqual(category, orchestrate.CAT_UNKNOWN)

    def test_blocked_stdout_reveals_rate_limit(self) -> None:
        # blocked.reason is the generic exit message; the limit lives only in stdout.
        tmp = tempfile.mkdtemp(prefix="orch_test_")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        out = Path(tmp) / "01_develop_attempt1_claude.out.txt"
        out.write_text(
            "You've hit your monthly spend limit · raise it at claude.ai/settings/usage\n",
            encoding="utf-8",
        )
        run_json = {
            "status": "blocked",
            "blocked": {
                "reason": "Provider claude exited with code 1 while running stage 01_develop.",
                "stdout": str(out),
            },
        }
        category, _ = orchestrate.classify_outcome(run_json, "")
        self.assertEqual(category, orchestrate.CAT_RATE_LIMIT)

    def test_blocked_stderr_reveals_rate_limit(self) -> None:
        # codex writes the usage-limit line to STDERR, not stdout; the classifier
        # must peek at the stderr tail too or it misreads a limit as a flaky exit.
        tmp = tempfile.mkdtemp(prefix="orch_test_")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        err = Path(tmp) / "00_specify_attempt1_codex.err.txt"
        err.write_text(
            "ERROR: You've hit your usage limit. ... try again at Jun 11th, 2026 9:37 AM.\n",
            encoding="utf-8",
        )
        run_json = {
            "status": "blocked",
            "blocked": {
                "reason": "Provider codex exited with code 1 while running stage 00_specify.",
                "stdout": str(Path(tmp) / "absent.out.txt"),  # empty/absent stdout stream
                "stderr": str(err),
            },
        }
        category, _ = orchestrate.classify_outcome(run_json, "")
        self.assertEqual(category, orchestrate.CAT_RATE_LIMIT)


class EffectiveConfigTests(unittest.TestCase):
    def test_layered_override(self) -> None:
        batch = {"defaults": {"performance": "high", "max_attempts": 7}}
        run = {"feature": "f", "request": "do it", "performance": "lite", "state": {"status": "pending"}}
        eff = orchestrate.effective_config(batch, run)
        self.assertEqual(eff["performance"], "lite")   # run overrides batch.defaults
        self.assertEqual(eff["max_attempts"], 7)       # from batch.defaults
        self.assertEqual(eff["pipeline"], "standard")  # from hard defaults
        self.assertNotIn("state", eff)                 # state is never config


class ValidateBatchTests(unittest.TestCase):
    def test_duplicate_feature_rejected(self) -> None:
        batch = {
            "runs": [
                {"feature": "dup", "request": "a"},
                {"feature": "dup", "request": "b"},
            ]
        }
        with self.assertRaises(orchestrate.OrchestrateError):
            orchestrate.validate_batch(batch)

    def test_missing_request_rejected(self) -> None:
        batch = {"runs": [{"feature": "f"}]}
        with self.assertRaises(orchestrate.OrchestrateError):
            orchestrate.validate_batch(batch)

    def test_bad_pipeline_rejected(self) -> None:
        batch = {"runs": [{"feature": "f", "request": "x", "pipeline": "turbo"}]}
        with self.assertRaises(orchestrate.OrchestrateError):
            orchestrate.validate_batch(batch)

    def test_valid_batch_passes(self) -> None:
        batch = {"runs": [{"feature": "f", "request": "x", "pipeline": "full", "deep_thinking": True, "strategy": "max"}]}
        orchestrate.validate_batch(batch)  # should not raise


class BuildCommandTests(unittest.TestCase):
    def _eff(self, **overrides: object) -> dict:
        run = {"feature": "feat", "request": "build feat"}
        run.update(overrides)
        return orchestrate.effective_config({}, run)

    def test_start_standard_includes_flags(self) -> None:
        cmd = orchestrate.build_start_command(self._eff())
        self.assertIn("run", cmd)
        self.assertIn("--feature", cmd)
        self.assertIn("feat", cmd)
        self.assertIn("--yes", cmd)
        self.assertIn("--defaults", cmd)
        self.assertIn("--performance", cmd)
        self.assertIn("harness_standard.py", cmd[1])
        self.assertNotIn("--deep-thinking", cmd)

    def test_start_full_deep_thinking(self) -> None:
        cmd = orchestrate.build_start_command(self._eff(pipeline="full", deep_thinking=True, strategy="max", performance="high"))
        self.assertIn("--deep-thinking", cmd)
        self.assertIn("--strategy", cmd)
        self.assertIn("max", cmd)
        self.assertIn("harness.py", cmd[1])

    def test_deep_thinking_ignored_when_not_full(self) -> None:
        cmd = orchestrate.build_start_command(self._eff(pipeline="fast", deep_thinking=True, strategy="max"))
        self.assertNotIn("--deep-thinking", cmd)

    def test_interactive_mode_flag(self) -> None:
        cmd = orchestrate.build_start_command(self._eff(decision_mode="interactive"))
        self.assertIn("--interactive", cmd)
        self.assertNotIn("--defaults", cmd)

    def test_retry_command_is_auto_yes(self) -> None:
        cmd = orchestrate.build_retry_command(self._eff())
        self.assertIn("retry", cmd)
        self.assertIn("--auto", cmd)
        self.assertIn("--yes", cmd)
        self.assertIn("feat", cmd)


class StateTransitionTests(unittest.TestCase):
    def test_transient_under_budget_waits(self) -> None:
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 1}}
        eff = orchestrate.effective_config({}, run)
        orchestrate.apply_policy(run, orchestrate.CAT_TRANSIENT, "exited with code 1", eff, {})
        state = run["state"]
        self.assertEqual(state["status"], orchestrate.ST_WAITING_RETRY)
        self.assertTrue(state["next_retry_at"])

    def test_transient_at_budget_fails(self) -> None:
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 3}}
        eff = orchestrate.effective_config({}, run)  # max_attempts default 3
        orchestrate.apply_policy(run, orchestrate.CAT_TRANSIENT, "exited with code 1", eff, {})
        self.assertEqual(run["state"]["status"], orchestrate.ST_FAILED)

    def test_unknown_budget_is_two(self) -> None:
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 2}}
        eff = orchestrate.effective_config({}, run)  # max_attempts default 3, unknown cap 2
        orchestrate.apply_policy(run, orchestrate.CAT_UNKNOWN, "weird error", eff, {})
        self.assertEqual(run["state"]["status"], orchestrate.ST_FAILED)

    def test_auth_escalates_immediately_to_manual(self) -> None:
        # No retry budget consumed: a blocked login can't be fixed by waiting.
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 0}}
        eff = orchestrate.effective_config({}, run)
        orchestrate.apply_policy(run, orchestrate.CAT_AUTH, "401 unauthorized", eff, {})
        self.assertEqual(run["state"]["status"], orchestrate.ST_MANUAL)

    def test_mark_manual(self) -> None:
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 1}}
        orchestrate.mark_manual(run, "Verify/Fix retry limit reached (3/3).")
        self.assertEqual(run["state"]["status"], orchestrate.ST_MANUAL)

    def test_mark_success_merges_branch(self) -> None:
        seen = []

        def fake_merge(run_json):
            seen.append(run_json)
            return True, "merged"

        original = orchestrate.merge_run_branch
        orchestrate.merge_run_branch = fake_merge  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(orchestrate, "merge_run_branch", original))
        orig_meta = orchestrate._commit_run_metadata
        orchestrate._commit_run_metadata = lambda feature: None  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(orchestrate, "_commit_run_metadata", orig_meta))
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 1}}
        run_json = {
            "status": "complete",
            "current_stage": "05_verify",
            "base_branch": "main",
            "run_branch": "run/f",
        }
        orchestrate.mark_success(run, run_json)
        self.assertEqual(run["state"]["status"], orchestrate.ST_SUCCESS)
        self.assertTrue(run["state"]["merged"])
        self.assertEqual(run["state"]["stage"], "05_verify")
        self.assertEqual(seen, [run_json])

    def test_merge_run_branch_linear_falls_back_to_push(self) -> None:
        calls = []

        def fake_push():
            calls.append(True)
            return True, ""

        original = orchestrate.push_current_branch
        orchestrate.push_current_branch = fake_push  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(orchestrate, "push_current_branch", original))
        # run.json with no base/run branch -> linear run -> old push behavior.
        merged, _ = orchestrate.merge_run_branch({"status": "complete"})
        self.assertTrue(merged)
        self.assertEqual(calls, [True])

    def test_merge_run_branch_stops_on_conflict(self) -> None:
        git_calls = []

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_git(args, check=False):
            git_calls.append(args)
            return _Proc()

        orig_conf = orchestrate.merge_tree_has_conflicts
        orig_git = orchestrate._git
        orchestrate.merge_tree_has_conflicts = lambda base, branch: True  # type: ignore[assignment]
        orchestrate._git = fake_git  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(orchestrate, "merge_tree_has_conflicts", orig_conf))
        self.addCleanup(lambda: setattr(orchestrate, "_git", orig_git))
        merged, msg = orchestrate.merge_run_branch({"base_branch": "main", "run_branch": "run/f"})
        self.assertFalse(merged)
        # A predicted conflict short-circuits BEFORE any checkout/merge git call.
        self.assertEqual(git_calls, [])


class RateLimitPolicyTests(unittest.TestCase):
    def _run(self, **state: object) -> dict:
        base = {"status": "running", "attempts": 1}
        base.update(state)
        return {"feature": "f", "request": "x", "state": base}

    def test_first_hit_waits_and_stamps_window(self) -> None:
        run = self._run()
        eff = orchestrate.effective_config({}, run)
        orchestrate.apply_policy(run, orchestrate.CAT_RATE_LIMIT, "spend limit", eff, {})
        state = run["state"]
        self.assertEqual(state["status"], orchestrate.ST_WAITING_RETRY)
        self.assertTrue(state["rate_limit_since"])   # window start recorded
        self.assertTrue(state["next_retry_at"])

    def test_poll_is_free_and_does_not_consume_attempts(self) -> None:
        # execute_run pre-increments attempts before classifying; a limit poll must
        # roll that back so it never erodes the real (transient) retry budget.
        run = self._run(attempts=1)
        eff = orchestrate.effective_config({}, run)
        orchestrate.apply_policy(run, orchestrate.CAT_RATE_LIMIT, "spend limit", eff, {})
        self.assertEqual(run["state"]["attempts"], 0)

    def test_cooldown_is_five_minutes(self) -> None:
        run = self._run()
        eff = orchestrate.effective_config({}, run)
        orchestrate.apply_policy(run, orchestrate.CAT_RATE_LIMIT, "spend limit", eff, {})
        due = datetime.fromisoformat(run["state"]["next_retry_at"])
        delta = (due - datetime.now()).total_seconds()
        self.assertTrue(250 <= delta <= 360, f"expected ~300s, got {delta}")

    def test_no_attempt_cap_keeps_waiting_within_deadline(self) -> None:
        # 50 polls in, still within the 24h window -> still waiting, never failed.
        run = self._run(attempts=50, rate_limit_since=datetime.now().isoformat(timespec="seconds"))
        eff = orchestrate.effective_config({}, run)
        orchestrate.apply_policy(run, orchestrate.CAT_RATE_LIMIT, "spend limit", eff, {})
        self.assertEqual(run["state"]["status"], orchestrate.ST_WAITING_RETRY)

    def test_past_deadline_escalates_to_manual(self) -> None:
        # Past the 24h default ceiling -> give up and escalate to a human.
        old = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        run = self._run(status="waiting_retry", rate_limit_since=old)
        eff = orchestrate.effective_config({}, run)
        orchestrate.apply_policy(run, orchestrate.CAT_RATE_LIMIT, "spend limit", eff, {})
        self.assertEqual(run["state"]["status"], orchestrate.ST_MANUAL)

    def test_batch_can_override_deadline(self) -> None:
        old = (datetime.now() - timedelta(minutes=20)).isoformat(timespec="seconds")
        run = self._run(status="waiting_retry", rate_limit_since=old)
        eff = orchestrate.effective_config({}, run)
        # Shrink the ceiling to 10 min -> 20 min in is already past it.
        orchestrate.apply_policy(
            run, orchestrate.CAT_RATE_LIMIT, "spend limit", eff, {"rate_limit_max_wait_seconds": 600}
        )
        self.assertEqual(run["state"]["status"], orchestrate.ST_MANUAL)


class PcReviewTests(unittest.TestCase):
    def _swap(self, name: str, fn: object) -> None:
        original = getattr(orchestrate, name)
        setattr(orchestrate, name, fn)
        self.addCleanup(lambda: setattr(orchestrate, name, original))

    def test_disabled_when_false(self) -> None:
        calls: list = []
        self._swap("invoke_harness", lambda cmd: calls.append(cmd) or (0, ""))
        orchestrate._run_pc_review({"pc_review": False}, "f")
        self.assertEqual(calls, [])

    def test_disabled_when_enabled_false(self) -> None:
        calls: list = []
        self._swap("invoke_harness", lambda cmd: calls.append(cmd) or (0, ""))
        orchestrate._run_pc_review({"pc_review": {"enabled": False}}, "f")
        self.assertEqual(calls, [])

    def test_runs_with_yes_and_commits_on_success(self) -> None:
        seen: dict = {}
        self._swap("invoke_harness", lambda cmd: seen.__setitem__("cmd", cmd) or (0, ""))
        self._swap("_commit_pc_review_changes", lambda feature: seen.__setitem__("committed", feature))
        orchestrate._run_pc_review({}, "feat-x")  # default: enabled
        self.assertIn("--yes", seen["cmd"])
        self.assertTrue(any("pc_review.py" in str(c) for c in seen["cmd"]))
        self.assertEqual(seen.get("committed"), "feat-x")

    def test_skips_commit_on_nonzero_exit(self) -> None:
        # Best-effort: a failed review must NOT commit and must NOT raise.
        committed: list = []
        self._swap("invoke_harness", lambda cmd: (1, "boom"))
        self._swap("_commit_pc_review_changes", lambda feature: committed.append(feature))
        orchestrate._run_pc_review({}, "f")
        self.assertEqual(committed, [])

    def test_uses_configured_agent(self) -> None:
        seen: dict = {}
        self._swap("invoke_harness", lambda cmd: seen.__setitem__("cmd", cmd) or (0, ""))
        self._swap("_commit_pc_review_changes", lambda feature: None)
        orchestrate._run_pc_review({"pc_review": {"agent": "claude"}}, "f")
        self.assertIn("--agent", seen["cmd"])
        self.assertIn("claude", seen["cmd"])

    def test_mark_success_runs_pc_review_with_batch(self) -> None:
        seen: list = []
        self._swap("push_current_branch", lambda: (True, ""))
        self._swap("_run_pc_review", lambda batch, feature: seen.append(feature))
        self._swap("_commit_run_metadata", lambda feature: None)
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 1}}
        orchestrate.mark_success(run, {"status": "complete"}, {"pc_review": True})
        self.assertEqual(seen, ["f"])

    def test_mark_success_skips_pc_review_without_batch(self) -> None:
        seen: list = []
        self._swap("push_current_branch", lambda: (True, ""))
        self._swap("_run_pc_review", lambda batch, feature: seen.append(feature))
        self._swap("_commit_run_metadata", lambda feature: None)
        run = {"feature": "f", "request": "x", "state": {"status": "running", "attempts": 1}}
        orchestrate.mark_success(run, {"status": "complete"})  # no batch -> no review
        self.assertEqual(seen, [])

    def test_mark_success_commits_run_metadata_after_pc_review_before_merge(self) -> None:
        # The run-meta commit must land on the run branch AFTER pc_review and
        # BEFORE the merge, so it rides into base. Mocked so the suite stays git-free.
        order: list = []
        self._swap("_run_pc_review", lambda batch, feature: order.append("pc_review"))
        self._swap("_commit_run_metadata", lambda feature: order.append(("run_meta", feature)))
        self._swap("merge_run_branch", lambda run_json: (order.append("merge"), (True, "merged"))[1])
        run = {"feature": "feat-x", "request": "x", "state": {"status": "running", "attempts": 1}}
        orchestrate.mark_success(run, {"status": "complete"}, {"pc_review": True})
        self.assertEqual(order, ["pc_review", ("run_meta", "feat-x"), "merge"])


class FrontlineAndStopLineTests(unittest.TestCase):
    def test_first_active_skips_success(self) -> None:
        batch = {
            "runs": [
                {"feature": "a", "request": "x", "state": {"status": "success"}},
                {"feature": "b", "request": "x", "state": {"status": "pending"}},
            ]
        }
        self.assertEqual(orchestrate.first_active_run(batch)["feature"], "b")

    def test_all_success_returns_none(self) -> None:
        batch = {
            "runs": [
                {"feature": "a", "request": "x", "state": {"status": "success"}},
                {"feature": "b", "request": "x", "state": {"status": "success"}},
            ]
        }
        self.assertIsNone(orchestrate.first_active_run(batch))


class SaveBatchMergeTests(unittest.TestCase):
    def _tmp_path(self) -> Path:
        tmp = tempfile.mkdtemp(prefix="orch_test_")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        return Path(tmp) / "batch.json"

    def test_save_only_updates_state_and_preserves_appended(self) -> None:
        path = self._tmp_path()
        # Disk starts with A, B.
        orchestrate._write_json_atomic(
            path,
            {
                "runs": [
                    {"feature": "a", "request": "ra", "performance": "high", "state": {"status": "pending"}},
                    {"feature": "b", "request": "rb", "state": {"status": "pending"}},
                ]
            },
        )
        mem = orchestrate.load_batch(path)
        orchestrate.run_state(mem["runs"][0])["status"] = "success"

        # User appends C on disk while we held the in-memory copy.
        disk = read_json_value_file(path)
        disk["runs"].append({"feature": "c", "request": "rc", "state": {"status": "pending"}})
        orchestrate._write_json_atomic(path, disk)

        orchestrate.save_batch(path, mem)

        final = read_json_value_file(path)
        features = [r["feature"] for r in final["runs"]]
        self.assertEqual(features, ["a", "b", "c"])           # appended C survived
        by_feature = {r["feature"]: r for r in final["runs"]}
        self.assertEqual(by_feature["a"]["state"]["status"], "success")  # our state applied
        self.assertEqual(by_feature["a"]["request"], "ra")              # input untouched
        self.assertEqual(by_feature["a"]["performance"], "high")
        self.assertEqual(by_feature["c"]["state"]["status"], "pending") # C untouched


if __name__ == "__main__":
    unittest.main()
