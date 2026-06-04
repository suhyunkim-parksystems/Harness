from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Callable, Mapping


@dataclass
class HarnessContext:
    """Explicit dependency surface passed from harness.py into harness_core.

    Fields mirror the harness-level constants and functions that the core
    modules consume. This replaces the former ad-hoc ctx dict / globals()
    injection: dependencies are now an explicit, attribute-accessible,
    IDE-navigable, statically-checkable interface. Build instances with
    from_namespace(); every field defaults to None so partial contexts
    (e.g. in unit tests) are valid. Types are intentionally broad because
    the harness runtime is composed dynamically.
    """

    # --- constants ---
    AI_DIR: Any = None
    DEFAULT_MODEL_POLICY: Any = None
    DEFAULT_PERFORMANCE: Any = None
    DEFAULT_PROVIDER_CAPABILITIES: Any = None
    DEFAULT_PROVIDER_COMMANDS: Any = None
    DEFAULT_PROVIDER_HEARTBEAT_SECONDS: Any = None
    DEFAULT_VERIFY_COMMAND_TIMEOUT_SECONDS: Any = None
    DOCS_DIR: Any = None
    DOCUMENT_STAGE: Any = None
    HISTORY_DIR: Any = None
    HISTORY_SCHEMA_VERSION: Any = None
    NO_COMMIT_STAGES: Any = None
    PC_CANDIDATES_PATH: Any = None
    PC_CANDIDATES_SCHEMA_VERSION: Any = None
    PC_PENDING_STATUS: Any = None
    PC_PROJECT_WIDE_SCOPE: Any = None
    PC_REVIEW_STAGE: Any = None
    PERFORMANCE_PROFILES: Any = None
    PIPELINE_MODE: Any = None
    PROJECT_CONTRACT_PATH: Any = None
    PROVIDERS: Any = None
    PROVIDER_BY_MODEL: Any = None
    ROOT: Any = None
    STAGES: Any = None
    STAGE_OUTPUTS: Any = None
    START_STAGE: Any = None
    VERIFY_RETRY_TARGET_STAGE: Any = None
    VERIFY_STAGE: Any = None

    # --- callables ---
    apply_performance_to_command: Callable[..., Any] | None = None
    assert_no_incomplete_runs_for_new_run: Callable[..., Any] | None = None
    assert_no_unpushed_commits_for_new_run: Callable[..., Any] | None = None
    available_providers: Callable[..., Any] | None = None
    boolish: Callable[..., Any] | None = None
    build_provider_schedule: Callable[..., Any] | None = None
    candidate_providers_for_stage: Callable[..., Any] | None = None
    color_text: Callable[..., Any] | None = None
    compact_history_text: Callable[..., Any] | None = None
    compute_provider_schedule: Callable[..., Any] | None = None
    config_path: Callable[..., Any] | None = None
    configured_verification_commands: Callable[..., Any] | None = None
    display_cwd: Callable[..., Any] | None = None
    enforce_harness_verify_result: Callable[..., Any] | None = None
    ensure_dirs: Callable[..., Any] | None = None
    ensure_project_contract_file: Callable[..., Any] | None = None
    ensure_provider_schedule: Callable[..., Any] | None = None
    execute_current_prompt: Callable[..., Any] | None = None
    expand_runtime_placeholders: Callable[..., Any] | None = None
    expected_docx_path: Callable[..., Any] | None = None
    extract_feature_name: Callable[..., Any] | None = None
    extract_project_contract_candidates: Callable[..., Any] | None = None
    feature_dir: Callable[..., Any] | None = None
    file_hash: Callable[..., Any] | None = None
    file_policy_snapshot: Callable[..., Any] | None = None
    file_size: Callable[..., Any] | None = None
    filtered_changed_paths: Callable[..., Any] | None = None
    find_stage_result: Callable[..., Any] | None = None
    format_bytes: Callable[..., Any] | None = None
    format_duration: Callable[..., Any] | None = None
    generate_prompt: Callable[..., Any] | None = None
    git_add: Callable[..., Any] | None = None
    git_changed_paths: Callable[..., Any] | None = None
    git_commit: Callable[..., Any] | None = None
    git_head: Callable[..., Any] | None = None
    history_list: Callable[..., Any] | None = None
    history_object_list: Callable[..., Any] | None = None
    is_production_code_path: Callable[..., Any] | None = None
    is_test_path: Callable[..., Any] | None = None
    iso_now: Callable[..., Any] | None = None
    known_provider_names: Callable[..., Any] | None = None
    latest_code_writer: Callable[..., Any] | None = None
    latest_verification_result_path: Callable[..., Any] | None = None
    load_config: Callable[..., Any] | None = None
    load_state: Callable[..., Any] | None = None
    log_event: Callable[..., Any] | None = None
    markdown_section_items: Callable[..., Any] | None = None
    model_policy: Callable[..., Any] | None = None
    norm_repo_path: Callable[..., Any] | None = None
    normalize_performance: Callable[..., Any] | None = None
    now_stamp: Callable[..., Any] | None = None
    ordered_unique: Callable[..., Any] | None = None
    parse_result_json_from_text: Callable[..., Any] | None = None
    pc_candidates_path: Callable[..., Any] | None = None
    performance_profile: Callable[..., Any] | None = None
    pipeline_extracts_pc_candidates: Callable[..., Any] | None = None
    prepare_provider_command: Callable[..., Any] | None = None
    preset_provider_for_stage: Callable[..., Any] | None = None
    project_contract_prompt_text: Callable[..., Any] | None = None
    prompt_path: Callable[..., Any] | None = None
    provider_available: Callable[..., Any] | None = None
    provider_capabilities: Callable[..., Any] | None = None
    provider_command: Callable[..., Any] | None = None
    provider_config: Callable[..., Any] | None = None
    provider_enabled: Callable[..., Any] | None = None
    provider_failure_reason: Callable[..., Any] | None = None
    provider_for_stage: Callable[..., Any] | None = None
    provider_order_for_role: Callable[..., Any] | None = None
    provider_performance_settings: Callable[..., Any] | None = None
    provider_schedule_stages: Callable[..., Any] | None = None
    raw_provider_command: Callable[..., Any] | None = None
    read_json_file: Callable[..., Any] | None = None
    read_preset: Callable[..., Any] | None = None
    read_stage_result_json: Callable[..., Any] | None = None
    record_project_history: Callable[..., Any] | None = None
    redact_prompt_command: Callable[..., Any] | None = None
    rel: Callable[..., Any] | None = None
    resolve_executable: Callable[..., Any] | None = None
    run_dir: Callable[..., Any] | None = None
    run_harness_verification: Callable[..., Any] | None = None
    run_text_provider_prompt: Callable[..., Any] | None = None
    safe_git_head: Callable[..., Any] | None = None
    save_state: Callable[..., Any] | None = None
    should_extract_pc_candidates: Callable[..., Any] | None = None
    slugify: Callable[..., Any] | None = None
    stage_default_next: Callable[..., Any] | None = None
    stage_output_path: Callable[..., Any] | None = None
    stage_provider_score: Callable[..., Any] | None = None
    stage_result_json_path: Callable[..., Any] | None = None
    stage_role: Callable[..., Any] | None = None
    stage_status: Callable[..., Any] | None = None
    state_path: Callable[..., Any] | None = None
    suggested_retry_command: Callable[..., Any] | None = None
    validate_deep_thinking_ready: Callable[..., Any] | None = None
    validate_docx_file: Callable[..., Any] | None = None
    validate_slug: Callable[..., Any] | None = None
    verification_dir: Callable[..., Any] | None = None
    warn_pending_pc_candidates_for_new_run: Callable[..., Any] | None = None
    write_config: Callable[..., Any] | None = None
    write_handoff: Callable[..., Any] | None = None
    write_json_file: Callable[..., Any] | None = None
    write_policy_violations: Callable[..., Any] | None = None

    @classmethod
    def from_namespace(cls, ns: "Mapping[str, Any]") -> "HarnessContext":
        """Build a context from any name->value mapping, ignoring extra keys."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in ns.items() if k in known})

    # --- dict-compatibility safety belt (defensive; prefer attribute access) ---
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        return getattr(self, key, None) is not None

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
