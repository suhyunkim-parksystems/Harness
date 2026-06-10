"""Unit tests for harness_core/docx_validation.py.

``validate_docx_file`` is a real correctness gate: it rejects artifacts that
claim a .docx extension but are not valid OOXML (a common failure mode where a
provider writes Markdown/plain text and renames it). The function is pure and
self-contained, so the tests build real fixtures (plain files, hand-rolled ZIP
archives, valid minimal .docx) in a temp directory and assert each rejection
branch plus the success path. It returns ``None`` on success and an error string
otherwise.
"""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from support import ensure_ai_path

ensure_ai_path()

from harness_core.docx_validation import validate_docx_file  # noqa: E402

REQUIRED_ENTRIES = {"[Content_Types].xml", "word/document.xml"}


def _write_docx(path: Path, *, entries: dict[str, bytes] | None = None) -> None:
    payload = (
        entries
        if entries is not None
        else {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<w:document><w:body/></w:document>",
        }
    )
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in payload.items():
            zf.writestr(name, data)


class ValidateDocxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_missing_file(self) -> None:
        error = validate_docx_file(self.root / "nope.docx")
        self.assertIsNotNone(error)
        self.assertIn("Missing document artifact", error or "")

    def test_path_is_directory(self) -> None:
        sub = self.root / "adir.docx"
        sub.mkdir()
        error = validate_docx_file(sub)
        self.assertIn("not a file", error or "")

    def test_plain_text_rejected_by_signature(self) -> None:
        path = self.root / "fake.docx"
        path.write_text("# Just markdown pretending to be a docx\n", encoding="utf-8")
        error = validate_docx_file(path)
        self.assertIn("expected ZIP/OOXML signature", error or "")

    def test_pk_signature_but_not_a_zip(self) -> None:
        path = self.root / "truncated.docx"
        # Starts with the ZIP magic but is not a parseable archive.
        path.write_bytes(b"PK\x03\x04 not really a zip")
        error = validate_docx_file(path)
        self.assertIn("not a valid ZIP archive", error or "")

    def test_zip_missing_required_ooxml_entries(self) -> None:
        path = self.root / "incomplete.docx"
        _write_docx(path, entries={"random.txt": b"hello"})
        error = validate_docx_file(path)
        self.assertIn("missing OOXML entries", error or "")
        # both required entries should be named in the message
        for entry in REQUIRED_ENTRIES:
            self.assertIn(entry, error or "")

    def test_zip_with_empty_document_xml(self) -> None:
        path = self.root / "empty-body.docx"
        _write_docx(
            path,
            entries={"[Content_Types].xml": b"<Types/>", "word/document.xml": b"   \n\t  "},
        )
        error = validate_docx_file(path)
        self.assertIn("word/document.xml is empty", error or "")

    def test_valid_docx_passes(self) -> None:
        path = self.root / "good.docx"
        _write_docx(path)
        self.assertIsNone(validate_docx_file(path))

    def test_display_path_used_in_message(self) -> None:
        error = validate_docx_file(self.root / "hidden.docx", display_path="features/x/report.docx")
        self.assertIn("features/x/report.docx", error or "")
        self.assertNotIn(str(self.root), error or "")


if __name__ == "__main__":
    unittest.main()
