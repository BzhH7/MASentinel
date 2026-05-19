from masentinel.oracle.rule_oracle import RuleOracle
from masentinel.schema import RunTrace, TestCase, TestOracleSpec, TraceEvent


def trace(**kwargs) -> RunTrace:
    defaults = dict(
        case_id="C1",
        system_id="toy",
        started_at="now",
        ended_at="later",
        status="passed",
        terminated=True,
        timeout=False,
        turn_count=1,
        events=[],
        final_output="ok",
        stdout="ok",
        stderr="",
        returncode=0,
    )
    defaults.update(kwargs)
    return RunTrace(**defaults)


def test_oracle_detects_timeout() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="", oracle=TestOracleSpec(max_turns=1))
    result = RuleOracle().evaluate(case, trace(status="timeout", terminated=False, timeout=True))
    assert "TIMEOUT" in {failure.code for failure in result.failures}


def test_oracle_marks_overlong_generated_input_as_harness_timeout() -> None:
    case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="property_boundary",
        objective="",
        input="x" * 3000,
        oracle=TestOracleSpec(max_turns=1),
        metadata={"fuzz_template": "very_long_input"},
    )
    result = RuleOracle().evaluate(case, trace(status="timeout", terminated=False, timeout=True, turn_count=0))
    codes = {failure.code for failure in result.failures}
    assert "TESTCASE_SETUP_TIMEOUT" in codes
    assert "TIMEOUT" not in codes
    assert "NON_TERMINATION" not in codes


def test_oracle_detects_missing_tool() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="", oracle=TestOracleSpec(must_call_tools=["search_tool"]))
    result = RuleOracle(registered_tools={"search_tool"}).evaluate(case, trace())
    assert "MISSING_TOOL_CALL" in {failure.code for failure in result.failures}


def test_oracle_downgrades_missing_expectations_when_no_workflow_is_observed() -> None:
    case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="x",
        objective="",
        input="",
        oracle=TestOracleSpec(must_visit_agents=["planner"], must_call_tools=["search_tool"], must_cover_edges=[("manager", "planner")]),
    )

    result = RuleOracle(registered_tools={"search_tool"}).evaluate(case, trace(turn_count=0, events=[], stdout="", final_output=""))

    codes = {failure.code for failure in result.failures}
    assert "TARGET_WORKFLOW_NOT_OBSERVED" in codes
    assert "MISSING_AGENT" not in codes
    assert "MISSING_TOOL_CALL" not in codes
    assert "MISSING_MESSAGE_EDGE" not in codes


def test_oracle_reads_autogen_edges_from_stdout() -> None:
    case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="x",
        objective="",
        input="",
        oracle=TestOracleSpec(must_visit_agents=["manager", "planner"], must_cover_edges=[("manager", "planner")]),
    )
    stdout = "\x1b[33mmanager\x1b[0m (to planner):\n\nhello\n\n--------------------------------------------------------------------------------\n"
    result = RuleOracle().evaluate(case, trace(stdout=stdout, final_output="ok"))
    assert result.passed


def test_oracle_detects_type_error_schema_mismatch() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="")
    stderr = "TypeError: search_tool() got an unexpected keyword argument 'term'"
    result = RuleOracle().evaluate(case, trace(status="failed", terminated=False, stderr=stderr, returncode=1))
    assert "TOOL_SCHEMA_MISMATCH" in {failure.code for failure in result.failures}


def test_oracle_separates_model_provider_failure() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="")
    stderr = "HTTP 401 Authorization Required: api key is invalid"
    result = RuleOracle().evaluate(case, trace(status="failed", terminated=False, stderr=stderr, returncode=1))
    assert "MODEL_PROVIDER_FAILURE" in {failure.code for failure in result.failures}


def test_oracle_detects_human_input_request() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="")
    event = TraceEvent(type="human_input_requested", timestamp=1.0)
    result = RuleOracle().evaluate(case, trace(status="failed", terminated=False, events=[event], metadata={"human_input_requested": True}))
    assert "HUMAN_INPUT_REQUESTED" in {failure.code for failure in result.failures}
