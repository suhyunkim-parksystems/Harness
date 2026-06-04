from __future__ import annotations

from typing import Any


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    meta_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :]) + "\n"
    meta: dict[str, Any] = {}
    current_key: str | None = None
    for line in meta_lines:
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            meta.setdefault(current_key, []).append(parse_scalar(line[4:].strip()))
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                meta[key] = []
                current_key = key
            else:
                meta[key] = parse_scalar(value)
                current_key = key
    return meta, body


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value

