from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentInfo:
    name: str
    var_name: str | None = None
    class_name: str | None = None
    system_message: str | None = None
    description: str | None = None
    tools: list[str] = field(default_factory=list)


@dataclass
class ToolInfo:
    name: str
    function_name: str | None = None
    signature: str | None = None
    docstring: str | None = None
    parameters: list[dict[str, Any]] = field(default_factory=list)
    source_file: str | None = None


@dataclass
class RequirementInfo:
    id: str
    description: str
    expected_agents: list[str] = field(default_factory=list)
    expected_tools: list[str] = field(default_factory=list)
    expected_behavior: list[str] = field(default_factory=list)
    negative_cases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MessageEdge:
    source: str
    target: str
    evidence: str | None = None


@dataclass
class SystemProfile:
    system_id: str
    root_path: str
    doc_path: str | None
    entrypoint: str | None
    agents: list[AgentInfo]
    tools: list[ToolInfo]
    requirements: list[RequirementInfo]
    message_edges: list[MessageEdge]
    termination_conditions: list[str] = field(default_factory=list)
    raw_notes: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestOracleSpec:
    must_terminate: bool = True
    max_turns: int = 15
    must_not_crash: bool = True
    must_visit_agents: list[str] = field(default_factory=list)
    must_call_tools: list[str] = field(default_factory=list)
    must_cover_edges: list[tuple[str, str]] = field(default_factory=list)
    must_not_call_tools: list[str] = field(default_factory=list)
    must_not_fabricate_tool_result: bool = False
    output_contract: str | None = None
    expected_keywords: list[str] = field(default_factory=list)


@dataclass
class FaultInjectionSpec:
    tool: str | None = None
    behavior: str | None = None
    exception_message: str | None = None


@dataclass
class TestCase:
    case_id: str
    system_id: str
    case_type: str
    objective: str
    input: str
    input_sequence: list[dict[str, str]] = field(default_factory=list)
    target_requirements: list[str] = field(default_factory=list)
    target_agents: list[str] = field(default_factory=list)
    target_tools: list[str] = field(default_factory=list)
    target_edges: list[tuple[str, str]] = field(default_factory=list)
    oracle: TestOracleSpec = field(default_factory=TestOracleSpec)
    fault_injection: FaultInjectionSpec | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceEvent:
    type: str
    timestamp: float
    turn: int | None = None
    sender: str | None = None
    receiver: str | None = None
    content: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    result_preview: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunTrace:
    case_id: str
    system_id: str
    started_at: str
    ended_at: str | None
    status: str
    terminated: bool
    timeout: bool
    turn_count: int
    events: list[TraceEvent]
    final_output: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    returncode: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OracleFailure:
    code: str
    message: str
    severity: str = "medium"
    evidence: list[str] = field(default_factory=list)


@dataclass
class OracleResult:
    case_id: str
    passed: bool
    failures: list[OracleFailure] = field(default_factory=list)


def _tuple_edges(items: list[Any]) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for item in items or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            edges.append((str(item[0]), str(item[1])))
    return edges


def profile_from_dict(data: dict[str, Any]) -> SystemProfile:
    return SystemProfile(
        system_id=data["system_id"],
        root_path=data.get("root_path", ""),
        doc_path=data.get("doc_path"),
        entrypoint=data.get("entrypoint"),
        agents=[AgentInfo(**x) for x in data.get("agents", [])],
        tools=[ToolInfo(**x) for x in data.get("tools", [])],
        requirements=[RequirementInfo(**x) for x in data.get("requirements", [])],
        message_edges=[MessageEdge(**x) for x in data.get("message_edges", [])],
        termination_conditions=list(data.get("termination_conditions", [])),
        raw_notes=dict(data.get("raw_notes", {})),
    )


def testcase_from_dict(data: dict[str, Any]) -> TestCase:
    oracle_data = dict(data.get("oracle") or {})
    oracle_data["must_cover_edges"] = _tuple_edges(oracle_data.get("must_cover_edges", []))
    injection = data.get("fault_injection")
    return TestCase(
        case_id=data["case_id"],
        system_id=data["system_id"],
        case_type=data.get("case_type", "unknown"),
        objective=data.get("objective", ""),
        input=data.get("input", ""),
        input_sequence=[dict(x) for x in data.get("input_sequence", []) if isinstance(x, dict)],
        target_requirements=list(data.get("target_requirements", [])),
        target_agents=list(data.get("target_agents", [])),
        target_tools=list(data.get("target_tools", [])),
        target_edges=_tuple_edges(data.get("target_edges", [])),
        oracle=TestOracleSpec(**oracle_data),
        fault_injection=FaultInjectionSpec(**injection) if injection else None,
        metadata=dict(data.get("metadata", {})),
    )


def trace_from_dict(data: dict[str, Any]) -> RunTrace:
    return RunTrace(
        case_id=data["case_id"],
        system_id=data["system_id"],
        started_at=data.get("started_at", ""),
        ended_at=data.get("ended_at"),
        status=data.get("status", "unknown"),
        terminated=bool(data.get("terminated", False)),
        timeout=bool(data.get("timeout", False)),
        turn_count=int(data.get("turn_count", 0)),
        events=[TraceEvent(**x) for x in data.get("events", [])],
        final_output=data.get("final_output"),
        stdout=data.get("stdout"),
        stderr=data.get("stderr"),
        returncode=data.get("returncode"),
        metadata=dict(data.get("metadata", {})),
    )


# Prevent pytest from trying to collect schema dataclasses whose names begin with Test.
TestOracleSpec.__test__ = False
TestCase.__test__ = False
