"""Pure console-presentation helpers (color, status styling, human formatting).

Extracted from harness.py. These functions have no dependency on harness runtime
state, so they live as a standalone leaf module that both harness.py and the core
modules can import.
"""
from __future__ import annotations

import os
import sys

from .status import RunStatus

COLOR_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
}


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)() or getattr(sys.stderr, "isatty", lambda: False)())


def color_text(text: str, *styles: str) -> str:
    if not color_enabled() or not styles:
        return text
    codes = [COLOR_CODES[style] for style in styles if style in COLOR_CODES]
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def event_line_for_console(line: str, event: str) -> str:
    event = event.lower()
    if "blocked" in event or "failed" in event:
        return color_text(line, "red", "bold")
    if "complete" in event or "created" in event or "advanced" in event or "approved" in event:
        return color_text(line, "green")
    if "started" in event or event in {"auto_step", "prompt_generated"}:
        return color_text(line, "cyan")
    if "retry" in event or "skipped" in event or "warning" in event:
        return color_text(line, "yellow")
    return line


def status_style(status: str) -> tuple[str, ...]:
    status = status.lower()
    if status in {RunStatus.COMPLETE, RunStatus.MODEL_COMPLETED}:
        return ("green", "bold")
    if status in {RunStatus.BLOCKED}:
        return ("red", "bold")
    if status in {RunStatus.MODEL_RUNNING, RunStatus.WAITING_FOR_MODEL}:
        return ("cyan", "bold")
    if status in {RunStatus.CREATED}:
        return ("yellow", "bold")
    return ("bold",)


def format_duration(seconds: float) -> str:
    seconds_i = max(0, int(seconds))
    hours, rem = divmod(seconds_i, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
