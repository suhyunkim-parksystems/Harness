from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Any

from . import pipeline
from .errors import HarnessError
from .status import ResultStatus, RunStatus


DEFAULT_CONFIG: dict[str, Any] = {
    "plan_stage": "01_plan",
    "strategy": "parallel",
    "iterations": 3,
    "max_drafters": 3,
    "min_drafters": 2,
    "provider_order": ["agy", "claude", "codex"],
    "min_available_providers": 2,
    "no_adjacent_same_provider": True,
    "persist_intermediate_outputs": False,
    "show_iterations_in_user_output": True,
    "anonymize_candidates": True,
    "previous_candidate_max_chars": 60000,
    "common_instruction_lines": [
        "이 지시는 `01_plan` stage 내부에서만 사용하는 비공개 계획 지시다.",
        "산출물의 형식과 언어는 기존 `presets/full/01_plan.md`를 따른다.",
        "`00_spec.md`를 임의로 변경하거나 확장하지 않는다.",
        "사용자 판단이 필요하면 일반 `01_plan`과 동일하게 `status: NEEDS_USER`를 기록한다.",
        "확정된 스펙을 구현 가능한 계획으로 더 잘 번역하는 것이 목적이다.",
        "후보 계획과 최종 계획은 반드시 한국어로 작성한다.",
        "내부 후보, 종합, hidden draft, deep-thinking 같은 표현을 산출물에 남기지 않는다.",
    ],
    "draft_instruction": {
        "name": "blind_draft",
        "lines": [
            "현재 단계는 여러 독립 계획 후보 중 하나를 작성하는 단계다.",
            "다른 후보 계획은 제공되지 않으며, 다른 안을 참고할 수 없다.",
            "",
            "목표:",
            "확정된 `00_spec.md`와 기존 코드 확인만을 근거로 독립적인 구현 계획을 작성한다.",
            "",
            "중점:",
            "- 영향받는 파일과 기존 패턴을 직접 찾는다.",
            "- 구현 접근 방식을 제안한다. 합리적이라면 통념과 다른 접근도 과감히 고려한다.",
            "- 데이터/제어 흐름을 정리한다.",
            "- 호환성 위험과 회귀 위험을 식별한다.",
            "- 테스트 전략과 롤백 방향을 잡는다.",
            "- 불확실한 가정과 추가 확인이 필요한 부분을 기록한다.",
            "- 다른 후보와의 차별성을 의식하지 말고, 이 스펙에 가장 맞다고 판단하는 계획을 그대로 쓴다.",
        ],
    },
    "synthesis_instruction": {
        "name": "synthesis",
        "lines": [
            "현재 단계는 여러 독립 계획 후보를 종합하여 최종 `01_plan.md`를 작성하는 단계다.",
            "각 후보는 익명으로 제공된다. 누가 작성했는지는 알 수 없고, 알 필요도 없다.",
            "",
            "절차(반드시 이 순서로):",
            "1. 각 후보의 상위 구현 방향을 비교·평가한다. 각 후보의 핵심 접근과 그 장단점을 짚는다.",
            "2. 방향은 하나를 선택한다. 여러 안을 평균내거나 절반씩 섞어 절충안을 만들지 않는다.",
            "   - 한 후보의 방향을 채택하거나, 명백히 더 나은 제3의 방향이 있으면 근거를 들어 그것을 택한다.",
            "   - 선택한 방향과 탈락한 방향의 사유를 기록한다.",
            "3. 선택한 방향 위에서, 다른 후보의 좋은 디테일(변경 파일, 위험 완화, 테스트 케이스 등)만 체리픽하여 보강한다.",
            "4. 스펙과 실제 코드 확인으로 정당화되는 결정만 남긴다.",
            "",
            "주의:",
            "- 어떤 후보가 네 평소 출력과 비슷해 보여도 더 후하게 평가하지 않는다. 모든 후보를 동일한 기준으로 가혹하게 심사한다.",
            "- 스펙이 명시적으로 요구하지 않는 한 하위 호환성을 유지한다.",
            "- 개발자가 추가 설계 없이 실행할 수 있을 만큼 구현 단계를 구체화한다.",
            "- review/verify가 따라갈 수 있도록 테스트 전략과 호환성 검증 포인트를 명확히 한다.",
            "",
            "출력:",
            "최종 `01_plan.md`와 result JSON을 작성한다. 이 결과만 실제 `01_plan` stage 산출물로 인정된다.",
            "최종 문서는 반드시 한국어로 작성하고, 일반적인 `01_plan.md`처럼 보여야 한다.",
        ],
    },
    "select_instruction": {
        "name": "select",
        "lines": [
            "현재 단계는 여러 독립 계획 후보 중에서 구현 방향을 하나 선택하는 단계다.",
            "이 단계의 산출물은 임시 중간 결과이며 최종이 아니다. 이후 검증·심화 단계가 이어진다.",
            "각 후보는 익명으로 제공된다. 누가 작성했는지는 알 수 없고, 알 필요도 없다.",
            "",
            "절차:",
            "1. 각 후보의 상위 구현 방향을 비교·평가한다. 각 후보의 핵심 접근과 장단점을 짚는다.",
            "2. 방향은 하나를 선택한다. 여러 안을 평균내거나 절반씩 섞어 절충안을 만들지 않는다.",
            "   - 한 후보의 방향을 채택하거나, 명백히 더 나은 제3의 방향이 있으면 근거를 들어 그것을 택한다.",
            "   - 선택한 방향과 탈락한 방향의 사유를 기록한다.",
            "3. 선택한 방향 위에서 다른 후보의 좋은 디테일(변경 파일, 위험 완화, 테스트 케이스 등)만 체리픽하여 보강한다.",
            "",
            "주의:",
            "- 어떤 후보가 네 평소 출력과 비슷해 보여도 더 후하게 평가하지 않는다. 모든 후보를 동일 기준으로 가혹하게 심사한다.",
            "- 이 단계는 방향을 정하고 토대를 만드는 것이 목적이다. 세부 코드 검증과 최종 확정은 다음 단계에서 한다.",
            "",
            "출력:",
            "선택한 방향과 그 근거가 드러나는, 방향이 확정된 계획을 작성한다.",
            "이 산출물은 다음 검증·심화 단계의 입력으로만 사용되며, 공식 최종 결과가 아니다.",
        ],
    },
    "ground_instruction": {
        "name": "ground",
        "lines": [
            "현재 단계는 확정된 단일 계획을 실제 코드베이스에 대조하여 검증·심화하는 단계다.",
            "입력으로 받은 '현재 계획'은 방향이 이미 정해진 단일 계획이다.",
            "",
            "반드시 할 것:",
            "- 계획이 언급한 모든 파일·함수·심볼을 실제로 열어 존재 여부와 시그니처를 확인한다.",
            "- 틀렸거나 추측인 부분을 실제 코드 기준으로 교정하고, 무엇을 교정했는지 남긴다.",
            "- 구현 단계(시퀀싱), 엣지 케이스, 에러 경로, 롤백/복구 방향을 실행 가능한 수준으로 심화한다.",
            "- 호환성·회귀 위험을 실제 호출부 확인으로 구체화한다.",
            "- 검증되지 않은 가정은 코드로 확인하거나, 확인 불가하면 명시적으로 표시한다.",
            "",
            "하지 말 것:",
            "- 상위 방향을 바꾸지 않는다. 더 나은 방향이 보여도 이 단계에서 갈아엎지 않는다(이미 선택됨).",
            "- 코드를 수정하지 않는다. 계획만 보강한다.",
        ],
    },
    "premortem_instruction": {
        "name": "premortem",
        "lines": [
            "현재 단계는 보강된 계획에 사전 부검(pre-mortem)을 수행하고 최종 `01_plan.md`를 확정하는 단계다.",
            "",
            "절차:",
            "1. '이 계획대로 구현·배포했더니 장애가 났다'고 가정하고, 가장 그럴듯한 실패 원인 3가지를 도출한다.",
            "   - 누락된 엣지 케이스, 깨진 호환성, 검증 안 된 가정, 잘못된 시퀀싱 등을 노린다.",
            "2. 각 실패 원인을 막도록 계획을 패치한다(테스트 추가, 단계 보강, 위험 완화).",
            "3. 패치된 계획을 최종 `01_plan.md`로 작성한다. 상위 방향은 유지한다.",
            "",
            "출력:",
            "최종 `01_plan.md`와 result JSON을 작성한다. 이 결과만 실제 `01_plan` stage 산출물로 인정된다.",
            "사전 부검 과정은 'pre-mortem' 같은 표현 없이 위험 구간/완화/테스트 전략에 자연스럽게 녹인다.",
            "최종 문서는 반드시 한국어로 작성하고, 일반적인 `01_plan.md`처럼 보여야 한다.",
        ],
    },
    "instructions": [
        {
            "iteration": 1,
            "name": "initial_plan",
            "lines": [
                "목표:",
                "확정된 `00_spec.md`와 기존 코드 확인을 바탕으로 넓은 초기 구현 계획을 작성한다.",
                "",
                "중점:",
                "- 영향받는 파일과 기존 패턴을 찾는다.",
                "- 구현 접근 방식을 제안한다.",
                "- 데이터/제어 흐름을 정리한다.",
                "- 호환성 위험과 회귀 위험을 식별한다.",
                "- 테스트 전략과 롤백 방향을 잡는다.",
                "- 불확실한 가정과 추가 확인이 필요한 부분을 기록한다.",
            ],
        },
        {
            "iteration": 2,
            "name": "improve_plan",
            "lines": [
                "목표:",
                "확정된 `00_spec.md`와 1회차 후보 계획을 바탕으로 더 나은 계획을 작성한다.",
                "",
                "중점:",
                "- 누락된 영향 파일, 호출 흐름, 데이터 흐름을 찾는다.",
                "- 약한 가정이나 코드 확인 없이 세운 판단을 보강한다.",
                "- 기존 코드와의 하위 호환성이 유지되는지 검토한다.",
                "- 위험 완화 방안이 구체적인지 확인한다.",
                "- 테스트 전략에 회귀/호환성 검증이 충분한지 보강한다.",
                "- 과한 설계나 범위 밖 작업을 제거한다.",
                "- 스펙은 변경하지 않고 계획만 개선한다.",
            ],
        },
        {
            "iteration": 3,
            "name": "final_plan",
            "lines": [
                "목표:",
                "확정된 `00_spec.md`, 1회차 후보 계획, 2회차 후보 계획을 종합하여 최종 `01_plan.md`를 작성한다.",
                "",
                "중점:",
                "- 앞선 후보 계획들의 장점을 종합한다.",
                "- 후보 계획 사이의 충돌을 해소한다.",
                "- 스펙과 실제 코드 확인으로 정당화되는 결정만 남긴다.",
                "- 스펙이 명시적으로 요구하지 않는 한 하위 호환성을 유지한다.",
                "- 개발자가 추가 설계 없이 실행할 수 있을 만큼 구현 단계를 구체화한다.",
                "- review/verify가 따라갈 수 있도록 테스트 전략과 호환성 검증 포인트를 명확히 한다.",
                "",
                "출력:",
                "최종 `01_plan.md`와 result JSON을 작성한다.",
                "이 결과만 실제 `01_plan` stage 산출물로 인정된다.",
                "최종 문서는 반드시 한국어로 작성하고, 일반적인 `01_plan.md`처럼 보여야 한다.",
            ],
        },
    ],
}


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _as_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value).splitlines()


def _config(ctx) -> dict[str, Any]:
    loaded = ctx.load_config()
    raw = loaded.get("deep_thinking")
    if raw is None:
        raw = loaded.get("heavy_thinking", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise HarnessError("deep_thinking config must be an object.")
    return _merge_dicts(DEFAULT_CONFIG, raw)


def _iterations(config: dict[str, Any]) -> int:
    try:
        iterations = int(config.get("iterations", 3))
    except (TypeError, ValueError) as exc:
        raise HarnessError("deep_thinking.iterations must be an integer.") from exc
    if iterations < 1:
        raise HarnessError("deep_thinking.iterations must be at least 1.")
    return iterations


def _plan_stage(config: dict[str, Any]) -> str:
    return str(config.get("plan_stage") or "01_plan")


def _instruction_entry(config: dict[str, Any], iteration: int) -> dict[str, Any]:
    instructions = config.get("instructions", [])
    if isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, dict) and int(item.get("iteration", -1) or -1) == iteration:
                return item
    return {}


def _instruction_lines(config: dict[str, Any], iteration: int) -> list[str]:
    entry = _instruction_entry(config, iteration)
    lines: list[str] = []
    lines.extend(_as_lines(config.get("common_instruction_lines")))
    if lines and _as_lines(entry.get("lines")):
        lines.append("")
    lines.extend(_as_lines(entry.get("lines")))
    return lines


def _instruction_name(config: dict[str, Any], iteration: int) -> str:
    entry = _instruction_entry(config, iteration)
    return str(entry.get("name") or f"iteration_{iteration}")


def _show_iteration_logs(config: dict[str, Any]) -> bool:
    return bool(config.get("show_iterations_in_user_output", True))


def _available_plan_providers(ctx, config: dict[str, Any]) -> list[str]:
    configured_order = _as_lines(config.get("provider_order"))
    order = ctx.ordered_unique([*configured_order, *ctx.known_provider_names()])
    result: list[str] = []
    for provider in order:
        if not ctx.provider_available(provider):
            continue
        if "plan" not in ctx.provider_capabilities(provider):
            continue
        result.append(provider)
    return ctx.ordered_unique(result)


def validate_config_for_state(ctx, state: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _config(ctx)
    if not pipeline.supports_deep_thinking(ctx.PIPELINE_MODE):
        raise HarnessError("--deep-thinking is only available for the full pipeline.")
    candidates = _available_plan_providers(ctx, config)
    try:
        minimum = int(config.get("min_available_providers", 2) or 0)
    except (TypeError, ValueError) as exc:
        raise HarnessError("deep_thinking.min_available_providers must be an integer.") from exc
    if len(candidates) < minimum:
        available_text = ", ".join(candidates) if candidates else "none"
        raise HarnessError(
            f"--deep-thinking requires at least {minimum} available planning providers. "
            f"Available planning providers: {available_text}."
        )
    _iterations(config)
    if state is not None:
        plan_stage = _plan_stage(config)
        if plan_stage not in ctx.STAGES:
            raise HarnessError(f"deep_thinking.plan_stage is not in this pipeline: {plan_stage}")
    return config


def _previous_stage_provider(ctx, state: dict[str, Any], stage: str) -> str | None:
    try:
        index = ctx.STAGES.index(stage)
    except ValueError:
        return None
    if index <= 0:
        return None
    schedule = ctx.ensure_provider_schedule(state, record_event=False)
    return str(schedule.get(ctx.STAGES[index - 1]) or "") or None


def _next_stage_provider(ctx, state: dict[str, Any], stage: str) -> str | None:
    try:
        index = ctx.STAGES.index(stage)
    except ValueError:
        return None
    if index + 1 >= len(ctx.STAGES):
        return None
    schedule = ctx.ensure_provider_schedule(state, record_event=False)
    return str(schedule.get(ctx.STAGES[index + 1]) or "") or None


def _rotated_order(order: list[str], start_index: int) -> list[str]:
    if not order:
        return []
    index = start_index % len(order)
    return order[index:] + order[:index]


def _select_iteration_providers(ctx, state: dict[str, Any], config: dict[str, Any]) -> list[str]:
    stage = _plan_stage(config)
    iterations = _iterations(config)
    candidates = _available_plan_providers(ctx, config)
    preferred = ctx.ordered_unique([*_as_lines(config.get("provider_order")), *candidates])
    no_adjacent = bool(config.get("no_adjacent_same_provider", True))
    previous_provider = _previous_stage_provider(ctx, state, stage)
    next_provider = _next_stage_provider(ctx, state, stage)
    selected: list[str] = []
    last_provider = previous_provider

    for index in range(iterations):
        preferred_for_iteration = ctx.ordered_unique(
            [provider for provider in _rotated_order(preferred, index) if provider in candidates]
        )
        eligible = [
            provider
            for provider in preferred_for_iteration
            if not (no_adjacent and last_provider and provider == last_provider)
        ]
        if index == iterations - 1 and next_provider:
            non_next = [provider for provider in eligible if provider != next_provider]
            if non_next:
                eligible = non_next
        if not eligible:
            raise HarnessError(
                "Cannot choose deep-thinking providers without adjacent provider reuse. "
                "Enable another planning provider or disable --deep-thinking."
            )
        provider = eligible[0]
        selected.append(provider)
        last_provider = provider
    return selected


def _limit_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated]\n"


_IDENTITY_RESULT_KEYS = ("actual_model", "model_mismatch", "preferred_model", "scheduled_provider")


def _scrub_candidate_identity(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    scrubbed = dict(result)
    for key in _IDENTITY_RESULT_KEYS:
        scrubbed.pop(key, None)
    return scrubbed


def _previous_candidate_context(candidates: list[dict[str, Any]], config: dict[str, Any]) -> str:
    if not candidates:
        return "- 없음"
    try:
        max_chars = int(config.get("previous_candidate_max_chars", 60000) or 60000)
    except (TypeError, ValueError):
        max_chars = 60000
    anonymize = bool(config.get("anonymize_candidates", True))
    parts: list[str] = []
    for position, candidate in enumerate(candidates, start=1):
        output_text = _limit_text(str(candidate.get("output_text") or ""), max_chars)
        result = candidate.get("result") if isinstance(candidate.get("result"), dict) else {}
        if anonymize:
            header = f"### 후보 계획 {position}"
            result_for_prompt: dict[str, Any] = _scrub_candidate_identity(result)
            provider_line: str | None = None
        else:
            header = f"### {candidate.get('iteration')}회차 후보 계획"
            result_for_prompt = result if isinstance(result, dict) else {}
            provider_line = f"- provider: {candidate.get('provider')}"
        block = [header]
        if provider_line is not None:
            block.append(provider_line)
        block.extend(
            [
                "",
                "```markdown",
                output_text,
                "```",
                "",
                "후보 result JSON:",
                "```json",
                json.dumps(result_for_prompt, ensure_ascii=False, indent=2),
                "```",
            ]
        )
        parts.extend(block)
    return "\n".join(parts)


def _iteration_prompt(ctx, 
    *,
    base_prompt: str,
    config: dict[str, Any],
    iteration: int,
    total: int,
    candidates: list[dict[str, Any]],
    official_output: Path,
    official_result_json: Path,
    output_path: Path,
    result_json_path: Path,
    final_iteration: bool,
) -> str:
    if final_iteration:
        # The final iteration writes the official artifact, exactly as base_prompt directs.
        text = base_prompt
    else:
        # Point this intermediate iteration at its own temp path by substituting the
        # official paths baked into base_prompt. The path itself says "write here", so
        # there is no contradictory "write official / do not write official" override.
        text = base_prompt.replace(ctx.rel(official_result_json), ctx.rel(result_json_path))
        text = text.replace(ctx.rel(official_output), ctx.rel(output_path))

    instruction = "\n".join(_instruction_lines(config, iteration)).strip() or "- 추가 내부 지시 없음"
    return (
        text.rstrip()
        + "\n\n---\n\n"
        + "## Deep Thinking 이전 후보 계획\n\n"
        + _previous_candidate_context(candidates, config)
        + "\n\n"
        + "## Deep Thinking 내부 지시\n\n"
        + f"현재 반복: {iteration}/{total}\n\n"
        + instruction
        + "\n"
    )


def _read_candidate(
    ctx, output_path: Path,
    result_json_path: Path,
    *,
    fallback_output_path: Path | None = None,
    fallback_result_json_path: Path | None = None,
) -> tuple[Path, str, dict[str, Any]] | None:
    output = output_path if output_path.exists() else fallback_output_path
    result_json = result_json_path if result_json_path.exists() else fallback_result_json_path
    if output is None or not output.exists():
        return None
    text = output.read_text(encoding="utf-8")
    if result_json is not None and result_json.exists():
        result = ctx.read_stage_result_json(result_json)
    else:
        result = ctx.find_stage_result(text)
    if not result:
        return None
    return output, text, result


def _write_official_result(output: Path, result_json: Path, text: str, result: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    result_json.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text.rstrip() + "\n", encoding="utf-8")
    result_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _official_backups(paths: list[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def _restore_official_backups(backups: dict[Path, bytes | None]) -> None:
    for path, content in backups.items():
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def _cleanup_temp_path(path: Path) -> None:
    if path.exists():
        path.unlink()


def _cleanup_temp_dir(temp_dir: Path) -> None:
    try:
        temp_dir.rmdir()
    except OSError:
        pass


def _block_provider_failure(
    ctx, state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    failure: str,
    run_result: dict[str, Any],
) -> dict[str, Any]:
    stdout_path = ctx.ROOT / str(run_result.get("stdout", ""))
    stderr_path = ctx.ROOT / str(run_result.get("stderr", ""))
    provider_log_path = ctx.ROOT / str(run_result.get("provider_log", ""))
    reason = ctx.provider_failure_reason(
        state,
        stage=stage,
        provider=provider,
        failure=failure,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        provider_log_path=provider_log_path,
    )
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": reason,
        "stdout": str(run_result.get("stdout") or ""),
        "stderr": str(run_result.get("stderr") or ""),
        "provider_log": str(run_result.get("provider_log") or ""),
        "retry_command": ctx.suggested_retry_command(state),
    }
    ctx.write_handoff(
        state,
        reason,
        stage=stage,
        next_action=f"로그를 확인한 뒤 현재 단계를 다시 실행하세요: {ctx.suggested_retry_command(state)}",
    )
    ctx.log_event(
        state,
        "provider_failed",
        f"{provider} failed during deep-thinking plan",
        stage=stage,
        provider=provider,
        stdout=str(run_result.get("stdout") or ""),
        stderr=str(run_result.get("stderr") or ""),
        provider_log=str(run_result.get("provider_log") or ""),
        retry_command=ctx.suggested_retry_command(state),
    )
    ctx.save_state(state)
    return state


def _block_missing_candidate(
    ctx, state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    run_result: dict[str, Any],
    output_path: Path,
    result_json_path: Path,
) -> dict[str, Any]:
    reason = (
        "Heavy-thinking plan provider did not produce a readable plan candidate. "
        f"Expected {ctx.rel(output_path)} and {ctx.rel(result_json_path)}."
    )
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": reason,
        "stdout": str(run_result.get("stdout") or ""),
        "stderr": str(run_result.get("stderr") or ""),
        "provider_log": str(run_result.get("provider_log") or ""),
        "retry_command": ctx.suggested_retry_command(state),
    }
    ctx.write_handoff(
        state,
        reason,
        stage=stage,
        next_action=f"로그를 확인한 뒤 현재 단계를 다시 실행하세요: {ctx.suggested_retry_command(state)}",
    )
    ctx.log_event(
        state,
        "deep_thinking_missing_candidate",
        "deep-thinking provider did not produce a readable candidate",
        stage=stage,
        provider=provider,
        output=ctx.rel(output_path),
        result_json=ctx.rel(result_json_path),
    )
    ctx.save_state(state)
    return state


def _update_stage_provider(state: dict[str, Any], stage: str, provider: str) -> None:
    schedule = state.setdefault("provider_schedule", {})
    if isinstance(schedule, dict):
        schedule[stage] = provider


def _strategy(state: dict[str, Any] | None, config: dict[str, Any]) -> str:
    raw = state.get("strategy") if isinstance(state, dict) else None
    value = str(raw or config.get("strategy") or "parallel").strip().lower()
    if value in {"parallel", "ensemble"}:
        return "parallel"
    if value in {"sequential", "relay", "series", "iterative"}:
        return "sequential"
    if value in {"max", "hybrid", "deep"}:
        return "max"
    raise HarnessError(
        f"Unknown deep_thinking strategy: {value!r}. Use 'parallel', 'sequential', or 'max'."
    )


def _instruction_block_lines(config: dict[str, Any], key: str) -> list[str]:
    lines: list[str] = list(_as_lines(config.get("common_instruction_lines")))
    entry = config.get(key)
    body = _as_lines(entry.get("lines")) if isinstance(entry, dict) else []
    if lines and body:
        lines.append("")
    lines.extend(body)
    return lines


def _min_drafters(config: dict[str, Any]) -> int:
    try:
        value = int(config.get("min_drafters", 2) or 2)
    except (TypeError, ValueError) as exc:
        raise HarnessError("deep_thinking.min_drafters must be an integer.") from exc
    return max(1, value)


def _select_drafters(ctx, config: dict[str, Any]) -> list[str]:
    candidates = _available_plan_providers(ctx, config)
    try:
        max_drafters = int(config.get("max_drafters", 3) or 3)
    except (TypeError, ValueError) as exc:
        raise HarnessError("deep_thinking.max_drafters must be an integer.") from exc
    if max_drafters < 1:
        raise HarnessError("deep_thinking.max_drafters must be at least 1.")
    return candidates[:max_drafters]


def _select_synthesizer(ctx, state: dict[str, Any], config: dict[str, Any], drafters: list[str]) -> str:
    stage = _plan_stage(config)
    try:
        scheduled = ctx.provider_for_stage(stage, state)
    except HarnessError:
        scheduled = None
    if scheduled and scheduled in drafters:
        return scheduled
    return drafters[0]


def _draft_prompt(ctx, 
    *,
    base_prompt: str,
    official_output: Path,
    official_result_json: Path,
    draft_output: Path,
    draft_result_json: Path,
    config: dict[str, Any],
) -> str:
    text = base_prompt
    text = text.replace(ctx.rel(official_result_json), ctx.rel(draft_result_json))
    text = text.replace(ctx.rel(official_output), ctx.rel(draft_output))
    instruction = "\n".join(_instruction_block_lines(config, "draft_instruction")).strip()
    if not instruction:
        instruction = "- 추가 내부 지시 없음"
    return (
        text.rstrip()
        + "\n\n---\n\n"
        + "## Deep Thinking 내부 지시 (독립 초안)\n\n"
        + instruction
        + "\n"
    )


def _synthesis_prompt(
    *,
    base_prompt: str,
    candidates: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    instruction = "\n".join(_instruction_block_lines(config, "synthesis_instruction")).strip()
    if not instruction:
        instruction = "- 추가 내부 지시 없음"
    return (
        base_prompt.rstrip()
        + "\n\n---\n\n"
        + "## Deep Thinking 종합 대상 후보 계획 (익명)\n\n"
        + _previous_candidate_context(candidates, config)
        + "\n\n"
        + "## Deep Thinking 종합 지시\n\n"
        + instruction
        + "\n"
    )


def _run_one_draft(
    ctx, spec: dict[str, Any],
    *,
    logs_dir: Path,
    stage: str,
    timeout_seconds: int,
    performance: Any,
) -> dict[str, Any]:
    provider = spec["provider"]
    try:
        run_result = ctx.run_text_provider_prompt(
            provider,
            spec["prompt_text"],
            logs_dir=logs_dir,
            log_prefix=f"{stage}_draft_{provider}",
            timeout_seconds=timeout_seconds,
            performance=performance,
        )
    except Exception as exc:  # provider executable missing, spawn failure, etc.
        return {**spec, "run_result": None, "error": str(exc)}
    return {**spec, "run_result": run_result, "error": None}


def _run_drafts_parallel(
    ctx, specs: list[dict[str, Any]],
    *,
    logs_dir: Path,
    stage: str,
    timeout_seconds: int,
    performance: Any,
) -> list[dict[str, Any]]:
    if len(specs) <= 1:
        return [
            _run_one_draft(ctx, 
                spec, logs_dir=logs_dir, stage=stage, timeout_seconds=timeout_seconds, performance=performance
            )
            for spec in specs
        ]
    order = {spec["provider"]: index for index, spec in enumerate(specs)}
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(specs)) as pool:
        futures = [
            pool.submit(
                _run_one_draft,
                ctx,
                spec,
                logs_dir=logs_dir,
                stage=stage,
                timeout_seconds=timeout_seconds,
                performance=performance,
            )
            for spec in specs
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: order.get(item["provider"], 0))
    return results


def _cleanup_temp_tree(temp_dir: Path) -> None:
    if not temp_dir.exists():
        return
    for child in temp_dir.iterdir():
        try:
            if child.is_file():
                child.unlink()
        except OSError:
            pass
    _cleanup_temp_dir(temp_dir)


def _block_head_change(
    ctx, state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    before_head: str,
    after_head: str,
) -> dict[str, Any]:
    reason = "Provider changed Git HEAD. The harness owns commits; inspect history before continuing."
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": reason,
        "retry_command": ctx.suggested_retry_command(state),
    }
    ctx.write_handoff(
        state,
        reason,
        stage=stage,
        next_action="Git history를 점검한 뒤 수동으로 정리하고 retry 하세요.",
    )
    ctx.log_event(
        state,
        "blocked_provider_changed_head",
        "provider changed Git HEAD",
        stage=stage,
        provider=provider,
        before_head=before_head,
        after_head=after_head,
    )
    ctx.save_state(state)
    return state


def _block_deep_thinking(ctx, state: dict[str, Any], *, stage: str, reason: str) -> dict[str, Any]:
    state["status"] = RunStatus.BLOCKED
    state["blocked"] = {
        "stage": stage,
        "reason": reason,
        "retry_command": ctx.suggested_retry_command(state),
    }
    ctx.write_handoff(
        state,
        reason,
        stage=stage,
        next_action=f"로그를 확인한 뒤 현재 단계를 다시 실행하세요: {ctx.suggested_retry_command(state)}",
    )
    ctx.log_event(state, "deep_thinking_blocked", reason, stage=stage)
    ctx.save_state(state)
    return state


def _finalize_parallel(
    ctx, state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    result: dict[str, Any],
    config: dict[str, Any],
    temp_dir: Path,
    warnings: list[str],
    label: str,
) -> dict[str, Any]:
    if not bool(config.get("persist_intermediate_outputs", False)):
        _cleanup_temp_tree(temp_dir)
    _update_stage_provider(state, stage, provider)
    state["status"] = RunStatus.MODEL_COMPLETED
    if warnings:
        state["deep_thinking_warnings"] = warnings
    else:
        state.pop("deep_thinking_warnings", None)
    ctx.log_event(state, "provider_completed", f"{provider} completed", stage=stage, provider=provider, console=False)
    ctx.log_event(
        state,
        "deep_thinking_completed",
        f"deep-thinking parallel plan completed ({label})",
        stage=stage,
        console=False,
        provider=provider,
        status=ctx.stage_status(result),
        warnings=len(warnings),
    )
    ctx.save_state(state)
    return state


def _execute_parallel_plan(
    ctx, state: dict[str, Any], timeout_seconds: int, config: dict[str, Any]
) -> dict[str, Any]:
    stage = _plan_stage(config)
    feature = state["feature_name"]

    prompt_rel = state.get("current_prompt")
    if not prompt_rel:
        raise HarnessError("No current prompt to execute.")
    prompt_file = ctx.ROOT / str(prompt_rel)
    if not prompt_file.exists():
        raise HarnessError(f"Prompt file does not exist: {prompt_file}")
    base_prompt = prompt_file.read_text(encoding="utf-8")

    official_output = ctx.stage_output_path(feature, stage)
    official_result_json = ctx.stage_result_json_path(feature, stage)
    backups = _official_backups([official_output, official_result_json])

    drafters = _select_drafters(ctx, config)
    min_drafters = _min_drafters(config)
    if len(drafters) < min_drafters:
        available_text = ", ".join(drafters) if drafters else "none"
        raise HarnessError(
            f"--deep-thinking parallel strategy needs at least {min_drafters} planning providers. "
            f"Available planning providers: {available_text}."
        )
    synthesizer = _select_synthesizer(ctx, state, config, drafters)

    temp_dir = ctx.run_dir(feature) / ".tmp" / "deep_thinking"
    temp_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = ctx.run_dir(feature) / "logs"
    performance = ctx.normalize_performance(state.get("performance"))
    persist_intermediate = bool(config.get("persist_intermediate_outputs", False))
    show_logs = _show_iteration_logs(config)

    ctx.log_event(
        state,
        "deep_thinking_started",
        "deep-thinking parallel plan started",
        stage=stage,
        console=False,
        strategy="parallel",
        drafters=" ".join(drafters),
        synthesizer=synthesizer,
    )

    # Phase 1: independent blind drafts (each writes only to its own temp path).
    specs: list[dict[str, Any]] = []
    for provider in drafters:
        draft_output = temp_dir / f"{stage}_draft_{provider}.md"
        draft_result_json = temp_dir / f"{stage}_draft_{provider}.result.json"
        _cleanup_temp_path(draft_output)
        _cleanup_temp_path(draft_result_json)
        specs.append(
            {
                "provider": provider,
                "output_path": draft_output,
                "result_json_path": draft_result_json,
                "prompt_text": _draft_prompt(ctx, 
                    base_prompt=base_prompt,
                    official_output=official_output,
                    official_result_json=official_result_json,
                    draft_output=draft_output,
                    draft_result_json=draft_result_json,
                    config=config,
                ),
            }
        )

    state["status"] = RunStatus.MODEL_RUNNING
    ctx.save_state(state)
    before_head = ctx.safe_git_head()
    draft_runs = _run_drafts_parallel(ctx, 
        specs, logs_dir=logs_dir, stage=stage, timeout_seconds=timeout_seconds, performance=performance
    )
    after_head = ctx.safe_git_head()
    if before_head and after_head and before_head != after_head:
        _restore_official_backups(backups)
        return _block_head_change(ctx, 
            state, stage=stage, provider="draft", before_head=before_head, after_head=after_head
        )

    candidates: list[dict[str, Any]] = []
    needs_user: dict[str, Any] | None = None
    warnings: list[str] = []

    def drop(provider: str, why: str) -> None:
        warnings.append(f"{provider}: {why}")
        ctx.log_event(
            state,
            "deep_thinking_draft_dropped",
            f"draft from {provider} dropped: {why}",
            stage=stage,
            console=show_logs,
            provider=provider,
        )

    for run in draft_runs:
        provider = run["provider"]
        if run.get("error"):
            drop(provider, str(run["error"]))
            continue
        run_result = run["run_result"]
        if run_result.get("timed_out"):
            drop(provider, f"timed out after {timeout_seconds}s")
            continue
        returncode = run_result.get("returncode")
        if returncode not in {0, None}:
            drop(provider, f"exited with code {returncode}")
            continue
        candidate = _read_candidate(ctx, run["output_path"], run["result_json_path"])
        if candidate is None:
            drop(provider, "no readable candidate")
            continue
        candidate_path, candidate_text, candidate_result = candidate
        candidate_status = ctx.stage_status(candidate_result)
        if candidate_status == ResultStatus.NEEDS_USER:
            if needs_user is None:
                needs_user = {"provider": provider, "text": candidate_text, "result": candidate_result}
            continue
        if candidate_status == ResultStatus.PASS:
            candidates.append(
                {
                    "iteration": len(candidates) + 1,
                    "provider": provider,
                    "output_path": ctx.rel(candidate_path),
                    "output_text": candidate_text,
                    "result": candidate_result,
                }
            )
        else:
            drop(provider, f"status {candidate_status}")

    # Drafts only target temp paths; restore official in case a provider ignored the path.
    _restore_official_backups(backups)

    if needs_user is not None:
        _write_official_result(official_output, official_result_json, needs_user["text"], needs_user["result"])
        return _finalize_parallel(ctx, 
            state,
            stage=stage,
            provider=needs_user["provider"],
            result=needs_user["result"],
            config=config,
            temp_dir=temp_dir,
            warnings=warnings,
            label="needs_user",
        )

    if not candidates:
        reason = "Heavy-thinking parallel drafting produced no usable plan candidate."
        if warnings:
            reason += " Dropped drafts: " + "; ".join(warnings)
        if not persist_intermediate:
            _cleanup_temp_tree(temp_dir)
        return _block_deep_thinking(ctx, state, stage=stage, reason=reason)

    if len(candidates) == 1:
        only = candidates[0]
        _write_official_result(official_output, official_result_json, only["output_text"], only["result"])
        ctx.log_event(
            state,
            "deep_thinking_single_candidate",
            "only one usable draft; promoted without synthesis",
            stage=stage,
            console=show_logs,
            provider=only["provider"],
        )
        return _finalize_parallel(ctx, 
            state,
            stage=stage,
            provider=only["provider"],
            result=only["result"],
            config=config,
            temp_dir=temp_dir,
            warnings=warnings,
            label="single_candidate",
        )

    # Phase 2: synthesize the candidates into the official plan.
    synth_prompt = _synthesis_prompt(base_prompt=base_prompt, candidates=candidates, config=config)
    state["status"] = RunStatus.MODEL_RUNNING
    ctx.save_state(state)
    before_head = ctx.safe_git_head()
    run_result = ctx.run_text_provider_prompt(
        synthesizer,
        synth_prompt,
        logs_dir=logs_dir,
        log_prefix=f"{stage}_synthesis_{synthesizer}",
        timeout_seconds=timeout_seconds,
        performance=performance,
    )
    after_head = ctx.safe_git_head()
    if before_head and after_head and before_head != after_head:
        return _block_head_change(ctx, 
            state, stage=stage, provider=synthesizer, before_head=before_head, after_head=after_head
        )
    if run_result.get("timed_out"):
        return _block_provider_failure(ctx, 
            state,
            stage=stage,
            provider=synthesizer,
            failure=f"timed out after {timeout_seconds} seconds",
            run_result=run_result,
        )
    returncode = run_result.get("returncode")
    if returncode not in {0, None}:
        return _block_provider_failure(ctx, 
            state,
            stage=stage,
            provider=synthesizer,
            failure=f"exited with code {returncode}",
            run_result=run_result,
        )

    candidate = _read_candidate(ctx, official_output, official_result_json)
    if candidate is None:
        return _block_missing_candidate(ctx, 
            state,
            stage=stage,
            provider=synthesizer,
            run_result=run_result,
            output_path=official_output,
            result_json_path=official_result_json,
        )

    _, _, synth_result = candidate
    return _finalize_parallel(ctx, 
        state,
        stage=stage,
        provider=synthesizer,
        result=synth_result,
        config=config,
        temp_dir=temp_dir,
        warnings=warnings,
        label="synthesis",
    )


_ROLE_INSTRUCTION_KEYS = {
    "select": "select_instruction",
    "ground": "ground_instruction",
    "premortem": "premortem_instruction",
}


def _bundle(roles: list[str], n: int) -> list[list[str]]:
    if n <= 0:
        return []
    buckets: list[list[str]] = [[] for _ in range(n)]
    for index, role in enumerate(roles):
        buckets[min(index, n - 1)].append(role)
    return buckets


def _relay_instruction(config: dict[str, Any], roles: list[str]) -> str:
    lines: list[str] = list(_as_lines(config.get("common_instruction_lines")))
    for role in roles:
        entry = config.get(_ROLE_INSTRUCTION_KEYS.get(role, ""))
        body = _as_lines(entry.get("lines")) if isinstance(entry, dict) else []
        if body:
            if lines:
                lines.append("")
            lines.extend(body)
    return "\n".join(lines).strip() or "- 추가 내부 지시 없음"


def _relay_step_prompt(ctx, 
    *,
    base_prompt: str,
    official_output: Path,
    official_result_json: Path,
    step_output: Path,
    step_result_json: Path,
    config: dict[str, Any],
    roles: list[str],
    prior_plan_text: str | None,
    candidates: list[dict[str, Any]],
    is_final: bool,
) -> str:
    if is_final:
        text = base_prompt
    else:
        text = base_prompt.replace(ctx.rel(official_result_json), ctx.rel(step_result_json))
        text = text.replace(ctx.rel(official_output), ctx.rel(step_output))
    if "select" in roles:
        input_block = (
            "## Deep Thinking 종합 대상 후보 계획 (익명)\n\n"
            + _previous_candidate_context(candidates, config)
        )
    else:
        try:
            max_chars = int(config.get("previous_candidate_max_chars", 60000) or 60000)
        except (TypeError, ValueError):
            max_chars = 60000
        input_block = (
            "## Deep Thinking 현재 계획 (직전 단계 결과)\n\n"
            + "```markdown\n"
            + _limit_text(str(prior_plan_text or ""), max_chars)
            + "\n```"
        )
    instruction = _relay_instruction(config, roles)
    return (
        text.rstrip()
        + "\n\n---\n\n"
        + input_block
        + "\n\n## Deep Thinking 단계 지시\n\n"
        + instruction
        + "\n"
    )


def _finalize_max(
    ctx, state: dict[str, Any],
    *,
    stage: str,
    provider: str,
    result: dict[str, Any],
    config: dict[str, Any],
    temp_dir: Path,
    warnings: list[str],
    label: str,
) -> dict[str, Any]:
    if not bool(config.get("persist_intermediate_outputs", False)):
        _cleanup_temp_tree(temp_dir)
    _update_stage_provider(state, stage, provider)
    state["status"] = RunStatus.MODEL_COMPLETED
    if warnings:
        state["deep_thinking_warnings"] = warnings
    else:
        state.pop("deep_thinking_warnings", None)
    ctx.log_event(state, "provider_completed", f"{provider} completed", stage=stage, provider=provider, console=False)
    ctx.log_event(
        state,
        "deep_thinking_completed",
        f"deep-thinking max plan completed ({label})",
        stage=stage,
        console=False,
        provider=provider,
        status=ctx.stage_status(result),
        warnings=len(warnings),
    )
    ctx.save_state(state)
    return state


def _collect_max_drafts(
    ctx, state: dict[str, Any],
    *,
    stage: str,
    base_prompt: str,
    official_output: Path,
    official_result_json: Path,
    backups: dict[Path, bytes | None],
    drafters: list[str],
    temp_dir: Path,
    logs_dir: Path,
    config: dict[str, Any],
    timeout_seconds: int,
    performance: Any,
    show_logs: bool,
) -> dict[str, Any]:
    specs: list[dict[str, Any]] = []
    for provider in drafters:
        draft_output = temp_dir / f"{stage}_draft_{provider}.md"
        draft_result_json = temp_dir / f"{stage}_draft_{provider}.result.json"
        _cleanup_temp_path(draft_output)
        _cleanup_temp_path(draft_result_json)
        specs.append(
            {
                "provider": provider,
                "output_path": draft_output,
                "result_json_path": draft_result_json,
                "prompt_text": _draft_prompt(ctx, 
                    base_prompt=base_prompt,
                    official_output=official_output,
                    official_result_json=official_result_json,
                    draft_output=draft_output,
                    draft_result_json=draft_result_json,
                    config=config,
                ),
            }
        )

    state["status"] = RunStatus.MODEL_RUNNING
    ctx.save_state(state)
    before_head = ctx.safe_git_head()
    draft_runs = _run_drafts_parallel(ctx, 
        specs, logs_dir=logs_dir, stage=stage, timeout_seconds=timeout_seconds, performance=performance
    )
    after_head = ctx.safe_git_head()
    if before_head and after_head and before_head != after_head:
        _restore_official_backups(backups)
        return {"head_change": (before_head, after_head)}

    candidates: list[dict[str, Any]] = []
    needs_user: dict[str, Any] | None = None
    warnings: list[str] = []

    def drop(provider: str, why: str) -> None:
        warnings.append(f"{provider}: {why}")
        ctx.log_event(
            state,
            "deep_thinking_draft_dropped",
            f"draft from {provider} dropped: {why}",
            stage=stage,
            console=show_logs,
            provider=provider,
        )

    for run in draft_runs:
        provider = run["provider"]
        if run.get("error"):
            drop(provider, str(run["error"]))
            continue
        run_result = run["run_result"]
        if run_result.get("timed_out"):
            drop(provider, f"timed out after {timeout_seconds}s")
            continue
        returncode = run_result.get("returncode")
        if returncode not in {0, None}:
            drop(provider, f"exited with code {returncode}")
            continue
        candidate = _read_candidate(ctx, run["output_path"], run["result_json_path"])
        if candidate is None:
            drop(provider, "no readable candidate")
            continue
        candidate_path, candidate_text, candidate_result = candidate
        candidate_status = ctx.stage_status(candidate_result)
        if candidate_status == ResultStatus.NEEDS_USER:
            if needs_user is None:
                needs_user = {"provider": provider, "text": candidate_text, "result": candidate_result}
            continue
        if candidate_status == ResultStatus.PASS:
            candidates.append(
                {
                    "iteration": len(candidates) + 1,
                    "provider": provider,
                    "output_path": ctx.rel(candidate_path),
                    "output_text": candidate_text,
                    "result": candidate_result,
                }
            )
        else:
            drop(provider, f"status {candidate_status}")

    _restore_official_backups(backups)
    return {"candidates": candidates, "needs_user": needs_user, "warnings": warnings}


def _execute_max_plan(
    ctx, state: dict[str, Any], timeout_seconds: int, config: dict[str, Any]
) -> dict[str, Any]:
    stage = _plan_stage(config)
    feature = state["feature_name"]

    prompt_rel = state.get("current_prompt")
    if not prompt_rel:
        raise HarnessError("No current prompt to execute.")
    prompt_file = ctx.ROOT / str(prompt_rel)
    if not prompt_file.exists():
        raise HarnessError(f"Prompt file does not exist: {prompt_file}")
    base_prompt = prompt_file.read_text(encoding="utf-8")

    official_output = ctx.stage_output_path(feature, stage)
    official_result_json = ctx.stage_result_json_path(feature, stage)
    backups = _official_backups([official_output, official_result_json])

    drafters = _select_drafters(ctx, config)
    min_drafters = _min_drafters(config)
    if len(drafters) < min_drafters:
        available_text = ", ".join(drafters) if drafters else "none"
        raise HarnessError(
            f"--deep-thinking max strategy needs at least {min_drafters} planning providers. "
            f"Available planning providers: {available_text}."
        )
    owner = _select_synthesizer(ctx, state, config, drafters)

    temp_dir = ctx.run_dir(feature) / ".tmp" / "deep_thinking"
    temp_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = ctx.run_dir(feature) / "logs"
    performance = ctx.normalize_performance(state.get("performance"))
    persist_intermediate = bool(config.get("persist_intermediate_outputs", False))
    show_logs = _show_iteration_logs(config)

    ctx.log_event(
        state,
        "deep_thinking_started",
        "deep-thinking max plan started",
        stage=stage,
        console=False,
        strategy="max",
        drafters=" ".join(drafters),
        owner=owner,
    )

    # Phase 1: independent blind drafts (breadth).
    collected = _collect_max_drafts(ctx, 
        state,
        stage=stage,
        base_prompt=base_prompt,
        official_output=official_output,
        official_result_json=official_result_json,
        backups=backups,
        drafters=drafters,
        temp_dir=temp_dir,
        logs_dir=logs_dir,
        config=config,
        timeout_seconds=timeout_seconds,
        performance=performance,
        show_logs=show_logs,
    )
    if "head_change" in collected:
        before_head, after_head = collected["head_change"]
        return _block_head_change(ctx, 
            state, stage=stage, provider="draft", before_head=before_head, after_head=after_head
        )
    candidates = collected["candidates"]
    needs_user = collected["needs_user"]
    warnings = collected["warnings"]

    if needs_user is not None:
        _write_official_result(official_output, official_result_json, needs_user["text"], needs_user["result"])
        return _finalize_max(ctx, 
            state,
            stage=stage,
            provider=needs_user["provider"],
            result=needs_user["result"],
            config=config,
            temp_dir=temp_dir,
            warnings=warnings,
            label="needs_user",
        )

    if not candidates:
        reason = "Deep-thinking max drafting produced no usable plan candidate."
        if warnings:
            reason += " Dropped drafts: " + "; ".join(warnings)
        if not persist_intermediate:
            _cleanup_temp_tree(temp_dir)
        return _block_deep_thinking(ctx, state, stage=stage, reason=reason)

    # Phase 2: grounded sequential relay (depth). Only providers whose draft succeeded
    # are reused, so a failing provider never blocks the relay. Jobs bundle to fit the
    # agent count; the owner always takes the final pre-mortem + finalize pass.
    healthy = [candidate["provider"] for candidate in candidates]
    preferred_owner = _select_synthesizer(ctx, state, config, drafters)
    owner = preferred_owner if preferred_owner in healthy else healthy[-1]
    relay_agents = [provider for provider in healthy if provider != owner] + [owner]
    early_roles = (["select"] if len(candidates) >= 2 else []) + ["ground"]
    early_agents = relay_agents[:-1]
    steps: list[dict[str, Any]] = []
    if early_agents:
        buckets = _bundle(early_roles, len(early_agents))
        for agent, bucket in zip(early_agents, buckets):
            if bucket:
                steps.append({"provider": agent, "roles": bucket, "is_final": False})
        final_roles = ["premortem"]
    else:
        final_roles = early_roles + ["premortem"]
    steps.append({"provider": relay_agents[-1], "roles": final_roles, "is_final": True})

    prior_text: str | None = candidates[0]["output_text"] if len(candidates) == 1 else None
    step_result: dict[str, Any] = candidates[0]["result"]

    for index, step in enumerate(steps):
        provider = step["provider"]
        roles = step["roles"]
        is_final = step["is_final"]
        if is_final:
            step_output, step_result_json = official_output, official_result_json
        else:
            step_output = temp_dir / f"{stage}_relay{index}_{provider}.md"
            step_result_json = temp_dir / f"{stage}_relay{index}_{provider}.result.json"
            _cleanup_temp_path(step_output)
            _cleanup_temp_path(step_result_json)

        prompt_text = _relay_step_prompt(ctx, 
            base_prompt=base_prompt,
            official_output=official_output,
            official_result_json=official_result_json,
            step_output=step_output,
            step_result_json=step_result_json,
            config=config,
            roles=roles,
            prior_plan_text=prior_text,
            candidates=candidates,
            is_final=is_final,
        )
        state["status"] = RunStatus.MODEL_RUNNING
        ctx.save_state(state)
        ctx.log_event(
            state,
            "deep_thinking_relay_started",
            f"max relay step {index + 1}/{len(steps)} ({'+'.join(roles)})",
            stage=stage,
            console=False,
            provider=provider,
            roles="+".join(roles),
        )
        before_head = ctx.safe_git_head()
        run_result = ctx.run_text_provider_prompt(
            provider,
            prompt_text,
            logs_dir=logs_dir,
            log_prefix=f"{stage}_relay{index}_{provider}",
            timeout_seconds=timeout_seconds,
            performance=performance,
        )
        after_head = ctx.safe_git_head()
        if before_head and after_head and before_head != after_head:
            return _block_head_change(ctx, 
                state, stage=stage, provider=provider, before_head=before_head, after_head=after_head
            )
        if run_result.get("timed_out"):
            return _block_provider_failure(ctx, 
                state,
                stage=stage,
                provider=provider,
                failure=f"timed out after {timeout_seconds} seconds",
                run_result=run_result,
            )
        returncode = run_result.get("returncode")
        if returncode not in {0, None}:
            return _block_provider_failure(ctx, 
                state,
                stage=stage,
                provider=provider,
                failure=f"exited with code {returncode}",
                run_result=run_result,
            )
        candidate = _read_candidate(ctx, step_output, step_result_json)
        if candidate is None:
            return _block_missing_candidate(ctx, 
                state,
                stage=stage,
                provider=provider,
                run_result=run_result,
                output_path=step_output,
                result_json_path=step_result_json,
            )
        _, step_text, step_result = candidate
        step_status = ctx.stage_status(step_result)
        if step_status == ResultStatus.NEEDS_USER:
            if not is_final:
                _write_official_result(official_output, official_result_json, step_text, step_result)
            return _finalize_max(ctx, 
                state,
                stage=stage,
                provider=provider,
                result=step_result,
                config=config,
                temp_dir=temp_dir,
                warnings=warnings,
                label="needs_user",
            )
        if step_status != ResultStatus.PASS:
            return _block_deep_thinking(ctx, 
                state,
                stage=stage,
                reason=f"Deep-thinking max relay step ({'+'.join(roles)}) by {provider} returned status {step_status}.",
            )
        prior_text = step_text

    return _finalize_max(ctx, 
        state,
        stage=stage,
        provider=owner,
        result=step_result,
        config=config,
        temp_dir=temp_dir,
        warnings=warnings,
        label="max",
    )


def execute_plan(ctx, state: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    config = validate_config_for_state(ctx, state)
    stage = _plan_stage(config)
    if state.get("current_stage") != stage:
        raise HarnessError(f"deep-thinking can only execute {stage}, got {state.get('current_stage')!r}.")
    strategy = _strategy(state, config)
    if strategy == "sequential":
        return _execute_relay_plan(ctx, state, timeout_seconds, config)
    if strategy == "max":
        return _execute_max_plan(ctx, state, timeout_seconds, config)
    return _execute_parallel_plan(ctx, state, timeout_seconds, config)


def _execute_relay_plan(
    ctx, state: dict[str, Any], timeout_seconds: int, config: dict[str, Any]
) -> dict[str, Any]:
    stage = _plan_stage(config)
    prompt_rel = state.get("current_prompt")
    if not prompt_rel:
        raise HarnessError("No current prompt to execute.")
    prompt_file = ctx.ROOT / str(prompt_rel)
    if not prompt_file.exists():
        raise HarnessError(f"Prompt file does not exist: {prompt_file}")

    feature = state["feature_name"]
    base_prompt = prompt_file.read_text(encoding="utf-8")
    official_output = ctx.stage_output_path(feature, stage)
    official_result_json = ctx.stage_result_json_path(feature, stage)
    backups = _official_backups([official_output, official_result_json])
    providers = _select_iteration_providers(ctx, state, config)
    iterations = _iterations(config)
    temp_dir = ctx.run_dir(feature) / ".tmp" / "deep_thinking"
    temp_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = ctx.run_dir(feature) / "logs"
    candidates: list[dict[str, Any]] = []
    persist_intermediate = bool(config.get("persist_intermediate_outputs", False))
    performance = ctx.normalize_performance(state.get("performance"))
    before_head = ctx.safe_git_head()
    show_iteration_logs = _show_iteration_logs(config)

    ctx.log_event(
        state,
        "deep_thinking_started",
        "deep-thinking plan stage started",
        stage=stage,
        console=show_iteration_logs,
        iterations=iterations,
        providers=" -> ".join(providers),
    )

    for index, provider in enumerate(providers, start=1):
        final_iteration = index == iterations
        instruction_name = _instruction_name(config, index)
        if final_iteration:
            output_path = official_output
            result_json_path = official_result_json
        else:
            output_path = temp_dir / f"{stage}_candidate{index}.md"
            result_json_path = temp_dir / f"{stage}_candidate{index}.result.json"
            _cleanup_temp_path(output_path)
            _cleanup_temp_path(result_json_path)

        prompt_text = _iteration_prompt(ctx, 
            base_prompt=base_prompt,
            config=config,
            iteration=index,
            total=iterations,
            candidates=candidates,
            official_output=official_output,
            official_result_json=official_result_json,
            output_path=output_path,
            result_json_path=result_json_path,
            final_iteration=final_iteration,
        )

        state["status"] = RunStatus.MODEL_RUNNING
        ctx.log_event(
            state,
            "deep_thinking_iteration_started",
            f"deep-thinking plan {index}/{iterations} started",
            stage=stage,
            console=show_iteration_logs,
            provider=provider,
            role=instruction_name,
            performance=performance,
            timeout_seconds=timeout_seconds,
        )
        ctx.save_state(state)

        run_result = ctx.run_text_provider_prompt(
            provider,
            prompt_text,
            logs_dir=logs_dir,
            log_prefix=f"{stage}_heavy{index}",
            timeout_seconds=timeout_seconds,
            performance=performance,
        )

        after_head = ctx.safe_git_head()
        if before_head and after_head and before_head != after_head:
            state["status"] = RunStatus.BLOCKED
            state["blocked"] = {
                "stage": stage,
                "reason": "Provider changed Git HEAD. The harness owns commits; inspect history before continuing.",
                "retry_command": ctx.suggested_retry_command(state),
            }
            ctx.write_handoff(
                state,
                str(state["blocked"]["reason"]),
                stage=stage,
                next_action="Git history를 점검한 뒤 수동으로 정리하고 retry 하세요.",
            )
            ctx.log_event(
                state,
                "blocked_provider_changed_head",
                "provider changed Git HEAD",
                stage=stage,
                provider=provider,
                before_head=before_head,
                after_head=after_head,
            )
            ctx.save_state(state)
            return state

        if run_result.get("timed_out"):
            return _block_provider_failure(ctx, 
                state,
                stage=stage,
                provider=provider,
                failure=f"timed out after {timeout_seconds} seconds",
                run_result=run_result,
            )
        returncode = run_result.get("returncode")
        if returncode not in {0, None}:
            return _block_provider_failure(ctx, 
                state,
                stage=stage,
                provider=provider,
                failure=f"exited with code {returncode}",
                run_result=run_result,
            )

        candidate = _read_candidate(ctx, 
            output_path,
            result_json_path,
            fallback_output_path=official_output if not final_iteration else None,
            fallback_result_json_path=official_result_json if not final_iteration else None,
        )
        if candidate is None:
            return _block_missing_candidate(ctx, 
                state,
                stage=stage,
                provider=provider,
                run_result=run_result,
                output_path=output_path,
                result_json_path=result_json_path,
            )

        candidate_path, candidate_text, candidate_result = candidate
        candidate_status = ctx.stage_status(candidate_result)
        if not final_iteration and candidate_status == ResultStatus.PASS:
            candidates.append(
                {
                    "iteration": index,
                    "provider": provider,
                    "output_path": ctx.rel(candidate_path),
                    "output_text": candidate_text,
                    "result": candidate_result,
                }
            )
            _restore_official_backups(backups)
            if not persist_intermediate:
                _cleanup_temp_path(output_path)
                _cleanup_temp_path(result_json_path)
            ctx.log_event(
                state,
                "deep_thinking_candidate_completed",
                f"deep-thinking plan {index}/{iterations} candidate completed",
                stage=stage,
                console=show_iteration_logs,
                provider=provider,
                role=instruction_name,
                status=candidate_status,
            )
            continue

        if not final_iteration:
            _write_official_result(official_output, official_result_json, candidate_text, candidate_result)
            if not persist_intermediate:
                _cleanup_temp_path(output_path)
                _cleanup_temp_path(result_json_path)
        elif not official_result_json.exists() and candidate_result:
            official_result_json.write_text(
                json.dumps(candidate_result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        _update_stage_provider(state, stage, provider)
        state["status"] = RunStatus.MODEL_COMPLETED
        ctx.log_event(
            state,
            "provider_completed",
            f"{provider} completed",
            stage=stage,
            provider=provider,
            stdout=str(run_result.get("stdout") or ""),
            stderr=str(run_result.get("stderr") or ""),
            elapsed_seconds=run_result.get("elapsed_seconds"),
        )
        ctx.log_event(
            state,
            "deep_thinking_completed",
            f"deep-thinking plan stage completed after {index}/{iterations}",
            stage=stage,
            console=show_iteration_logs,
            provider=provider,
            role=instruction_name,
            status=candidate_status,
        )
        ctx.save_state(state)
        if not persist_intermediate:
            _cleanup_temp_dir(temp_dir)
        return state

    raise HarnessError("deep-thinking finished without producing a final plan.")


def should_execute_plan(ctx, state: dict[str, Any]) -> bool:
    if not (state.get("deep_thinking") or state.get("heavy_thinking")):
        return False
    config = _config(ctx)
    return pipeline.supports_deep_thinking(ctx.PIPELINE_MODE) and str(
        state.get("current_stage") or ""
    ) == _plan_stage(config)
