from __future__ import annotations

from masentinel.oracle.contract_oracle import evaluate_contracts
from masentinel.schema import AgentInfo, RunTrace, SystemProfile, TestCase, TestOracleSpec, TraceEvent


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
        metadata={},
    )
    defaults.update(kwargs)
    return RunTrace(**defaults)


def case(case_type: str, metadata: dict | None = None) -> TestCase:
    return TestCase(case_id="C1", system_id="toy", case_type=case_type, objective="", input="", oracle=TestOracleSpec(), metadata=metadata or {})


def test_filesystem_escape_contract() -> None:
    failures = evaluate_contracts(
        case("filesystem_safety", {"assertions": ["no_write_outside_root"]}),
        trace(metadata={"filesystem_effects": {"outside_root_writes": ["/tmp/escaped/MasterPlan.txt"]}}),
    )
    assert {failure.code for failure in failures} == {"FILESYSTEM_ESCAPE"}


def test_tool_api_contract_detects_view_and_pagination() -> None:
    metadata = {
        "mock_http": True,
        "http_fixture": {"fixture_id": "airtable_101_records", "expected_query_params": {"view": "viw1"}, "pagination_pages": 2},
    }
    event = TraceEvent(type="http_request", timestamp=1.0, metadata={"fixture_id": "airtable_101_records", "query_params": {}, "page_index": 0, "status_code": 200})
    failures = evaluate_contracts(case("tool_api_contract", metadata), trace(events=[event]))
    assert {"VIEW_PARAMETER_IGNORED", "PAGINATION_NOT_FOLLOWED"} <= {failure.code for failure in failures}


def test_tool_error_contract_detects_unstructured_error() -> None:
    metadata = {"mock_http": True, "http_fixture": {"status_code": 401}}
    event = TraceEvent(type="http_request", timestamp=1.0, metadata={"status_code": 401, "query_params": {}})
    failures = evaluate_contracts(case("tool_error_contract", metadata), trace(events=[event]))
    assert "TOOL_UNSTRUCTURED_ERROR" in {failure.code for failure in failures}


def test_message_handoff_contract_detects_terminate_only() -> None:
    event = TraceEvent(
        type="message_handoff",
        timestamp=1.0,
        sender="data_agent",
        content="TERMINATE",
        metadata={"is_terminate_only": True, "caller": "conduct_analysis"},
    )
    failures = evaluate_contracts(case("message_handoff_integrity"), trace(events=[event]))
    assert "MESSAGE_HANDOFF_TERMINATE_ONLY" in {failure.code for failure in failures}


def test_data_invariant_contract_detects_negative_risk_magnitude() -> None:
    failures = evaluate_contracts(
        case("data_invariant", {"generic_pattern": "numeric_sign_convention"}),
        trace(metadata={"output_metrics": {"var_95": -0.05}}),
    )
    assert "NUMERIC_SIGN_CONVENTION_ERROR" in {failure.code for failure in failures}


def test_cli_doc_contract_detects_missing_command() -> None:
    failures = evaluate_contracts(
        case("cli_doc_conformance", {"command_override": "python -m src.main interactive"}),
        trace(status="failed", terminated=False, returncode=2, stderr="invalid choice: 'interactive'", metadata={"command": ["python", "-m", "src.main", "interactive"]}),
    )
    assert "DOCUMENTED_CLI_COMMAND_MISSING" in {failure.code for failure in failures}


def test_autogen_wiring_contract_detects_empty_orchestrator_without_messages() -> None:
    profile = SystemProfile(
        system_id="toy",
        root_path=".",
        doc_path=None,
        entrypoint=None,
        agents=[AgentInfo(name="a")],
        tools=[],
        requirements=[],
        message_edges=[],
        raw_notes={"autogen_wiring_risks": [{"risk": "AgentOrchestrator initialized with empty mapping"}]},
    )
    failures = evaluate_contracts(case("autogen_wiring"), trace(events=[]), profile)
    assert "AUTOGEN_WIRING_MISSING" in {failure.code for failure in failures}
