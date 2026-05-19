from masentinel.diagnosis.fault_classifier import classify_faults, classify_non_target_issues
from masentinel.schema import RunTrace, SystemProfile, TestCase, TestOracleSpec


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

