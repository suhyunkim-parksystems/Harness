"""Unit tests for harness_core/history.py.

history.py is the largest and most parse-heavy core module (project history
recording + Project Contract candidate extraction) and previously had no
dedicated unit test -- only indirect integration coverage. These tests exercise
its functions directly.

Strategy: every function in history.py already takes an explicit ``ctx`` first
argument (dependency injection), so no production code needs to change. We build
a lightweight HarnessContext via ``make_ctx`` that wires the *real* pure helpers
(text.py / policy.py / json_io.py / stage_runtime.py parsers) and points all
filesystem paths at a per-test temp directory, with deterministic stubs for
clock/colour/logging. That way the tests exercise the real normalization logic
rather than re-stubbed approximations.
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from support import ensure_ai_path

ensure_ai_path()

from harness_core import history  # noqa: E402
from harness_core import policy as policy_core  # noqa: E402
from harness_core import stage_runtime  # noqa: E402
from harness_core import text as text_core  # noqa: E402
from harness_core.context import HarnessContext  # noqa: E402
from harness_core.errors import HarnessError  # noqa: E402
from harness_core.json_io import read_json_file, write_json_file  # noqa: E402


# Mirror the shipping standard pipeline so the fake context matches reality.
STANDARD_STAGES = ("00_specify", "01_develop", "02_review", "03_fix", "04_verify")
STANDARD_STAGE_OUTPUTS = {
    "00_specify": "00_spec.md",
    "01_develop": "01_dev.md",
    "02_review": "02_review.md",
    "03_fix": "03_fix.md",
    "04_verify": "04_verify.md",
}


def make_ctx(
    root: Path,
    *,
    pipeline_mode: str = "standard",
    stages: tuple[str, ...] = STANDARD_STAGES,
    stage_outputs: dict[str, str] = STANDARD_STAGE_OUTPUTS,
    verify_stage: str = "04_verify",
    document_stage: Any = None,
    **overrides: Any,
) -> HarnessContext:
    """Build a HarnessContext faithful to harness.py but rooted at ``root``."""
    root = Path(root).resolve()
    project_dir = root / ".project"
    history_dir = project_dir / "history"
    features_dir = project_dir / "features"
    runs_dir = project_dir / "runs"

    def feature_dir(feature: str) -> Path:
        return features_dir / feature

    def run_dir(feature: str) -> Path:
        return runs_dir / feature

    def state_path(feature: str) -> Path:
        return run_dir(feature) / "run.json"

    def stage_output_path(feature: str, stage: str) -> Path:
        return feature_dir(feature) / stage_outputs[stage]

    def stage_result_json_path(feature: str, stage: str) -> Path:
        output = stage_output_path(feature, stage)
        return output.with_name(f"{output.stem}.result.json")

    def verification_dir(feature: str) -> Path:
        return run_dir(feature) / "verification"

    def latest_verification_result_path(feature: str) -> Path:
        return verification_dir(feature) / "latest.json"

    def expected_docx_path(feature: str) -> Path:
        return run_dir(feature) / f"{feature}.docx"

    def rel(path: Any) -> str:
        return Path(path).resolve().relative_to(root).as_posix()

    namespace: dict[str, Any] = {
        # --- constants (values mirror harness.py) ---
        "ROOT": root,
        "PROJECT_DIR": project_dir,
        "HISTORY_DIR": history_dir,
        "PC_CANDIDATES_PATH": history_dir / "pc_candidates.json",
        "PROJECT_CONTRACT_PATH": project_dir / "project_contract.md",
        "HISTORY_SCHEMA_VERSION": 1,
        "PC_CANDIDATES_SCHEMA_VERSION": 1,
        "PC_PENDING_STATUS": "미정",
        "PC_PROJECT_WIDE_SCOPE": "project_wide",
        "PC_REVIEW_STAGE": "pc_candidates",
        "PIPELINE_MODE": pipeline_mode,
        "STAGES": list(stages),
        "VERIFY_STAGE": verify_stage,
        "DOCUMENT_STAGE": document_stage,
        # --- real pure helpers (exercise the genuine logic) ---
        "compact_history_text": text_core.compact_history_text,
        "history_list": text_core.history_list,
        "history_object_list": text_core.history_object_list,
        "markdown_section_items": text_core.markdown_section_items,
        "norm_repo_path": text_core.norm_repo_path,
        "slugify": text_core.slugify,
        "is_test_path": policy_core.is_test_path,
        "is_production_code_path": policy_core.is_production_code_path,
        # stage_runtime parsers ignore ctx internally, so pass None.
        "parse_result_json_from_text": lambda text: stage_runtime.parse_result_json_from_text(None, text),
        "find_stage_result": lambda text: stage_runtime.find_stage_result(None, text),
        # --- real json io (BOM tolerant) ---
        "read_json_file": read_json_file,
        "write_json_file": write_json_file,
        # --- path builders ---
        "feature_dir": feature_dir,
        "run_dir": run_dir,
        "state_path": state_path,
        "stage_output_path": stage_output_path,
        "stage_result_json_path": stage_result_json_path,
        "verification_dir": verification_dir,
        "latest_verification_result_path": latest_verification_result_path,
        "expected_docx_path": expected_docx_path,
        "rel": rel,
        # --- deterministic stubs ---
        "iso_now": lambda: "2026-06-08T12:00:00",
        "now_stamp": lambda: "20260608-120000",
        "color_text": lambda text, *args, **kwargs: text,
        "log_event": lambda *args, **kwargs: None,
        "pipeline_extracts_pc_candidates": lambda mode: True,
    }
    namespace.update(overrides)
    return HarnessContext.from_namespace(namespace)


class HistoryTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ctx = make_ctx(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- fixture helpers ---
    def write_stage_result(self, feature: str, stage: str, data: dict[str, Any]) -> Path:
        path = self.ctx.stage_result_json_path(feature, stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(path, data)
        return path

    def write_stage_md(self, feature: str, stage: str, text: str) -> Path:
        path = self.ctx.stage_output_path(feature, stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_latest_verification(self, feature: str, data: dict[str, Any]) -> Path:
        path = self.ctx.latest_verification_result_path(feature)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(path, data)
        return path


class PcCandidateStoreTests(HistoryTestBase):
    def test_missing_store_returns_empty(self) -> None:
        store = history.read_pc_candidates_store(self.ctx)
        self.assertEqual(store, {"version": 1, "candidates": []})

    def test_round_trip_and_non_dict_items_filtered(self) -> None:
        history.write_pc_candidates_store(
            self.ctx, {"candidates": [{"id": "a"}, "garbage", 7, {"id": "b"}]}
        )
        store = history.read_pc_candidates_store(self.ctx)
        self.assertEqual([c["id"] for c in store["candidates"]], ["a", "b"])
        self.assertEqual(store["version"], 1)

    def test_invalid_json_raises(self) -> None:
        path = history.pc_candidates_path(self.ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(HarnessError):
            history.read_pc_candidates_store(self.ctx)

    def test_non_object_json_raises(self) -> None:
        path = history.pc_candidates_path(self.ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(HarnessError):
            history.read_pc_candidates_store(self.ctx)

    def test_candidates_not_list_raises(self) -> None:
        path = history.pc_candidates_path(self.ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"candidates": {}}', encoding="utf-8")
        with self.assertRaises(HarnessError):
            history.read_pc_candidates_store(self.ctx)

    def test_bom_tolerant_read(self) -> None:
        path = history.pc_candidates_path(self.ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write with an explicit UTF-8 BOM.
        path.write_text('﻿{"version": 1, "candidates": []}', encoding="utf-8")
        store = history.read_pc_candidates_store(self.ctx)
        self.assertEqual(store["candidates"], [])

    def test_write_coerces_non_list_candidates(self) -> None:
        history.write_pc_candidates_store(self.ctx, {"candidates": "nope"})
        store = history.read_pc_candidates_store(self.ctx)
        self.assertEqual(store["candidates"], [])

    def test_pending_filters_by_status(self) -> None:
        history.write_pc_candidates_store(
            self.ctx,
            {
                "candidates": [
                    {"id": "a", "status": "미정"},
                    {"id": "b", "status": "승인"},
                    {"id": "c", "status": "미정"},
                ]
            },
        )
        pending = history.pending_pc_candidates(self.ctx)
        self.assertEqual({c["id"] for c in pending}, {"a", "c"})

    def test_warn_pending_does_not_raise(self) -> None:
        history.write_pc_candidates_store(
            self.ctx, {"candidates": [{"id": "a", "status": "미정", "rule_candidate": "규칙"}]}
        )
        with contextlib.redirect_stderr(io.StringIO()):
            history.warn_pending_pc_candidates_for_new_run(self.ctx)  # must not raise

    def test_warn_pending_noop_when_empty(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            history.warn_pending_pc_candidates_for_new_run(self.ctx)
        self.assertEqual(err.getvalue(), "")


class HistoryIndexTests(HistoryTestBase):
    def test_missing_index_returns_default(self) -> None:
        self.assertEqual(
            history.read_history_index(self.ctx),
            {"schema_version": 1, "features": []},
        )

    def test_malformed_features_coerced(self) -> None:
        write_json_file(history.history_index_path(self.ctx), {"features": "x", "schema_version": 99})
        index = history.read_history_index(self.ctx)
        self.assertEqual(index["features"], [])
        self.assertEqual(index["schema_version"], 1)  # forced to ctx value

    def test_non_dict_feature_entries_filtered(self) -> None:
        write_json_file(
            history.history_index_path(self.ctx),
            {"features": [{"feature": "a"}, "bad", 5]},
        )
        index = history.read_history_index(self.ctx)
        self.assertEqual(index["features"], [{"feature": "a"}])

    def test_upsert_insert_then_replace_and_sort(self) -> None:
        _, inserted = history.upsert_history_index_entry(
            self.ctx, {"feature": "a", "completed_at": "2026-06-08T10:00:00"}
        )
        self.assertTrue(inserted)
        _, inserted = history.upsert_history_index_entry(
            self.ctx, {"feature": "b", "completed_at": "2026-06-08T12:00:00"}
        )
        self.assertTrue(inserted)
        index, inserted = history.upsert_history_index_entry(
            self.ctx, {"feature": "a", "completed_at": "2026-06-08T13:00:00"}
        )
        self.assertFalse(inserted)  # replaced existing "a"
        features = index["features"]
        self.assertEqual(len(features), 2)
        # Sorted by completed_at desc: a(13:00) then b(12:00).
        self.assertEqual([f["feature"] for f in features], ["a", "b"])


class IdAndTimestampTests(HistoryTestBase):
    def test_stable_history_id_deterministic(self) -> None:
        a = history.stable_history_id(self.ctx, "pc", "demo", "naming", "규칙 A")
        b = history.stable_history_id(self.ctx, "pc", "demo", "naming", "규칙 A")
        c = history.stable_history_id(self.ctx, "pc", "demo", "naming", "규칙 B")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertRegex(a, r"^pc-[0-9a-f]{12}$")

    def test_timestamp_id_strips_non_digits(self) -> None:
        self.assertEqual(
            history.history_timestamp_id(self.ctx, "2026-06-08T12:00:00"),
            "20260608120000",
        )

    def test_timestamp_id_falls_back_to_now(self) -> None:
        self.assertEqual(history.history_timestamp_id(self.ctx, None), "20260608120000")
        self.assertEqual(history.history_timestamp_id(self.ctx, ""), "20260608120000")

    def test_event_id_format(self) -> None:
        state = {
            "feature_name": "My Feature",
            "pipeline_mode": "standard",
            "created_at": "2026-06-08T10:30:00",
        }
        self.assertEqual(
            history.history_event_id(self.ctx, state),
            "20260608103000-my-feature-standard",
        )


class ChangedFilesBucketingTests(HistoryTestBase):
    def test_split_event_paths(self) -> None:
        self.assertEqual(
            history.split_event_paths(self.ctx, ["a\\b", "c", ""]),
            ["a/b", "c"],
        )
        self.assertEqual(
            history.split_event_paths(self.ctx, "a, b ,c"),
            ["a", "b", "c"],
        )
        self.assertEqual(history.split_event_paths(self.ctx, 123), [])

    def test_bucketing(self) -> None:
        stage_results = {
            "01_develop": {
                "changed_files": ["src/app.py", "tests/test_app.py"],
                "produced_files": [".project/features/demo/01_dev.md", ".project/docs/guide.md"],
            }
        }
        state = {
            "events": [
                {"event": "commit_created", "paths": ["README.md", ".ai/harness.py"]},
                {"event": "noise", "paths": ["should_not_appear.py"]},
            ]
        }
        grouped = history.collect_history_changed_files(self.ctx, state, stage_results)
        self.assertEqual(grouped["production"], ["src/app.py"])
        self.assertEqual(grouped["tests"], ["tests/test_app.py"])
        self.assertEqual(grouped["docs"], [".project/docs/guide.md"])
        self.assertEqual(
            grouped["harness_artifacts"],
            [".ai/harness.py", ".project/features/demo/01_dev.md"],
        )
        self.assertEqual(grouped["other"], ["README.md"])
        self.assertNotIn("should_not_appear.py", str(grouped))


class UnresolvedItemsTests(HistoryTestBase):
    def test_normalize_dict_key_precedence(self) -> None:
        out = history.normalize_unresolved_source_item(
            self.ctx,
            {"finding": "보안 취약점", "severity": "high", "reason": "시간 부족"},
            item_type="review_finding",
            status="open",
            disposition="not_actioned",
            source_stage="02_review",
            source_artifact="a.md",
        )
        assert out is not None
        self.assertEqual(out["title"], "보안 취약점")
        self.assertEqual(out["severity"], "high")
        self.assertEqual(out["reason_not_actioned"], "시간 부족")
        self.assertEqual(out["type"], "review_finding")

    def test_normalize_string_uses_default_severity(self) -> None:
        out = history.normalize_unresolved_source_item(
            self.ctx,
            "단순 경고",
            item_type="warning",
            status="open",
            disposition="warning_only",
            source_stage="s",
            source_artifact="",
        )
        assert out is not None
        self.assertEqual(out["title"], "단순 경고")
        self.assertEqual(out["severity"], "info")

    def test_normalize_empty_returns_none(self) -> None:
        self.assertIsNone(
            history.normalize_unresolved_source_item(
                self.ctx,
                {},
                item_type="x",
                status="o",
                disposition="d",
                source_stage="s",
                source_artifact="",
            )
        )

    def test_normalize_item_own_fields_override(self) -> None:
        out = history.normalize_unresolved_source_item(
            self.ctx,
            {"title": "T", "status": "rejected"},
            item_type="x",
            status="open",
            disposition="d",
            source_stage="s",
            source_artifact="",
        )
        assert out is not None
        self.assertEqual(out["status"], "rejected")

    def test_items_from_value_dedup_and_none(self) -> None:
        self.assertEqual(
            history.unresolved_items_from_value(
                self.ctx,
                None,
                item_type="x",
                status="o",
                disposition="d",
                source_stage="s",
                source_artifact="",
            ),
            [],
        )
        items = history.unresolved_items_from_value(
            self.ctx,
            [{"title": "dup"}, {"title": "dup"}, {"title": "other"}],
            item_type="x",
            status="o",
            disposition="d",
            source_stage="s",
            source_artifact="",
        )
        self.assertEqual([i["title"] for i in items], ["dup", "other"])

    def test_collect_from_many_sources(self) -> None:
        feature = "demo"
        self.write_stage_md(feature, "02_review", "## 거부된 항목\n- 항목A 거부\n\n## 경고\n- 경고B\n")
        stage_results = {
            "02_review": {
                "unresolved_items": [{"finding": "미해결 X", "severity": "high", "reason": "시간"}],
                "warnings": ["주의사항 Y"],
                "fix_inputs": {
                    "rejected": [{"title": "거절 Z", "reason_not_actioned": "불필요"}],
                    "deferred": ["나중에 W"],
                },
            }
        }
        items = history.collect_history_unresolved_items(self.ctx, feature, stage_results)
        titles = {i["title"] for i in items}
        for expected in {"미해결 X", "주의사항 Y", "거절 Z", "나중에 W", "항목A 거부", "경고B"}:
            self.assertIn(expected, titles)

        by_title = {i["title"]: i for i in items}
        self.assertEqual(by_title["미해결 X"]["severity"], "high")
        self.assertEqual(by_title["미해결 X"]["status"], "open")
        self.assertEqual(by_title["미해결 X"]["reason_not_actioned"], "시간")
        self.assertEqual(by_title["거절 Z"]["status"], "rejected")
        self.assertEqual(by_title["거절 Z"]["disposition"], "rejected")


class HistoryNotesTests(HistoryTestBase):
    def test_collect_notes_merges_fields_and_markdown(self) -> None:
        feature = "demo"
        self.write_stage_md(
            feature,
            "01_develop",
            "## Implementation Summary\n- 모듈 A 추가\n\n## Future Work\n- 캐싱 도입\n",
        )
        stage_results = {
            "01_develop": {
                "implemented": ["기능 구현 완료"],
                "risks": [{"title": "동시성 위험", "severity": "high"}],
                "future_improvements": ["성능 개선"],
                "decisions": [{"title": "라이브러리 X 선택", "summary": "가볍다"}],
                "fix_inputs": {"deferred": ["리팩터링 보류"]},
            }
        }
        implemented, risks, future, decisions = history.collect_history_notes(
            self.ctx, feature, stage_results
        )
        self.assertIn("기능 구현 완료", implemented)
        self.assertIn("모듈 A 추가", implemented)
        self.assertIn("성능 개선", future)
        self.assertIn("캐싱 도입", future)
        self.assertIn("리팩터링 보류", future)

        risk = next(r for r in risks if r["title"] == "동시성 위험")
        self.assertEqual(risk["category"], "risk")
        self.assertEqual(risk["source_stage"], "01_develop")
        self.assertTrue(any(d["title"] == "라이브러리 X 선택" for d in decisions))

    def test_compact_history_titles(self) -> None:
        items = [{"title": "A"}, {"summary": "B"}, {"title": "A"}, "C"]
        self.assertEqual(history.compact_history_titles(self.ctx, items, max_items=2), ["A", "B"])
        self.assertEqual(history.compact_history_titles(self.ctx, items, max_items=0), [])


class VerificationSummaryTests(HistoryTestBase):
    def test_uses_latest_json(self) -> None:
        self.write_latest_verification(
            "demo",
            {
                "status": "PASS",
                "passed": True,
                "failed_commands": [],
                "commands": [{"name": "pytest"}, {"name": "build"}, {"missing": "name"}],
            },
        )
        out = history.load_history_verification(self.ctx, "demo", {})
        self.assertEqual(out["status"], "PASS")
        self.assertTrue(out["passed"])
        self.assertEqual(out["commands"], ["pytest", "build"])
        self.assertTrue(out["source"].endswith("latest.json"))

    def test_falls_back_to_verify_summary(self) -> None:
        stage_results = {
            "04_verify": {"status": "PASS", "verification_summary": {"status": "PASS", "pytest": "ok"}}
        }
        out = history.load_history_verification(self.ctx, "demo", stage_results)
        self.assertEqual(out["status"], "PASS")
        self.assertTrue(out["passed"])
        self.assertIn("pytest", out["commands"])

    def test_final_fallback_to_status(self) -> None:
        out = history.load_history_verification(self.ctx, "demo", {"04_verify": {"status": "FAIL"}})
        self.assertEqual(out["status"], "FAIL")
        self.assertFalse(out["passed"])
        self.assertEqual(out["commands"], [])


class PcCandidateNormalizeAppendTests(HistoryTestBase):
    def test_normalize_project_wide(self) -> None:
        state = {"feature_name": "demo", "pipeline_mode": "standard", "created_at": "2026-06-08T10:00:00"}
        out = history.normalize_pc_candidate(
            self.ctx,
            {
                "impact_scope": "project_wide",
                "category": "naming",
                "rule_candidate": "함수는 동사로 시작한다",
                "rationale": "일관성",
                "evidence": ["src/app.py"],
                "recommended_contract_section": "Naming",
            },
            state,
            "2026-06-08T12:00:00",
            "claude",
        )
        assert out is not None
        self.assertEqual(out["impact_scope"], "project_wide")
        self.assertEqual(out["status"], "미정")
        self.assertEqual(out["category"], "naming")
        self.assertEqual(out["rule_candidate"], "함수는 동사로 시작한다")
        self.assertEqual(out["extraction_model"], "claude")
        self.assertRegex(out["id"], r"^pc-[0-9a-f]{12}$")

    def test_normalize_rejects_non_project_wide(self) -> None:
        state = {"feature_name": "demo"}
        self.assertIsNone(
            history.normalize_pc_candidate(
                self.ctx,
                {"impact_scope": "stack_wide", "rule_candidate": "x"},
                state,
                "t",
                "claude",
            )
        )

    def test_normalize_rejects_empty_rule(self) -> None:
        state = {"feature_name": "demo"}
        self.assertIsNone(
            history.normalize_pc_candidate(
                self.ctx,
                {"impact_scope": "project_wide", "rule_candidate": ""},
                state,
                "t",
                "claude",
            )
        )

    def test_append_dedups_by_id(self) -> None:
        state = {"feature_name": "demo", "pipeline_mode": "standard"}
        res = history.append_pc_candidates(
            self.ctx,
            [{"id": "pc-1"}, {"id": "pc-2"}, {"id": "pc-1"}],
            state,
        )
        self.assertEqual(res["added_count"], 2)
        self.assertEqual(set(res["added_ids"]), {"pc-1", "pc-2"})

        res2 = history.append_pc_candidates(self.ctx, [{"id": "pc-2"}, {"id": "pc-3"}], state)
        self.assertEqual(res2["added_count"], 1)
        self.assertEqual(res2["added_ids"], ["pc-3"])

        store = history.read_pc_candidates_store(self.ctx)
        self.assertEqual({c["id"] for c in store["candidates"]}, {"pc-1", "pc-2", "pc-3"})


class PcExtractionParseTests(HistoryTestBase):
    def test_provider_failure_raises(self) -> None:
        with self.assertRaises(HarnessError):
            history.parse_pc_candidate_extraction_result(
                self.ctx, {"returncode": 1, "stdout": "e", "stderr": "x"}
            )

    def test_timed_out_raises(self) -> None:
        with self.assertRaises(HarnessError):
            history.parse_pc_candidate_extraction_result(
                self.ctx, {"returncode": 0, "timed_out": True}
            )

    def test_parses_stdout_json(self) -> None:
        out = history.parse_pc_candidate_extraction_result(
            self.ctx,
            {"returncode": 0, "timed_out": False, "stdout_text": '{"candidates": [{"rule_candidate": "r"}]}'},
        )
        self.assertEqual(out, [{"rule_candidate": "r"}])

    def test_candidates_not_list_raises(self) -> None:
        with self.assertRaises(HarnessError):
            history.parse_pc_candidate_extraction_result(
                self.ctx, {"returncode": 0, "stdout_text": '{"candidates": {}}'}
            )

    def test_missing_candidates_key_raises(self) -> None:
        with self.assertRaises(HarnessError):
            history.parse_pc_candidate_extraction_result(
                self.ctx, {"returncode": 0, "stdout_text": '{"foo": 1}'}
            )

    def test_json_output_fallback(self) -> None:
        cap = self.root / "logs" / "cap.json"
        cap.parent.mkdir(parents=True, exist_ok=True)
        cap.write_text('{"candidates": [{"rule_candidate": "z"}]}', encoding="utf-8")
        out = history.parse_pc_candidate_extraction_result(
            self.ctx,
            {"returncode": 0, "timed_out": False, "stdout_text": "", "json_output": "logs/cap.json"},
        )
        self.assertEqual(out, [{"rule_candidate": "z"}])

    def test_run_window_none_cases(self) -> None:
        self.assertIsNone(history._pc_candidate_run_window({}))
        self.assertIsNone(history._pc_candidate_run_window({"finished_at": "nope"}))
        self.assertIsNone(
            history._pc_candidate_run_window(
                {"finished_at": "2026-06-08T12:00:00", "elapsed_seconds": "bad"}
            )
        )

    def test_run_window_valid(self) -> None:
        window = history._pc_candidate_run_window(
            {"finished_at": "2026-06-08T12:00:00", "elapsed_seconds": 10}
        )
        assert window is not None
        self.assertLess(window[0], window[1])

    def test_capture_fallback_picks_recent_within_attempt(self) -> None:
        logs = self.root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        finished = datetime(2026, 6, 8, 12, 0, 0)
        base = finished.timestamp()

        def write(name: str, body: str, mtime: float) -> Path:
            path = logs / name
            path.write_text(body, encoding="utf-8")
            os.utime(path, (mtime, mtime))
            return path

        write("pc_candidates_claude_attempt1_result.json", '{"candidates": [{"rule_candidate": "old"}]}', base - 2)
        write("pc_candidates_claude_attempt2_result.json", '{"candidates": [{"rule_candidate": "new"}]}', base - 1)
        # attempt3 is the most recent but must be excluded (attempt > expected).
        write("pc_candidates_claude_attempt3_result.json", '{"candidates": []}', base - 0.5)

        output_path = logs / "pc_candidates_claude_attempt2_result.json"
        result = {"finished_at": finished.isoformat(), "elapsed_seconds": 0}
        parsed = history._pc_candidate_capture_fallback_json(self.ctx, output_path, result)
        self.assertEqual(parsed.get("candidates"), [{"rule_candidate": "new"}])

    def test_capture_fallback_excludes_out_of_window(self) -> None:
        logs = self.root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        finished = datetime(2026, 6, 8, 12, 0, 0)
        path = logs / "pc_candidates_claude_attempt1_result.json"
        path.write_text('{"candidates": [{"rule_candidate": "old"}]}', encoding="utf-8")
        # 100 seconds before the window start -> excluded.
        stale = finished.timestamp() - 100
        os.utime(path, (stale, stale))
        result = {"finished_at": finished.isoformat(), "elapsed_seconds": 0}
        parsed = history._pc_candidate_capture_fallback_json(self.ctx, path, result)
        self.assertEqual(parsed, {})


class StoreBootstrapAndRenderTests(HistoryTestBase):
    def test_ensure_history_store_bootstrap(self) -> None:
        self.assertTrue(history.ensure_history_store(self.ctx))
        self.assertTrue(history.history_index_path(self.ctx).exists())
        self.assertTrue(history.pc_candidates_path(self.ctx).exists())
        self.assertTrue(history.history_summary_path(self.ctx).exists())
        # Second call: everything exists already.
        self.assertFalse(history.ensure_history_store(self.ctx))

    def test_render_history_summary(self) -> None:
        history.ensure_history_store(self.ctx)
        index = {
            "features": [
                {
                    "feature": "demo",
                    "completed_at": "2026-06-08T12:00:00",
                    "pipeline": "standard",
                    "status": "complete",
                    "verification": "PASS",
                    "implemented": ["A", "B", "C", "D"],
                }
            ]
        }
        history.render_history_summary(self.ctx, index)
        text = history.history_summary_path(self.ctx).read_text(encoding="utf-8")
        self.assertIn("demo", text)
        self.assertIn("기록된 feature: 1", text)
        self.assertIn("- A", text)

    def test_history_document_path_empty_without_document_stage(self) -> None:
        self.assertEqual(history.history_document_path(self.ctx, "demo"), "")

    def test_history_document_path_with_document_stage(self) -> None:
        ctx = make_ctx(self.root, document_stage="06_document")
        doc = ctx.expected_docx_path("demo")
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("x", encoding="utf-8")
        self.assertTrue(history.history_document_path(ctx, "demo").endswith("demo.docx"))


class PromptAndContractTests(HistoryTestBase):
    def test_contract_default_created(self) -> None:
        text = history.project_contract_prompt_text(self.ctx)
        self.assertIn("## Project Contract", text)
        self.assertIn("Source:", text)
        self.assertTrue(history.project_contract_path(self.ctx).exists())

    def test_contract_empty_file_returns_placeholder(self) -> None:
        path = history.project_contract_path(self.ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        text = history.project_contract_prompt_text(self.ctx)
        self.assertIn("No approved project contract", text)

    def test_build_extraction_prompt(self) -> None:
        state = {
            "feature_name": "demo",
            "pipeline_mode": "standard",
            "request": "build X",
            "created_at": "2026-06-08T10:00:00",
        }
        prompt = history.build_pc_candidate_extraction_prompt(self.ctx, state)
        self.assertIn("# Project Contract Candidate Extraction", prompt)
        self.assertIn("feature_name: demo", prompt)
        self.assertIn('"candidates": []', prompt)
        self.assertIn("## Output Contract", prompt)

    def test_build_extraction_prompt_with_capture(self) -> None:
        state = {"feature_name": "demo", "pipeline_mode": "standard", "request": "build X"}
        cap = self.ctx.run_dir("demo") / "logs" / "cap.json"
        prompt = history.build_pc_candidate_extraction_prompt(self.ctx, state, cap)
        self.assertIn("Required Capture File", prompt)
        self.assertIn("cap.json", prompt)


class MiscHelperTests(HistoryTestBase):
    def test_safe_stage_text(self) -> None:
        self.assertEqual(history.safe_stage_text(self.ctx, "demo", "01_develop"), "")
        self.write_stage_md("demo", "01_develop", "hello")
        self.assertEqual(history.safe_stage_text(self.ctx, "demo", "01_develop"), "hello")

    def test_load_stage_results_from_json_and_md(self) -> None:
        self.write_stage_result("demo", "01_develop", {"status": "PASS", "risk_level": "low"})
        self.write_stage_md("demo", "02_review", "## 단계 결과\n- status: PASS\n- next_stage: 03_fix\n")
        results = history.load_history_stage_results(self.ctx, "demo")
        self.assertEqual(results["01_develop"]["status"], "PASS")
        self.assertEqual(results["02_review"]["status"], "PASS")
        self.assertEqual(results["02_review"]["next_stage"], "03_fix")

    def test_history_source_artifacts_sorted(self) -> None:
        self.write_stage_md("demo", "00_specify", "spec")
        self.write_stage_result("demo", "00_specify", {"status": "PASS"})
        self.write_latest_verification("demo", {"status": "PASS"})
        state_path = self.ctx.state_path("demo")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(state_path, {"feature_name": "demo"})
        artifacts = history.history_source_artifacts(self.ctx, "demo")
        self.assertEqual(artifacts, sorted(artifacts))
        self.assertTrue(any(a.endswith("00_spec.md") for a in artifacts))
        self.assertTrue(any(a.endswith("latest.json") for a in artifacts))
        self.assertTrue(any(a.endswith("run.json") for a in artifacts))


class RecordProjectHistoryIntegrationTests(HistoryTestBase):
    def test_record_then_update(self) -> None:
        feature = "demo"
        self.write_stage_result(
            feature,
            "01_develop",
            {"status": "PASS", "changed_files": ["src/app.py"], "implemented": ["A 기능 구현"], "risk_level": "low"},
        )
        self.write_stage_result(
            feature,
            "04_verify",
            {"status": "PASS", "verification_summary": {"status": "PASS"}},
        )
        state = {
            "feature_name": feature,
            "pipeline_mode": "standard",
            "status": "complete",
            "created_at": "2026-06-08T10:00:00",
            "request": "build X",
            "commits": {},
            "events": [{"event": "commit_created", "paths": ["src/app.py"]}],
        }
        recorded = history.record_project_history(self.ctx, state)
        self.assertEqual(recorded["status"], "recorded")
        self.assertEqual(state["history"]["status"], "recorded")

        index = history.read_history_index(self.ctx)
        entry = next(f for f in index["features"] if f["feature"] == feature)
        self.assertEqual(entry["verification"], "PASS")
        self.assertIn("A 기능 구현", entry["implemented"])

        summary = history.history_summary_path(self.ctx).read_text(encoding="utf-8")
        self.assertIn(feature, summary)

        # Re-running the same feature updates rather than inserts.
        recorded2 = history.record_project_history(self.ctx, state)
        self.assertEqual(recorded2["status"], "updated")
        index2 = history.read_history_index(self.ctx)
        self.assertEqual(len([f for f in index2["features"] if f["feature"] == feature]), 1)


if __name__ == "__main__":
    unittest.main()
