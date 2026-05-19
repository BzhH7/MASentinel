from __future__ import annotations

from pathlib import Path
from typing import Any

from masentinel.schema import SystemProfile, TestCase
from masentinel.utils import write_json


def validate_testcases(
    testcases: list[TestCase],
    profile: SystemProfile,
    out_dir: str | Path | None = None,
    max_input_chars: int | None = None,
) -> tuple[list[TestCase], list[dict[str, Any]]]:
    agent_names = {agent.name for agent in profile.agents}
    tool_names = {tool.name for tool in profile.tools}
    requirement_ids = {req.id for req in profile.requirements}
    valid: list[TestCase] = []
    report: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for case in testcases:
        errors: list[str] = []
        warnings: list[str] = []
        if not case.case_id:
            errors.append("missing case_id")
        if not case.input and not case.input_sequence and case.metadata.get("fuzz_template") != "empty_input":
            errors.append("empty input outside explicit empty_input/property case")
        if not case.oracle:
            errors.append("missing oracle")
        if max_input_chars and max_input_chars > 0:
            _apply_input_budget(case, max_input_chars, warnings)
        if not (
            case.oracle.must_terminate
            or case.oracle.must_not_crash
            or case.oracle.must_visit_agents
            or case.oracle.must_call_tools
            or case.oracle.must_cover_edges
            or case.oracle.must_not_fabricate_tool_result
            or case.oracle.output_contract
        ):
            errors.append("oracle has no executable condition")
        unknown_agents = [agent for agent in case.target_agents + case.oracle.must_visit_agents if agent and agent not in agent_names]
        unknown_tools = [tool for tool in case.target_tools + case.oracle.must_call_tools + case.oracle.must_not_call_tools if tool and tool not in tool_names]
        unknown_reqs = [req for req in case.target_requirements if req and req not in requirement_ids]
        if unknown_agents:
            warnings.append(f"unknown agents removed: {unknown_agents}")
            case.target_agents = [agent for agent in case.target_agents if agent in agent_names]
            case.oracle.must_visit_agents = [agent for agent in case.oracle.must_visit_agents if agent in agent_names]
        if unknown_tools:
            warnings.append(f"unknown tools removed: {unknown_tools}")
            case.target_tools = [tool for tool in case.target_tools if tool in tool_names]
            case.oracle.must_call_tools = [tool for tool in case.oracle.must_call_tools if tool in tool_names]
            case.oracle.must_not_call_tools = [tool for tool in case.oracle.must_not_call_tools if tool in tool_names]
        if unknown_reqs:
            warnings.append(f"unknown requirements removed: {unknown_reqs}")
            case.target_requirements = [req for req in case.target_requirements if req in requirement_ids]
        if case.fault_injection and case.fault_injection.tool and case.fault_injection.tool not in tool_names:
            errors.append(f"fault injection targets unknown tool: {case.fault_injection.tool}")
        key = (case.case_type, case.input, ",".join(case.target_agents + case.target_tools))
        if key in seen:
            warnings.append("duplicate case dropped")
            errors.append("duplicate")
        else:
            seen.add(key)
        accepted = not errors
        report.append({"case_id": case.case_id, "accepted": accepted, "errors": errors, "warnings": warnings})
        if accepted:
            valid.append(case)
    if out_dir:
        write_json(Path(out_dir) / "testcases.validation_report.json", report)
    return valid, report


def _apply_input_budget(case: TestCase, max_input_chars: int, warnings: list[str]) -> None:
    if case.input and len(case.input) > max_input_chars:
        original_length = len(case.input)
        case.input = case.input[:max_input_chars].rstrip() + "\n[MASentinel truncated overlong generated input]"
        case.metadata["original_input_length"] = original_length
        case.metadata["input_truncated_by_masentinel"] = True
        warnings.append(f"input truncated from {original_length} to {len(case.input)} chars")
    for item in case.input_sequence:
        content = str(item.get("content", ""))
        if len(content) <= max_input_chars:
            continue
        original_length = len(content)
        item["content"] = content[:max_input_chars].rstrip() + "\n[MASentinel truncated overlong generated input]"
        case.metadata["input_sequence_truncated_by_masentinel"] = True
        warnings.append(f"input_sequence item truncated from {original_length} to {len(item['content'])} chars")
