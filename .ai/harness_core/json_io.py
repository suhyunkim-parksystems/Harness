from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def loads_json_text(text: str) -> Any:
    """Parse JSON text while tolerating a UTF-8 BOM at the start."""
    return json.loads(text.lstrip("\ufeff"))


def read_json_value_file(path: Path) -> Any:
    """Read JSON from disk while accepting UTF-8 files with or without BOM."""
    return loads_json_text(path.read_text(encoding="utf-8-sig"))


def replace_with_retry(source: Path, target: Path, *, attempts: int = 10) -> None:
    """os.replace with a short retry loop.

    On Windows the atomic rename can transiently fail with EACCES when an
    antivirus/indexer briefly holds the freshly written file or the target.
    Retrying for a moment keeps the atomicity guarantee without surfacing a
    spurious PermissionError to the caller."""
    delay = 0.05
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.5)


def write_json_file(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=4) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    replace_with_retry(tmp, path)


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return read_json_value_file(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default

