from __future__ import annotations

import zipfile
from pathlib import Path


def validate_docx_file(path: Path, display_path: str | None = None) -> str | None:
    shown = display_path or str(path)
    if not path.exists():
        return f"Missing document artifact: {shown}"
    if not path.is_file():
        return f"Document artifact is not a file: {shown}"

    try:
        with path.open("rb") as fh:
            signature = fh.read(2)
    except OSError as exc:
        return f"Cannot read document artifact {shown}: {exc}"

    if signature != b"PK":
        return (
            f"Invalid .docx artifact {shown}: expected ZIP/OOXML signature "
            f"'PK', got {signature!r}. Do not save Markdown/plain text with a .docx extension."
        )

    if not zipfile.is_zipfile(path):
        return f"Invalid .docx artifact {shown}: file is not a valid ZIP archive."

    required_entries = {"[Content_Types].xml", "word/document.xml"}
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            missing = sorted(required_entries - names)
            if missing:
                return (
                    f"Invalid .docx artifact {shown}: missing OOXML entries "
                    f"{', '.join(missing)}."
                )
            if not zf.read("word/document.xml").strip():
                return f"Invalid .docx artifact {shown}: word/document.xml is empty."
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        return f"Invalid .docx artifact {shown}: {exc}"

    return None

