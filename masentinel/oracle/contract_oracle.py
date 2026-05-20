from __future__ import annotations

import re
from typing import Any

from masentinel.schema import OracleFailure, RunTrace, SystemProfile, TestCase


def evaluate_contracts(testcase: TestCase, trace: RunTrace, profile: SystemProfile | None = None) -> list[OracleFailure]:
    failures: list[OracleFailure] = []
    failures.extend(evaluate_artifact_contract(testcase, trace, profile))
    failures.extend(evaluate_filesystem_contract(testcase, trace))
    failures.extend(evaluate_resume_contract(testcase, trace))
    failures.extend(evaluate_tool_contract(testcase, trace))
    failures.extend(evaluate_message_handoff_contract(testcase, trace))
    failures.extend(evaluate_data_invariant_contract(testcase, trace))
    failures.extend(evaluate_cli_doc_contract(testcase, trace))
    failures.extend(evaluate_autogen_wiring_contract(testcase, trace, profile))
    failures.extend(evaluate_scalable_budget_contract(testcase, trace))
    return failures


def evaluate_artifact_contract(testcase: TestCase, trace: RunTrace, profile: SystemProfile | None = None) -> list[OracleFailure]:
    if testcase.case_type != "artifact_contract":
        return []
    failures: list[OracleFailure] = []
    metadata = testcase.metadata or {}
    checks = trace.metadata.get("artifact_checks") or metadata.get("artifact_checks") or []
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict) or check.get("passed", True):
            continue
        assertion = str(check.get("assertion") or "")
        evidence = [str(check.get("path") or ""), str(check.get("message") or "")]
        if assertion in {"python_compile_succeeds", "no_markdown_fence_markers", "artifact_content_preserves_first_code_token"}:
            failures.append(OracleFailure("MARKDOWN_ARTIFACT_CORRUPTION", "Persisted code artifact is corrupted or not executable.", "high", evidence))
        elif assertion in {"artifact_extension_matches_docs", "documented_artifact_exists"}:
            failures.append(OracleFailure("ARTIFACT_SCHEMA_MISMATCH", "Generated artifact name/extension does not match documented schema.", "medium", evidence))
    text = _combined_text(trace)
    if "syntaxerror" in text.lower() and any(item in metadata.get("assertions", []) for item in ("python_compile_succeeds", "artifact_content_preserves_first_code_token")):
        failures.append(OracleFailure("MARKDOWN_ARTIFACT_CORRUPTION", "Generated Python artifact appears syntactically invalid.", "high", _evidence(text)))
    if re.search(r"comments_v\d+\.log", text) and "comments_v" in text and "comments_vn.txt" in text:
        failures.append(OracleFailure("ARTIFACT_SCHEMA_MISMATCH", "Review artifact extension differs from documented comments_vN.txt contract.", "medium", _evidence(text)))
    return failures


def evaluate_filesystem_contract(testcase: TestCase, trace: RunTrace) -> list[OracleFailure]:
    metadata = testcase.metadata or {}
    if testcase.case_type != "filesystem_safety" and "no_write_outside_root" not in metadata.get("assertions", []):
        return []
    effects = trace.metadata.get("filesystem_effects") or {}
    outside = effects.get("outside_root_writes") or []
    if outside:
        return [
            OracleFailure(
                "FILESYSTEM_ESCAPE",
                "User-controlled path/name caused writes outside the configured project root.",
                "high",
                [str(item) for item in outside[:8]],
            )
        ]
    text = _combined_text(trace).lower()
    if "../" in (testcase.input or "") and any(marker in text for marker in ("masterplan.txt", "script_v", "created", "writing")):
        return [OracleFailure("FILESYSTEM_ESCAPE", "Path traversal input was accepted during filesystem-writing workflow.", "high", _evidence(text))]
    return []


def evaluate_resume_contract(testcase: TestCase, trace: RunTrace) -> list[OracleFailure]:
    if testcase.case_type != "state_resume_contract":
        return []
    text = _combined_text(trace).lower()
    fixture = trace.metadata.get("case_fixture") or {}
    created = " ".join(fixture.get("created_files") or []).lower()
    if "script_v1.py" in created and any(marker in text for marker in ("iterationnumber = 1", "iteration 1", "first iteration", "new project")):
        return [OracleFailure("RESUME_STATE_INCOMPLETE", "Existing script state was ignored and the project was treated as a first iteration.", "medium", _evidence(text))]
    if "script_v1.py" in created and "script_v1.py" not in text and trace.terminated:
        return [OracleFailure("RESUME_STATE_INCOMPLETE", "Partial resume fixture existed, but trace/output did not show the latest script being resumed or explicitly repaired.", "medium", [created])]
    return []


def evaluate_tool_contract(testcase: TestCase, trace: RunTrace) -> list[OracleFailure]:
    if testcase.case_type not in {"tool_api_contract", "tool_error_contract"} and not (testcase.metadata or {}).get("mock_http"):
        return []
    failures: list[OracleFailure] = []
    metadata = testcase.metadata or {}
    fixture = metadata.get("http_fixture") if isinstance(metadata.get("http_fixture"), dict) else {}
    http_events = [event for event in trace.events if event.type == "http_request"]
    tool_results = [event for event in trace.events if event.type in {"tool_result", "tool_error"}]
    expected_params = fixture.get("expected_query_params") if isinstance(fixture.get("expected_query_params"), dict) else {}
    needs_http_observation = bool(expected_params or int(fixture.get("pagination_pages") or 0) > 1 or int(fixture.get("status_code") or 0) >= 400)
    if needs_http_observation and not http_events:
        return [
            OracleFailure(
                "CONTRACT_TEST_NOT_EXERCISED",
                "HTTP/API contract was configured, but no target HTTP request was observed; expected fixture values are not target evidence.",
                "low",
                [f"fixture_id={fixture.get('fixture_id', '')}", f"case_type={testcase.case_type}"],
            )
        ]
    if expected_params:
        observed_params: dict[str, str] = {}
        for event in http_events:
            params = event.metadata.get("query_params") if isinstance(event.metadata, dict) else {}
            if isinstance(params, dict):
                observed_params.update({str(key): str(value) for key, value in params.items()})
        missing = {key: value for key, value in expected_params.items() if observed_params.get(str(key)) != str(value)}
        if missing:
            failures.append(
                OracleFailure(
                    "VIEW_PARAMETER_IGNORED",
                    "External API request did not preserve documented semantic query parameters.",
                    "high",
                    [f"missing_or_mismatched_query_params={missing}", f"observed_query_params={observed_params}"],
                )
            )
    expected_pages = int(fixture.get("pagination_pages") or 0)
    if expected_pages > 1:
        observed_pages = {
            str(event.metadata.get("page_index"))
            for event in http_events
            if isinstance(event.metadata, dict) and event.metadata.get("fixture_id") == fixture.get("fixture_id")
        }
        if len(observed_pages) < expected_pages:
            failures.append(
                OracleFailure(
                    "PAGINATION_NOT_FOLLOWED",
                    "External API pagination stopped before all fixture pages were requested.",
                    "high",
                    [f"expected_pages={expected_pages}", f"observed_pages={sorted(observed_pages)}"],
                )
            )
    status_code = int(fixture.get("status_code") or 0)
    if status_code >= 400:
        observed_error_statuses = [
            int(event.metadata.get("status_code") or 0)
            for event in http_events
            if isinstance(event.metadata, dict) and int(event.metadata.get("status_code") or 0) >= 400
        ]
        if not observed_error_statuses:
            failures.append(
                OracleFailure(
                    "CONTRACT_TEST_NOT_EXERCISED",
                    "Tool-error fixture expected an HTTP failure, but no failing HTTP response was observed.",
                    "low",
                    [f"expected_status={status_code}"],
                )
            )
            return failures
        structured = any(event.metadata.get("structured") is True or event.type == "tool_error" for event in tool_results)
        http_recorded = bool(observed_error_statuses)
        if not http_recorded:
            failures.append(OracleFailure("HTTP_STATUS_NOT_CHECKED", "HTTP failure status was not captured in the trace envelope.", "medium", [f"expected_status={status_code}"]))
        if not structured:
            failures.append(
                OracleFailure(
                    "TOOL_UNSTRUCTURED_ERROR",
                    "External tool failure did not produce a structured error envelope.",
                    "high",
                    [f"observed_statuses={observed_error_statuses}"],
                )
            )
    for event in tool_results:
        if event.type == "tool_result" and event.result_preview in (None, "", "None") and testcase.case_type == "tool_error_contract":
            failures.append(OracleFailure("TOOL_RETURNED_NONE", "Tool returned None/empty result for an error path instead of a structured envelope.", "high", [str(event.tool or "")]))
    text = _combined_text(trace).lower()
    if testcase.case_type == "tool_error_contract" and any(marker in text for marker in ("401", "403", "unauthorized", "invalid api key")) and not tool_results:
        failures.append(OracleFailure("TOOL_RAW_HTTP_ERROR", "Raw HTTP/API error text appears to have reached the workflow without a tool error envelope.", "high", _evidence(text)))
    return failures


def evaluate_message_handoff_contract(testcase: TestCase, trace: RunTrace) -> list[OracleFailure]:
    if testcase.case_type != "message_handoff_integrity":
        return []
    failures: list[OracleFailure] = []
    for event in trace.events:
        if event.type != "message_handoff":
            continue
        metadata = event.metadata or {}
        evidence = [f"agent={event.sender or ''}", f"caller={metadata.get('caller', '')}", f"content={event.content or ''}"]
        if metadata.get("is_terminate_only") or (event.content or "").strip().upper() == "TERMINATE":
            failures.append(OracleFailure("MESSAGE_HANDOFF_TERMINATE_ONLY", "Downstream handoff returned only a termination marker instead of substantive prior analysis.", "high", evidence))
        elif metadata.get("is_empty") or not (event.content or "").strip():
            failures.append(OracleFailure("MESSAGE_HANDOFF_EMPTY", "Downstream handoff returned empty content.", "high", evidence))
    text = _combined_text(trace)
    if "data analysis results: terminate" in text.lower() or "analysis results: terminate" in text.lower():
        failures.append(OracleFailure("MESSAGE_HANDOFF_TERMINATE_ONLY", "Downstream prompt contains TERMINATE as forwarded prior analysis.", "high", _evidence(text)))
    return failures


def evaluate_data_invariant_contract(testcase: TestCase, trace: RunTrace) -> list[OracleFailure]:
    if testcase.case_type != "data_invariant":
        return []
    failures: list[OracleFailure] = []
    metadata = testcase.metadata or {}
    pattern = metadata.get("generic_pattern")
    text = _combined_text(trace).lower()
    metrics = trace.metadata.get("output_metrics") if isinstance(trace.metadata.get("output_metrics"), dict) else {}
    if pattern == "partial_data_invariant":
        revenue = _metric(metrics, ("revenue", "total_revenue"))
        profit = _metric(metrics, ("profit_margin", "net_margin"))
        if revenue == 0 or profit == 0:
            failures.append(OracleFailure("PARTIAL_METRIC_ZEROED", "Available financial inputs were present but unrelated metrics were zeroed.", "high", [f"metrics={metrics}"]))
        if not metrics and any(marker in text for marker in ("revenue: 0", "total revenue: 0", "profit margin: 0", "profit_margin\": 0")):
            failures.append(OracleFailure("PARTIAL_METRIC_ZEROED", "Output indicates available revenue/profit metrics were zeroed.", "high", _evidence(text)))
    if pattern == "numeric_sign_convention":
        for key in ("var_95", "value_at_risk", "max_drawdown", "maximum_drawdown"):
            value = _metric(metrics, (key,))
            if value is not None and value < 0:
                failures.append(OracleFailure("NUMERIC_SIGN_CONVENTION_ERROR", "Risk metric documented as magnitude is negative.", "medium", [f"{key}={value}"]))
        if not metrics and re.search(r"(var_95|value at risk|max_drawdown|maximum drawdown)[^-\n]{0,20}-\d", text):
            failures.append(OracleFailure("NUMERIC_SIGN_CONVENTION_ERROR", "Risk metric appears as a negative magnitude without signed-return labeling.", "medium", _evidence(text)))
    return failures


def evaluate_cli_doc_contract(testcase: TestCase, trace: RunTrace) -> list[OracleFailure]:
    if testcase.case_type != "cli_doc_conformance":
        return []
    text = _combined_text(trace)
    lowered = text.lower()
    if trace.returncode in (0, None) and not trace.timeout:
        return []
    evidence = [f"command={' '.join(str(x) for x in trace.metadata.get('command', []) or [])}", *_evidence(text)]
    if "invalid choice" in lowered or "unrecognized arguments" in lowered:
        return [OracleFailure("DOCUMENTED_CLI_COMMAND_MISSING", "Documented CLI command is not accepted by the parser/dispatcher.", "high", evidence)]
    if any(marker in lowered for marker in ("importerror", "modulenotfounderror", "attributeerror", "typeerror", "constructor", "no module named")):
        return [OracleFailure("DOCUMENTED_ENTRYPOINT_BROKEN", "Documented entrypoint fails before controlled configuration/runtime handling.", "high", evidence)]
    return [OracleFailure("DOCUMENTED_ENTRYPOINT_BROKEN", "Documented command failed instead of running or emitting a controlled config/dependency diagnostic.", "medium", evidence)]


def evaluate_autogen_wiring_contract(testcase: TestCase, trace: RunTrace, profile: SystemProfile | None = None) -> list[OracleFailure]:
    if testcase.case_type != "autogen_wiring":
        return []
    risks = []
    if profile is not None:
        risks = list(profile.raw_notes.get("autogen_wiring_risks", []) or [])
    risks.extend((testcase.metadata or {}).get("static_risks", []) or [])
    has_message = any(event.type == "message" and event.sender and event.receiver for event in trace.events)
    if risks and not has_message:
        return [
            OracleFailure(
                "AUTOGEN_WIRING_MISSING",
                "Documented AutoGen workflow appears statically miswired and no runtime multi-agent messages were observed.",
                "high",
                [str(item) for item in risks[:8]],
            )
        ]
    if testcase.oracle.must_visit_agents and trace.terminated and not has_message:
        return [
            OracleFailure(
                "AUTOGEN_WIRING_MISSING",
                "Documented multi-agent workflow completed without observable AutoGen collaboration.",
                "medium",
                [f"expected_agents={testcase.oracle.must_visit_agents}"],
            )
        ]
    return []


def evaluate_scalable_budget_contract(testcase: TestCase, trace: RunTrace) -> list[OracleFailure]:
    if testcase.case_type != "scalable_budget":
        return []
    metadata = testcase.metadata or {}
    estimate = int(metadata.get("required_steps_estimate") or 0)
    configured_max = int(trace.metadata.get("max_round") or trace.metadata.get("max_turns") or testcase.oracle.max_turns or 0)
    if configured_max and estimate > configured_max:
        return [
            OracleFailure(
                "SCALABLE_BUDGET_EXCEEDED",
                "Configured turn/round budget is lower than the estimated work required by the record fixture.",
                "medium",
                [f"required_steps_estimate={estimate}", f"configured_budget={configured_max}"],
            )
        ]
    text = _combined_text(trace).lower()
    if trace.timeout and any(marker in text for marker in ("max_round", "maximum rounds", "max turns", "maximum turns")):
        return [OracleFailure("SCALABLE_BUDGET_EXCEEDED", "Run exhausted the framework turn/round budget before completing all records.", "high", _evidence(text))]
    return []


def _combined_text(trace: RunTrace) -> str:
    event_text = "\n".join(str(event.content or event.result_preview or event.error_message or "") for event in trace.events)
    return "\n".join(str(item or "") for item in (trace.stdout, trace.stderr, trace.final_output, event_text))


def _evidence(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()][-8:]


def _metric(metrics: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in metrics:
            continue
        try:
            return float(metrics[key])
        except (TypeError, ValueError):
            return None
    return None
