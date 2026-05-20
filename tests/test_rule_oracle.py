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


def test_oracle_detects_speaker_selection_loop_from_stdout() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="speaker_selection_robustness", objective="", input="", oracle=TestOracleSpec())
    stdout = "speaker_selection_agent\nchecking_agent\nYou didn't choose a speaker\nspeaker_selection_agent\nchecking_agent\nYou didn't choose a speaker"
    result = RuleOracle().evaluate(case, trace(stdout=stdout, terminated=False, timeout=True, turn_count=8))
    assert "SPEAKER_SELECTION_LOOP" in {failure.code for failure in result.failures}


def test_oracle_detects_termination_signal_ignored() -> None:
    case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="termination_signal",
        objective="",
        input="",
        oracle=TestOracleSpec(),
        metadata={"termination_marker": "TERMINATE", "termination_grace_messages": 1},
    )
    stdout = "assistant: done TERMINATE\nassistant: Is there anything else you would like me to do?"
    result = RuleOracle().evaluate(case, trace(stdout=stdout, terminated=False, timeout=False, turn_count=5))
    assert "TERMINATION_SIGNAL_IGNORED" in {failure.code for failure in result.failures}


def test_oracle_checks_expected_keywords_for_output_contract() -> None:
    case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="output_contract",
        objective="",
        input="",
        oracle=TestOracleSpec(expected_keywords=["risk", "summary"]),
    )
    result = RuleOracle().evaluate(case, trace(stdout="summary only", final_output="summary only"))
    assert "OUTPUT_SCHEMA_VIOLATION" in {failure.code for failure in result.failures}


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
    codes = {failure.code for failure in result.failures}
    assert "MODEL_PROVIDER_FAILURE" in codes
    assert "RUNTIME_EXCEPTION" not in codes


def test_oracle_suppresses_contract_failures_on_startup_dependency_error() -> None:
    case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="tool_api_contract",
        objective="",
        input="",
        metadata={"mock_http": True, "http_fixture": {"expected_query_params": {"view": "viw1"}, "pagination_pages": 2}},
    )
    stderr = "ModuleNotFoundError: No module named 'autogen'"
    result = RuleOracle().evaluate(case, trace(status="failed", terminated=False, stderr=stderr, returncode=1, turn_count=0))
    codes = {failure.code for failure in result.failures}
    assert "RUNTIME_EXCEPTION" in codes
    assert "VIEW_PARAMETER_IGNORED" not in codes
    assert "PAGINATION_NOT_FOLLOWED" not in codes


def test_oracle_treats_openai_timeout_as_provider_failure_and_suppresses_derived_expectations() -> None:
    case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="x",
        objective="",
        input="",
        oracle=TestOracleSpec(must_visit_agents=["planner"], must_call_tools=["search_tool"], must_cover_edges=[("manager", "planner")]),
    )
    stderr = "openai.APITimeoutError: Request timed out\nTimeoutError: OpenAI API call timed out"
    result = RuleOracle(registered_tools={"search_tool"}).evaluate(trace=trace(status="failed", stderr=stderr, returncode=1), testcase=case)
    codes = {failure.code for failure in result.failures}
    assert "MODEL_PROVIDER_FAILURE" in codes
    assert "RUNTIME_EXCEPTION" not in codes
    assert "MISSING_AGENT" not in codes
    assert "MISSING_TOOL_CALL" not in codes
    assert "MISSING_MESSAGE_EDGE" not in codes


def test_oracle_turn_budget_is_soft_when_run_terminated() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="", oracle=TestOracleSpec(max_turns=2))
    result = RuleOracle().evaluate(case, trace(terminated=True, turn_count=8, status="passed", returncode=0))
    codes = {failure.code for failure in result.failures}
    assert "TURN_BUDGET_EXCEEDED" in codes
    assert "NON_TERMINATION" not in codes
    assert result.passed


def test_oracle_ignores_internal_runtime_method_for_tool_hallucination() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="")
    event = TraceEvent(
        type="tool_call",
        timestamp=1.0,
        tool="internal_helper",
        metadata={"source": "runtime_method", "llm_visible": False},
    )
    result = RuleOracle(registered_tools={"search_tool"}).evaluate(case, trace(events=[event]))
    assert "TOOL_HALLUCINATION" not in {failure.code for failure in result.failures}


def test_oracle_still_flags_llm_visible_unregistered_tool() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="")
    event = TraceEvent(
        type="tool_call",
        timestamp=1.0,
        tool="made_up_tool",
        metadata={"source": "autogen_function_call", "llm_visible": True},
    )
    result = RuleOracle(registered_tools={"search_tool"}).evaluate(case, trace(events=[event]))
    assert "TOOL_HALLUCINATION" in {failure.code for failure in result.failures}


def test_oracle_detects_human_input_request() -> None:
    case = TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="")
    event = TraceEvent(type="human_input_requested", timestamp=1.0)
    result = RuleOracle().evaluate(case, trace(status="failed", terminated=False, events=[event], metadata={"human_input_requested": True}))
    assert "HUMAN_INPUT_REQUESTED" in {failure.code for failure in result.failures}
