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
    "speaker_selection",
    "message_handoff_integrity",
    "data_invariant",
    "cli_doc_conformance",
    "autogen_wiring",
}

DETERMINISTIC_BACKSTOP_PATTERNS = {
    # Direct data-processing invariants are concrete enough for the verifier to
    # exercise when an agent omits them despite matching deterministic features.
    "data_invariant",
}

CASE_TYPE_PATTERN_ALIASES = {
    "speaker_selection_robustness": "speaker_selection",
}


class ApplicabilityVerifier:
    def __init__(self, features: dict[str, Any]) -> None:
        self.features = features

    def verify(self, items: list[dict[str, Any]], diagnostic: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return verify_pattern_selection(items, self.features, diagnostic=diagnostic)


def build_test_plan(features: dict[str, Any], agent_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    agent_payload = agent_plan if isinstance(agent_plan, dict) else {}
    agent_selected = _normalize_items(agent_payload.get("selected_patterns", []))
    agent_diagnostic = _normalize_items(agent_payload.get("diagnostic_only_patterns", []))
    agent_rejected = _normalize_items(agent_payload.get("rejected_patterns", []))
    selection_mode = "agent_verified" if _has_agent_selection_payload(agent_payload) else "deterministic_fallback"

    if selection_mode == "deterministic_fallback":
        proposed = _deterministic_proposals(features)
    else:
        proposed = _dedupe_by_pattern(_mark_source(agent_selected, "PatternApplicabilityAgent"))

    verifier = ApplicabilityVerifier(features)
    verified, rejected = verifier.verify(proposed)
    diagnostic_verified, diagnostic_rejected = verifier.verify(agent_diagnostic, diagnostic=True)
    rejected.extend(diagnostic_rejected)
    selected_names = {item["pattern"] for item in verified}
    diagnostic_names = {item["pattern"] for item in diagnostic_verified}
    omitted_applicable = []
    verifier_promoted: list[dict[str, Any]] = []
    if selection_mode == "agent_verified":
        omitted_applicable = _deterministic_proposals(features, selected_names | diagnostic_names)
        verifier_promoted = _promote_backstop_patterns(omitted_applicable)
        if verifier_promoted:
            verified.extend(verifier_promoted)
            selected_names.update(item["pattern"] for item in verifier_promoted)
            omitted_applicable = [item for item in omitted_applicable if item.get("pattern") not in selected_names]
    agent_rejected_marked = _mark_source(agent_rejected, "PatternApplicabilityAgent")
    promoted_names = {item["pattern"] for item in verifier_promoted}
    rejected.extend([item for item in agent_rejected_marked if item.get("pattern") not in promoted_names])
    overridden_rejections = [
        {
            **item,
            "overridden_by_verifier": True,
            "verifier_reason": "deterministic backstop pattern passed feature verification and should be exercised despite agent rejection",
        }
        for item in agent_rejected_marked
        if item.get("pattern") in promoted_names
    ]
    rejected.extend(_deterministic_rejections(features, selected_names | diagnostic_names))
    precision_denominator = len(verified) + len([item for item in rejected if item.get("rejected_by_verifier")])
    precision = round(len(verified) / precision_denominator, 4) if precision_denominator else 1.0
    return {
        "selected_patterns": verified,
        "rejected_patterns": rejected,
        "verifier_omitted_applicable_patterns": omitted_applicable,
        "verifier_promoted_patterns": verifier_promoted,
        "verifier_overridden_rejections": overridden_rejections,
        "diagnostic_only_patterns": diagnostic_verified,
        "deterministic_features": features,
        "agent_rationale": agent_payload,
        "selection_mode": selection_mode,
        "metrics": {
            "pattern_applicability_precision": precision,
            "selected_count": len(verified),
            "rejected_count": len(rejected),
            "diagnostic_only_count": len(diagnostic_verified),
            "omitted_applicable_count": len(omitted_applicable),
            "verifier_promoted_count": len(verifier_promoted),
        },
        "confidence": min(1.0, max([float(item.get("confidence", 0.75) or 0.75) for item in verified] or [0.75])),
    }


def selected_pattern_names(test_plan: dict[str, Any]) -> list[str]:
    return [str(item.get("pattern")) for item in test_plan.get("selected_patterns", []) if item.get("pattern")]


def diagnostic_pattern_names(test_plan: dict[str, Any]) -> list[str]:
    return [str(item.get("pattern")) for item in test_plan.get("diagnostic_only_patterns", []) if item.get("pattern")]


def active_pattern_names(test_plan: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for pattern in selected_pattern_names(test_plan) + diagnostic_pattern_names(test_plan):
        if pattern not in names:
            names.append(pattern)
    return names


def pattern_strengths(test_plan: dict[str, Any]) -> dict[str, str]:
    strengths: dict[str, str] = {}
    for item in test_plan.get("selected_patterns", []) or []:
        pattern = str(item.get("pattern") or "")
        if pattern:
            strengths[pattern] = str(item.get("oracle_strength") or "hard")
    for item in test_plan.get("diagnostic_only_patterns", []) or []:
        pattern = str(item.get("pattern") or "")
        if pattern:
            strengths[pattern] = "diagnostic"
    return strengths


def pattern_budgets(test_plan: dict[str, Any]) -> dict[str, int]:
    budgets: dict[str, int] = {}
    for item in (test_plan.get("selected_patterns", []) or []) + (test_plan.get("diagnostic_only_patterns", []) or []):
        pattern = str(item.get("pattern") or "")
        if not pattern:
            continue
        try:
            budgets[pattern] = max(1, int(item.get("case_budget") or 1))
        except (TypeError, ValueError):
            budgets[pattern] = 1
    return budgets


def filter_cases_by_test_plan(cases: list[TestCase], test_plan: dict[str, Any]) -> list[TestCase]:
    selected = set(active_pattern_names(test_plan))
    strengths = pattern_strengths(test_plan)
    filtered: list[TestCase] = []
    for case in cases:
        pattern = _case_pattern_name(case)
        if pattern in CONTRACT_PATTERNS and pattern not in selected:
            continue
        if pattern in strengths:
            case.metadata["selected_pattern"] = pattern
            case.metadata["oracle_strength"] = strengths[pattern]
            if strengths[pattern] == "diagnostic":
                case.metadata["diagnostic_only"] = True
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
        elif diagnostic:
            item["oracle_strength"] = "diagnostic"
            item.setdefault("case_budget", _default_budget(pattern))
            item.setdefault("confidence", 0.5)
            item.setdefault("required_evidence", _required_evidence(pattern))
            item["diagnostic_only"] = True
            item["verifier_warning"] = reason
            verified.append(item)
        else:
            item["oracle_strength"] = "diagnostic"
            item["rejected_by_verifier"] = True
            item["verifier_reason"] = reason
            item.setdefault("confidence", 0.85)
            rejected.append(item)
    return verified, rejected


def _deterministic_proposals(features: dict[str, Any], exclude: set[str] | None = None) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    excluded = exclude or set()
    for pattern in sorted(CONTRACT_PATTERNS):
        if pattern in excluded:
            continue
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


def _promote_backstop_patterns(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    promoted: list[dict[str, Any]] = []
    for raw in items:
        pattern = str(raw.get("pattern") or "")
        if pattern not in DETERMINISTIC_BACKSTOP_PATTERNS:
            continue
        item = dict(raw)
        item["source"] = "deterministic_verifier_backstop"
        item["verifier_promoted"] = True
        item["reasons"] = list(item.get("reasons", []) or []) + [
            "PatternApplicabilityAgent omitted a deterministic invariant pattern that passed feature verification."
        ]
        promoted.append(item)
    return promoted


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


def _has_agent_selection_payload(agent_plan: dict[str, Any]) -> bool:
    if not agent_plan:
        return False
    if bool(agent_plan.get("fallback")):
        return False
    return any(
        isinstance(agent_plan.get(key), list)
        for key in ("selected_patterns", "diagnostic_only_patterns", "rejected_patterns")
    )


def _dedupe_by_pattern(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        pattern = str(item.get("pattern") or "")
        if pattern and pattern not in deduped:
            deduped[pattern] = item
    return list(deduped.values())


def _mark_source(items: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    marked = []
    for raw in items:
        item = dict(raw)
        item.setdefault("source", source)
        marked.append(item)
    return marked


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
        ok = bool(artifacts.get("has_resume_state") and artifacts.get("has_versioned_artifacts"))
        return ok, "requires real resume/version/state artifacts"
    if pattern == "tool_api_contract":
        ok = bool(tools.get("has_http_tools") or tools.get("has_airtable_tools") or tools.get("has_external_api_tools") or tools.get("has_pagination_risk"))
        return ok, "requires HTTP/API/Airtable tool evidence"
    if pattern == "tool_error_contract":
        ok = bool(tools.get("has_tools") and (tools.get("has_http_tools") or tools.get("has_airtable_tools") or tools.get("has_external_api_tools")))
        return ok, "requires request-like external tool wrapper evidence"
    if pattern == "scalable_budget":
        ok = bool(framework.get("uses_groupchat") and (framework.get("has_fixed_round_budget") or tools.get("has_pagination_risk")) and tools.get("has_multi_record_work"))
        return ok, "requires GroupChat/fixed budget plus multi-record or paginated work"
    if pattern == "speaker_selection":
        ok = bool(framework.get("uses_groupchat") or framework.get("has_speaker_selection"))
        return ok, "requires GroupChat or speaker-selection configuration"
    if pattern == "message_handoff_integrity":
        ok = bool(message_flow.get("has_last_message_calls") or message_flow.get("has_multistage_handoff"))
        return ok, "requires last_message/chat_messages or explicit multi-stage handoff"
    if pattern == "data_invariant":
        ok = bool(data.get("has_financial_metrics") or data.get("has_risk_metrics") or data.get("has_dataframe_metrics"))
        return ok, "requires financial/risk/dataframe metric calculation code"
    if pattern == "cli_doc_conformance":
        ok = bool(cli.get("has_documented_commands"))
        return ok, "requires executable README/documented python commands"
    if pattern == "autogen_wiring":
        ok = bool((docs.get("claims_multi_agent") and framework.get("uses_autogen")) or risks.get("has_autogen_wiring_risk"))
        return ok, "requires documented AutoGen/multi-agent workflow or static wiring risk"
    return True, "no feature gate"


def _default_budget(pattern: str) -> int:
    return {
        "speaker_selection": 1,
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
        "speaker_selection": ["GroupChat_or_speaker_selection_config", "speaker_selection_response_or_error_trace"],
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


def _case_pattern_name(case: TestCase) -> str:
    value = str(case.metadata.get("selected_pattern") or case.case_type or "")
    return CASE_TYPE_PATTERN_ALIASES.get(value, value)
