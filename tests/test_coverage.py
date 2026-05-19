from masentinel.metrics.coverage import compute_coverage
from masentinel.schema import AgentInfo, MessageEdge, RequirementInfo, RunTrace, SystemProfile, TestCase, ToolInfo, TraceEvent


def test_coverage_calculates_semantic_metrics() -> None:
    profile = SystemProfile(
        system_id="toy",
        root_path=".",
        doc_path=None,
        entrypoint=None,
        agents=[AgentInfo(name="planner"), AgentInfo(name="executor")],
        tools=[ToolInfo(name="search_tool")],
        requirements=[RequirementInfo(id="R1", description="do work")],
        message_edges=[MessageEdge("planner", "executor")],
    )
    cases = [TestCase(case_id="C1", system_id="toy", case_type="requirement_positive", objective="", input="", target_requirements=["R1"])]
    traces = [
        RunTrace(
            case_id="C1",
            system_id="toy",
            started_at="now",
            ended_at="later",
            status="passed",
            terminated=True,
            timeout=False,
            turn_count=2,
            events=[
                TraceEvent(type="message", timestamp=1.0, sender="planner", receiver="executor", content="go"),
                TraceEvent(type="tool_call", timestamp=1.0, tool="search_tool"),
            ],
            final_output="ok",
            stdout="ok",
            stderr="",
        )
    ]
    coverage = compute_coverage(profile, cases, traces, [])
    assert coverage["agent_coverage"] == 1.0
    assert coverage["tool_coverage"] == 1.0
    assert coverage["message_edge_coverage"] == 1.0
    assert coverage["mascov"] > 0.5
