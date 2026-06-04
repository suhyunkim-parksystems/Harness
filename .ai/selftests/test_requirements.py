from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import ensure_ai_path


ensure_ai_path()

from harness_core import requirements  # noqa: E402


class RequirementsSelfTests(unittest.TestCase):
    def test_requirement_name_parses_simple_requirement_lines(self) -> None:
        self.assertEqual(requirements.requirement_name("python-docx>=1.2.0"), "python-docx")
        self.assertEqual(requirements.requirement_name("PyMuPDF>=1.24.0  # pdf support"), "PyMuPDF")
        self.assertIsNone(requirements.requirement_name(""))
        self.assertIsNone(requirements.requirement_name("# comment"))
        self.assertIsNone(requirements.requirement_name("-r other-requirements.txt"))

    def test_missing_requirements_reports_uninstalled_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            req_dir = root / ".ai"
            req_dir.mkdir()
            req = req_dir / "requirements.txt"
            req.write_text(
                "# test requirements\n"
                "definitely-missing-harness-package-xyz>=1.0\n",
                encoding="utf-8",
            )

            missing = requirements.missing_requirements(root)

        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].name, "definitely-missing-harness-package-xyz")


if __name__ == "__main__":
    unittest.main()
