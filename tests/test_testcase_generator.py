from masentinel.generator.testcase_generator import generate_testcases
from masentinel.schema import AgentInfo, MessageEdge, RequirementInfo, SystemProfile, ToolInfo
from masentinel.testcase_generation.validator import validate_testcases


def make_profile() -> SystemProfile:
    return SystemProfile(
        system_id="toy",
        root_path=".",
        doc_path=None,
        entrypoint=None,
        agents=[AgentInfo(name="planner"), AgentInfo(name="executor")],
        tools=[ToolInfo(name="search_tool")],
        requirements=[RequirementInfo(id="R1", description="planner should use executor and search_tool", expected_agents=["planner", "executor"], expected_tools=["search_tool"])],
        message_edges=[MessageEdge("planner", "executor")],
    )


def test_generator_covers_required_case_types_and_oracles() -> None:
    cases = generate_testcases(make_profile(), num_cases=20)
    assert {
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


def test_validator_truncates_overlong_generated_inputs() -> None:
    profile = make_profile()
    cases = generate_testcases(profile, num_cases=20)
    long_case = next(case for case in cases if case.metadata.get("fuzz_template") == "very_long_input")
    long_case.input = "x" * 200
    valid, report = validate_testcases([long_case], profile, max_input_chars=50)
    assert valid
    assert len(valid[0].input) < 120
    assert valid[0].metadata["input_truncated_by_masentinel"] is True
    assert report[0]["warnings"]
