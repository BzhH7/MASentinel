from masentinel.generator.testcase_generator import generate_testcases
from masentinel.schema import AgentInfo, MessageEdge, RequirementInfo, SystemProfile, ToolInfo
from masentinel.testcase_generation.validator import validate_testcases


def make_profile() -> SystemProfile:
    return SystemProfile(
        system_id="toy",
        root_path=".",
        doc_path=None,
        entrypoint=None,
        agents=[AgentInfo(name="planner", class_name="AssistantAgent"), AgentInfo(name="executor", class_name="AssistantAgent")],
        tools=[ToolInfo(name="search_tool")],
        requirements=[RequirementInfo(id="R1", description="planner should use executor and search_tool", expected_agents=["planner", "executor"], expected_tools=["search_tool"])],
        message_edges=[MessageEdge("planner", "executor")],
    )


def test_generator_covers_required_case_types_and_oracles() -> None:
    cases = generate_testcases(make_profile(), num_cases=30)
    assert {
        "positive_smoke",
        "automation_no_human",
        "termination_signal",
        "tool_contract_positive",
        "output_contract",
        "requirement_positive",
        "coverage_guided",
        "property_boundary",
        "fuzz_negative",
        "fuzz_tool_failure",
        "metamorphic",
        "regression",
    } <= {case.case_type for case in cases}
    assert all(case.oracle is not None for case in cases)
    assert any(case.fault_injection for case in cases)
    metamorphic = next(case for case in cases if case.case_type == "metamorphic")
    assert metamorphic.metadata["expected_relation"]["allow_different_agent_path"] is True


def test_validator_truncates_overlong_generated_inputs() -> None:
    profile = make_profile()
    cases = generate_testcases(profile, num_cases=60)
    long_case = next(case for case in cases if case.metadata.get("fuzz_template") == "very_long_input")
    long_case.input = "x" * 200
    valid, report = validate_testcases([long_case], profile, max_input_chars=50)
    assert valid
    assert len(valid[0].input) < 120
    assert valid[0].metadata["input_truncated_by_masentinel"] is True
    assert report[0]["warnings"]


def test_generator_treats_potential_edges_as_soft_oracle() -> None:
    profile = make_profile()
    profile.message_edges.append(MessageEdge("planner", "executor", "potential GroupChat routing"))
    cases = generate_testcases(profile, num_cases=30)
    potential_cases = [case for case in cases if case.metadata.get("potential_edge")]

    assert potential_cases
    assert potential_cases[0].metadata["oracle_strength"] == "soft"
    assert potential_cases[0].oracle.must_cover_edges == []
