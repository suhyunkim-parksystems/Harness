from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from support import ensure_ai_path

ensure_ai_path()

import deep_interview as di  # noqa: E402
import project_planning as pp  # noqa: E402


def _ns(**overrides: Any) -> types.SimpleNamespace:
    base = dict(model="codex", timeout=10, performance="medium")
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _feat(slug: str, *, tier: str = "standard", perf: str = "medium", deps: list[str] | None = None) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": slug.title(),
        "tier": tier,
        "performance": perf,
        "depends_on": deps or [],
        "refined_prompt": f"{slug} 구현",
    }


# --------------------------------------------------------------------------- #
# slugify / derive_project_slug
# --------------------------------------------------------------------------- #
class SlugifyTests(unittest.TestCase):
    def test_basic(self) -> None:
        self.assertEqual(pp.slugify("Hello World!"), "hello-world")

    def test_collapses_and_trims(self) -> None:
        self.assertEqual(pp.slugify("  __A--B__  "), "a-b")

    def test_empty_uses_fallback(self) -> None:
        self.assertEqual(pp.slugify("", fallback="proj"), "proj")
        self.assertEqual(pp.slugify("***"), "project")

    def test_length_capped(self) -> None:
        self.assertLessEqual(len(pp.slugify("x" * 200)), 64)

    def test_derive_prefers_explicit_project(self) -> None:
        args = types.SimpleNamespace(project="My Proj")
        self.assertEqual(pp.derive_project_slug(args, "ignored", [], []), "my-proj")

    def test_derive_from_request_first_words(self) -> None:
        args = types.SimpleNamespace(project=None)
        slug = pp.derive_project_slug(args, "build a shopping mall backend now please", [], [])
        self.assertEqual(slug, "build-a-shopping-mall-backend-now")  # first 6 words


# --------------------------------------------------------------------------- #
# input resolution (filesystem-backed, temp dirs)
# --------------------------------------------------------------------------- #
class ResolveInputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pp-in-"))

    def _touch(self, name: str, content: str = "x") -> Path:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_supported_file_accepted(self) -> None:
        md = self._touch("spec.md", "# spec")
        self.assertEqual(pp.resolve_plan_files([str(md)]), [md.resolve()])

    def test_ppt_rejected(self) -> None:
        ppt = self._touch("deck.pptx")
        with self.assertRaises(pp.PlanningError):
            pp.resolve_plan_files([str(ppt)])

    def test_missing_file_rejected(self) -> None:
        with self.assertRaises(pp.PlanningError):
            pp.resolve_plan_files([str(self.tmp / "nope.md")])

    def test_unsupported_extension_rejected(self) -> None:
        bad = self._touch("data.xlsx")
        with self.assertRaises(pp.PlanningError):
            pp.resolve_plan_files([str(bad)])

    def test_folder_scan_collects_supported_skips_others(self) -> None:
        self._touch("a.md")
        self._touch("sub/b.txt")
        self._touch("img.png")  # skipped silently
        self._touch("deck.ppt")  # skipped with notice
        self._touch(".hidden/c.md")  # hidden dir skipped
        collected, folders = pp.resolve_plan_folders([str(self.tmp)])
        names = sorted(p.name for p in collected)
        self.assertEqual(names, ["a.md", "b.txt"])
        self.assertEqual(folders, [self.tmp.resolve()])

    def test_folder_without_supported_files_raises(self) -> None:
        self._touch("only.png")
        with self.assertRaises(pp.PlanningError):
            pp.resolve_plan_folders([str(self.tmp)])

    def test_merge_dedupes_preserving_order(self) -> None:
        a = self._touch("a.md")
        b = self._touch("b.md")
        merged = pp.merge_plan_files([a.resolve()], [a.resolve(), b.resolve()])
        self.assertEqual(merged, [a.resolve(), b.resolve()])


# --------------------------------------------------------------------------- #
# inputs / folder-map sections
# --------------------------------------------------------------------------- #
class SectionBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pp-sec-"))

    def test_inputs_section_inlines_markdown(self) -> None:
        md = self.tmp / "spec.md"
        md.write_text("# 제목\n본문 내용", encoding="utf-8")
        section = pp.build_inputs_section([md])
        self.assertIn("본문 내용", section)
        self.assertIn(str(md), section)

    def test_inputs_section_empty(self) -> None:
        section = pp.build_inputs_section([])
        self.assertIn("첨부 파일 없음", section)

    def test_scan_reference_folder_filters(self) -> None:
        (self.tmp / "src").mkdir()
        (self.tmp / "obj").mkdir()
        (self.tmp / "README.md").write_text("orient", encoding="utf-8")
        (self.tmp / "src" / "Foo.cs").write_text("class", encoding="utf-8")
        (self.tmp / "src" / "logo.png").write_bytes(b"\x89PNG")
        (self.tmp / "obj" / "gen.cs").write_text("gen", encoding="utf-8")
        map_files, orientation = pp._scan_reference_folder(self.tmp)
        map_names = {p.name for p in map_files}
        self.assertIn("Foo.cs", map_names)
        self.assertNotIn("logo.png", map_names)      # binary skipped
        self.assertNotIn("gen.cs", map_names)        # build dir skipped
        self.assertNotIn("README.md", map_names)     # orientation pulled out
        self.assertEqual([p.name for p in orientation], ["README.md"])

    def test_reuse_section_has_reuse_framing(self) -> None:
        (self.tmp / "Platform.cs").write_text("x", encoding="utf-8")
        section = pp.build_reuse_section([self.tmp])
        self.assertIn("재사용", section)
        self.assertIn("Platform.cs", section)

    def test_reference_section_has_no_copy_framing(self) -> None:
        (self.tmp / "Sibling.cs").write_text("x", encoding="utf-8")
        section = pp.build_references_section([self.tmp])
        self.assertIn("통째로 베끼지", section)

    def test_empty_folders_produce_empty_sections(self) -> None:
        self.assertEqual(pp.build_reuse_section([]), "")
        self.assertEqual(pp.build_references_section([]), "")


# --------------------------------------------------------------------------- #
# anonymized candidate blocks / prompt builders
# --------------------------------------------------------------------------- #
class PromptBuilderTests(unittest.TestCase):
    def test_candidates_block_is_anonymized(self) -> None:
        candidates = [
            {"provider": "claude", "features": [{"slug": "a"}]},
            {"provider": "codex", "features": [{"slug": "b"}]},
        ]
        block = pp._candidates_block(candidates)
        self.assertIn("### 초안 A", block)
        self.assertIn("### 초안 B", block)
        self.assertIn("익명", block)

    def test_decompose_prompt_contains_schema(self) -> None:
        prompt = pp.build_decompose_prompt(
            request="쇼핑몰",
            plan_files=[],
            reference_folders=[],
            reuse_folders=[],
            transcript=[],
        )
        self.assertIn("쇼핑몰", prompt)
        self.assertIn("project_slug", prompt)  # from DECOMPOSE_SCHEMA

    def test_draft_prompt_adds_blind_instruction(self) -> None:
        prompt = pp.build_draft_decompose_prompt(
            request="r", plan_files=[], reference_folders=[], reuse_folders=[], transcript=[]
        )
        self.assertIn("블라인드", prompt)

    def test_max_stage_prompt_marks_latest(self) -> None:
        history = [("블라인드 초안 A", {"features": []}), ("[ground] 결과", {"features": []})]
        prompt = pp.build_max_stage_prompt(
            request="r",
            plan_files=[],
            reference_folders=[],
            reuse_folders=[],
            transcript=[],
            history=history,
            instruction=pp.PREMORTEM_INSTRUCTION,
        )
        self.assertIn("현재 최신본", prompt)
        self.assertIn("사전 부검", prompt)


# --------------------------------------------------------------------------- #
# topological_order — the highest-risk pure logic
# --------------------------------------------------------------------------- #
class TopologicalOrderTests(unittest.TestCase):
    def test_orders_by_dependency(self) -> None:
        feats = [_feat("api", deps=["model"]), _feat("model")]
        ordered = pp.topological_order(feats)
        slugs = [f["_slug"] for f in ordered]
        self.assertEqual(slugs, ["model", "api"])
        self.assertEqual(ordered[0]["_id"], "01-model")
        self.assertEqual(ordered[1]["_id"], "02-api")

    def test_independent_features_keep_input_order(self) -> None:
        feats = [_feat("b"), _feat("a"), _feat("c")]
        ordered = pp.topological_order(feats)
        self.assertEqual([f["_slug"] for f in ordered], ["b", "a", "c"])

    def test_duplicate_slugs_get_suffixed(self) -> None:
        feats = [_feat("auth"), _feat("auth")]
        ordered = pp.topological_order(feats)
        slugs = sorted(f["_slug"] for f in ordered)
        self.assertEqual(slugs, ["auth", "auth-2"])

    def test_cycle_raises(self) -> None:
        feats = [_feat("a", deps=["b"]), _feat("b", deps=["a"])]
        with self.assertRaises(pp.PlanningError):
            pp.topological_order(feats)

    def test_self_dependency_is_ignored(self) -> None:
        feats = [_feat("solo", deps=["solo"])]
        ordered = pp.topological_order(feats)
        self.assertEqual(ordered[0]["_deps"], [])

    def test_unknown_dependency_is_dropped(self) -> None:
        feats = [_feat("a", deps=["ghost"])]
        ordered = pp.topological_order(feats)
        self.assertEqual(ordered[0]["_deps"], [])

    def test_diamond_dependency_resolves(self) -> None:
        feats = [
            _feat("d", deps=["b", "c"]),
            _feat("b", deps=["a"]),
            _feat("c", deps=["a"]),
            _feat("a"),
        ]
        ordered = [f["_slug"] for f in pp.topological_order(feats)]
        self.assertLess(ordered.index("a"), ordered.index("b"))
        self.assertLess(ordered.index("a"), ordered.index("c"))
        self.assertLess(ordered.index("b"), ordered.index("d"))
        self.assertLess(ordered.index("c"), ordered.index("d"))


# --------------------------------------------------------------------------- #
# tier / performance / command assembly
# --------------------------------------------------------------------------- #
class TierPerformanceTests(unittest.TestCase):
    def test_tier_to_invocation_known(self) -> None:
        self.assertEqual(pp.tier_to_invocation("fast"), (".ai/harness_fast.py", []))
        self.assertEqual(pp.tier_to_invocation("standard"), (".ai/harness_standard.py", []))
        self.assertEqual(
            pp.tier_to_invocation("full-max"),
            (".ai/harness.py", ["--deep-thinking", "--strategy", "max"]),
        )

    def test_tier_to_invocation_unknown_defaults_full(self) -> None:
        self.assertEqual(pp.tier_to_invocation("nonsense"), (".ai/harness.py", []))

    def test_normalize_performance_passthrough_and_default(self) -> None:
        self.assertEqual(pp.normalize_performance("high", "fast"), "high")
        self.assertEqual(pp.normalize_performance("", "fast"), "lite")        # tier default
        self.assertEqual(pp.normalize_performance("bogus", "full-max"), "high")
        self.assertEqual(pp.normalize_performance("", "unknown-tier"), "medium")

    def test_quote_arg_converts_inner_quotes(self) -> None:
        out = pp.quote_arg('say "hi" now')
        self.assertTrue(out.startswith('"') and out.endswith('"'))
        self.assertNotIn('""', out)        # inner double quotes replaced
        self.assertIn("'hi'", out)

    def test_feature_command_full_max(self) -> None:
        feat = _feat("auth", tier="full-max", perf="high")
        ordered = pp.topological_order([feat])
        cmd = pp.feature_command(ordered[0])
        self.assertIn("python .ai/harness.py run", cmd)
        self.assertIn("--feature 01-auth", cmd)
        self.assertIn("--performance high", cmd)
        self.assertIn("--deep-thinking --strategy max", cmd)
        self.assertIn("--yes --defaults", cmd)


# --------------------------------------------------------------------------- #
# relay provider assignment
# --------------------------------------------------------------------------- #
class RelayAssignmentTests(unittest.TestCase):
    def test_rotated(self) -> None:
        self.assertEqual(pp._rotated(["a", "b", "c"], 1), ["b", "c", "a"])
        self.assertEqual(pp._rotated([], 3), [])

    def test_last_phase_is_owner(self) -> None:
        assigned = pp._assign_relay_providers(3, ["codex", "claude", "agy"], "codex")
        self.assertEqual(assigned[-1], "codex")
        self.assertEqual(len(assigned), 3)

    def test_adjacent_phases_differ_when_possible(self) -> None:
        assigned = pp._assign_relay_providers(3, ["codex", "claude", "agy"], "codex")
        for i in range(len(assigned) - 1):
            self.assertNotEqual(assigned[i], assigned[i + 1])

    def test_single_provider_pool_falls_back_to_owner(self) -> None:
        assigned = pp._assign_relay_providers(2, [], "codex")
        self.assertEqual(assigned, ["codex", "codex"])


# --------------------------------------------------------------------------- #
# render_plan_text structural
# --------------------------------------------------------------------------- #
class RenderPlanTextTests(unittest.TestCase):
    def test_renders_order_and_commands(self) -> None:
        ordered = pp.topological_order([_feat("model"), _feat("api", deps=["model"])])
        for f in ordered:
            f["_performance"] = pp.normalize_performance(f.get("performance"), f.get("tier"))
        text = pp.render_plan_text(
            project_slug="shop",
            summary="쇼핑몰",
            model="codex",
            mode="auto",
            strategy="single",
            plan_files=[],
            ordered=ordered,
        )
        self.assertIn("01-model", text)
        self.assertIn("02-api", text)
        self.assertIn("연속 실행 명령어 모음", text)
        # dependency shown by id
        self.assertIn("선행   : 01-model", text)


# --------------------------------------------------------------------------- #
# available_plan_providers
# --------------------------------------------------------------------------- #
class AvailableProvidersTests(unittest.TestCase):
    def test_filters_by_availability_and_capability(self) -> None:
        class H:
            def known_provider_names(self):
                return ["codex", "claude", "agy", "broken"]

            def provider_available(self, p):
                if p == "broken":
                    raise RuntimeError("probe failed")
                return p != "claude"  # claude unavailable

            def provider_capabilities(self, p):
                return {"plan", "review"} if p != "agy" else {"review"}  # agy lacks plan

        self.assertEqual(pp.available_plan_providers(H()), ["codex"])


# --------------------------------------------------------------------------- #
# strategies (faked plan_model_json + available providers)
# --------------------------------------------------------------------------- #
class _PlanModelFake:
    """Records log_prefix per call and returns a tagged decomposition."""

    def __init__(self, valid_drafters: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.valid_drafters = valid_drafters  # None => all drafts valid

    def __call__(self, harness, args, *, prompt=None, logs_dir=None, log_prefix=None,
                 repair_schema=None, status_message=None, provider=None):
        self.calls.append(log_prefix)
        if log_prefix and log_prefix.startswith("draft_"):
            drafter = log_prefix[len("draft_"):]
            if self.valid_drafters is not None and drafter not in self.valid_drafters:
                return {"_via": log_prefix, "features": []}  # invalid -> dropped
            return {"_via": log_prefix, "features": [_feat(f"d-{drafter}")]}
        return {"_via": log_prefix, "features": [_feat(f"x-{log_prefix}")]}


class ParallelStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pp-par-"))

    def _run(self, fake: _PlanModelFake, providers: list[str]) -> dict[str, Any]:
        with mock.patch.object(pp, "plan_model_json", fake), \
             mock.patch.object(pp, "available_plan_providers", return_value=providers):
            return pp.run_parallel_decompose(
                object(), _ns(),
                request="r", plan_files=[], reference_folders=[], reuse_folders=[],
                transcript=[], logs_dir=self.tmp,
            )

    def test_three_drafts_then_synthesis(self) -> None:
        fake = _PlanModelFake()
        result = self._run(fake, ["codex", "claude", "agy"])
        self.assertEqual(result["_via"], "synthesis")
        self.assertEqual(sum(1 for c in fake.calls if c.startswith("draft_")), 3)
        self.assertIn("synthesis", fake.calls)

    def test_single_provider_falls_back_to_single(self) -> None:
        fake = _PlanModelFake()
        result = self._run(fake, ["codex"])
        self.assertEqual(result["_via"], "decompose")
        self.assertNotIn("synthesis", fake.calls)

    def test_one_valid_draft_is_promoted_without_synthesis(self) -> None:
        fake = _PlanModelFake(valid_drafters={"codex"})
        result = self._run(fake, ["codex", "claude", "agy"])
        self.assertNotIn("synthesis", fake.calls)
        self.assertEqual(result["features"][0]["slug"], "d-codex")

    def test_zero_valid_drafts_raises(self) -> None:
        fake = _PlanModelFake(valid_drafters=set())
        with self.assertRaises(pp.PlanningError):
            self._run(fake, ["codex", "claude"])


class MaxStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pp-max-"))

    def _run(self, fake: _PlanModelFake, providers: list[str]) -> dict[str, Any]:
        with mock.patch.object(pp, "plan_model_json", fake), \
             mock.patch.object(pp, "available_plan_providers", return_value=providers):
            return pp.run_max_decompose(
                object(), _ns(),
                request="r", plan_files=[], reference_folders=[], reuse_folders=[],
                transcript=[], logs_dir=self.tmp,
            )

    def test_full_relay_runs_select_ground_premortem(self) -> None:
        fake = _PlanModelFake()
        self._run(fake, ["codex", "claude", "agy"])
        self.assertIn("max_select", fake.calls)
        self.assertIn("max_ground", fake.calls)
        self.assertIn("max_premortem", fake.calls)

    def test_single_candidate_skips_select_keeps_depth(self) -> None:
        fake = _PlanModelFake(valid_drafters={"codex"})
        self._run(fake, ["codex", "claude", "agy"])
        self.assertNotIn("max_select", fake.calls)   # nothing to select among
        self.assertIn("max_ground", fake.calls)       # depth still runs
        self.assertIn("max_premortem", fake.calls)

    def test_zero_drafts_raises(self) -> None:
        fake = _PlanModelFake(valid_drafters=set())
        with self.assertRaises(pp.PlanningError):
            self._run(fake, ["codex", "claude"])


# --------------------------------------------------------------------------- #
# agy file-output transport + plan_model_json routing
# --------------------------------------------------------------------------- #
class AgyFileTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pp-agy-"))
        # Redirect agy output + repo root into the temp tree so nothing touches
        # the real repo.
        self._patches = [
            mock.patch.object(pp, "ROOT", self.tmp),
            mock.patch.object(pp, "AGY_OUTPUT_DIR", self.tmp / "cache" / "agy_out"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()

    def _fake_provider_writes_file(self, payload: dict[str, Any]) -> Any:
        import re

        def fake(harness, provider, prompt_text, *, logs_dir, log_prefix,
                 timeout_seconds, performance):
            m = re.search(r"output_file \(repo 루트 기준 상대경로\): (\S+)", prompt_text)
            assert m, "instruction must embed the output_file path"
            target = self.tmp / m.group(1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return {"returncode": 0, "stdout_text": "", "stderr_text": ""}

        return fake

    def test_reads_json_from_written_file_and_cleans_up(self) -> None:
        payload = {"features": [_feat("a")]}
        with mock.patch.object(di, "run_deep_interview_provider_prompt",
                               self._fake_provider_writes_file(payload)):
            out = pp._run_agy_via_file(
                object(), _ns(),
                prompt="## 출력 계약\n...", logs_dir=self.tmp / "logs",
                log_prefix="draft_agy", status_message="...",
            )
        self.assertEqual(out, payload)
        # success path removes the cache file
        leftovers = list((self.tmp / "cache" / "agy_out").glob("*.json"))
        self.assertEqual(leftovers, [])

    def test_missing_output_file_raises_and_keeps_diagnostics(self) -> None:
        def fake(harness, provider, prompt_text, *, logs_dir, log_prefix,
                 timeout_seconds, performance):
            return {"returncode": 0, "stdout_text": "", "stderr_text": ""}  # writes nothing

        with mock.patch.object(di, "run_deep_interview_provider_prompt", fake):
            with self.assertRaises(di.InterviewError):
                pp._run_agy_via_file(
                    object(), _ns(),
                    prompt="p", logs_dir=self.tmp / "logs",
                    log_prefix="draft_agy", status_message="...",
                )

    def test_plan_model_json_routes_agy_to_file_transport(self) -> None:
        sentinel = {"features": [_feat("z")]}
        with mock.patch.object(pp, "_run_agy_via_file", return_value=sentinel) as agy_fn, \
             mock.patch.object(di, "model_json") as std_fn:
            out = pp.plan_model_json(
                object(), _ns(),
                prompt="p", logs_dir=self.tmp, log_prefix="draft_agy",
                repair_schema="schema", status_message="...", provider="agy",
            )
        self.assertEqual(out, sentinel)
        agy_fn.assert_called_once()
        std_fn.assert_not_called()

    def test_plan_model_json_routes_codex_to_standard(self) -> None:
        sentinel = {"features": [_feat("z")]}
        with mock.patch.object(pp, "_run_agy_via_file") as agy_fn, \
             mock.patch.object(di, "model_json", return_value=sentinel) as std_fn:
            out = pp.plan_model_json(
                object(), _ns(),
                prompt="p", logs_dir=self.tmp, log_prefix="decompose",
                repair_schema="schema", status_message="...", provider="codex",
            )
        self.assertEqual(out, sentinel)
        std_fn.assert_called_once()
        agy_fn.assert_not_called()


# --------------------------------------------------------------------------- #
# contract update: add-only merge primitives
# --------------------------------------------------------------------------- #
_SAMPLE_CONTRACT = """# Project Contract

## Hard Rules
- 모델은 Git을 직접 실행하지 않는다.
- 기존 테스트를 삭제하지 않는다.

## Code Style
- 같은 디렉터리의 기존 패턴을 우선 따른다.
"""


class InsertRuleTests(unittest.TestCase):
    def test_insert_into_existing_section_after_last_bullet(self) -> None:
        out = pp.insert_rule_into_contract(_SAMPLE_CONTRACT, "Code Style", "snake_case를 따른다")
        lines = out.splitlines()
        cs = lines.index("## Code Style")
        # new bullet sits right after the existing bullet of that section
        self.assertEqual(lines[cs + 1], "- 같은 디렉터리의 기존 패턴을 우선 따른다.")
        self.assertEqual(lines[cs + 2], "- snake_case를 따른다")

    def test_insert_does_not_leak_into_other_section(self) -> None:
        out = pp.insert_rule_into_contract(_SAMPLE_CONTRACT, "Hard Rules", "새 하드룰")
        # The Hard Rules bullet count grows; Code Style is untouched.
        self.assertIn("- 새 하드룰\n", out)
        hr = out.splitlines().index("## Hard Rules")
        cs = out.splitlines().index("## Code Style")
        self.assertEqual(out.splitlines()[cs - 1], "")  # blank line before next header preserved
        self.assertLess(hr, cs)

    def test_unknown_section_appends_new_section(self) -> None:
        out = pp.insert_rule_into_contract(_SAMPLE_CONTRACT, "Testing", "테스트는 tests/ 아래 둔다")
        self.assertIn("## Testing", out)
        self.assertTrue(out.rstrip().endswith("- 테스트는 tests/ 아래 둔다"))

    def test_preserves_all_existing_lines(self) -> None:
        out = pp.insert_rule_into_contract(_SAMPLE_CONTRACT, "Code Style", "새 규칙")
        for line in _SAMPLE_CONTRACT.splitlines():
            if line.strip():
                self.assertIn(line, out)


class NormalizeAddedRulesTests(unittest.TestCase):
    def test_splits_applied_and_skipped(self) -> None:
        proposal = {
            "added_rules": [
                {"target_section": "Code Style", "rule_text": "snake_case를 따른다", "reason": "Python"},
                {"target_section": "Hard Rules", "rule_text": "모델은 Git을 직접 실행하지 않는다."},  # already covered
                {"target_section": "Code Style", "rule_text": "snake_case를 따른다"},  # duplicate in batch
                {"target_section": "X", "rule_text": "x" * 300},  # too long
                {"target_section": "Y", "rule_text": ""},  # empty -> dropped
            ]
        }
        applied, skipped = pp.normalize_added_rules(proposal, _SAMPLE_CONTRACT)
        self.assertEqual([r["rule_text"] for r in applied], ["snake_case를 따른다"])
        reasons = sorted(s["skip_reason"] for s in skipped)
        self.assertEqual(reasons, ["already_covered", "duplicate", "too_long"])

    def test_no_added_rules_returns_empty(self) -> None:
        self.assertEqual(pp.normalize_added_rules({"added_rules": []}, _SAMPLE_CONTRACT), ([], []))
        self.assertEqual(pp.normalize_added_rules({}, _SAMPLE_CONTRACT), ([], []))


# --------------------------------------------------------------------------- #
# contract update: full phase (faked provider + temp contract file)
# --------------------------------------------------------------------------- #
class _FakeHarnessWithContract:
    def __init__(self, path: Path) -> None:
        self._path = path

    def ensure_project_contract_file(self) -> None:
        if not self._path.exists():
            self._path.write_text(_SAMPLE_CONTRACT, encoding="utf-8")

    def project_contract_path(self) -> Path:
        return self._path


class ContractUpdatePhaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pp-pc-"))
        self.contract = self.tmp / "project_contract.md"
        self.contract.write_text(_SAMPLE_CONTRACT, encoding="utf-8")
        self.harness = _FakeHarnessWithContract(self.contract)
        self.ordered = pp.topological_order([_feat("model"), _feat("api", deps=["model"])])

    def _run(self, proposal: dict[str, Any]) -> dict[str, Any]:
        with mock.patch.object(pp, "plan_model_json", return_value=proposal):
            return pp.run_contract_update_phase(
                self.harness, _ns(),
                request="r", plan_files=[], reference_folders=[], reuse_folders=[],
                ordered=self.ordered, summary="요약", logs_dir=self.tmp / "logs",
            )

    def test_adds_rules_and_overwrites_file(self) -> None:
        result = self._run({
            "summary": "Python 관례 추가",
            "added_rules": [
                {"target_section": "Code Style", "rule_text": "이 프로젝트는 snake_case를 따른다", "reason": "Python"},
            ],
        })
        self.assertEqual(len(result["applied"]), 1)
        text = self.contract.read_text(encoding="utf-8")
        self.assertIn("- 이 프로젝트는 snake_case를 따른다", text)

    def test_existing_rules_preserved_after_update(self) -> None:
        self._run({"added_rules": [{"target_section": "Architecture", "rule_text": "어댑터 뒤로 분리한다"}]})
        text = self.contract.read_text(encoding="utf-8")
        for line in _SAMPLE_CONTRACT.splitlines():
            if line.strip():
                self.assertIn(line, text)  # add-only: nothing removed

    def test_no_additions_leaves_file_byte_identical(self) -> None:
        before = self.contract.read_text(encoding="utf-8")
        result = self._run({"summary": "추가 없음", "added_rules": []})
        self.assertEqual(result["applied"], [])
        self.assertEqual(self.contract.read_text(encoding="utf-8"), before)

    def test_already_covered_rule_is_skipped_not_duplicated(self) -> None:
        self._run({"added_rules": [
            {"target_section": "Hard Rules", "rule_text": "모델은 Git을 직접 실행하지 않는다."},
        ]})
        text = self.contract.read_text(encoding="utf-8")
        self.assertEqual(text.count("모델은 Git을 직접 실행하지 않는다."), 1)


if __name__ == "__main__":
    unittest.main()
