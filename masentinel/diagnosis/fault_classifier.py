from __future__ import annotations

import ast

from masentinel.diagnosis.static_faults import detect_static_faults
from masentinel.oracle.rule_oracle import RuleOracle
from masentinel.schema import RunTrace, SystemProfile, TestCase


FAULT_MAP = {
    "RUNTIME_EXCEPTION": ("application", "Missing Error Handling", "high", 0.85),
    "TIMEOUT": ("autogen_framework", "Non-Termination", "high", 0.82),
    "NON_TERMINATION": ("autogen_framework", "Termination Condition Error", "high", 0.8),
    "MISSING_AGENT": ("autogen_framework", "Wrong Agent Routing", "medium", 0.72),
    "MISSING_TOOL_CALL": ("application", "Missing Tool Call", "medium", 0.7),
    "FORBIDDEN_TOOL_CALL": ("application", "Tool Not Registered", "high", 0.75),
    "MISSING_MESSAGE_EDGE": ("autogen_framework", "Message Routing Error", "medium", 0.68),
    "TOOL_HALLUCINATION": ("autogen_framework", "Function Calling Integration Error", "high", 0.88),
    "TOOL_SCHEMA_MISMATCH": ("application", "Tool Schema Mismatch", "high", 0.92),
    "OUTPUT_EMPTY": ("application", "Output Contract Violation", "medium", 0.62),
    "OUTPUT_SCHEMA_VIOLATION": ("application", "Output Contract Violation", "medium", 0.78),
    "REPETITIVE_LOOP": ("autogen_framework", "Speaker Selection Error", "medium", 0.67),
    "SPEAKER_SELECTION_LOOP": ("autogen_framework", "Speaker Selection Error", "high", 0.86),
    "HUMAN_INPUT_REQUESTED": ("autogen_framework", "Human Input Mode Error", "high", 0.9),
    "TERMINATION_SIGNAL_IGNORED": ("autogen_framework", "Termination Signal Ignored", "high", 0.88),
    "MARKDOWN_ARTIFACT_CORRUPTION": ("application", "Artifact Persistence Corruption", "high", 0.9),
    "ARTIFACT_SCHEMA_MISMATCH": ("application", "Output Artifact Schema Mismatch", "medium", 0.84),
    "FILESYSTEM_ESCAPE": ("application", "Unsafe Project Path", "high", 0.92),
    "RESUME_STATE_INCOMPLETE": ("application", "Resume State Inconsistency", "medium", 0.84),
    "VIEW_PARAMETER_IGNORED": ("application", "Tool API Semantics Error", "high", 0.9),
    "PAGINATION_NOT_FOLLOWED": ("application", "Tool API Pagination Missing", "high", 0.9),
    "TOOL_RAW_HTTP_ERROR": ("application", "Tool Error Contract Missing", "high", 0.88),
    "TOOL_RETURNED_NONE": ("application", "Tool Error Contract Missing", "high", 0.88),
    "TOOL_UNSTRUCTURED_ERROR": ("application", "Tool Error Contract Missing", "high", 0.88),
    "HTTP_STATUS_NOT_CHECKED": ("application", "Tool Error Contract Missing", "medium", 0.8),
    "SCALABLE_BUDGET_EXCEEDED": ("autogen_framework", "Scalable Turn Budget Error", "medium", 0.82),
    "MESSAGE_HANDOFF_TERMINATE_ONLY": ("autogen_framework", "Message Handoff Error", "high", 0.92),
    "MESSAGE_HANDOFF_EMPTY": ("autogen_framework", "Message Handoff Error", "high", 0.9),
    "MESSAGE_HANDOFF_WRONG_SOURCE": ("autogen_framework", "Message Handoff Error", "medium", 0.82),
    "PARTIAL_METRIC_ZEROED": ("application", "Data Processing Invariant Violation", "high", 0.88),
    "NUMERIC_SIGN_CONVENTION_ERROR": ("application", "Data Processing Invariant Violation", "medium", 0.84),
    "DOCUMENTED_ENTRYPOINT_BROKEN": ("application", "Documented Entrypoint Broken", "high", 0.9),
    "DOCUMENTED_CLI_COMMAND_MISSING": ("application", "Documented CLI Command Missing", "high", 0.88),
    "AUTOGEN_WIRING_MISSING": ("autogen_framework", "Agent Orchestration Wiring Missing", "high", 0.9),
    "METAMORPHIC_RELATION_VIOLATION": ("application", "Metamorphic Relation Violation", "medium", 0.74),
    "BUSINESS_TASK_FAILED": ("application", "Business Task Failure", "high", 0.82),
    "TURN_BUDGET_EXCEEDED": ("test_harness", "Soft Turn Budget Exceeded", "low", 0.95),
    "TESTCASE_SETUP_TIMEOUT": ("test_harness", "Generated Test Input Exceeded Runtime Budget", "low", 0.95),
    "TARGET_WORKFLOW_NOT_OBSERVED": ("test_harness", "Target Workflow Not Observed", "low", 0.95),
    "CONTRACT_TEST_NOT_EXERCISED": ("test_harness", "Contract Fixture Not Exercised", "low", 0.95),
    "MODEL_PROVIDER_FAILURE": ("model_provider", "Model/API Provider Failure", "low", 0.95),
}

TARGET_LAYERS = {"application", "autogen_framework"}
NON_TARGET_FAILURE_CODES = {"TESTCASE_SETUP_TIMEOUT", "TARGET_WORKFLOW_NOT_OBSERVED", "CONTRACT_TEST_NOT_EXERCISED", "MODEL_PROVIDER_FAILURE", "TURN_BUDGET_EXCEEDED"}
HIGH_PRECISION_ORACLE_CODES = {
    "MARKDOWN_ARTIFACT_CORRUPTION",
    "ARTIFACT_SCHEMA_MISMATCH",
    "FILESYSTEM_ESCAPE",
    "RESUME_STATE_INCOMPLETE",
    "VIEW_PARAMETER_IGNORED",
    "PAGINATION_NOT_FOLLOWED",
    "TOOL_RAW_HTTP_ERROR",
    "TOOL_RETURNED_NONE",
    "TOOL_UNSTRUCTURED_ERROR",
    "HTTP_STATUS_NOT_CHECKED",
    "MESSAGE_HANDOFF_TERMINATE_ONLY",
    "MESSAGE_HANDOFF_EMPTY",
    "MESSAGE_HANDOFF_WRONG_SOURCE",
    "PARTIAL_METRIC_ZEROED",
    "NUMERIC_SIGN_CONVENTION_ERROR",
    "DOCUMENTED_ENTRYPOINT_BROKEN",
    "DOCUMENTED_CLI_COMMAND_MISSING",
    "AUTOGEN_WIRING_MISSING",
    "SPEAKER_SELECTION_LOOP",
    "HUMAN_INPUT_REQUESTED",
    "TERMINATION_SIGNAL_IGNORED",
}


def classify_faults(profile: SystemProfile, testcases: list[TestCase], traces: list[RunTrace]) -> list[dict]:
    tools = {tool.name for tool in profile.tools}
    oracle = RuleOracle(registered_tools=tools, profile=profile)
    case_by_id = {case.case_id: case for case in testcases}
    faults: list[dict] = []
    counter = 1
    for trace in traces:
        testcase = case_by_id.get(trace.case_id)
        if not testcase:
            continue
        result = oracle.evaluate(testcase, trace)
        for failure in result.failures:
            layer, fault_type, severity, confidence = _classify_failure(profile, failure.code, failure.severity, failure.evidence)
            fault = {
                "fault_id": f"{profile.system_id.upper()}_FAULT_{counter:03d}",
                "case_id": testcase.case_id,
                "layer": layer,
                "fault_type": fault_type,
                "failure_code": failure.code,
                "severity": severity,
                "confidence": confidence,
                "summary": failure.message,
                "evidence": failure.evidence,
                "root_cause": _root_cause(failure.code, profile, failure.evidence),
                "suggested_fix": _suggested_fix(failure.code, failure.evidence),
                "reproduction": {
                    "input": testcase.input,
                    "command": " ".join(trace.metadata.get("command", [])),
                },
                "suspected_false_positive": confidence < 0.65,
            }
            fault = _normalize_fault(fault, trace, profile)
            if fault.get("layer") not in TARGET_LAYERS:
                continue
            fault["evidence_strength"] = _evidence_strength(fault, trace)
            fault["not_model_fault_because"] = _not_model_fault_because(fault)
            fault["code_locations"] = _code_locations(profile, fault)
            fault["root_cause_confidence"] = _root_cause_confidence(fault, trace)
            if _is_diagnostic_case(testcase):
                fault["diagnostic_only"] = True
            fault = apply_deterministic_confirmation_gate(fault)
            faults.append(fault)
            counter += 1
    faults.extend(detect_static_faults(profile, start_index=counter))
    return faults


def apply_deterministic_confirmation_gate(fault: dict) -> dict:
    """Set final confirmation from deterministic oracle/code/trace evidence only.

    Agent diagnosis and audit outputs may be attached later as advisory context, but
    they must not turn weak evidence into a confirmed target fault.
    """

    gated = dict(fault)
    code = str(gated.get("failure_code", ""))
    layer = str(gated.get("layer", ""))
    confidence = _safe_float(gated.get("confidence"), 0.0)
    evidence_strength = _safe_float(gated.get("evidence_strength"), 0.0)
    root_confidence = str(gated.get("root_cause_confidence", "") or "")
    diagnostic_only = bool(gated.get("diagnostic_only"))

    target_layer = layer in TARGET_LAYERS
    non_target_code = code in NON_TARGET_FAILURE_CODES
    has_code_evidence = root_confidence == "code_evidence" and evidence_strength >= 0.55
    has_strong_trace = root_confidence == "trace_only" and evidence_strength >= 0.65
    high_precision_trace = code in HIGH_PRECISION_ORACLE_CODES and root_confidence in {"code_evidence", "trace_only"} and evidence_strength >= 0.55
    deterministic_confirmed = bool(
        target_layer
        and not non_target_code
        and not diagnostic_only
        and confidence >= 0.65
        and (has_code_evidence or has_strong_trace or high_precision_trace)
    )

    reasons: list[str] = []
    if diagnostic_only:
        reasons.append("diagnostic_only_pattern")
    if not target_layer:
        reasons.append(f"non_target_layer={layer or 'unknown'}")
    if non_target_code:
        reasons.append(f"non_target_failure_code={code}")
    if confidence < 0.65:
        reasons.append(f"confidence<{0.65:g}")
    if not (has_code_evidence or has_strong_trace or high_precision_trace):
        reasons.append("insufficient deterministic code/trace evidence")
    if deterministic_confirmed:
        reasons.append("deterministic oracle failure with sufficient code/trace evidence")

    gated["deterministic_confirmation"] = {
        "confirmed": deterministic_confirmed,
        "source": "rule_oracle_and_deterministic_evidence",
        "reason": "; ".join(reasons),
        "confidence_threshold": 0.65,
        "code_evidence_strength_threshold": 0.55,
        "trace_evidence_strength_threshold": 0.65,
        "evidence_strength": evidence_strength,
        "root_cause_confidence": root_confidence,
    }
    gated["confirmation_status"] = "confirmed_fault" if deterministic_confirmed else "suspected_fault"
    gated["confirmation_source"] = "deterministic_oracle_evidence"
    gated["suspected_false_positive"] = not deterministic_confirmed
    return gated


def _is_diagnostic_case(testcase: TestCase | None) -> bool:
    if testcase is None:
        return False
    metadata = testcase.metadata or {}
    return bool(metadata.get("diagnostic_only") or str(metadata.get("oracle_strength", "")).lower() == "diagnostic")


def classify_non_target_issues(profile: SystemProfile, testcases: list[TestCase], traces: list[RunTrace]) -> list[dict]:
    tools = {tool.name for tool in profile.tools}
    oracle = RuleOracle(registered_tools=tools, profile=profile)
    case_by_id = {case.case_id: case for case in testcases}
    issues: list[dict] = []
    for trace in traces:
        testcase = case_by_id.get(trace.case_id)
        if not testcase:
            continue
        result = oracle.evaluate(testcase, trace)
        for failure in result.failures:
            layer, issue_type, severity, confidence = _classify_failure(profile, failure.code, failure.severity, failure.evidence)
            normalized = _normalize_fault(
                {
                    "case_id": testcase.case_id,
                    "layer": layer,
                    "fault_type": issue_type,
                    "failure_code": failure.code,
                    "severity": severity,
                    "confidence": confidence,
                    "summary": failure.message,
                    "evidence": failure.evidence,
                    "root_cause": _root_cause(failure.code, profile, failure.evidence),
                    "suggested_fix": _suggested_fix(failure.code, failure.evidence),
                },
                trace,
                profile,
            )
            if normalized.get("layer") in TARGET_LAYERS:
                continue
            issues.append(
                {
                    "case_id": testcase.case_id,
                    "code": failure.code,
                    "layer": normalized.get("layer", layer),
                    "issue_type": normalized.get("fault_type", issue_type),
                    "severity": severity,
                    "confidence": normalized.get("confidence", confidence),
                    "message": failure.message,
                    "evidence": failure.evidence,
                    "root_cause": normalized.get("root_cause", _root_cause(failure.code, profile, failure.evidence)),
                    "suggested_fix": normalized.get("suggested_fix", _suggested_fix(failure.code, failure.evidence)),
                    "excluded_from_target_faults": True,
                }
            )
    return issues


def _classify_failure(profile: SystemProfile, code: str, severity_hint: str, evidence: list[str]) -> tuple[str, str, str, float]:
    layer, fault_type, severity, confidence = FAULT_MAP.get(code, ("uncertain", code.replace("_", " ").title(), severity_hint, 0.55))
    if code == "RUNTIME_EXCEPTION":
        env_classification = _environment_runtime_exception(evidence)
        if env_classification:
            layer, fault_type, severity, confidence = env_classification
    if code == "SPEAKER_SELECTION_LOOP" and _speaker_name_parsing_evidence(evidence):
        layer, fault_type, severity, confidence = ("application", "Speaker Name Parsing Error", "high", 0.88)
    if code == "MISSING_MESSAGE_EDGE" and _is_potential_groupchat_edge(profile, evidence):
        confidence = 0.6
    return layer, fault_type, severity, confidence


def _normalize_fault(fault: dict, trace: RunTrace, profile: SystemProfile) -> dict:
    normalized = dict(fault)
    text = _combined_text(normalized, trace)
    code = str(normalized.get("failure_code", ""))
    if code in {"MISSING_AGENT", "BUSINESS_TASK_FAILED"} and _data_provider_or_tool_gap(text):
        normalized.update(
            {
                "failure_code": "BUSINESS_TASK_FAILED",
                "layer": "application",
                "fault_type": "Data Collection Tool Registration Missing",
                "summary": "Data collection workflow ran or was requested, but produced missing/empty data or lacked a wired provider.",
                "root_cause": (
                    "The documented data collection capability is not backed by a robust registered tool, mock provider, "
                    "or output contract fallback in the automated run."
                ),
                "suggested_fix": "Register the data provider/tool explicitly or add a deterministic mock data fallback and validate required report sections.",
                "confidence": max(float(normalized.get("confidence", 0) or 0), 0.82),
                "suspected_false_positive": False,
            }
        )
    if code in {"MISSING_AGENT", "MISSING_MESSAGE_EDGE"} and _weak_routing_observation(trace, text):
        normalized.update(
            {
                "layer": "inconclusive",
                "fault_type": "Coverage Gap / Weak Routing Evidence",
                "confidence": min(float(normalized.get("confidence", 0) or 0), 0.45),
                "root_cause": "The process completed without a blocking target failure, but the trace did not prove the expected routing path.",
                "suggested_fix": "Improve AutoGen send/receive instrumentation or add a focused case before treating this as an application/framework fault.",
                "suspected_false_positive": True,
            }
        )
    if code == "SPEAKER_SELECTION_LOOP" and _speaker_name_parsing_evidence(normalized.get("evidence", []) or []):
        normalized.update(
            {
                "layer": "application",
                "fault_type": "Speaker Name Parsing Error",
                "root_cause": "The speaker checking logic appears to require an exact speaker name and does not robustly strip prefixes or whitespace.",
                "suggested_fix": "Normalize speaker-selection output by stripping prefixes/whitespace and validating against aliases before rejecting it.",
                "confidence": max(float(normalized.get("confidence", 0) or 0), 0.88),
                "suspected_false_positive": False,
            }
        )
    if code == "BUSINESS_TASK_FAILED" and _message_handoff_evidence(text):
        normalized.update(
            {
                "failure_code": "MESSAGE_HANDOFF_TERMINATE_ONLY",
                "layer": "autogen_framework",
                "fault_type": "Message Handoff Error",
                "summary": "Downstream task reported missing data after a prior-stage handoff appears to contain only TERMINATE/empty content.",
                "root_cause": "The workflow forwarded termination or empty auto-reply content instead of substantive upstream analysis.",
                "suggested_fix": "Pass the previous assistant analysis explicitly, or filter termination markers before calling downstream agents.",
                "confidence": max(float(normalized.get("confidence", 0) or 0), 0.9),
                "suspected_false_positive": False,
            }
        )
    if code == "TIMEOUT" and _timeout_without_causal_evidence(trace, text):
        normalized.update(
            {
                "layer": "inconclusive",
                "fault_type": "Timeout Symptom / Root Cause Not Isolated",
                "confidence": min(float(normalized.get("confidence", 0) or 0), 0.45),
                "root_cause": "The process exceeded the timeout, but the trace did not show human input, speaker-selection loop, max-round exhaustion, or termination-marker misuse.",
                "suggested_fix": "Increase trace instrumentation and reproduce with a narrower contract case before counting this as a target fault.",
                "suspected_false_positive": True,
            }
        )
    return normalized


def _combined_text(fault: dict, trace: RunTrace) -> str:
    return "\n".join(
        [
            str(fault.get("root_cause", "")),
            str(fault.get("summary", "")),
            "\n".join(str(item) for item in fault.get("evidence", []) or []),
            trace.stdout or "",
            trace.stderr or "",
            trace.final_output or "",
        ]
    ).lower()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _data_provider_or_tool_gap(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "数据缺失",
            "没有数据",
            "无法收集数据",
            "missing data",
            "empty data",
            "failed to collect data",
            "data collection failed",
            "yfinance",
            "tool registration",
            "registered tool",
            "data provider",
        )
    )


def _message_handoff_evidence(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "message_handoff",
            "data analysis results: terminate",
            "analysis results: terminate",
            "handoff returned only",
            "terminate instead of substantive",
        )
    )


def _timeout_without_causal_evidence(trace: RunTrace, text: str) -> bool:
    if not trace.timeout:
        return False
    causal_markers = (
        "human input",
        "waiting for human",
        "manual input",
        "you didn't choose a speaker",
        "speaker_selection_agent",
        "checking_agent",
        "max_round",
        "maximum rounds",
        "terminate",
    )
    return not any(marker in text for marker in causal_markers)


def _weak_routing_observation(trace: RunTrace, text: str) -> bool:
    if trace.timeout or trace.returncode not in (0, None):
        return False
    if "speaker_selection_agent" in text or "you didn't choose a speaker" in text:
        return False
    if _data_provider_or_tool_gap(text):
        return False
    return trace.status == "passed" or trace.terminated


def _speaker_name_parsing_evidence(evidence: list[str]) -> bool:
    text = "\n".join(str(item) for item in evidence).lower()
    return "response " in text and "choose a speaker" in text


def _evidence_strength(fault: dict, trace: RunTrace) -> float:
    text = _combined_text(fault, trace)
    score = 0.0
    if trace.returncode not in (0, None):
        score += 0.15
    if trace.timeout:
        score += 0.15
    if "traceback" in text and fault.get("failure_code") != "MODEL_PROVIDER_FAILURE":
        score += 0.2
    if fault.get("failure_code") == "HUMAN_INPUT_REQUESTED" and any(marker in text for marker in ("press enter", "anything else", "human input", "waiting for human", "input requested")):
        score += 0.25
    if fault.get("failure_code") in {"TIMEOUT", "NON_TERMINATION", "TERMINATION_SIGNAL_IGNORED"} and "terminate" in text:
        score += 0.15
    if fault.get("failure_code") == "SPEAKER_SELECTION_LOOP" and any(marker in text for marker in ("you didn't choose a speaker", "speaker_selection_agent", "checking_agent")):
        score += 0.25
    if fault.get("failure_code") == "BUSINESS_TASK_FAILED" and _data_provider_or_tool_gap(text):
        score += 0.25
    if fault.get("failure_code") in {
        "MESSAGE_HANDOFF_TERMINATE_ONLY",
        "MESSAGE_HANDOFF_EMPTY",
        "FILESYSTEM_ESCAPE",
        "VIEW_PARAMETER_IGNORED",
        "PAGINATION_NOT_FOLLOWED",
        "PARTIAL_METRIC_ZEROED",
        "DOCUMENTED_ENTRYPOINT_BROKEN",
        "AUTOGEN_WIRING_MISSING",
    }:
        score += 0.25
    if fault.get("suggested_fix"):
        score += 0.1
    score += min(float(fault.get("confidence", 0) or 0), 1.0) * 0.25
    return round(min(score, 1.0), 2)


def _is_potential_groupchat_edge(profile: SystemProfile, evidence: list[str]) -> bool:
    parsed_edges: set[tuple[str, str]] = set()
    for item in evidence:
        try:
            value = ast.literal_eval(item)
        except Exception:
            continue
        if isinstance(value, tuple) and len(value) == 2:
            parsed_edges.add((str(value[0]), str(value[1])))
    potential_edges = {
        (edge.source, edge.target)
        for edge in profile.message_edges
        if edge.evidence and "potential" in edge.evidence.lower()
    }
    return bool(parsed_edges & potential_edges)


def _root_cause_confidence(fault: dict, trace: RunTrace) -> str:
    if fault.get("code_locations"):
        return "code_evidence"
    if fault.get("failure_code") in {
        "FILESYSTEM_ESCAPE",
        "MESSAGE_HANDOFF_TERMINATE_ONLY",
        "MESSAGE_HANDOFF_EMPTY",
        "VIEW_PARAMETER_IGNORED",
        "PAGINATION_NOT_FOLLOWED",
        "TOOL_UNSTRUCTURED_ERROR",
        "PARTIAL_METRIC_ZEROED",
        "NUMERIC_SIGN_CONVENTION_ERROR",
    }:
        return "trace_only"
    if trace.events:
        return "trace_only"
    if float(fault.get("confidence", 0) or 0) >= 0.8:
        return "oracle_assumption"
    return "uncertain"


def _not_model_fault_because(fault: dict) -> str:
    code = str(fault.get("failure_code", ""))
    if code in {"MODEL_PROVIDER_FAILURE"}:
        return "This item is excluded from target faults because it is provider availability/authentication."
    if code == "CONTRACT_TEST_NOT_EXERCISED":
        return "The expected contract fixture was not observed in target execution, so this is a test harness/applicability issue rather than target software evidence."
    if code.startswith("DOCUMENTED_"):
        return "The failure occurs in deterministic CLI/import/parser/dispatcher code before model output quality is relevant."
    if code in {"FILESYSTEM_ESCAPE", "RESUME_STATE_INCOMPLETE", "MARKDOWN_ARTIFACT_CORRUPTION", "ARTIFACT_SCHEMA_MISMATCH"}:
        return "The failure is caused by deterministic filesystem/artifact handling code."
    if code.startswith("TOOL_") or code in {"VIEW_PARAMETER_IGNORED", "PAGINATION_NOT_FOLLOWED", "HTTP_STATUS_NOT_CHECKED"}:
        return "The failure is in the tool wrapper contract: arguments, HTTP status, pagination, or error envelope."
    if code.startswith("MESSAGE_HANDOFF"):
        return "The failure is in framework/application message plumbing that forwards empty or termination-only content."
    if code in {"PARTIAL_METRIC_ZEROED", "NUMERIC_SIGN_CONVENTION_ERROR"}:
        return "The failure is a deterministic data processing invariant violation."
    if code in {"AUTOGEN_WIRING_MISSING", "SPEAKER_SELECTION_LOOP", "HUMAN_INPUT_REQUESTED", "TERMINATION_SIGNAL_IGNORED"}:
        return "The failure follows from AutoGen configuration or orchestration wiring, not LLM parameter behavior."
    return "The reported issue can be mitigated by code, configuration, tool, or orchestration changes without changing model parameters."


def _code_locations(profile: SystemProfile, fault: dict) -> list[dict[str, str]]:
    code = str(fault.get("failure_code", ""))
    keywords = _location_keywords(code)
    locations: list[dict[str, str]] = []
    for item in profile.raw_notes.get("functions", []) or []:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(str(item.get(key, "")) for key in ("name", "source_file", "docstring")).lower()
        if any(keyword in haystack for keyword in keywords):
            locations.append(
                {
                    "file": str(item.get("source_file", "")),
                    "function": str(item.get("name", "")),
                    "line": str(item.get("line", "")),
                }
            )
        if len(locations) >= 5:
            break
    for item in profile.raw_notes.get("call_sites", []) or []:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(str(item.get(key, "")) for key in ("kind", "call", "snippet", "source_file")).lower()
        if any(keyword in haystack for keyword in keywords):
            locations.append(
                {
                    "file": str(item.get("source_file", "")),
                    "function": str(item.get("kind", "")),
                    "line": str(item.get("line", "")),
                }
            )
        if len(locations) >= 5:
            break
    if not locations and code.startswith("TOOL_"):
        for tool in profile.tools:
            if tool.source_file:
                locations.append({"file": str(tool.source_file), "function": str(tool.function_name or tool.name), "line": ""})
            if len(locations) >= 5:
                break
    return locations


def _location_keywords(code: str) -> list[str]:
    mapping = {
        "MARKDOWN_ARTIFACT_CORRUPTION": ["write", "iteration", "artifact", "script", "code"],
        "ARTIFACT_SCHEMA_MISMATCH": ["comment", "artifact", "write"],
        "FILESYSTEM_ESCAPE": ["project", "path", "dir", "mkdir", "write"],
        "RESUME_STATE_INCOMPLETE": ["resume", "version", "latest", "iteration", "script"],
        "VIEW_PARAMETER_IGNORED": ["airtable", "record", "get"],
        "PAGINATION_NOT_FOLLOWED": ["airtable", "record", "get"],
        "MESSAGE_HANDOFF_TERMINATE_ONLY": ["analysis", "conduct", "last_message"],
        "PARTIAL_METRIC_ZEROED": ["metric", "financial", "calculate"],
        "NUMERIC_SIGN_CONVENTION_ERROR": ["risk", "drawdown", "var", "calculate"],
        "DOCUMENTED_ENTRYPOINT_BROKEN": ["main", "analyze", "cli"],
        "DOCUMENTED_CLI_COMMAND_MISSING": ["main", "interactive", "portfolio", "cli"],
        "AUTOGEN_WIRING_MISSING": ["orchestrator", "agent", "factory"],
    }
    return mapping.get(code, [code.lower().split("_")[0]])


def _root_cause(code: str, profile: SystemProfile, evidence: list[str] | None = None) -> str:
    evidence_text = "\n".join(evidence or []).lower()
    if code == "RUNTIME_EXCEPTION" and "docker is not running" in evidence_text:
        return "AutoGen attempted to run code execution in Docker, but Docker is not available in the evaluation environment."
    if code == "RUNTIME_EXCEPTION" and "modulenotfounderror" in evidence_text:
        return "The target system failed before the agent workflow started because a required Python dependency was not installed in the active environment."
    if code == "TOOL_SCHEMA_MISMATCH":
        return "A registered tool appears to be called with arguments that do not match the Python function signature."
    if code in {"MISSING_AGENT", "MISSING_MESSAGE_EDGE"}:
        return "The configured or expected AutoGen routing path was not visible in the collected execution trace."
    if code in {"TIMEOUT", "NON_TERMINATION", "REPETITIVE_LOOP"}:
        return "The conversation may lack a reliable termination condition, max-turn guard, or speaker selection constraint."
    if code == "SPEAKER_SELECTION_LOOP":
        return "The AutoGen GroupChat speaker selection path repeatedly rejected or failed to parse the next speaker."
    if code == "HUMAN_INPUT_REQUESTED":
        return "The target system attempted to enter a manual input path after automated evaluation had started."
    if code == "TERMINATION_SIGNAL_IGNORED":
        return "The target system emitted a termination marker but continued asking for follow-up input or routing messages."
    if code == "MARKDOWN_ARTIFACT_CORRUPTION":
        return "The artifact persistence path does not robustly parse valid Markdown code fences before writing source files."
    if code == "ARTIFACT_SCHEMA_MISMATCH":
        return "Generated artifact filenames or extensions diverge from the documented/profile output contract."
    if code == "FILESYSTEM_ESCAPE":
        return "A user-controlled project/file name is resolved without constraining it to the configured safe root."
    if code == "RESUME_STATE_INCOMPLETE":
        return "The resume-state detector treats partial but meaningful on-disk state as absent or silently starts a fresh workflow."
    if code in {"VIEW_PARAMETER_IGNORED", "PAGINATION_NOT_FOLLOWED"}:
        return "The external API tool wrapper does not preserve semantic parameters or iterate paginated responses."
    if code in {"TOOL_RAW_HTTP_ERROR", "TOOL_RETURNED_NONE", "TOOL_UNSTRUCTURED_ERROR", "HTTP_STATUS_NOT_CHECKED"}:
        return "The external tool wrapper does not normalize HTTP/API failures into a structured error envelope."
    if code == "SCALABLE_BUDGET_EXCEEDED":
        return "The AutoGen turn/round budget is fixed below the estimated work required for multi-record tasks."
    if code in {"MESSAGE_HANDOFF_TERMINATE_ONLY", "MESSAGE_HANDOFF_EMPTY", "MESSAGE_HANDOFF_WRONG_SOURCE"}:
        return "The workflow forwards empty, termination-only, or wrong-source content to downstream agents instead of substantive prior analysis."
    if code == "PARTIAL_METRIC_ZEROED":
        return "Metric calculation zeros available financial values when an unrelated optional row is missing."
    if code == "NUMERIC_SIGN_CONVENTION_ERROR":
        return "Risk metric output violates the documented magnitude/sign convention."
    if code == "DOCUMENTED_ENTRYPOINT_BROKEN":
        return "A README/documented entrypoint fails in deterministic import, constructor, method, or dispatcher code."
    if code == "DOCUMENTED_CLI_COMMAND_MISSING":
        return "A README/documented CLI command is missing from the parser or dispatcher."
    if code == "AUTOGEN_WIRING_MISSING":
        return "The documented AutoGen workflow is not wired into a non-empty orchestrator or does not emit agent collaboration trace."
    if code == "METAMORPHIC_RELATION_VIOLATION":
        return "Equivalent test prompts did not preserve the expected agent/tool routing relation."
    if code == "BUSINESS_TASK_FAILED":
        return "The process finished without a Python crash, but the application reported that the requested task could not be completed."
    if code == "TESTCASE_SETUP_TIMEOUT":
        return "The generated test input exceeded the configured automated execution budget before the target agent workflow could be meaningfully observed."
    if code == "TARGET_WORKFLOW_NOT_OBSERVED":
        return "The target process did not expose a meaningful agent workflow for this generated case, so routing/tool expectations would be unreliable as target faults."
    if code == "CONTRACT_TEST_NOT_EXERCISED":
        return "The contract fixture was not exercised by an observed target HTTP/tool event, so no target root cause can be asserted."
    if code == "MODEL_PROVIDER_FAILURE":
        return "The failure is caused by model/API service authentication, authorization, rate limiting, or timeout rather than a target application or AutoGen framework defect."
    if code == "TURN_BUDGET_EXCEEDED":
        return "The target workflow terminated successfully, but the generated oracle turn budget was too strict for this interaction."
    if code == "RUNTIME_EXCEPTION":
        return "The application raised an unhandled exception during the test run."
    return f"The rule oracle detected {code} for system {profile.system_id}."


def _suggested_fix(code: str, evidence: list[str] | None = None) -> str:
    evidence_text = "\n".join(evidence or []).lower()
    if code == "RUNTIME_EXCEPTION" and "docker is not running" in evidence_text:
        return "Set AUTOGEN_USE_DOCKER=0 for automated evaluation or configure code_execution_config={'use_docker': False}; rerun to expose application-level behavior."
    if code == "RUNTIME_EXCEPTION" and "modulenotfounderror" in evidence_text:
        return "Install the target system dependencies in the active virtual environment, then rerun the same frozen testcases."
    if code == "TOOL_SCHEMA_MISMATCH":
        return "Align the AutoGen function schema, function_map name, and Python callable signature; add a regression test with invalid arguments."
    if code == "MISSING_TOOL_CALL":
        return "Verify tool registration and prompting; ensure the target agent has access to the tool."
    if code in {"TIMEOUT", "NON_TERMINATION"}:
        return "Set human_input_mode='NEVER' for automated runs, add is_termination_msg, and enforce max_turns/max_round."
    if code == "SPEAKER_SELECTION_LOOP":
        return "Harden GroupChat speaker selection: normalize speaker names, handle empty responses, and cap repeated retries."
    if code == "HUMAN_INPUT_REQUESTED":
        return "Set human_input_mode='NEVER' and remove blocking input() calls from automated execution paths."
    if code == "TERMINATION_SIGNAL_IGNORED":
        return "Add or fix is_termination_msg handling so TERMINATE stops the conversation within a small grace window."
    if code == "MARKDOWN_ARTIFACT_CORRUPTION":
        return "Replace ad hoc backtick slicing with a Markdown fence parser and compile-check Python artifacts before writing."
    if code == "ARTIFACT_SCHEMA_MISMATCH":
        return "Align generated artifact filenames/extensions with README/profile contracts, or explicitly update the documented schema."
    if code == "FILESYSTEM_ESCAPE":
        return "Resolve candidate paths, reject absolute/parent-directory components, and enforce relative_to(configured_project_root)."
    if code == "RESUME_STATE_INCOMPLETE":
        return "Discover plan, latest script, and latest comments independently; resume complete state or report incomplete state explicitly."
    if code in {"VIEW_PARAMETER_IGNORED", "PAGINATION_NOT_FOLLOWED"}:
        return "Parse semantic URL fields such as view/base/table, pass them to the API, and follow offset pagination until exhausted."
    if code in {"TOOL_RAW_HTTP_ERROR", "TOOL_RETURNED_NONE", "TOOL_UNSTRUCTURED_ERROR", "HTTP_STATUS_NOT_CHECKED"}:
        return "Check HTTP status codes and return typed success/error payloads instead of raw text or None."
    if code == "SCALABLE_BUDGET_EXCEEDED":
        return "Scale max_round/max_turns with record count or move repeated per-record work into a deterministic/batched tool."
    if code in {"MESSAGE_HANDOFF_TERMINATE_ONLY", "MESSAGE_HANDOFF_EMPTY", "MESSAGE_HANDOFF_WRONG_SOURCE"}:
        return "Store explicit upstream assistant outputs and pass those to downstream agents; filter TERMINATE/default auto-replies from handoff content."
    if code == "PARTIAL_METRIC_ZEROED":
        return "Compute metrics independently and mark only missing-row-dependent metrics as unavailable/null."
    if code == "NUMERIC_SIGN_CONVENTION_ERROR":
        return "Normalize VaR/drawdown fields to documented magnitudes or label signed returns explicitly."
    if code == "DOCUMENTED_ENTRYPOINT_BROKEN":
        return "Run README commands in CI and align imports, constructor signatures, and called methods with implementation."
    if code == "DOCUMENTED_CLI_COMMAND_MISSING":
        return "Add parser/dispatcher branches for documented commands or remove them from the README."
    if code == "AUTOGEN_WIRING_MISSING":
        return "Wire factory-created agents into the orchestrator/group chat and expose runtime messages from each documented role."
    if code == "METAMORPHIC_RELATION_VIOLATION":
        return "Inspect prompts, tool registration, and routing logic for equivalent requests; add a paired metamorphic regression test."
    if code == "BUSINESS_TASK_FAILED":
        return "Add a deterministic evaluation fallback or mock external data source so automated tests can distinguish application logic faults from upstream service failures."
    if code == "TESTCASE_SETUP_TIMEOUT":
        return "Reduce or truncate the generated prompt for interactive LLM systems and rerun; do not count this as a target-system defect."
    if code == "TARGET_WORKFLOW_NOT_OBSERVED":
        return "Improve the case-to-target adapter, command template, or runtime instrumentation, then rerun the frozen testcase before judging application/framework faults."
    if code == "CONTRACT_TEST_NOT_EXERCISED":
        return "Improve the case adapter or instrumentation so the target actually performs the expected HTTP/tool action before judging the contract."
    if code == "MODEL_PROVIDER_FAILURE":
        return "Fix API credentials/network limits or add application-level retry/fallback configuration, then rerun; do not treat model/provider availability as a model defect."
    if code == "TURN_BUDGET_EXCEEDED":
        return "Treat max_turns as a soft efficiency budget, adjust the generated oracle budget, and do not count this as an application/framework defect by itself."
    if code == "RUNTIME_EXCEPTION":
        return "Inspect stderr evidence, add defensive error handling, and make required environment/config dependencies explicit."
    if code == "OUTPUT_SCHEMA_VIOLATION":
        return "Validate output before returning and add deterministic fallback formatting."
    return "Inspect the trace and configuration, then add a focused regression test for this case."


def _environment_runtime_exception(evidence: list[str]) -> tuple[str, str, str, float] | None:
    text = "\n".join(evidence).lower()
    if "docker is not running" in text:
        return ("environment", "AutoGen Docker Runtime Not Available", "high", 0.96)
    if "modulenotfounderror" in text:
        return ("environment", "Missing Target Runtime Dependency", "high", 0.96)
    if any(
        marker in text
        for marker in (
            "authentication fails",
            "authorization required",
            "unauthorized consumer",
            "invalid api key",
            "api key is invalid",
            "http 401",
            "http 403",
            "rate limit",
            "too many requests",
            "read operation timed out",
            "openai.apitimeouterror",
            "openai api call timed out",
            "request timed out",
            "connecttimeout",
            "httpx.connecttimeout",
            "httpcore.connecttimeout",
            "api timeout",
            "llm timeout",
        )
    ):
        return ("model_provider", "Model/API Provider Failure", "low", 0.96)
    return None
