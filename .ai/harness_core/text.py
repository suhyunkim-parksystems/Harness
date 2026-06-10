from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


def norm_repo_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = "feature-" + datetime.now().strftime("%Y%m%d%H%M%S")
    return text[:60].strip("-") or "feature-" + datetime.now().strftime("%Y%m%d%H%M%S")


def validate_slug(slug: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", slug))


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def compact_history_text(value: Any, max_len: int = 240) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower() in {"", "none", "n/a", "na", "null", "[]", "{}"}:
        return ""
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def history_list(value: Any, max_items: int = 40) -> list[str]:
    items: list[str] = []

    def add(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                add(child)
            return
        if isinstance(item, dict):
            title = (
                item.get("title")
                or item.get("summary")
                or item.get("description")
                or item.get("risk")
                or item.get("decision")
                or item
            )
            text = compact_history_text(title)
        else:
            text = compact_history_text(item)
        if text and text not in items:
            items.append(text)

    add(value)
    return items[:max_items]


def history_object_list(value: Any, title_keys: list[str], max_items: int = 40) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []

    def add(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                add(child)
            return
        if isinstance(item, dict):
            copied = dict(item)
            title = next((copied.get(key) for key in title_keys if copied.get(key)), None)
            copied["title"] = compact_history_text(title or copied.get("title") or copied)
        else:
            copied = {"title": compact_history_text(item)}
        if copied["title"] and copied["title"] not in {obj.get("title") for obj in objects}:
            objects.append(copied)

    add(value)
    return objects[:max_items]


def markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = re.match(r"^##+\s+(.+?)\s*$", line)
        if match:
            current = str(match.group(1) or "").strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def section_matches(heading: str, needles: list[str]) -> bool:
    lower = heading.lower()
    return any(needle.lower() in lower for needle in needles)


def markdown_section_items(text: str, heading_needles: list[str], max_items: int = 20) -> list[str]:
    items: list[str] = []
    for heading, body in markdown_sections(text).items():
        if not section_matches(heading, heading_needles):
            continue
        in_fence = False
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not line or line.startswith("|") or set(line) <= {"-", " "}:
                continue
            if line.startswith("- "):
                line = line[2:].strip()
            elif line.startswith("* "):
                line = line[2:].strip()
            elif re.match(r"^\d+\.\s+", line):
                line = re.sub(r"^\d+\.\s+", "", line).strip()
            elif items:
                continue
            text_item = compact_history_text(line)
            if text_item and text_item not in items:
                items.append(text_item)
            if len(items) >= max_items:
                return items
    return items

