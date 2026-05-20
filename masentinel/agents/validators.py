from __future__ import annotations

from typing import Any

from masentinel.schema import FaultInjectionSpec, RequirementInfo, SystemProfile, TestCase, TestOracleSpec


def requirements_from_agent_output(output: dict[str, Any], fallback: list[RequirementInfo]) -> list[RequirementInfo]:
    requirements: list[RequirementInfo] = []
    for index, item in enumerate(output.get("requirements", []) if isinstance(output, dict) else []):
        if not isinstance(item, dict) or not item.get("description"):
            continue
        requirements.append(
            RequirementInfo(
                id=str(item.get("id") or f"R{index + 1}"),
                description=str(item["description"]),
                expected_agents=[str(x) for x in item.get("expected_agents", [])],
                expected_tools=[str(x) for x in item.get("expected_tools", [])],
                expected_behavior=[str(x) for x in item.get("expected_behavior", [])],
                negative_cases=[str(x) for x in item.get("negative_cases", [])],
            )
        )
    return requirements or fallback


def testcases_from_agent_output(output: dict[str, Any], profile: SystemProfile) -> list[TestCase]:
    cases: list[TestCase] = []
    for index, item in enumerate(output.get("testcases", []) if isinstance(output, dict) else []):
        if not isinstance(item, dict):
            continue
        input_sequence = [dict(x) for x in _as_list(item.get("input_sequence", [])) if isinstance(x, dict)]
        raw_input = str(item.get("input") or _input_from_sequence(input_sequence))
        if not raw_input and not input_sequence:
            continue
        oracle_data = item.get("oracle") if isinstance(item.get("oracle"), dict) else {}
        must_cover_edges = []
        for edge in _as_list(oracle_data.get("must_cover_edges", [])):
            if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                must_cover_edges.append((str(edge[0]), str(edge[1])))
        target_edges = []
        for edge in _as_list(item.get("target_edges", [])):
            if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                target_edges.append((str(edge[0]), str(edge[1])))
        injection_data = item.get("fault_injection") if isinstance(item.get("fault_injection"), dict) else None
        cases.append(
            TestCase(
                case_id=str(item.get("case_id") or f"{profile.system_id}_AGENT_{index + 1:03d}"),
                system_id=profile.system_id,
                case_type=str(item.get("case_type") or "agent_generated"),
                objective=str(item.get("objective") or "Agent-generated test case"),
                input=raw_input,
                input_sequence=input_sequence,
                target_requirements=[str(x) for x in _as_list(item.get("target_requirements", []))],
                target_agents=[str(x) for x in _as_list(item.get("target_agents", []))],
                target_tools=[str(x) for x in _as_list(item.get("target_tools", []))],
                target_edges=target_edges,
                oracle=TestOracleSpec(
                    must_terminate=_as_bool(oracle_data.get("must_terminate", True), default=True),
                    max_turns=_as_int(oracle_data.get("max_turns", 15), default=15, minimum=1, maximum=100),
                    must_not_crash=_as_bool(oracle_data.get("must_not_crash", True), default=True),
                    must_visit_agents=[str(x) for x in _as_list(oracle_data.get("must_visit_agents", []))],
                    must_call_tools=[str(x) for x in _as_list(oracle_data.get("must_call_tools", []))],
                    must_cover_edges=must_cover_edges,
                    must_not_call_tools=[str(x) for x in _as_list(oracle_data.get("must_not_call_tools", []))],
                    must_not_fabricate_tool_result=_as_bool(oracle_data.get("must_not_fabricate_tool_result", False), default=False),
                    output_contract=str(oracle_data.get("output_contract")) if oracle_data.get("output_contract") is not None else None,
                    expected_keywords=[str(x) for x in _as_list(oracle_data.get("expected_keywords", []))],
                ),
                fault_injection=FaultInjectionSpec(**injection_data) if injection_data else None,
                metadata=dict(item.get("metadata", {})) if isinstance(item.get("metadata"), dict) else {"source": "agent"},
            )
        )
    return cases


def merge_testcases(agent_cases: list[TestCase], deterministic_cases: list[TestCase], limit: int | None = None) -> list[TestCase]:
    merged: list[TestCase] = []
    seen: set[tuple[str, str]] = set()
    for case in agent_cases + deterministic_cases:
        key = (case.case_type, case.input or _input_from_sequence(case.input_sequence))
        if key in seen:
            continue
        seen.add(key)
        merged.append(case)
    if limit and len(merged) > limit:
        merged = _select_with_required_types(merged, limit)
    return _renumber(merged)


def _input_from_sequence(input_sequence: list[dict[str, str]]) -> str:
    return "\n".join(str(item.get("content", "")) for item in input_sequence if item.get("content")).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        if "items" in value and isinstance(value["items"], list):
            return value["items"]
        if "value" in value:
            return _as_list(value["value"])
        return [value]
    return [value]


def _as_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, (list, tuple)):
        value = next((item for item in value if item not in (None, "")), default)
    if isinstance(value, dict):
        value = value.get("value", value.get("max_turns", default))
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, (list, tuple)):
        value = next((item for item in value if item not in (None, "")), default)
    if isinstance(value, dict):
        value = value.get("value", default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _select_with_required_types(cases: list[TestCase], limit: int) -> list[TestCase]:
    required = [
        "positive_smoke",
        "automation_no_human",
        "requirement_positive",
        "artifact_contract",
        "filesystem_safety",
        "state_resume_contract",
        "tool_api_contract",
        "tool_error_contract",
        "message_handoff_integrity",
        "data_invariant",
        "cli_doc_conformance",
        "autogen_wiring",
        "scalable_budget",
        "coverage_guided",
        "termination_signal",
        "speaker_selection_robustness",
        "tool_contract_positive",
        "output_contract",
        "tool_registration_contract",
        "property_boundary",
        "fuzz_negative",
        "fuzz_tool_failure",
        "metamorphic",
        "regression",
    ]
    selected: list[TestCase] = []
    for case_type in required:
        match = next((case for case in cases if case.case_type == case_type), None)
        if match and match not in selected:
            selected.append(match)
    for case in cases:
        if len(selected) >= limit:
            break
        if case not in selected:
            selected.append(case)
    return selected[:limit]


def _renumber(cases: list[TestCase]) -> list[TestCase]:
    counters: dict[str, int] = {}
    prefixes = {
        "requirement_positive": "REQ",
        "positive_smoke": "SMOKE",
        "automation_no_human": "NOHUMAN",
        "termination_signal": "TERM",
        "speaker_selection_robustness": "SPEAKER",
        "tool_contract_positive": "TOOLCONTRACT",
        "output_contract": "OUTCONTRACT",
        "tool_registration_contract": "TOOLREG",
        "coverage_guided": "COV",
        "property_boundary": "PROP",
        "fuzz_negative": "FUZZ",
        "fuzz_tool_failure": "TOOLFUZZ",
        "metamorphic": "META",
        "regression": "REG",
        "artifact_contract": "ARTIFACT",
        "filesystem_safety": "FSSAFE",
        "state_resume_contract": "RESUME",
        "tool_api_contract": "TOOLAPI",
        "tool_error_contract": "TOOLERR",
        "scalable_budget": "BUDGET",
        "message_handoff_integrity": "HANDOFF",
        "data_invariant": "DATAINV",
        "cli_doc_conformance": "CLIDOC",
        "autogen_wiring": "WIRING",
        "agent_generated": "AGENT",
    }
    for case in cases:
        counters[case.case_type] = counters.get(case.case_type, 0) + 1
        prefix = prefixes.get(case.case_type, "AGENT")
        case.case_id = f"{case.system_id}_{prefix}_{counters[case.case_type]:03d}"
    return cases
