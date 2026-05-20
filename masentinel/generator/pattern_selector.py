from __future__ import annotations

from typing import Any

from masentinel.schema import TestCase


CONTRACT_PATTERNS = {
    "artifact_contract",
    "filesystem_safety",
    "state_resume_contract",
    "tool_api_contract",
    "tool_error_contract",
    "scalable_budget",
    "message_handoff_integrity",
    "data_invariant",
    "cli_doc_conformance",
    "autogen_wiring",
}


def build_test_plan(features: dict[str, Any], agent_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    deterministic = _deterministic_proposals(features)
    agent_selected = _normalize_items((agent_plan or {}).get("selected_patterns", []))
    agent_diagnostic = _normalize_items((agent_plan or {}).get("diagnostic_only_patterns", []))
    proposed_by_name: dict[str, dict[str, Any]] = {item["pattern"]: item for item in deterministic}
    for item in agent_selected:
        proposed_by_name.setdefault(item["pattern"], item)
    verified, rejected = verify_pattern_selection(list(proposed_by_name.values()), features)
    diagnostic_verified, diagnostic_rejected = verify_pattern_selection(agent_diagnostic, features, diagnostic=True)
    rejected.extend(diagnostic_rejected)
    selected_names = {item["pattern"] for item in verified}
    rejected.extend(_deterministic_rejections(features, selected_names))
    precision_denominator = len(verified) + len([item for item in rejected if item.get("rejected_by_verifier")])
    precision = round(len(verified) / precision_denominator, 4) if precision_denominator else 1.0
    return {
        "selected_patterns": verified,
        "rejected_patterns": rejected,
        "diagnostic_only_patterns": diagnostic_verified,
        "deterministic_features": features,
        "agent_rationale": agent_plan or {},
        "metrics": {
            "pattern_applicability_precision": precision,
            "selected_count": len(verified),
            "rejected_count": len(rejected),
            "diagnostic_only_count": len(diagnostic_verified),
        },
        "confidence": min(1.0, max([float(item.get("confidence", 0.75) or 0.75) for item in verified] or [0.75])),
    }


def selected_pattern_names(test_plan: dict[str, Any]) -> list[str]:
    return [str(item.get("pattern")) for item in test_plan.get("selected_patterns", []) if item.get("pattern")]


def pattern_budgets(test_plan: dict[str, Any]) -> dict[str, int]:
    budgets: dict[str, int] = {}
    for item in test_plan.get("selected_patterns", []) or []:
        pattern = str(item.get("pattern") or "")
        if not pattern:
            continue
        try:
            budgets[pattern] = max(1, int(item.get("case_budget") or 1))
        except (TypeError, ValueError):
            budgets[pattern] = 1
    return budgets


def filter_cases_by_test_plan(cases: list[TestCase], test_plan: dict[str, Any]) -> list[TestCase]:
    selected = set(selected_pattern_names(test_plan))
    filtered: list[TestCase] = []
    for case in cases:
        if case.case_type in CONTRACT_PATTERNS and case.case_type not in selected:
            continue
        filtered.append(case)
    return filtered


def verify_pattern_selection(items: list[dict[str, Any]], features: dict[str, Any], diagnostic: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    verified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        pattern = str(item.get("pattern") or "")
        ok, reason = _feature_gate(pattern, features)
        if ok:
            item.setdefault("oracle_strength", "diagnostic" if diagnostic else "hard")
            item.setdefault("case_budget", _default_budget(pattern))
            item.setdefault("confidence", 0.85)
            item.setdefault("required_evidence", _required_evidence(pattern))
            verified.append(item)
        else:
            item["oracle_strength"] = "diagnostic"
            item["rejected_by_verifier"] = True
            item["verifier_reason"] = reason
            item.setdefault("confidence", 0.85)
            rejected.append(item)
    return verified, rejected


def _deterministic_proposals(features: dict[str, Any]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for pattern in sorted(CONTRACT_PATTERNS):
        ok, reason = _feature_gate(pattern, features)
        if ok:
            proposals.append(
                {
                    "pattern": pattern,
                    "applicability": "hard",
                    "oracle_strength": "hard",
                    "case_budget": _default_budget(pattern),
                    "confidence": 0.9,
                    "reasons": [reason],
                    "required_evidence": _required_evidence(pattern),
                    "source": "deterministic_feature_extractor",
                }
            )
    return proposals


def _deterministic_rejections(features: dict[str, Any], selected_names: set[str]) -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    for pattern in sorted(CONTRACT_PATTERNS - selected_names):
        _ok, reason = _feature_gate(pattern, features)
        rejected.append(
            {
                "pattern": pattern,
                "reason": reason,
                "confidence": 0.9,
                "source": "deterministic_feature_extractor",
            }
        )
    return rejected


def _feature_gate(pattern: str, features: dict[str, Any]) -> tuple[bool, str]:
    framework = features.get("framework", {}) or {}
    tools = features.get("tools", {}) or {}
    artifacts = features.get("artifacts", {}) or {}
    data = features.get("data_processing", {}) or {}
    cli = features.get("cli", {}) or {}
    message_flow = features.get("message_flow", {}) or {}
    docs = features.get("docs", {}) or {}
    risks = features.get("static_risks", {}) or {}
    if pattern == "artifact_contract":
        ok = bool(artifacts.get("writes_files") or artifacts.get("has_documented_artifacts"))
        return ok, "requires file-writing or documented artifacts"
    if pattern == "filesystem_safety":
        ok = bool(artifacts.get("writes_files") and artifacts.get("has_user_controlled_path"))
        return ok, "requires user-controlled path plus filesystem writes"
    if pattern == "state_resume_contract":
        ok = bool(artifacts.get("has_resume_state"))
        return ok, "requires real resume/version/state artifacts"
    if pattern == "tool_api_contract":
        ok = bool(tools.get("has_http_tools") or tools.get("has_airtable_tools") or tools.get("has_pagination_risk"))
        return ok, "requires HTTP/API/Airtable tool evidence"
    if pattern == "tool_error_contract":
        ok = bool(tools.get("has_tools") and (tools.get("has_http_tools") or tools.get("has_airtable_tools")))
        return ok, "requires request-like external tool wrapper evidence"
    if pattern == "scalable_budget":
        ok = bool(framework.get("uses_groupchat") and (framework.get("has_fixed_round_budget") or tools.get("has_pagination_risk")) and tools.get("has_multi_record_work"))
        return ok, "requires GroupChat/fixed budget plus multi-record or paginated work"
    if pattern == "message_handoff_integrity":
        ok = bool(message_flow.get("has_last_message_calls") or message_flow.get("has_multistage_handoff"))
        return ok, "requires last_message/chat_messages or explicit multi-stage handoff"
    if pattern == "data_invariant":
        ok = bool(data.get("has_financial_metrics") or data.get("has_risk_metrics"))
        return ok, "requires financial/risk metric calculation code"
    if pattern == "cli_doc_conformance":
        ok = bool(cli.get("has_documented_commands"))
        return ok, "requires executable README/documented python commands"
    if pattern == "autogen_wiring":
        ok = bool((docs.get("claims_multi_agent") and framework.get("uses_autogen")) or risks.get("has_autogen_wiring_risk"))
        return ok, "requires documented AutoGen/multi-agent workflow or static wiring risk"
    return True, "no feature gate"


def _default_budget(pattern: str) -> int:
    return {
        "cli_doc_conformance": 4,
        "data_invariant": 2,
        "tool_api_contract": 2,
        "tool_error_contract": 1,
        "artifact_contract": 2,
    }.get(pattern, 1)


def _required_evidence(pattern: str) -> list[str]:
    return {
        "tool_api_contract": ["observed_http_request", "observed_query_params_or_pages"],
        "tool_error_contract": ["observed_http_status>=400", "observed_tool_result_or_error"],
        "data_invariant": ["mocked_financial_or_price_fixture", "observed_output_metrics_or_report_values"],
        "artifact_contract": ["observed_artifact_path", "artifact_content_or_compile_result"],
        "filesystem_safety": ["observed_filesystem_effects"],
        "state_resume_contract": ["fixture_files", "observed_resume_or_missing_resume_output"],
        "message_handoff_integrity": ["observed_message_handoff_event_or_prompt"],
        "cli_doc_conformance": ["documented_command", "process_returncode_and_stderr"],
        "autogen_wiring": ["static_wiring_risk_or_missing_runtime_messages"],
        "scalable_budget": ["record_count_or_budget_estimate", "configured_max_round"],
    }.get(pattern, [])


def _normalize_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return items
    for raw in value:
        if isinstance(raw, str):
            raw = {"pattern": raw}
        if not isinstance(raw, dict):
            continue
        pattern = str(raw.get("pattern") or raw.get("case_type") or "")
        if pattern in CONTRACT_PATTERNS:
            item = dict(raw)
            item["pattern"] = pattern
            items.append(item)
    return items
