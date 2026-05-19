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
]


def compute_coverage(profile: SystemProfile, testcases: list[TestCase], traces: list[RunTrace], faults: list[dict]) -> dict:
    text_by_trace = {trace.case_id: f"{trace.stdout or ''}\n{trace.stderr or ''}\n{trace.final_output or ''}".lower() for trace in traces}
    visited_agents = set()
    called_tools = set()
    observed_edges = set()
    for trace in traces:
        text = text_by_trace.get(trace.case_id, "")
        for agent in profile.agents:
            if agent.name.lower() in text:
                visited_agents.add(agent.name)
        for tool in profile.tools:
            if tool.name.lower() in text:
                called_tools.add(tool.name)
        for event in trace.events:
            if event.sender:
                visited_agents.add(event.sender)
            if event.receiver:
                visited_agents.add(event.receiver)
            if event.tool:
                called_tools.add(event.tool)
            if event.type == "message" and event.sender and event.receiver:
                observed_edges.add((event.sender, event.receiver))
    target_reqs = {req for case in testcases for req in case.target_requirements}
    state_hits = _state_hits(testcases, traces, faults)
    fault_mode_hits = _fault_mode_hits(testcases, faults)
    metrics = {
        "agent_coverage": _ratio(len(visited_agents & {a.name for a in profile.agents}), len(profile.agents)),
        "tool_coverage": _ratio(len(called_tools & {t.name for t in profile.tools}), len(profile.tools)),
        "message_edge_coverage": _ratio(len(observed_edges & {(e.source, e.target) for e in profile.message_edges}), len(profile.message_edges)),
        "requirement_coverage": _ratio(len(target_reqs & {r.id for r in profile.requirements}), len(profile.requirements)),
        "state_coverage": _ratio(len(state_hits), len(STATES)),
        "fault_mode_coverage": _ratio(len(fault_mode_hits), len(FAULT_MODES)),
        "details": {
            "visited_agents": sorted(visited_agents),
            "called_tools": sorted(called_tools),
            "observed_edges": sorted([list(edge) for edge in observed_edges]),
            "covered_requirements": sorted(target_reqs),
            "covered_states": sorted(state_hits),
            "covered_fault_modes": sorted(fault_mode_hits),
        },
    }
    metrics["mascov"] = round(
        0.18 * metrics["agent_coverage"]
        + 0.18 * metrics["tool_coverage"]
        + 0.16 * metrics["message_edge_coverage"]
        + 0.16 * metrics["requirement_coverage"]
        + 0.16 * metrics["state_coverage"]
        + 0.16 * metrics["fault_mode_coverage"],
        4,
    )
    return metrics


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 4)


def _state_hits(testcases: list[TestCase], traces: list[RunTrace], faults: list[dict]) -> set[str]:
    hits: set[str] = set()
    trace_by_case = {trace.case_id: trace for trace in traces}
    failure_codes = {fault.get("failure_code") for fault in faults}
    for case in testcases:
        template = case.metadata.get("fuzz_template")
        if case.case_type in {"requirement_positive", "coverage_guided", "metamorphic", "regression"}:
            hits.add("normal_task")
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
        "METAMORPHIC_RELATION_VIOLATION": "metamorphic_relation_violation",
    }
    for fault in faults:
        mode = failure_map.get(fault.get("failure_code"))
        if mode:
            hits.add(mode)
    return hits
