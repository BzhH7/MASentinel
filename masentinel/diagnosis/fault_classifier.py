from __future__ import annotations

import ast

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
    "HUMAN_INPUT_REQUESTED": ("autogen_framework", "Human Input Mode Error", "high", 0.9),
    "METAMORPHIC_RELATION_VIOLATION": ("application", "Metamorphic Relation Violation", "medium", 0.74),
    "BUSINESS_TASK_FAILED": ("application", "Business Task Failure", "high", 0.82),
    "TURN_BUDGET_EXCEEDED": ("test_harness", "Soft Turn Budget Exceeded", "low", 0.95),
    "TESTCASE_SETUP_TIMEOUT": ("test_harness", "Generated Test Input Exceeded Runtime Budget", "low", 0.95),
    "TARGET_WORKFLOW_NOT_OBSERVED": ("test_harness", "Target Workflow Not Observed", "low", 0.95),
    "MODEL_PROVIDER_FAILURE": ("model_provider", "Model/API Provider Failure", "low", 0.95),
}

TARGET_LAYERS = {"application", "autogen_framework"}
NON_TARGET_FAILURE_CODES = {"TESTCASE_SETUP_TIMEOUT", "TARGET_WORKFLOW_NOT_OBSERVED", "MODEL_PROVIDER_FAILURE", "TURN_BUDGET_EXCEEDED"}


def classify_faults(profile: SystemProfile, testcases: list[TestCase], traces: list[RunTrace]) -> list[dict]:
    tools = {tool.name for tool in profile.tools}
    oracle = RuleOracle(registered_tools=tools)
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
            if layer not in TARGET_LAYERS:
                continue
            faults.append(
                {
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
            )
            counter += 1
    return faults


def classify_non_target_issues(profile: SystemProfile, testcases: list[TestCase], traces: list[RunTrace]) -> list[dict]:
    tools = {tool.name for tool in profile.tools}
    oracle = RuleOracle(registered_tools=tools)
    case_by_id = {case.case_id: case for case in testcases}
    issues: list[dict] = []
    for trace in traces:
        testcase = case_by_id.get(trace.case_id)
        if not testcase:
            continue
        result = oracle.evaluate(testcase, trace)
        for failure in result.failures:
            layer, issue_type, severity, confidence = _classify_failure(profile, failure.code, failure.severity, failure.evidence)
            if layer in TARGET_LAYERS:
                continue
            issues.append(
                {
                    "case_id": testcase.case_id,
                    "code": failure.code,
                    "layer": layer,
                    "issue_type": issue_type,
                    "severity": severity,
                    "confidence": confidence,
                    "message": failure.message,
                    "evidence": failure.evidence,
                    "root_cause": _root_cause(failure.code, profile, failure.evidence),
                    "suggested_fix": _suggested_fix(failure.code, failure.evidence),
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
    if code == "MISSING_MESSAGE_EDGE" and _is_potential_groupchat_edge(profile, evidence):
        confidence = 0.6
    return layer, fault_type, severity, confidence


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
    if code == "HUMAN_INPUT_REQUESTED":
        return "The target system attempted to enter a manual input path after automated evaluation had started."
    if code == "METAMORPHIC_RELATION_VIOLATION":
        return "Equivalent test prompts did not preserve the expected agent/tool routing relation."
    if code == "BUSINESS_TASK_FAILED":
        return "The process finished without a Python crash, but the application reported that the requested task could not be completed."
    if code == "TESTCASE_SETUP_TIMEOUT":
        return "The generated test input exceeded the configured automated execution budget before the target agent workflow could be meaningfully observed."
    if code == "TARGET_WORKFLOW_NOT_OBSERVED":
        return "The target process did not expose a meaningful agent workflow for this generated case, so routing/tool expectations would be unreliable as target faults."
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
    if code == "HUMAN_INPUT_REQUESTED":
        return "Set human_input_mode='NEVER' and remove blocking input() calls from automated execution paths."
    if code == "METAMORPHIC_RELATION_VIOLATION":
        return "Inspect prompts, tool registration, and routing logic for equivalent requests; add a paired metamorphic regression test."
    if code == "BUSINESS_TASK_FAILED":
        return "Add a deterministic evaluation fallback or mock external data source so automated tests can distinguish application logic faults from upstream service failures."
    if code == "TESTCASE_SETUP_TIMEOUT":
        return "Reduce or truncate the generated prompt for interactive LLM systems and rerun; do not count this as a target-system defect."
    if code == "TARGET_WORKFLOW_NOT_OBSERVED":
        return "Improve the case-to-target adapter, command template, or runtime instrumentation, then rerun the frozen testcase before judging application/framework faults."
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
