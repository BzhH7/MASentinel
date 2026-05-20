from masentinel.diagnosis.fault_classifier import apply_deterministic_confirmation_gate, classify_faults, classify_non_target_issues
from masentinel.schema import RunTrace, SystemProfile, TestCase, TestOracleSpec, TraceEvent


def profile() -> SystemProfile:
    return SystemProfile(
        system_id="toy",
        root_path=".",
        doc_path=None,
        entrypoint=None,
        agents=[],
        tools=[],
        requirements=[],
        message_edges=[],
    )


def case() -> TestCase:
    return TestCase(case_id="C1", system_id="toy", case_type="x", objective="", input="", oracle=TestOracleSpec())


def trace(stderr: str) -> RunTrace:
    return RunTrace(
        case_id="C1",
        system_id="toy",
        started_at="now",
        ended_at="later",
        status="failed",
        terminated=False,
        timeout=False,
        turn_count=0,
        events=[],
        final_output="",
        stdout="",
        stderr=stderr,
        returncode=1,
    )


def test_model_provider_failures_are_not_target_faults() -> None:
    stderr = "Traceback (most recent call last)\nHTTP 403 Forbidden: Unauthorized consumer."
    target_faults = classify_faults(profile(), [case()], [trace(stderr)])
    non_target = classify_non_target_issues(profile(), [case()], [trace(stderr)])
    assert target_faults == []
    assert {issue["layer"] for issue in non_target} == {"model_provider"}


def test_openai_timeout_failures_are_non_target_provider_issues() -> None:
    stderr = "Traceback (most recent call last)\nopenai.APITimeoutError: Request timed out\nTimeoutError: OpenAI API call timed out"
    target_faults = classify_faults(profile(), [case()], [trace(stderr)])
    non_target = classify_non_target_issues(profile(), [case()], [trace(stderr)])
    assert target_faults == []
    assert {issue["code"] for issue in non_target} == {"MODEL_PROVIDER_FAILURE"}


def test_weak_missing_agent_is_inconclusive_not_target_fault() -> None:
    test_case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="coverage_guided",
        objective="",
        input="",
        oracle=TestOracleSpec(must_visit_agents=["planner"]),
    )
    run_trace = RunTrace(
        case_id="C1",
        system_id="toy",
        started_at="now",
        ended_at="later",
        status="passed",
        terminated=True,
        timeout=False,
        turn_count=1,
        events=[TraceEvent(type="message", timestamp=1.0, sender="executor", receiver="manager", content="done")],
        final_output="ok",
        stdout="ok",
        stderr="",
        returncode=0,
    )

    assert classify_faults(profile(), [test_case], [run_trace]) == []
    issues = classify_non_target_issues(profile(), [test_case], [run_trace])
    assert issues[0]["layer"] == "inconclusive"


def test_data_gap_missing_agent_is_reclassified_as_business_task_failure() -> None:
    test_case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="output_contract",
        objective="",
        input="",
        oracle=TestOracleSpec(must_visit_agents=["data_collector"]),
    )
    run_trace = RunTrace(
        case_id="C1",
        system_id="toy",
        started_at="now",
        ended_at="later",
        status="failed",
        terminated=True,
        timeout=False,
        turn_count=2,
        events=[TraceEvent(type="message", timestamp=1.0, sender="analyst", receiver="manager", content="missing data")],
        final_output="missing data",
        stdout="missing data",
        stderr="",
        returncode=0,
    )

    faults = classify_faults(profile(), [test_case], [run_trace])
    assert any(fault["fault_type"] == "Data Collection Tool Registration Missing" for fault in faults)
    assert all("evidence_strength" in fault for fault in faults)


def test_message_handoff_takes_priority_over_missing_data() -> None:
    test_case = TestCase(case_id="C1", system_id="toy", case_type="message_handoff_integrity", objective="", input="", oracle=TestOracleSpec())
    run_trace = RunTrace(
        case_id="C1",
        system_id="toy",
        started_at="now",
        ended_at="later",
        status="passed",
        terminated=True,
        timeout=False,
        turn_count=2,
        events=[TraceEvent(type="message_handoff", timestamp=1.0, sender="data_agent", content="TERMINATE", metadata={"is_terminate_only": True})],
        final_output="missing data",
        stdout="Data analysis results: TERMINATE\nmissing data",
        stderr="",
        returncode=0,
    )

    faults = classify_faults(profile(), [test_case], [run_trace])

    assert any(fault["failure_code"] == "MESSAGE_HANDOFF_TERMINATE_ONLY" for fault in faults)
    assert all(fault.get("not_model_fault_because") for fault in faults)
    assert all(fault.get("root_cause_confidence") for fault in faults)


def test_bare_timeout_is_inconclusive_not_target_fault() -> None:
    test_case = case()
    run_trace = RunTrace(
        case_id="C1",
        system_id="toy",
        started_at="now",
        ended_at="later",
        status="timeout",
        terminated=False,
        timeout=True,
        turn_count=4,
        events=[],
        final_output="",
        stdout="working...",
        stderr="",
        returncode=None,
    )

    assert classify_faults(profile(), [test_case], [run_trace]) == []
    issues = classify_non_target_issues(profile(), [test_case], [run_trace])
    assert issues[0]["layer"] == "inconclusive"


def test_deterministic_gate_confirms_only_strong_code_or_trace_evidence() -> None:
    fault = {
        "failure_code": "DOCUMENTED_ENTRYPOINT_BROKEN",
        "layer": "application",
        "confidence": 0.9,
        "evidence_strength": 0.58,
        "root_cause_confidence": "code_evidence",
        "suspected_false_positive": True,
    }

    gated = apply_deterministic_confirmation_gate(fault)

    assert gated["confirmation_status"] == "confirmed_fault"
    assert gated["confirmation_source"] == "deterministic_oracle_evidence"
    assert gated["suspected_false_positive"] is False


def test_agent_audit_cannot_confirm_weak_oracle_evidence() -> None:
    fault = {
        "failure_code": "MISSING_AGENT",
        "layer": "autogen_framework",
        "confidence": 0.72,
        "evidence_strength": 0.28,
        "root_cause_confidence": "oracle_assumption",
        "false_positive_audit": {"audit_result": "confirmed_fault", "confidence": 0.99},
        "suspected_false_positive": False,
    }

    gated = apply_deterministic_confirmation_gate(fault)

    assert gated["confirmation_status"] == "suspected_fault"
    assert gated["suspected_false_positive"] is True
    assert gated["deterministic_confirmation"]["confirmed"] is False


def test_diagnostic_only_case_failure_is_not_confirmed_primary_fault() -> None:
    test_case = TestCase(
        case_id="C1",
        system_id="toy",
        case_type="cli_doc_conformance",
        objective="",
        input="",
        oracle=TestOracleSpec(),
        metadata={"oracle_strength": "diagnostic", "diagnostic_only": True},
    )
    run_trace = RunTrace(
        case_id="C1",
        system_id="toy",
        started_at="now",
        ended_at="later",
        status="failed",
        terminated=False,
        timeout=False,
        turn_count=0,
        events=[],
        final_output="",
        stdout="",
        stderr="Traceback (most recent call last)\nValueError: broken deterministic path",
        returncode=1,
    )

    faults = classify_faults(profile(), [test_case], [run_trace])

    assert faults
    assert faults[0]["diagnostic_only"] is True
    assert faults[0]["confirmation_status"] == "suspected_fault"
    assert faults[0]["suspected_false_positive"] is True
