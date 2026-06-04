from __future__ import annotations

import importlib.metadata
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import HarnessError


REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class MissingRequirement:
    name: str
    line_no: int
    line: str


class HarnessRequirementsError(HarnessError):
    pass


def requirements_path(root: Path) -> Path:
    return root / ".ai" / "requirements.txt"


def requirement_name(line: str) -> str | None:
    cleaned = line.strip()
    if not cleaned or cleaned.startswith("#"):
        return None
    if cleaned.startswith(("-", "http://", "https://", "git+")):
        return None

    cleaned = cleaned.split(";", 1)[0].strip()
    cleaned = re.split(r"\s+#", cleaned, maxsplit=1)[0].strip()
    match = REQUIREMENT_NAME_RE.match(cleaned)
    if not match:
        return None
    return match.group(1)


def missing_requirements(root: Path) -> list[MissingRequirement]:
    path = requirements_path(root)
    if not path.exists():
        return []

    missing: list[MissingRequirement] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        name = requirement_name(line)
        if not name:
            continue
        try:
            importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(MissingRequirement(name=name, line_no=line_no, line=line.strip()))
    return missing


def ensure_requirements_installed(root: Path) -> None:
    missing = missing_requirements(root)
    if not missing:
        return

    rel_path = ".ai\\requirements.txt"
    missing_lines = "\n".join(
        f"  - {item.name} ({rel_path}:{item.line_no}, {item.line})"
        for item in missing
    )
    raise HarnessRequirementsError(
        "Missing harness Python requirements.\n\n"
        f"{missing_lines}\n\n"
        "Install the harness dependencies first:\n"
        f"  python -m pip install -r {rel_path}\n\n"
        "Then rerun the harness command."
    )
