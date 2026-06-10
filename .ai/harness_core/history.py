from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import HarnessRuntime

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .errors import HarnessError
from .json_io import read_json_value_file
from .status import ResultStatus


PC_CANDIDATE_EXTRACTION_MAX_ATTEMPTS = 3


def history_summary_path(ctx: HarnessRuntime) -> Path:
    return ctx.HISTORY_DIR / "summary.md"


def history_index_path(ctx: HarnessRuntime) -> Path:
    return ctx.HISTORY_DIR / "index.json"


def pc_candidates_path(ctx: HarnessRuntime) -> Path:
    return ctx.PC_CANDIDATES_PATH


def project_contract_path(ctx: HarnessRuntime) -> Path:
    return ctx.PROJECT_CONTRACT_PATH


def empty_pc_candidates_store(ctx: HarnessRuntime) -> dict[str, Any]:
    return {"version": ctx.PC_CANDIDATES_SCHEMA_VERSION, "candidates": []}


def read_pc_candidates_store(ctx: HarnessRuntime) -> dict[str, Any]:
    path = pc_candidates_path(ctx)
    if not path.exists():
        return empty_pc_candidates_store(ctx)
    try:
        parsed = read_json_value_file(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HarnessError(f"Invalid PC candidates JSON: {ctx.rel(path)}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HarnessError(f"PC candidates file must be a JSON object: {ctx.rel(path)}")
    candidates = parsed.get("candidates", [])
    if not isinstance(candidates, list):
        raise HarnessError(f"PC candidates file must contain a candidates list: {ctx.rel(path)}")
    parsed["version"] = parsed.get("version") or ctx.PC_CANDIDATES_SCHEMA_VERSION
    parsed["candidates"] = [item for item in candidates if isinstance(item, dict)]
    return parsed


def write_pc_candidates_store(ctx: HarnessRuntime, store: dict[str, Any]) -> None:
    candidates = store.get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []
    ctx.write_json_file(
        pc_candidates_path(ctx),
        {
            "version": store.get("version") or ctx.PC_CANDIDATES_SCHEMA_VERSION,
            "candidates": candidates,
        },
    )


def pending_pc_candidates(ctx: HarnessRuntime) -> list[dict[str, Any]]:
    store = read_pc_candidates_store(ctx)
    return [
        item
        for item in store.get("candidates", [])
        if str(item.get("status") or "").strip() == ctx.PC_PENDING_STATUS
    ]


def ensure_project_contract_file(ctx: HarnessRuntime) -> None:
    path = project_contract_path(ctx)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Project Contract\n\n"
        "## Hard Rules\n"
        "- 모델은 Git commit, amend, reset, checkout, rebase, push를 직접 실행하지 않는다.\n"
        "- 기존 테스트를 삭제하거나 비활성화하지 않는다.\n"
        "- 요청 범위를 벗어난 리팩터링, 의존성 추가, 파일 이동은 하지 않는다.\n"
        "- 기존 코드와의 하위 호환성을 우선한다. 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 깨뜨리는 변경은 명시적으로 기록하고 사용자 승인을 받는다.\n"
        "\n"
        "## Project Layout\n"
        "- 프로덕션 코드는 루트 `src/` 하위에 둔다.\n"
        "- 테스트 코드는 루트 `tests/` 하위에 둔다.\n"
        "- 새 테스트 파일을 `src/` 하위에 만들지 않는다.\n"
        "\n"
        "## Code Style\n"
        "- 새 코드는 같은 디렉터리의 기존 패턴, 네이밍, 파일 구조를 우선 따른다.\n"
        "- 프로젝트에 이미 명확한 네이밍 관례가 없으면 변수와 함수는 camelCase를 기본으로 한다.\n"
        "- 함수 이름은 가능하면 동사 또는 동사구로 시작한다. 예: `loadConfig`, `validateInput`, `renderItem`.\n"
        "- Boolean 값과 Boolean 반환 함수는 `is`, `has`, `can`, `should` 같은 의미 있는 접두사를 사용한다.\n"
        "- 이벤트 핸들러는 `handle` 또는 기존 프로젝트의 이벤트 네이밍 패턴을 따른다.\n"
        "- 값을 변환하는 함수는 `to`, `from`, `parse`, `format`, `normalize`처럼 변환 의도가 드러나는 이름을 사용한다.\n"
        "- 데이터를 가져오는 함수는 `get`, `load`, `fetch`, `read` 중 실제 동작에 맞는 동사를 사용한다.\n"
        "- 부수효과가 있는 함수는 `save`, `write`, `update`, `delete`, `send`, `create`처럼 변경 의도가 드러나는 동사를 사용한다.\n"
        "- 구현이 30줄을 넘어가면 함수나 작은 단위로 분리한다.\n"
        "- 서비스레이어를 두어서 유지보수를 좋게하라.\n"
        "\n"
        "## Reliability\n"
        "- 외부 입력, 파일, 네트워크, 프로세스 실행 결과는 실패 가능성을 명시적으로 처리한다.\n",
        encoding="utf-8",
    )


def project_contract_prompt_text(ctx: HarnessRuntime) -> str:
    ensure_project_contract_file(ctx)
    path = project_contract_path(ctx)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return (
            "## Project Contract\n"
            "No approved project contract exists yet. Follow the existing codebase conventions.\n"
        )
    return f"## Project Contract\nSource: {ctx.rel(path)}\n\n{text}\n"


def warn_pending_pc_candidates_for_new_run(ctx: HarnessRuntime) -> None:
    pending = pending_pc_candidates(ctx)
    if not pending:
        return
    lines = [
        ctx.color_text("Project Contract 후보 경고", "yellow", "bold"),
        "",
        (
            "미정 상태의 Project Contract 후보가 "
            f"{ctx.color_text(str(len(pending)), 'yellow', 'bold')}개 있습니다."
        ),
        "새 파이프라인은 계속 시작하지만, 시간이 날 때 후보를 검토해 프로젝트 규약을 정리하세요.",
        "",
        ctx.color_text("선택 검토 명령:", "green", "bold"),
        "  python .ai/pc_review.py",
        "  python .ai/pc_review.py --agent claude  # optional: codex/claude/agy",
        "",
        ctx.color_text("미정 후보:", "yellow", "bold"),
    ]
    for item in pending[:20]:
        lines.append(
            "  - "
            f"{item.get('id', '-')}: "
            f"{ctx.compact_history_text(item.get('rule_candidate') or item.get('summary'), max_len=160)}"
        )
    if len(pending) > 20:
        lines.append(f"  - ... and {len(pending) - 20} more")
    print("\n".join(lines), file=sys.stderr)


def ensure_history_store(ctx: HarnessRuntime) -> bool:
    initialized = not ctx.HISTORY_DIR.exists()
    ctx.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not history_index_path(ctx).exists():
        ctx.write_json_file(history_index_path(ctx), {"schema_version": ctx.HISTORY_SCHEMA_VERSION, "features": []})
        initialized = True
    if not pc_candidates_path(ctx).exists():
        write_pc_candidates_store(ctx, empty_pc_candidates_store(ctx))
        initialized = True
    if not history_summary_path(ctx).exists():
        history_summary_path(ctx).write_text(
            "# 프로젝트 히스토리\n\n"
            "로컬 하네스가 자동 생성한 완료 run 인덱스 요약입니다.\n",
            encoding="utf-8",
        )
        initialized = True
    return initialized


def history_timestamp_id(ctx: HarnessRuntime, value: Any) -> str:
    stamp = re.sub(r"\D+", "", str(value or ""))[:14]
    return stamp or ctx.now_stamp().replace("-", "")


def history_event_id(ctx: HarnessRuntime, state: dict[str, Any]) -> str:
    feature = ctx.slugify(str(state.get("feature_name") or "feature"))
    pipeline = ctx.slugify(str(state.get("pipeline_mode") or ctx.PIPELINE_MODE))
    return f"{history_timestamp_id(ctx, state.get('created_at'))}-{feature}-{pipeline}"


def safe_stage_text(ctx: HarnessRuntime, feature: str, stage: str) -> str:
    path = ctx.stage_output_path(feature, stage)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_history_stage_results(ctx: HarnessRuntime, feature: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for stage in ctx.STAGES:
        result_path = ctx.stage_result_json_path(feature, stage)
        if result_path.exists():
            parsed = ctx.read_json_file(result_path, {})
            if isinstance(parsed, dict):
                results[stage] = parsed
                continue
        text = safe_stage_text(ctx, feature, stage)
        if text:
            parsed = ctx.find_stage_result(text)
            if parsed:
                results[stage] = parsed
    return results


def history_source_artifacts(ctx: HarnessRuntime, feature: str) -> list[str]:
    artifacts: list[str] = []
    for stage in ctx.STAGES:
        for path in [ctx.stage_output_path(feature, stage), ctx.stage_result_json_path(feature, stage)]:
            if path.exists():
                artifacts.append(ctx.rel(path))
    latest = ctx.latest_verification_result_path(feature)
    if latest.exists():
        artifacts.append(ctx.rel(latest))
    run_json = ctx.state_path(feature)
    if run_json.exists():
        artifacts.append(ctx.rel(run_json))
    return sorted(dict.fromkeys(artifacts))


def split_event_paths(ctx: HarnessRuntime, value: Any) -> list[str]:
    if isinstance(value, list):
        return [ctx.norm_repo_path(str(item)) for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    return [ctx.norm_repo_path(part.strip()) for part in value.split(",") if part.strip()]


def collect_history_changed_files(
    ctx: HarnessRuntime, state: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    paths: list[str] = []
    for result in stage_results.values():
        paths.extend(ctx.history_list(result.get("changed_files"), max_items=200))
        paths.extend(ctx.history_list(result.get("produced_files"), max_items=200))
    for event in state.get("events", []):
        if not isinstance(event, dict):
            continue
        if event.get("event") in {"commit_start", "commit_created", "commit_amended"}:
            paths.extend(split_event_paths(ctx, event.get("paths")))

    grouped = {"production": [], "tests": [], "harness_artifacts": [], "docs": [], "other": []}
    for raw_path in paths:
        path = ctx.norm_repo_path(raw_path)
        if not path or path in {".", "./"}:
            continue
        if path.startswith(".project/docs/"):
            bucket = "docs"
        elif path.startswith(".ai/") or path.startswith(".project/"):
            bucket = "harness_artifacts"
        elif ctx.is_test_path(path):
            bucket = "tests"
        elif ctx.is_production_code_path(path):
            bucket = "production"
        else:
            bucket = "other"
        if path not in grouped[bucket]:
            grouped[bucket].append(path)
    return {key: sorted(value) for key, value in grouped.items() if value}


def load_history_verification(ctx: HarnessRuntime, feature: str, stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    latest = ctx.latest_verification_result_path(feature)
    if latest.exists():
        parsed = ctx.read_json_file(latest, {})
        if isinstance(parsed, dict) and parsed:
            return {
                "status": parsed.get("status", "UNKNOWN"),
                "passed": bool(parsed.get("passed")),
                "failed_commands": parsed.get("failed_commands", []),
                "commands": [
                    command.get("name")
                    for command in parsed.get("commands", [])
                    if isinstance(command, dict) and command.get("name")
                ],
                "source": ctx.rel(latest),
            }

    verify_result = stage_results.get(ctx.VERIFY_STAGE, {})
    summary = verify_result.get("verification_summary")
    if isinstance(summary, dict):
        return {
            "status": summary.get("status", verify_result.get("status", "UNKNOWN")),
            "passed": str(summary.get("status", "")).upper() == ResultStatus.PASS,
            "failed_commands": [],
            "commands": [key for key in summary.keys() if key != "status"],
            "source": ctx.rel(ctx.stage_result_json_path(feature, ctx.VERIFY_STAGE)),
        }
    return {
        "status": verify_result.get("status", "UNKNOWN"),
        "passed": str(verify_result.get("status", "")).upper() == ResultStatus.PASS,
        "failed_commands": [],
        "commands": [],
        "source": ctx.rel(ctx.stage_result_json_path(feature, ctx.VERIFY_STAGE))
        if ctx.stage_result_json_path(feature, ctx.VERIFY_STAGE).exists()
        else "",
    }


def collect_history_notes(
    ctx: HarnessRuntime, feature: str,
    stage_results: dict[str, dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    implemented: list[str] = []
    risks: list[dict[str, Any]] = []
    future_improvements: list[str] = []
    decisions: list[dict[str, Any]] = []

    for stage, result in stage_results.items():
        source = ctx.rel(ctx.stage_output_path(feature, stage)) if ctx.stage_output_path(feature, stage).exists() else ""
        notes = result.get("history_notes") if isinstance(result.get("history_notes"), dict) else {}
        implemented.extend(ctx.history_list(result.get("implemented")))
        implemented.extend(ctx.history_list(notes.get("implemented") if notes else None))
        future_improvements.extend(ctx.history_list(result.get("future_improvements")))
        future_improvements.extend(ctx.history_list(notes.get("future_improvements") if notes else None))

        for item in ctx.history_object_list(result.get("risks"), ["title", "summary", "description", "risk"]) + ctx.history_object_list(
            notes.get("risks") if notes else None,
            ["title", "summary", "description", "risk"],
        ):
            item.setdefault("category", "risk")
            item["source_stage"] = item.get("source_stage") or stage
            item["source_artifact"] = item.get("source_artifact") or source
            risks.append(item)
        for item in ctx.history_object_list(result.get("known_limitations"), ["title", "summary", "description", "risk"]):
            item.setdefault("category", "known_limitation")
            item["source_stage"] = item.get("source_stage") or stage
            item["source_artifact"] = item.get("source_artifact") or source
            risks.append(item)

        fix_inputs = result.get("fix_inputs")
        if isinstance(fix_inputs, dict):
            deferred = ctx.history_list(fix_inputs.get("deferred"))
            future_improvements.extend(deferred)
            for item in deferred:
                risks.append(
                    {
                        "title": item,
                        "category": "future_improvement",
                        "source_stage": stage,
                        "source_artifact": source,
                    }
                )

        for item in ctx.history_object_list(result.get("decisions"), ["title", "summary", "description", "decision"]) + ctx.history_object_list(
            notes.get("decisions") if notes else None,
            ["title", "summary", "description", "decision"],
        ):
            item["source_stage"] = item.get("source_stage") or stage
            item["source_artifact"] = item.get("source_artifact") or source
            decisions.append(item)

        text = safe_stage_text(ctx, feature, stage)
        implemented.extend(
            ctx.markdown_section_items(
                text,
                ["implementation summary", "implemented", "implementation details", "changed files"],
            )
        )
        future_from_text = ctx.markdown_section_items(
            text,
            ["future", "follow-up", "known limitation", "remaining risk", "deferred"],
        )
        future_improvements.extend(future_from_text)
        for item in future_from_text:
            risks.append(
                {
                    "title": item,
                    "category": "future_improvement",
                    "source_stage": stage,
                    "source_artifact": source,
                }
            )
        for item in ctx.markdown_section_items(text, ["decision", "why", "alternative", "plan changed"]):
            decisions.append({"title": item, "source_stage": stage, "source_artifact": source})

    implemented = list(dict.fromkeys(item for item in implemented if item))
    future_improvements = list(dict.fromkeys(item for item in future_improvements if item))

    seen_risks: set[str] = set()
    deduped_risks: list[dict[str, Any]] = []
    for risk in risks:
        title = ctx.compact_history_text(risk.get("title"))
        if not title or title in seen_risks:
            continue
        seen_risks.add(title)
        risk["title"] = title
        deduped_risks.append(risk)

    seen_decisions: set[str] = set()
    deduped_decisions: list[dict[str, Any]] = []
    for decision in decisions:
        title = ctx.compact_history_text(decision.get("title"))
        if not title or title in seen_decisions:
            continue
        seen_decisions.add(title)
        decision["title"] = title
        deduped_decisions.append(decision)

    return implemented[:40], deduped_risks[:40], future_improvements[:40], deduped_decisions[:40]


def normalize_unresolved_source_item(
    ctx: HarnessRuntime, item: Any,
    *,
    item_type: str,
    status: str,
    disposition: str,
    source_stage: str,
    source_artifact: str,
    default_severity: str = "info",
) -> dict[str, Any] | None:
    if isinstance(item, dict):
        title = ctx.compact_history_text(
            item.get("title")
            or item.get("summary")
            or item.get("description")
            or item.get("finding")
            or item.get("warning")
            or item.get("item")
            or item
        )
        reason = ctx.compact_history_text(
            item.get("reason_not_actioned")
            or item.get("reason")
            or item.get("rationale")
            or item.get("rejection_reason")
            or item.get("defer_reason")
            or item.get("why")
        )
        future_action = ctx.compact_history_text(
            item.get("future_action")
            or item.get("future_improvement")
            or item.get("next_action")
            or item.get("mitigation")
        )
        severity = ctx.compact_history_text(item.get("severity") or default_severity, max_len=40)
        item_type = ctx.compact_history_text(item.get("type") or item_type, max_len=80)
        status = ctx.compact_history_text(item.get("status") or status, max_len=40)
        disposition = ctx.compact_history_text(item.get("disposition") or disposition, max_len=80)
        source_stage = ctx.compact_history_text(item.get("source_stage") or source_stage, max_len=80)
        source_artifact = ctx.compact_history_text(item.get("source_artifact") or source_artifact, max_len=300)
    else:
        title = ctx.compact_history_text(item)
        reason = ""
        future_action = ""
        severity = default_severity
    if not title:
        return None
    return {
        "title": title,
        "type": item_type,
        "severity": severity,
        "status": status,
        "disposition": disposition,
        "reason_not_actioned": reason,
        "future_action": future_action,
        "source_stage": source_stage,
        "source_artifact": source_artifact,
    }


def unresolved_items_from_value(
    ctx: HarnessRuntime, value: Any,
    *,
    item_type: str,
    status: str,
    disposition: str,
    source_stage: str,
    source_artifact: str,
    default_severity: str = "info",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if value is None:
        return items
    raw_items = value if isinstance(value, list) else [value]
    for raw_item in raw_items:
        normalized = normalize_unresolved_source_item(ctx, 
            raw_item,
            item_type=item_type,
            status=status,
            disposition=disposition,
            source_stage=source_stage,
            source_artifact=source_artifact,
            default_severity=default_severity,
        )
        if normalized and normalized["title"] not in {item["title"] for item in items}:
            items.append(normalized)
    return items


def collect_history_unresolved_items(
    ctx: HarnessRuntime, feature: str,
    stage_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for stage, result in stage_results.items():
        source = ctx.rel(ctx.stage_output_path(feature, stage)) if ctx.stage_output_path(feature, stage).exists() else ""
        notes = result.get("history_notes") if isinstance(result.get("history_notes"), dict) else {}

        items.extend(
            unresolved_items_from_value(ctx, 
                result.get("unresolved_items"),
                item_type="unresolved_item",
                status="open",
                disposition="not_actioned",
                source_stage=stage,
                source_artifact=source,
                default_severity="medium",
            )
        )
        items.extend(
            unresolved_items_from_value(ctx, 
                notes.get("unresolved_items") if notes else None,
                item_type="unresolved_item",
                status="open",
                disposition="not_actioned",
                source_stage=stage,
                source_artifact=source,
                default_severity="medium",
            )
        )
        items.extend(
            unresolved_items_from_value(ctx, 
                result.get("warnings") or result.get("warning"),
                item_type="warning",
                status="open",
                disposition="warning_only",
                source_stage=stage,
                source_artifact=source,
                default_severity="minor",
            )
        )

        fix_inputs = result.get("fix_inputs")
        if isinstance(fix_inputs, dict):
            items.extend(
                unresolved_items_from_value(ctx, 
                    fix_inputs.get("rejected"),
                    item_type="review_finding",
                    status="rejected",
                    disposition="rejected",
                    source_stage=stage,
                    source_artifact=source,
                    default_severity="minor",
                )
            )
            items.extend(
                unresolved_items_from_value(ctx, 
                    fix_inputs.get("deferred"),
                    item_type="review_finding",
                    status="deferred",
                    disposition="deferred",
                    source_stage=stage,
                    source_artifact=source,
                    default_severity="minor",
                )
            )
            items.extend(
                unresolved_items_from_value(ctx, 
                    fix_inputs.get("warnings"),
                    item_type="verification_warning",
                    status="open",
                    disposition="warning_only",
                    source_stage=stage,
                    source_artifact=source,
                    default_severity="minor",
                )
            )

        verification_summary = result.get("verification_summary")
        if isinstance(verification_summary, dict):
            notes_value = verification_summary.get("notes") or verification_summary.get("warning")
            if notes_value and str(result.get("status") or "").upper() == ResultStatus.PASS:
                items.extend(
                    unresolved_items_from_value(ctx, 
                        notes_value,
                        item_type="verification_note",
                        status="accepted",
                        disposition="pass_with_note",
                        source_stage=stage,
                        source_artifact=source,
                        default_severity="info",
                    )
                )

        text = safe_stage_text(ctx, feature, stage)
        for heading_needles, item_type, status, disposition, severity in [
            (["거부", "rejected", "not accepted"], "review_finding", "rejected", "rejected", "minor"),
            (["보류", "deferred", "future", "follow-up"], "review_finding", "deferred", "deferred", "minor"),
            (["warning", "경고"], "warning", "open", "warning_only", "minor"),
            (["should_consider", "minor", "nit"], "review_suggestion", "open", "not_actioned", "minor"),
        ]:
            for item in ctx.markdown_section_items(text, heading_needles, max_items=10):
                normalized = normalize_unresolved_source_item(ctx, 
                    item,
                    item_type=item_type,
                    status=status,
                    disposition=disposition,
                    source_stage=stage,
                    source_artifact=source,
                    default_severity=severity,
                )
                if normalized:
                    items.append(normalized)

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = "|".join(
            [
                ctx.compact_history_text(item.get("title"), max_len=500),
                ctx.compact_history_text(item.get("type"), max_len=80),
                ctx.compact_history_text(item.get("source_stage"), max_len=80),
            ]
        )
        if not key.strip("|") or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:80]


def stable_history_id(ctx: HarnessRuntime, prefix: str, *parts: Any) -> str:
    raw = "\n".join(ctx.compact_history_text(part, max_len=1000) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def read_history_index(ctx: HarnessRuntime) -> dict[str, Any]:
    index = ctx.read_json_file(history_index_path(ctx), {"schema_version": ctx.HISTORY_SCHEMA_VERSION, "features": []})
    if not isinstance(index, dict):
        return {"schema_version": ctx.HISTORY_SCHEMA_VERSION, "features": []}
    features = index.get("features")
    if not isinstance(features, list):
        index["features"] = []
    else:
        index["features"] = [item for item in features if isinstance(item, dict)]
    index["schema_version"] = ctx.HISTORY_SCHEMA_VERSION
    return index


def write_history_index(ctx: HarnessRuntime, index: dict[str, Any]) -> None:
    ctx.write_json_file(history_index_path(ctx), index)


def compact_history_titles(ctx: HarnessRuntime, items: list[Any], max_items: int = 5, max_len: int = 180) -> list[str]:
    if max_items <= 0:
        return []
    titles: list[str] = []
    for item in items:
        if isinstance(item, dict):
            value = (
                item.get("title")
                or item.get("summary")
                or item.get("description")
                or item.get("decision")
                or item.get("risk")
            )
        else:
            value = item
        title = ctx.compact_history_text(value, max_len=max_len)
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= max_items:
            break
    return titles


def history_document_path(ctx: HarnessRuntime, feature: str) -> str:
    if not ctx.DOCUMENT_STAGE:
        return ""
    doc = ctx.expected_docx_path(feature)
    return ctx.rel(doc) if doc.exists() else ""


def upsert_history_index_entry(ctx: HarnessRuntime, entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    index = read_history_index(ctx)
    features = index.setdefault("features", [])
    feature = str(entry.get("feature") or "")
    replaced = False
    for position, existing in enumerate(features):
        if isinstance(existing, dict) and existing.get("feature") == feature:
            features[position] = entry
            replaced = True
            break
    if not replaced:
        features.append(entry)
    features.sort(key=lambda item: str(item.get("completed_at") or ""), reverse=True)
    index["updated_at"] = ctx.iso_now()
    write_history_index(ctx, index)
    return index, not replaced


def render_history_summary(ctx: HarnessRuntime, index: dict[str, Any]) -> None:
    raw_features = index.get("features")
    features = raw_features if isinstance(raw_features, list) else []
    complete_features = [item for item in features if isinstance(item, dict)]
    lines = [
        "# 프로젝트 히스토리",
        "",
        "로컬 하네스가 자동 생성한 완료 run 인덱스 요약입니다.",
        "",
        f"- 기록된 feature: {len(complete_features)}",
        f"- 인덱스: {ctx.rel(history_index_path(ctx))}",
        f"- PC 후보: {ctx.rel(pc_candidates_path(ctx))}",
        "",
        "## 최근 완료 Run",
        "",
    ]
    if not complete_features:
        lines.append("- 없음")
    for entry in complete_features[:20]:
        verification = str(entry.get("verification") or "UNKNOWN")
        lines.append(
            "- "
            f"{entry.get('completed_at', '')} "
            f"{entry.get('feature', '')} "
            f"({entry.get('pipeline', '')}, {entry.get('status', '')}, verify={verification})"
        )
        raw_implemented = entry.get("implemented")
        implemented = raw_implemented if isinstance(raw_implemented, list) else []
        for item in implemented[:3]:
            lines.append(f"  - {item}")
    history_summary_path(ctx).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def record_project_history(ctx: HarnessRuntime, state: dict[str, Any]) -> dict[str, Any]:
    initialized = ensure_history_store(ctx)
    feature = str(state["feature_name"])
    stage_results = load_history_stage_results(ctx, feature)
    implemented, risks, future_improvements, decisions = collect_history_notes(ctx, feature, stage_results)
    verification = load_history_verification(ctx, feature, stage_results)
    completed_at = ctx.iso_now()
    event_id = history_event_id(ctx, state)
    risk_levels = [
        ctx.compact_history_text(result.get("risk_level"), max_len=40)
        for result in stage_results.values()
        if result.get("risk_level")
    ]
    risk_level = risk_levels[-1] if risk_levels else ""

    important_followups = compact_history_titles(ctx, future_improvements, max_items=5)
    medium_high_risks = [
        risk
        for risk in risks
        if isinstance(risk, dict)
        and str(risk.get("severity") or "low").strip().lower() in {"medium", "high", "critical"}
    ]
    important_followups.extend(
        item
        for item in compact_history_titles(ctx, medium_high_risks, max_items=5 - len(important_followups))
        if item not in important_followups
    )

    entry = {
        "schema_version": ctx.HISTORY_SCHEMA_VERSION,
        "event_id": event_id,
        "feature": feature,
        "pipeline": state.get("pipeline_mode") or ctx.PIPELINE_MODE,
        "status": state.get("status"),
        "created_at": state.get("created_at"),
        "completed_at": completed_at,
        "request_summary": ctx.compact_history_text(state.get("request"), max_len=800),
        "verification": verification.get("status", "UNKNOWN") if isinstance(verification, dict) else "UNKNOWN",
        "verification_source": verification.get("source", "") if isinstance(verification, dict) else "",
        "risk_level": risk_level,
        "feature_dir": ctx.rel(ctx.feature_dir(feature)),
        "run_dir": ctx.rel(ctx.run_dir(feature)),
        "doc": history_document_path(ctx, feature),
        "commits": state.get("commits", {}),
        "implemented": compact_history_titles(ctx, implemented, max_items=8),
        "important_followups": important_followups[:5],
        "important_decisions": compact_history_titles(ctx, decisions, max_items=5),
    }

    index, inserted = upsert_history_index_entry(ctx, entry)
    render_history_summary(ctx, index)

    state["history"] = {
        "schema_version": ctx.HISTORY_SCHEMA_VERSION,
        "event_id": event_id,
        "index": ctx.rel(history_index_path(ctx)),
        "summary": ctx.rel(history_summary_path(ctx)),
        "status": "recorded" if inserted else "updated",
        "recorded_at": completed_at,
        "history_initialized": initialized,
    }
    return state["history"]


def should_extract_pc_candidates(ctx: HarnessRuntime, state: dict[str, Any]) -> bool:
    return ctx.pipeline_extracts_pc_candidates(state.get("pipeline_mode") or ctx.PIPELINE_MODE)


def pc_candidate_source_artifact_text(ctx: HarnessRuntime, feature: str, max_chars_per_file: int = 8000) -> str:
    blocks: list[str] = []
    for artifact in history_source_artifacts(ctx, feature):
        path = ctx.ROOT / artifact
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > max_chars_per_file:
            text = text[:max_chars_per_file] + "\n...[truncated]"
        blocks.extend([f"### {artifact}", "```text", text, "```", ""])
    return "\n".join(blocks).strip() or "- none"


def build_pc_candidate_extraction_prompt(
    ctx: HarnessRuntime, state: dict[str, Any],
    output_json_path: Path | None = None,
) -> str:
    feature = str(state["feature_name"])
    stage_results = load_history_stage_results(ctx, feature)
    changed_files = collect_history_changed_files(ctx, state, stage_results)
    verification = load_history_verification(ctx, feature, stage_results)
    current_contract = project_contract_prompt_text(ctx)
    artifacts_text = pc_candidate_source_artifact_text(ctx, feature)
    existing_store = read_pc_candidates_store(ctx)
    existing_rule_candidates = [
        ctx.compact_history_text(item.get("rule_candidate"), max_len=240)
        for item in existing_store.get("candidates", [])
        if item.get("rule_candidate")
    ][-50:]
    capture_instructions = ""
    if output_json_path is not None:
        capture_instructions = f"""

## Required Capture File
Some providers do not reliably return print-mode text through stdout.
After producing the JSON object, write the exact same JSON object to this file:

- relative_path: {ctx.rel(output_json_path)}
- absolute_path: {output_json_path.resolve()}

Create parent directories if needed. Do not write any other files.
"""

    return f"""# Project Contract Candidate Extraction

You are extracting Project Contract candidates after a completed local AI development pipeline.

This is not a normal feature implementation task.
Do not edit repository source files, stage outputs, or project documentation.
Return only a JSON object in stdout. If a Required Capture File is specified, also write the same JSON object there.

## Goal
Find rules that should become candidates for the long-term Project Contract.
The Project Contract is observational: it is based on conventions and decisions that emerged from real development.

## Pipeline Context
- feature_name: {feature}
- pipeline_mode: {state.get("pipeline_mode") or ctx.PIPELINE_MODE}
- request: {state.get("request", "")}
- completed_at: {ctx.iso_now()}

## Current Approved Project Contract
{current_contract}

## Existing Candidate Summaries
{json.dumps(existing_rule_candidates, ensure_ascii=False, indent=2)}

## Changed Files Summary
{json.dumps(changed_files, ensure_ascii=False, indent=2)}

## Harness Verification
{json.dumps(verification, ensure_ascii=False, indent=2)}

## Source Artifacts
{artifacts_text}
{capture_instructions}

## Candidate Criteria
Create a candidate only when the rule is clearly worth managing as a project-wide contract.

The bar is intentionally high. A candidate must pass all of these:
- It applies across many future features or pipelines in this repository.
- It controls project-level engineering behavior, not a local implementation choice.
- It is likely to recur even when the exact feature, UI screen, or library changes.
- It is not already clearly covered by the current Project Contract.
- It belongs to a durable area such as naming, architecture, directory layout, testing policy, error handling, data boundaries, dependency policy, or cross-feature UX policy.

Before emitting anything, classify every observation internally:
- `project_wide`: broad project rule worth user review as Project Contract.
- `stack_wide`: useful only for one technology stack, framework, platform, or library.
- `feature_local`: useful only for this feature or domain.
- `implementation_detail`: small tactical implementation detail.

Emit only `project_wide` candidates.
Discard `stack_wide`, `feature_local`, and `implementation_detail`. Do not include them in the JSON.

Do not create candidates for:
- one-off implementation details
- framework-specific micro patterns unless the project has clearly standardized that stack globally
- UI control behavior that is merely a convenience for one screen
- performance tweaks tied to a single implementation
- obvious bug fixes
- temporary code
- rules already clearly covered by the current Project Contract
- weak observations with no future impact
- anything that would be better recorded as history than enforced as a future project rule

## Output Contract
Return exactly one JSON object. Do not wrap it in Markdown.

Schema:
{{
  "candidates": [
    {{
      "impact_scope": "project_wide",
      "category": "architecture | naming | ux | testing | error_handling | data | dependency | other",
      "rule_candidate": "A concise Korean rule phrased as something future work should do.",
      "rationale": "Why this is truly project-wide rather than stack-wide, feature-local, or an implementation detail.",
      "evidence": ["Relevant files, artifacts, or decisions."],
      "recommended_contract_section": "Hard Rules | Architecture | Naming | UX | Testing | Error Handling | Data | Dependencies | Other"
    }}
  ]
}}

If there are no worthwhile candidates, return {{"candidates": []}}.
"""


def normalize_pc_candidate(
    ctx: HarnessRuntime, raw: dict[str, Any],
    state: dict[str, Any],
    created_at: str,
    provider: str,
) -> dict[str, Any] | None:
    impact_scope = ctx.compact_history_text(raw.get("impact_scope") or raw.get("scope"), max_len=80)
    if impact_scope.strip().lower() != ctx.PC_PROJECT_WIDE_SCOPE:
        return None
    rule = ctx.compact_history_text(raw.get("rule_candidate") or raw.get("summary"), max_len=600)
    if not rule:
        return None
    category = ctx.compact_history_text(raw.get("category") or "other", max_len=80) or "other"
    feature = str(state["feature_name"])
    candidate_id = stable_history_id(ctx, "pc", feature, category, rule)
    evidence = ctx.history_list(raw.get("evidence"), max_items=40)
    return {
        "id": candidate_id,
        "status": ctx.PC_PENDING_STATUS,
        "source_feature": feature,
        "source_pipeline": state.get("pipeline_mode") or ctx.PIPELINE_MODE,
        "source_run_created_at": state.get("created_at", ""),
        "source_artifacts": history_source_artifacts(ctx, feature),
        "impact_scope": ctx.PC_PROJECT_WIDE_SCOPE,
        "category": category,
        "rule_candidate": rule,
        "rationale": ctx.compact_history_text(raw.get("rationale"), max_len=1000),
        "evidence": evidence,
        "recommended_contract_section": ctx.compact_history_text(
            raw.get("recommended_contract_section"),
            max_len=120,
        ),
        "created_at": created_at,
        "decided_at": "",
        "decision_reason": "",
        "extraction_model": provider,
    }


def append_pc_candidates(ctx: HarnessRuntime, candidates: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    store = read_pc_candidates_store(ctx)
    existing_ids = {
        str(item.get("id"))
        for item in store.get("candidates", [])
        if str(item.get("id") or "")
    }
    added: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "")
        if not candidate_id or candidate_id in existing_ids:
            continue
        store.setdefault("candidates", []).append(candidate)
        existing_ids.add(candidate_id)
        added.append(candidate)
    if added:
        write_pc_candidates_store(ctx, store)
    return {
        "status": "recorded",
        "path": ctx.rel(pc_candidates_path(ctx)),
        "added_count": len(added),
        "added_ids": [item["id"] for item in added],
    }


def _pc_candidate_run_window(result: dict[str, Any]) -> tuple[float, float] | None:
    finished_raw = str(result.get("finished_at") or "").strip()
    if not finished_raw:
        return None
    try:
        finished = datetime.fromisoformat(finished_raw)
        elapsed = float(result.get("elapsed_seconds") or 0)
    except (TypeError, ValueError):
        return None
    started = finished - timedelta(seconds=max(elapsed, 0) + 5)
    ended = finished + timedelta(seconds=15)
    return started.timestamp(), ended.timestamp()


def _parse_pc_candidate_json_path(ctx: HarnessRuntime, path: Path) -> dict[str, Any]:
    try:
        output_text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not output_text.strip():
        return {}
    return ctx.parse_result_json_from_text(output_text)


def _pc_candidate_capture_fallback_json(
    ctx: HarnessRuntime, output_path: Path,
    result: dict[str, Any],
) -> dict[str, Any]:
    match = re.match(r"^(pc_candidates_[A-Za-z0-9_.-]+)_attempt(\d+)_result\.json$", output_path.name)
    if not match:
        return {}
    run_window = _pc_candidate_run_window(result)
    if run_window is None:
        return {}

    prefix = match.group(1)
    expected_attempt = int(match.group(2))
    started_ts, ended_ts = run_window
    candidates: list[tuple[float, Path]] = []
    try:
        paths = output_path.parent.glob(f"{prefix}_attempt*_result.json")
    except OSError:
        return {}

    for path in paths:
        attempt_match = re.match(
            rf"^{re.escape(prefix)}_attempt(\d+)_result\.json$",
            path.name,
        )
        if not attempt_match:
            continue
        if int(attempt_match.group(1)) > expected_attempt:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if started_ts <= mtime <= ended_ts:
            candidates.append((mtime, path))

    for _, path in sorted(candidates, key=lambda item: item[0], reverse=True):
        parsed = _parse_pc_candidate_json_path(ctx, path)
        if isinstance(parsed.get("candidates"), list):
            return parsed
    return {}


def parse_pc_candidate_extraction_result(ctx: HarnessRuntime, result: dict[str, Any]) -> list[Any]:
    if result.get("returncode") != 0 or result.get("timed_out"):
        raise HarnessError(
            "PC candidate extraction provider failed. "
            f"stdout={result.get('stdout')} stderr={result.get('stderr')}"
        )

    parsed = ctx.parse_result_json_from_text(str(result.get("stdout_text") or ""))
    if not parsed:
        raw_output_path = str(result.get("json_output") or "").strip()
        if raw_output_path:
            output_path = ctx.ROOT / ctx.norm_repo_path(raw_output_path)
            parsed = _parse_pc_candidate_json_path(ctx, output_path)
            if not parsed:
                parsed = _pc_candidate_capture_fallback_json(ctx, output_path, result)
    raw_candidates = parsed.get("candidates") if isinstance(parsed, dict) else None
    if raw_candidates is None:
        raise HarnessError(
            "PC candidate extraction did not return a JSON object with a candidates list. "
            f"stdout={result.get('stdout')} json_output={result.get('json_output')}"
        )
    if not isinstance(raw_candidates, list):
        raise HarnessError("PC candidate extraction field 'candidates' must be a list.")
    return raw_candidates


def pc_candidate_extraction_warning(
    ctx: HarnessRuntime, provider: str,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "WARN",
        "provider": provider,
        "attempts": len(failures),
        "raw_candidate_count": 0,
        "candidate_count": 0,
        "filtered_out_count": 0,
        "recorded_count": 0,
        "candidate_ids": [],
        "candidates_path": ctx.rel(pc_candidates_path(ctx)),
        "warning": "Project Contract candidate extraction failed after retries.",
        "failures": failures,
    }


def extract_project_contract_candidates(ctx: HarnessRuntime, state: dict[str, Any]) -> dict[str, Any]:
    if not should_extract_pc_candidates(ctx, state):
        return {"status": "skipped", "reason": "pipeline does not extract PC candidates"}

    feature = str(state["feature_name"])
    provider = ctx.provider_for_stage(ctx.PC_REVIEW_STAGE, state)
    failures: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    raw_candidates: list[Any] | None = None

    for attempt in range(1, PC_CANDIDATE_EXTRACTION_MAX_ATTEMPTS + 1):
        attempt_result: dict[str, Any] = {}
        capture_path = ctx.run_dir(feature) / "logs" / f"pc_candidates_{provider}_attempt{attempt}_result.json"
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        if capture_path.exists():
            capture_path.unlink()
        prompt = build_pc_candidate_extraction_prompt(ctx, state, capture_path)
        ctx.log_event(
            state,
            "pc_candidate_extraction_started",
            "extracting project contract candidates",
            stage=ctx.PC_REVIEW_STAGE,
            provider=provider,
            attempt=attempt,
            max_attempts=PC_CANDIDATE_EXTRACTION_MAX_ATTEMPTS,
        )
        try:
            attempt_result = ctx.run_text_provider_prompt(
                provider,
                prompt,
                logs_dir=ctx.run_dir(feature) / "logs",
                log_prefix="pc_candidates",
                timeout_seconds=3600,
                performance=state.get("performance"),
            )
            attempt_result["json_output"] = ctx.rel(capture_path)
            result = attempt_result
            raw_candidates = parse_pc_candidate_extraction_result(ctx, result)
            break
        except Exception as exc:
            failures.append(
                {
                    "attempt": attempt,
                    "reason": str(exc),
                    "stdout": attempt_result.get("stdout"),
                    "stderr": attempt_result.get("stderr"),
                    "meta": attempt_result.get("meta"),
                    "json_output": attempt_result.get("json_output") or ctx.rel(capture_path),
                }
            )
            ctx.log_event(
                state,
                "pc_candidate_extraction_attempt_failed",
                str(exc),
                stage=ctx.PC_REVIEW_STAGE,
                provider=provider,
                attempt=attempt,
                max_attempts=PC_CANDIDATE_EXTRACTION_MAX_ATTEMPTS,
            )

    if raw_candidates is None:
        extraction = pc_candidate_extraction_warning(ctx, provider, failures)
        state["pc_candidate_extraction"] = extraction
        ctx.log_event(
            state,
            "pc_candidate_extraction_warning",
            "project contract candidate extraction failed after retries; continuing run",
            stage=ctx.PC_REVIEW_STAGE,
            provider=provider,
            attempts=len(failures),
        )
        return extraction

    created_at = ctx.iso_now()
    normalized = [
        candidate
        for candidate in (
            normalize_pc_candidate(ctx, item, state, created_at, provider)
            for item in raw_candidates
            if isinstance(item, dict)
        )
        if candidate
    ]
    append_result = append_pc_candidates(ctx, normalized, state)
    extraction = {
        "status": ResultStatus.PASS,
        "provider": provider,
        "raw_candidate_count": len(raw_candidates),
        "candidate_count": len(normalized),
        "filtered_out_count": len(raw_candidates) - len(normalized),
        "recorded_count": append_result["added_count"],
        "candidate_ids": append_result["added_ids"],
        "candidates_path": append_result["path"],
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "meta": result.get("meta"),
        "json_output": result.get("json_output"),
    }
    state["pc_candidate_extraction"] = extraction
    ctx.log_event(
        state,
        "pc_candidate_extraction_completed",
        "project contract candidates extracted",
        stage=ctx.PC_REVIEW_STAGE,
        provider=provider,
        raw_candidate_count=len(raw_candidates),
        candidate_count=len(normalized),
        filtered_out_count=len(raw_candidates) - len(normalized),
        recorded_count=append_result["added_count"],
    )
    return extraction


