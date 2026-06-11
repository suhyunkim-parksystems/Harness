"""Unit tests for harness_core/frontmatter.py.

Covers the minimal YAML-ish frontmatter parser: well-formed scalars and lists,
documents without frontmatter, the missing-closing-delimiter case (pinned
as-is: the whole text is returned as the body with empty meta), CRLF inputs,
and parse_scalar coercion rules (quoted strings, booleans; integers stay
strings — pinned with # NOTE).
"""
from __future__ import annotations

import unittest

from support import ensure_ai_path

ensure_ai_path()

from harness_core.frontmatter import parse_frontmatter, parse_scalar  # noqa: E402


class ParseFrontmatterTests(unittest.TestCase):
    def test_well_formed_scalars_and_list(self) -> None:
        text = (
            "---\n"
            'title: "My Feature"\n'
            "enabled: true\n"
            "count: 42\n"
            "tags:\n"
            '  - "alpha"\n'
            "  - beta\n"
            "---\n"
            "# Body\n"
            "content line\n"
        )
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["title"], "My Feature")
        self.assertIs(meta["enabled"], True)
        # NOTE: pinned current behavior — parse_scalar performs no numeric
        # coercion, so integers stay strings.
        self.assertEqual(meta["count"], "42")
        self.assertEqual(meta["tags"], ["alpha", "beta"])
        self.assertEqual(body, "# Body\ncontent line\n")

    def test_blank_lines_inside_frontmatter_skipped(self) -> None:
        text = "---\nkey: value\n\nother: x\n---\nbody\n"
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta, {"key": "value", "other": "x"})
        self.assertEqual(body, "body\n")

    def test_no_frontmatter_returns_empty_meta_and_full_body(self) -> None:
        text = "# Just a document\nwith content\n"
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_missing_closing_delimiter_returns_text_unchanged(self) -> None:
        # NOTE: pinned current behavior — when the closing '---' is missing the
        # parser bails out entirely: meta is empty and the ORIGINAL text
        # (including the opening '---' and would-be meta lines) is the body.
        text = "---\ntitle: dangling\nno closing delimiter\n"
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_crlf_line_endings(self) -> None:
        text = "---\r\ntitle: crlf doc\r\nflag: false\r\n---\r\nbody line\r\n"
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["title"], "crlf doc")
        self.assertIs(meta["flag"], False)
        # splitlines + '\n'.join normalizes the body to LF endings.
        self.assertEqual(body, "body line\n")

    def test_empty_value_starts_a_list_even_if_no_items_follow(self) -> None:
        text = "---\ntags:\nnext: value\n---\nbody\n"
        meta, _body = parse_frontmatter(text)
        self.assertEqual(meta["tags"], [])
        self.assertEqual(meta["next"], "value")

    def test_value_containing_colon_splits_only_on_first(self) -> None:
        text = "---\nurl: http://example.test/path\n---\nbody\n"
        meta, _body = parse_frontmatter(text)
        self.assertEqual(meta["url"], "http://example.test/path")


class ParseScalarTests(unittest.TestCase):
    def test_quoted_string_unwrapped(self) -> None:
        self.assertEqual(parse_scalar('"hello world"'), "hello world")
        self.assertEqual(parse_scalar('""'), "")

    def test_booleans_case_insensitive(self) -> None:
        self.assertIs(parse_scalar("true"), True)
        self.assertIs(parse_scalar("TRUE"), True)
        self.assertIs(parse_scalar("false"), False)
        self.assertIs(parse_scalar("False"), False)

    def test_integer_stays_string(self) -> None:
        # NOTE: pinned current behavior — there is no int/float conversion.
        self.assertEqual(parse_scalar("42"), "42")
        self.assertEqual(parse_scalar("3.14"), "3.14")

    def test_unquoted_string_passthrough_with_strip(self) -> None:
        self.assertEqual(parse_scalar("  plain value  "), "plain value")


if __name__ == "__main__":
    unittest.main()
