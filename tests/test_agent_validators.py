from masentinel.agents.validators import testcases_from_agent_output as parse_agent_testcases
from masentinel.schema import AgentInfo, RequirementInfo, SystemProfile, ToolInfo


def test_agent_testcase_parser_coerces_noisy_oracle_types() -> None:
    profile = SystemProfile(
        system_id="toy",
        root_path=".",
        doc_path=None,
        entrypoint=None,
        agents=[AgentInfo(name="planner")],
        tools=[ToolInfo(name="search")],
        requirements=[RequirementInfo(id="R1", description="demo")],
        message_edges=[],
    )
    output = {
        "testcases": [
            {
                "case_id": "C1",
                "case_type": "requirement_positive",
                "objective": "demo",
                "input": "run demo",
                "target_requirements": "R1",
                "target_agents": "planner",
                "oracle": {
                    "must_terminate": ["true"],
                    "max_turns": [12],
                    "must_not_crash": {"value": "false"},
                    "must_visit_agents": "planner",
                    "must_call_tools": {"items": ["search"]},
                    "must_not_fabricate_tool_result": ["0"],
                },
            }
        ]
    }

    cases = parse_agent_testcases(output, profile)

    assert len(cases) == 1
    assert cases[0].oracle.max_turns == 12
    assert cases[0].oracle.must_terminate is True
    assert cases[0].oracle.must_not_crash is False
    assert cases[0].oracle.must_visit_agents == ["planner"]
    assert cases[0].oracle.must_call_tools == ["search"]
    assert cases[0].oracle.must_not_fabricate_tool_result is False
    assert cases[0].target_requirements == ["R1"]
