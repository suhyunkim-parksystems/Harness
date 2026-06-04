"""Canonical status string constants (stage-result and run-lifecycle).

Extracted from harness.py / core modules. These are plain *string-valued*
constants, deliberately NOT an ``enum.Enum``: every existing ``==`` / ``in`` /
set-membership comparison and JSON round-trip keeps byte-identical behavior
because the constant simply *is* the string it replaces.

The values are the literal strings that were already in use. The selftests keep
asserting those literals directly, so they act as an independent oracle that
these constants did not silently drift from the originals.

Only genuine *status values* are constant-ised. Strings that merely share the
same spelling but mean something else (event-name substrings in
``event_line_for_console``, the ``state["blocked"]`` info-dict key, the
``"blocked"`` / ``"complete"`` event names passed to ``log_event``) are left as
literals on purpose -- they are different concepts that happen to overlap.
"""
from __future__ import annotations


class ResultStatus:
    """Status reported by a stage model in its result JSON."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    NEEDS_USER = "NEEDS_USER"


class RunStatus:
    """Lifecycle status stored in ``state["status"]``."""

    CREATED = "created"
    WAITING_FOR_MODEL = "waiting_for_model"
    MODEL_RUNNING = "model_running"
    MODEL_COMPLETED = "model_completed"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    PC_CANDIDATES_PENDING = "pc_candidates_pending"
