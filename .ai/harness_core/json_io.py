from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def loads_json_text(text: str) -> Any:
    """Parse JSON text while tolerating a UTF-8 BOM at the start."""
    return json.loads(text.lstrip("\ufeff"))


def read_json_value_file(path: Path) -> Any:
    """Read JSON from disk while accepting UTF-8 files with or without BOM."""
    return loads_json_text(path.read_text(encoding="utf-8-sig"))


def write_json_file(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=4) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return read_json_value_file(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default

