"""Single source of truth for per-pipeline-mode parameters.

Previously the fast/standard/full pipelines were expressed as ~12 module
globals assigned by hand in three places (harness.py defaults plus
harness_fast.py / harness_standard.py mutation blocks) and as scattered
``mode == "..."`` string comparisons spread across the core modules. Adding or
changing a mode meant hunting down every one of those sites.

This module centralizes all of that into one ``PipelineConfig`` per mode in the
``PIPELINES`` registry, plus a few pure lookup helpers. harness.py binds its
module globals from a config via ``apply_pipeline``; the core modules consume
the derived predicates (``extracts_pc_candidates``, ``harness_script``,
``supports_deep_thinking``) through the helpers here.

Pure data and lookups only: this module imports nothing from the harness so it
is safe to import from any core module without risking a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class PipelineConfig:
    mode: str
    presets_subdir: str
    stages: tuple[str, ...]
    stage_outputs: Mapping[str, str]
    start_stage: str
    develop_stage: Optional[str]
    verify_stage: str
    verify_retry_target_stage: Optional[str]
    fix_stage: Optional[str]
    document_stage: Optional[str]
    # Path string suggested in user-facing commands for this mode. Kept as a
    # literal (with Windows separators) to match the historical output exactly.
    harness_script: str
    # Whether the pipeline extracts Project Contract candidates on completion.
    extracts_pc_candidates: bool
    # Whether the pipeline exposes the multi-provider deep-thinking plan path.
    supports_deep_thinking: bool


PIPELINES: dict[str, PipelineConfig] = {
    "fast": PipelineConfig(
        mode="fast",
        presets_subdir="fast",
        stages=("00_specify", "01_develop", "02_verify"),
        stage_outputs={
            "00_specify": "00_spec.md",
            "01_develop": "01_dev.md",
            "02_verify": "02_verify.md",
        },
        start_stage="00_specify",
        develop_stage="01_develop",
        verify_stage="02_verify",
        verify_retry_target_stage="01_develop",
        fix_stage=None,
        document_stage=None,
        harness_script=".ai/harness_fast.py",
        extracts_pc_candidates=False,
        supports_deep_thinking=False,
    ),
    "standard": PipelineConfig(
        mode="standard",
        presets_subdir="standard",
        stages=("00_specify", "01_develop", "02_review", "03_fix", "04_verify"),
        stage_outputs={
            "00_specify": "00_spec.md",
            "01_develop": "01_dev.md",
            "02_review": "02_review.md",
            "03_fix": "03_fix.md",
            "04_verify": "04_verify.md",
        },
        start_stage="00_specify",
        develop_stage="01_develop",
        verify_stage="04_verify",
        verify_retry_target_stage="03_fix",
        fix_stage="03_fix",
        document_stage=None,
        harness_script=".ai/harness_standard.py",
        extracts_pc_candidates=True,
        supports_deep_thinking=False,
    ),
    "full": PipelineConfig(
        mode="full",
        presets_subdir="full",
        stages=(
            "00_specify",
            "01_plan",
            "02_develop",
            "03_review",
            "04_fix",
            "05_verify",
            "06_document",
        ),
        stage_outputs={
            "00_specify": "00_spec.md",
            "01_plan": "01_plan.md",
            "02_develop": "02_dev.md",
            "03_review": "03_review.md",
            "04_fix": "04_fix.md",
            "05_verify": "05_verify.md",
            "06_document": "06_document.md",
        },
        start_stage="00_specify",
        develop_stage="02_develop",
        verify_stage="05_verify",
        verify_retry_target_stage="04_fix",
        fix_stage="04_fix",
        document_stage="06_document",
        harness_script=".ai/harness.py",
        extracts_pc_candidates=True,
        supports_deep_thinking=True,
    ),
}

# Mode used as the fallback for unknown/empty values in lookups below. Matches
# the historical default branch (the full harness script / behavior).
DEFAULT_MODE = "full"


def _norm(mode: object) -> str:
    return str(mode or "").strip()


def get(mode: object) -> Optional[PipelineConfig]:
    """Return the PipelineConfig for ``mode``, or None if unknown."""
    return PIPELINES.get(_norm(mode))


def extracts_pc_candidates(mode: object) -> bool:
    config = get(mode)
    return bool(config.extracts_pc_candidates) if config else False


def harness_script(mode: object) -> str:
    config = get(mode)
    return config.harness_script if config else PIPELINES[DEFAULT_MODE].harness_script


def supports_deep_thinking(mode: object) -> bool:
    config = get(mode)
    return bool(config.supports_deep_thinking) if config else False
