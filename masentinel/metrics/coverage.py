from __future__ import annotations

from masentinel.schema import RunTrace, SystemProfile, TestCase


STATES = [
    "normal_task",
    "empty_input",
    "malformed_input",
    "missing_information",
    "conflicting_instruction",
    "tool_success",
    "tool_failure",
    "tool_invalid_output",
    "property_boundary",
    "multi_turn_memory",
    "termination",
    "non_termination",
    "runtime_exception",
    "human_input_requested",
    "metamorphic_relation",
    "output_schema_violation",
    "artifact_contract",
    "filesystem_safety",
    "state_resume",
    "tool_api_contract",
    "message_handoff",
    "data_invariant",
    "cli_doc_conformance",
    "autogen_wiring",
]

FAULT_MODES = [
    "tool_schema_mismatch",
    "tool_not_registered",
    "missing_tool_call",
    "wrong_agent_routing",
    "output_contract_violation",
    "missing_error_handling",
    "non_termination",
    "message_routing_error",
    "human_input_mode_error",
    "metamorphic_relation_violation",
    "context_loss",
    "async_sync_mismatch",
    "artifact_corruption",
    "filesystem_escape",
    "resume_state_incomplete",
    "tool_api_semantics",
    "tool_error_contract",
    "message_handoff_error",
    "data_invariant_violation",
    "documented_cli_conformance",
    "autogen_wiring_missing",
]

AGENT_ALIASES = {
    "chat_manager": "group_chat_manager",
    "GroupChatManager": "group_chat_manager",
    "groupchat_manager": "group_chat_manager",
}


def compute_coverage(profile: SystemProfile, testcases: list[TestCase], traces: list[RunTrace], faults: list[dict]) -> dict:
    text_by_trace = {trace.case_id: f"{trace.stdout or ''}\n{trace.stderr or ''}\n{trace.final_output or ''}".lower() for trace in traces}
    visited_agents = set()
    called_tools = set()
    observed_edges = set()
    profile_agents = {_canon_agent(agent.name) for agent in profile.agents}
    profile_tools = {tool.name for tool in profile.tools}
    required_edges = {
        (_canon_agent(edge.source), _canon_agent(edge.target))
        for edge in profile.message_edges
        if not (edge.evidence and "potential" in edge.evidence.lower())
    }
    for trace in traces:
        text = text_by_trace.get(trace.case_id, "")
        for agent in profile.agents:
            if agent.name.lower() in text:
                visited_agents.add(_canon_agent(agent.name))
        for tool in profile.tools:
            if tool.name.lower() in text:
                called_tools.add(tool.name)
        for event in trace.events:
            if event.sender:
                visited_agents.add(_canon_agent(event.sender))
            if event.receiver:
                visited_agents.add(_canon_agent(event.receiver))
            if event.tool:
                called_tools.add(event.tool)
            if event.type == "message" and event.sender and event.receiver:
                observed_edges.add((_canon_agent(event.sender), _canon_agent(event.receiver)))
    target_reqs = {req for case in testcases for req in case.target_requirements}
    req_intent_coverage = _ratio_or_none(len(target_reqs & {r.id for r in profile.requirements}), len(profile.requirements))
    req_verified_coverage = _req_verified_coverage(profile, testcases, traces, faults)
    state_hits = _state_hits(testcases, traces, faults)
    fault_mode_hits = _fault_mode_hits(testcases, faults)
    metrics = {
        "agent_coverage": _ratio_or_none(len(visited_agents & profile_agents), len(profile_agents)),
        "tool_coverage": _ratio_or_none(len(called_tools & profile_tools), len(profile_tools)),
        "message_edge_coverage": _ratio_or_none(len(observed_edges & required_edges), len(required_edges)),
        "requirement_coverage": req_intent_coverage,
        "req_intent_coverage": req_intent_coverage,
        "req_verified_coverage": req_verified_coverage,
        "state_coverage": _ratio_or_none(len(state_hits), len(STATES)),
        "fault_mode_coverage": _ratio_or_none(len(fault_mode_hits), len(FAULT_MODES)),
        "effective_workflow_rate": _effective_workflow_rate(profile, traces, text_by_trace),
        "trace_completeness": _trace_completeness(profile, traces, text_by_trace),
        "contract_coverage": _contract_coverage(testcases),
        "root_cause_evidence_rate": _root_cause_evidence_rate(faults),
        "details": {
            "visited_agents": sorted(visited_agents),
            "called_tools": sorted(called_tools),
            "observed_edges": sorted([list(edge) for edge in observed_edges]),
            "covered_requirements": sorted(target_reqs),
            "verified_requirements": sorted(_verified_requirements(testcases, traces, faults)),
            "covered_states": sorted(state_hits),
            "covered_fault_modes": sorted(fault_mode_hits),
            "covered_contract_patterns": sorted(_contract_patterns(testcases)),
            "applicability": {
                "agents": len(profile_agents),
                "tools": len(profile_tools),
                "required_message_edges": len(required_edges),
                "profile_message_edges": len(profile.message_edges),
                "potential_message_edges": len(profile.message_edges) - len(required_edges),
            },
        },
    }
    metrics["mascov"] = _weighted_mascov(metrics)
    return metrics


def _ratio_or_none(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _weighted_mascov(metrics: dict) -> float | None:
    weights = {
        "agent_coverage": 0.18,
        "tool_coverage": 0.18,
        "message_edge_coverage": 0.16,
        "requirement_coverage": 0.16,
        "state_coverage": 0.16,
        "fault_mode_coverage": 0.16,
    }
    weighted_sum = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        value = metrics.get(key)
        if value is None:
            continue
        weighted_sum += weight * float(value)
        weight_sum += weight
    return round(weighted_sum / weight_sum, 4) if weight_sum else None


def _effective_workflow_rate(profile: SystemProfile, traces: list[RunTrace], text_by_trace: dict[str, str]) -> float | None:
    if not traces:
        return None
    effective = 0
    for trace in traces:
        text = text_by_trace.get(trace.case_id, "")
        if _has_blocker(trace, text):
            continue
        profile_agent_hits = sum(1 for agent in profile.agents if agent.name.lower() in text)
        has_message = any(event.type == "message" for event in trace.events) or profile_agent_hits >= 2
        has_tool = any(event.type in {"tool_call", "tool_result", "tool_error"} for event in trace.events)
        has_edge = any(event.type == "message" and event.sender and event.receiver for event in trace.events)
        if trace.turn_count > 0 or has_message or has_tool or has_edge:
            effective += 1
    return _ratio_or_none(effective, len(traces))


def _trace_completeness(profile: SystemProfile, traces: list[RunTrace], text_by_trace: dict[str, str]) -> float | None:
    if not traces:
        return None
    expected = ["turn_index", "termination_status", "stdout_or_final_output"]
    if profile.agents:
        expected.append("message_sender_receiver")
    if profile.tools:
        expected.extend(["tool_call", "tool_result"])
    observed: set[str] = set()
    for trace in traces:
        text = text_by_trace.get(trace.case_id, "")
        if trace.turn_count is not None:
            observed.add("turn_index")
        if trace.terminated is not None or trace.timeout is not None:
            observed.add("termination_status")
        if text.strip():
            observed.add("stdout_or_final_output")
        if any(event.type == "message" and event.sender and event.receiver for event in trace.events):
            observed.add("message_sender_receiver")
        if any(event.type == "tool_call" and event.tool for event in trace.events):
            observed.add("tool_call")
        if any(event.type in {"tool_result", "tool_error"} and event.tool for event in trace.events):
            observed.add("tool_result")
    return _ratio_or_none(len(observed & set(expected)), len(expected))


def _contract_patterns(testcases: list[TestCase]) -> set[str]:
    return {str(case.metadata.get("generic_pattern")) for case in testcases if case.metadata.get("generic_pattern") and not case.metadata.get("legacy_type")}


def _contract_coverage(testcases: list[TestCase]) -> float | None:
    expected = {
        "artifact_contract",
        "safe_project_root",
        "partial_resume_state",
        "external_api_contract",
        "tool_error_envelope",
        "scalable_budget",
        "message_handoff_integrity",
        "partial_data_invariant",
        "numeric_sign_convention",
        "documented_cli_conformance",
        "autogen_wiring_conformance",
    }
    observed = _contract_patterns(testcases)
    applicable = expected & observed
    if not applicable:
        return None
    return _ratio_or_none(len(applicable), len(expected))


def _root_cause_evidence_rate(faults: list[dict]) -> float | None:
    if not faults:
        return None
    strong = [
        fault
        for fault in faults
        if fault.get("root_cause_confidence") in {"code_evidence", "trace_only"} and float(fault.get("evidence_strength", 0) or 0) >= 0.5
    ]
    return _ratio_or_none(len(strong), len(faults))


def _verified_requirements(testcases: list[TestCase], traces: list[RunTrace], faults: list[dict]) -> set[str]:
    trace_by_case = {trace.case_id: trace for trace in traces}
    fault_cases = {str(fault.get("case_id")) for fault in faults if not fault.get("suspected_false_positive")}
    verified: set[str] = set()
    for case in testcases:
        if not case.target_requirements:
            continue
        trace = trace_by_case.get(case.case_id)
        if not trace or case.case_id in fault_cases:
            continue
        if trace.status == "passed" and trace.terminated and not trace.timeout and trace.returncode in (0, None):
            verified.update(case.target_requirements)
    return verified


def _req_verified_coverage(profile: SystemProfile, testcases: list[TestCase], traces: list[RunTrace], faults: list[dict]) -> float | None:
    return _ratio_or_none(len(_verified_requirements(testcases, traces, faults) & {req.id for req in profile.requirements}), len(profile.requirements))


def _has_blocker(trace: RunTrace, text: str) -> bool:
    if trace.timeout and trace.turn_count == 0:
        return True
    return any(
        marker in text
        for marker in (
            "authentication fails",
            "http 401",
            "http 403",
            "unauthorized",
            "invalid api key",
            "rate limit",
            "openai.apitimeouterror",
            "request timed out",
            "connecttimeout",
        )
    )


def _canon_agent(name: str | None) -> str:
    if not name:
        return ""
    value = str(name).strip()
    return AGENT_ALIASES.get(value, AGENT_ALIASES.get(value.lower(), value))


def _state_hits(testcases: list[TestCase], traces: list[RunTrace], faults: list[dict]) -> set[str]:
    hits: set[str] = set()
    trace_by_case = {trace.case_id: trace for trace in traces}
    failure_codes = {fault.get("failure_code") for fault in faults}
    for case in testcases:
        template = case.metadata.get("fuzz_template")
        if case.case_type in {"positive_smoke", "requirement_positive", "coverage_guided", "metamorphic", "regression", "tool_contract_positive", "output_contract"}:
            hits.add("normal_task")
        state_by_case = {
            "artifact_contract": "artifact_contract",
            "filesystem_safety": "filesystem_safety",
            "state_resume_contract": "state_resume",
            "tool_api_contract": "tool_api_contract",
            "tool_error_contract": "tool_api_contract",
            "message_handoff_integrity": "message_handoff",
            "data_invariant": "data_invariant",
            "cli_doc_conformance": "cli_doc_conformance",
            "autogen_wiring": "autogen_wiring",
        }
        if case.case_type in state_by_case:
            hits.add(state_by_case[case.case_type])
        if case.case_type == "automation_no_human":
            hits.add("human_input_requested")
        if case.case_type == "termination_signal":
            hits.add("termination")
        if case.case_type == "speaker_selection_robustness":
            hits.add("non_termination")
        if case.case_type == "property_boundary":
            hits.add("property_boundary")
        if case.case_type == "metamorphic":
            hits.add("metamorphic_relation")
        if template in {"empty_input", "malformed_input", "missing_information", "conflicting_instruction", "multi_turn_memory"}:
            hits.add(template)
        if template == "tool_failure":
            hits.add("tool_failure")
        if template == "tool_empty_result":
            hits.add("tool_success")
        if template == "tool_invalid_json":
            hits.add("tool_invalid_output")
        trace = trace_by_case.get(case.case_id)
        if trace and trace.terminated:
            hits.add("termination")
        if trace and (trace.timeout or not trace.terminated):
            hits.add("non_termination")
    if "RUNTIME_EXCEPTION" in failure_codes:
        hits.add("runtime_exception")
    if "HUMAN_INPUT_REQUESTED" in failure_codes:
        hits.add("human_input_requested")
    if "OUTPUT_SCHEMA_VIOLATION" in failure_codes:
        hits.add("output_schema_violation")
    return hits


def _fault_mode_hits(testcases: list[TestCase], faults: list[dict]) -> set[str]:
    hits: set[str] = set()
    template_map = {
        "tool_failure": "missing_error_handling",
        "tool_invalid_json": "output_contract_violation",
        "termination_stress": "non_termination",
        "multi_turn_memory": "context_loss",
    }
    for case in testcases:
        mode = template_map.get(case.metadata.get("fuzz_template"))
        if mode:
            hits.add(mode)
    failure_map = {
        "TOOL_SCHEMA_MISMATCH": "tool_schema_mismatch",
        "TOOL_HALLUCINATION": "tool_not_registered",
        "MISSING_TOOL_CALL": "missing_tool_call",
        "MISSING_AGENT": "wrong_agent_routing",
        "OUTPUT_SCHEMA_VIOLATION": "output_contract_violation",
        "RUNTIME_EXCEPTION": "missing_error_handling",
        "NON_TERMINATION": "non_termination",
        "TIMEOUT": "non_termination",
        "MISSING_MESSAGE_EDGE": "message_routing_error",
        "HUMAN_INPUT_REQUESTED": "human_input_mode_error",
        "SPEAKER_SELECTION_LOOP": "message_routing_error",
        "TERMINATION_SIGNAL_IGNORED": "non_termination",
        "METAMORPHIC_RELATION_VIOLATION": "metamorphic_relation_violation",
        "BUSINESS_TASK_FAILED": "output_contract_violation",
        "MARKDOWN_ARTIFACT_CORRUPTION": "artifact_corruption",
        "ARTIFACT_SCHEMA_MISMATCH": "artifact_corruption",
        "FILESYSTEM_ESCAPE": "filesystem_escape",
        "RESUME_STATE_INCOMPLETE": "resume_state_incomplete",
        "VIEW_PARAMETER_IGNORED": "tool_api_semantics",
        "PAGINATION_NOT_FOLLOWED": "tool_api_semantics",
        "TOOL_RAW_HTTP_ERROR": "tool_error_contract",
        "TOOL_RETURNED_NONE": "tool_error_contract",
        "TOOL_UNSTRUCTURED_ERROR": "tool_error_contract",
        "HTTP_STATUS_NOT_CHECKED": "tool_error_contract",
        "SCALABLE_BUDGET_EXCEEDED": "non_termination",
        "MESSAGE_HANDOFF_TERMINATE_ONLY": "message_handoff_error",
        "MESSAGE_HANDOFF_EMPTY": "message_handoff_error",
        "PARTIAL_METRIC_ZEROED": "data_invariant_violation",
        "NUMERIC_SIGN_CONVENTION_ERROR": "data_invariant_violation",
        "DOCUMENTED_ENTRYPOINT_BROKEN": "documented_cli_conformance",
        "DOCUMENTED_CLI_COMMAND_MISSING": "documented_cli_conformance",
        "AUTOGEN_WIRING_MISSING": "autogen_wiring_missing",
    }
    for fault in faults:
        mode = failure_map.get(fault.get("failure_code"))
        if mode:
            hits.add(mode)
    metadata_mode_map = {
        "speaker_selection_loop": "message_routing_error",
        "human_input_mode_error": "human_input_mode_error",
        "termination_signal_ignored": "non_termination",
        "tool_registration_missing_or_data_provider_not_wired": "tool_not_registered",
        "artifact_corruption": "artifact_corruption",
        "artifact_schema_mismatch": "artifact_corruption",
        "filesystem_escape": "filesystem_escape",
        "resume_state_incomplete": "resume_state_incomplete",
        "tool_api_semantics": "tool_api_semantics",
        "tool_unstructured_error": "tool_error_contract",
        "message_handoff_error": "message_handoff_error",
        "partial_metric_zeroed": "data_invariant_violation",
        "numeric_sign_convention_error": "data_invariant_violation",
        "documented_cli_conformance": "documented_cli_conformance",
        "autogen_wiring_missing": "autogen_wiring_missing",
    }
    for case in testcases:
        mode = metadata_mode_map.get(str(case.metadata.get("target_fault_mode", "")))
        if mode:
            hits.add(mode)
    return hits
