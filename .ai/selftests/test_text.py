"""Unit tests for harness_core/text.py.

Covers the pure string utilities (slugify/validate_slug/norm_repo_path/boolish),
compact_history_text length capping and none-ish filtering, and the markdown
section helpers (markdown_sections / section_matches / markdown_section_items)
including table/divider skipping. Parser quirks (unclosed code fence dropping
trailing items, the first plain line being promoted to an item) are pinned
as current behavior with # NOTE comments, not fixed.
"""
from __future__ import annotations

import unittest

from support import ensure_ai_path

ensure_ai_path()

from harness_core import text as text_mod  # noqa: E402


class SlugifyTests(unittest.TestCase):
    def test_spaces_and_case_normalized(self) -> None:
        self.assertEqual(text_mod.slugify("My Feature"), "my-feature")

    def test_special_characters_collapse_to_single_dash(self) -> None:
        self.assertEqual(text_mod.slugify("Hello,   World!! (v2)"), "hello-world-v2")

    def test_leading_and_trailing_separators_stripped(self) -> None:
        self.assertEqual(text_mod.slugify("--My Feature--"), "my-feature")

    def test_empty_input_falls_back_to_timestamped_feature_slug(self) -> None:
        result = text_mod.slugify("!!! ???")
        self.assertTrue(result.startswith("feature-"))
        self.assertTrue(result[len("feature-"):].isdigit())
        self.assertTrue(text_mod.validate_slug(result))

    def test_truncates_to_60_chars(self) -> None:
        self.assertEqual(text_mod.slugify("a" * 100), "a" * 60)

    def test_trailing_dash_after_truncation_stripped(self) -> None:
        # Char 60 lands on the separator between the two words.
        self.assertEqual(text_mod.slugify("a" * 59 + " world"), "a" * 59)


class ValidateSlugTests(unittest.TestCase):
    def test_accepts_simple_slugs(self) -> None:
        for slug in ("my-feature", "a", "a1-b2-c3", "feature-20260612"):
            self.assertTrue(text_mod.validate_slug(slug), slug)

    def test_rejects_path_traversal_and_separators(self) -> None:
        for slug in ("..", "a..b", "a/b", "a\\b", "../etc", "a.b"):
            self.assertFalse(text_mod.validate_slug(slug), slug)

    def test_rejects_empty_uppercase_and_edge_dashes(self) -> None:
        for slug in ("", "-abc", "abc-", "My-Feature", "a_b", "a b"):
            self.assertFalse(text_mod.validate_slug(slug), slug)


class NormRepoPathTests(unittest.TestCase):
    def test_backslashes_become_forward_slashes(self) -> None:
        self.assertEqual(text_mod.norm_repo_path("src\\app\\main.py"), "src/app/main.py")

    def test_surrounding_whitespace_stripped(self) -> None:
        self.assertEqual(text_mod.norm_repo_path("  src/app.py \n"), "src/app.py")


class BoolishTests(unittest.TestCase):
    def test_true_values(self) -> None:
        for value in (True, "true", "True", "  TRUE  "):
            self.assertTrue(text_mod.boolish(value), repr(value))

    def test_false_values(self) -> None:
        for value in (False, "false", "yes", "1", 1, 0, None, [], {}, "truthy"):
            self.assertFalse(text_mod.boolish(value), repr(value))


class CompactHistoryTextTests(unittest.TestCase):
    def test_none_and_noneish_strings_return_empty(self) -> None:
        for value in (None, "", "  ", "none", "None", "N/A", "na", "null", "[]", "{}"):
            self.assertEqual(text_mod.compact_history_text(value), "", repr(value))

    def test_whitespace_collapsed(self) -> None:
        self.assertEqual(
            text_mod.compact_history_text("  line one\n\t line   two  "),
            "line one line two",
        )

    def test_dict_serialized_with_sorted_keys(self) -> None:
        self.assertEqual(
            text_mod.compact_history_text({"b": 1, "a": 2}),
            '{"a": 2, "b": 1}',
        )

    def test_default_length_cap_adds_ellipsis(self) -> None:
        result = text_mod.compact_history_text("x" * 300)
        self.assertEqual(len(result), 240)
        self.assertTrue(result.endswith("..."))
        self.assertEqual(result, "x" * 237 + "...")

    def test_custom_max_len(self) -> None:
        self.assertEqual(text_mod.compact_history_text("abcdefghijk", max_len=10), "abcdefg...")

    def test_short_text_unchanged(self) -> None:
        self.assertEqual(text_mod.compact_history_text("short"), "short")


class MarkdownSectionsTests(unittest.TestCase):
    def test_extracts_sections_by_heading(self) -> None:
        doc = (
            "# Doc Title\n"
            "preamble is dropped\n"
            "\n"
            "## Risks\n"
            "- one\n"
            "- two\n"
            "\n"
            "### Details\n"
            "nested body\n"
            "\n"
            "## Empty\n"
        )
        sections = text_mod.markdown_sections(doc)
        self.assertEqual(sections["Risks"], "- one\n- two")
        # '### Details' opens its own section: ## and deeper all match.
        self.assertEqual(sections["Details"], "nested body")
        self.assertEqual(sections["Empty"], "")
        self.assertNotIn("Doc Title", sections)

    def test_content_before_first_heading_is_ignored(self) -> None:
        sections = text_mod.markdown_sections("no headings here\njust text\n")
        self.assertEqual(sections, {})


class SectionMatchesTests(unittest.TestCase):
    def test_case_insensitive_substring_match(self) -> None:
        self.assertTrue(text_mod.section_matches("Open Risks", ["risk"]))
        self.assertTrue(text_mod.section_matches("3. RISK REGISTER", ["risk"]))
        self.assertFalse(text_mod.section_matches("Overview", ["risk"]))

    def test_any_needle_matches(self) -> None:
        self.assertTrue(text_mod.section_matches("Decisions", ["risk", "decision"]))


class MarkdownSectionItemsTests(unittest.TestCase):
    def test_extracts_dash_star_and_numbered_bullets(self) -> None:
        doc = (
            "## Open Risks\n"
            "- first risk\n"
            "* second risk\n"
            "1. third risk\n"
            "2. fourth risk\n"
        )
        self.assertEqual(
            text_mod.markdown_section_items(doc, ["risk"]),
            ["first risk", "second risk", "third risk", "fourth risk"],
        )

    def test_skips_tables_dividers_and_closed_fences(self) -> None:
        doc = (
            "## Risks\n"
            "- kept one\n"
            "\n"
            "| col | col |\n"
            "|-----|-----|\n"
            "| a   | b   |\n"
            "\n"
            "---\n"
            "\n"
            "```text\n"
            "- inside fence is skipped\n"
            "```\n"
            "- kept two\n"
        )
        self.assertEqual(
            text_mod.markdown_section_items(doc, ["risk"]),
            ["kept one", "kept two"],
        )

    def test_non_matching_sections_ignored(self) -> None:
        doc = "## Overview\n- not a risk\n\n## Risks\n- real risk\n"
        self.assertEqual(text_mod.markdown_section_items(doc, ["risk"]), ["real risk"])

    def test_duplicate_items_deduplicated(self) -> None:
        doc = "## Risks\n- same\n- same\n- other\n"
        self.assertEqual(text_mod.markdown_section_items(doc, ["risk"]), ["same", "other"])

    def test_respects_max_items(self) -> None:
        doc = "## Risks\n" + "".join(f"- item {i}\n" for i in range(10))
        self.assertEqual(
            text_mod.markdown_section_items(doc, ["risk"], max_items=3),
            ["item 0", "item 1", "item 2"],
        )

    def test_unclosed_code_fence_drops_following_items(self) -> None:
        # NOTE: pinned current behavior, not a spec. When a ``` fence is opened
        # but never closed, the parser's in_fence flag stays True for the rest
        # of the section, so every bullet after the unclosed fence is silently
        # dropped. Asserted as-is; do not "fix" in source.
        doc = (
            "## Risks\n"
            "- before fence\n"
            "```py\n"
            "- inside unclosed fence\n"
            "- after fence never seen\n"
        )
        self.assertEqual(
            text_mod.markdown_section_items(doc, ["risk"]),
            ["before fence"],
        )

    def test_leading_plain_line_promoted_to_first_item(self) -> None:
        # NOTE: pinned current behavior. A non-bullet line is only taken when no
        # items have been collected yet (`elif items: continue`), so the first
        # plain text line becomes an item while later plain lines are skipped.
        doc = (
            "## Risks\n"
            "Intro sentence taken as item.\n"
            "- bullet one\n"
            "Later plain line is skipped.\n"
            "- bullet two\n"
        )
        self.assertEqual(
            text_mod.markdown_section_items(doc, ["risk"]),
            ["Intro sentence taken as item.", "bullet one", "bullet two"],
        )


if __name__ == "__main__":
    unittest.main()
