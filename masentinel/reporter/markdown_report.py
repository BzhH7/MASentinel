from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups
from masentinel.diagnosis.report_builder import summarize_faults
from masentinel.schema import RunTrace, SystemProfile, TestCase
from masentinel.utils import ensure_dir, write_text


def write_markdown_reports(
    profile: SystemProfile,
    testcases: list[TestCase],
    traces: list[RunTrace],
    faults: list[dict],
    coverage: dict,
    out_dir: str | Path,
    agentic_info: dict | None = None,
) -> None:
    out_dir = ensure_dir(out_dir)
    write_text(out_dir / "report.md", build_report(profile, testcases, traces, faults, coverage, agentic_info=agentic_info))
    write_text(out_dir / "coverage.md", build_coverage_report(coverage))
    write_text(out_dir / "fault_report.md", build_fault_report(faults))


def build_report(
    profile: SystemProfile,
    testcases: list[TestCase],
    traces: list[RunTrace],
    faults: list[dict],
    coverage: dict,
    agentic_info: dict | None = None,
) -> str:
    faults = annotate_fault_groups(faults)
    passed = len([trace for trace in traces if trace.status == "passed"])
    failed = len(traces) - passed
    summary = summarize_faults(faults)
    fault_groups = build_fault_groups(faults)
    primary_faults = len([fault for fault in faults if fault.get("is_primary_fault", True)])
    lines = [
        f"# MASentinel Report: {profile.system_id}",
        "",
        "## System Overview",
        f"- Root path: `{profile.root_path}`",
        f"- Entrypoint: `{profile.entrypoint}`",
        f"- Agents: {len(profile.agents)}",
        f"- Tools: {len(profile.tools)}",
        f"- Requirements: {len(profile.requirements)}",
        f"- Message edges: {len(profile.message_edges)}",
        "",
        "## Detected Agents",
    ]
    lines.extend([f"- `{agent.name}` ({agent.class_name or 'unknown'}) tools={agent.tools}" for agent in profile.agents] or ["- None detected"])
    lines.append("")
    lines.append("## Detected Tools")
    lines.extend([f"- `{tool.name}` {tool.signature or ''}" for tool in profile.tools] or ["- None detected"])
    lines.append("")
    lines.append("## Requirements")
    lines.extend([f"- `{req.id}` {_clean_report_text(req.description)}" for req in profile.requirements] or ["- None detected"])
    lines.extend(
        [
            "",
            "## Test Summary",
            f"- Cases: {len(testcases)}",
            f"- Passed process runs: {passed}",
            f"- Failed/timeout process runs: {failed}",
            f"- Fault findings: {len(faults)}",
            f"- Root-cause groups: {len(fault_groups)}",
            f"- Primary fault findings: {primary_faults}",
            f"- Suspected false positives: {summary['suspected_false_positive']}",
            "",
            "## Coverage",
            _coverage_table(coverage),
            "",
            *_agentic_section(agentic_info),
            "",
            "## Fault Summary",
        ]
    )
    if fault_groups:
        lines.append("")
        lines.append("### Root-Cause Groups")
        for group in fault_groups[:12]:
            lines.append(
                f"- `{group['group_id']}` {group['title']} "
                f"primary=`{group['primary_fault_id']}` cases={len(group['affected_cases'])} "
                f"symptoms={len(group['symptom_fault_ids'])}"
            )
    if faults:
        for fault in faults[:20]:
            marker = "primary" if fault.get("is_primary_fault", True) else f"derived from `{fault.get('cascades_from')}`"
            lines.append(
                f"- `{fault['fault_id']}` `{fault['case_id']}` {fault['layer']} / {fault['fault_type']} / "
                f"{fault['severity']} / {marker}: {_clean_report_text(fault['summary'])}"
            )
    else:
        lines.append("- No rule-level faults detected.")
    lines.extend(
        [
            "",
            "## Suspected False Positives",
            "Findings with confidence below 0.65 are marked as suspected false positives. Missing-agent and missing-edge findings can be caused by limited instrumentation when a target system does not emit MASentinel trace events.",
            "",
            "## Limitations",
            "- Subprocess tracing captures stdout/stderr for arbitrary systems; deep AutoGen message/tool traces require optional monkey patch import in the target process.",
            "- The deterministic generator avoids judging subjective LLM answer quality.",
            "- Static AST extraction is conservative and may over-approximate potential GroupChat edges.",
            "",
            "## Next Steps",
            "- Import `masentinel.instrumentation.autogen_patch` in target entrypoints for richer traces.",
            "- Add system-specific configuration for command arguments and timeout budgets.",
            "- Enable an OpenAI-compatible local model for document extraction and optional LLM judge.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_coverage_report(coverage: dict) -> str:
    return "# Coverage\n\n" + _coverage_table(coverage) + "\n"


def build_fault_report(faults: list[dict]) -> str:
    faults = annotate_fault_groups(faults)
    lines = ["# Fault Report", ""]
    if not faults:
        lines.append("No faults detected.")
        return "\n".join(lines) + "\n"
    groups = build_fault_groups(faults)
    if groups:
        lines.append("## Root-Cause Groups")
        lines.append("")
        for group in groups:
            lines.extend(
                [
                    f"### {group['group_id']}",
                    f"- Title: {group['title']}",
                    f"- Primary Fault: `{group['primary_fault_id']}`",
                    f"- Fault IDs: {', '.join(f'`{item}`' for item in group['fault_ids'])}",
                    f"- Symptom Fault IDs: {', '.join(f'`{item}`' for item in group['symptom_fault_ids']) or 'None'}",
                    f"- Affected Cases: {len(group['affected_cases'])}",
                    f"- Failure Codes: {', '.join(group['failure_codes'])}",
                    f"- Root Cause: {group['root_cause']}",
                    f"- Suggested Fix: {group['suggested_fix']}",
                    "",
                ]
            )
        lines.append("## Fault Details")
        lines.append("")
    for fault in faults:
        marker = "primary" if fault.get("is_primary_fault", True) else f"derived from {fault.get('cascades_from')}"
        lines.extend(
            [
                f"## {fault['fault_id']}",
                f"- Case ID: `{fault['case_id']}`",
                f"- Root-Cause Group: `{fault.get('root_cause_group_id', '')}`",
                f"- Classification: {marker}",
                f"- Layer: {fault['layer']}",
                f"- Fault Type: {fault['fault_type']}",
                f"- Severity: {fault['severity']}",
                f"- Confidence: {fault['confidence']}",
                f"- EvidenceStrength: {fault.get('evidence_strength', 'n/a')}",
                f"- RootCauseConfidence: {fault.get('root_cause_confidence', 'n/a')}",
                f"- NotModelFaultBecause: {_clean_report_text(fault.get('not_model_fault_because', ''), limit=800)}",
                f"- Code Locations: {_clean_report_text(_format_code_locations(fault.get('code_locations', [])), limit=800)}",
                f"- Input: {_clean_report_text(fault['reproduction'].get('input', ''), limit=800)}",
                f"- Evidence: {_clean_report_text(' | '.join(fault.get('evidence', [])), limit=1200)}",
                f"- Root Cause: {_clean_report_text(fault['root_cause'])}",
                f"- Suggested Fix: {_clean_report_text(fault['suggested_fix'])}",
                f"- Reproduction Command: `{fault['reproduction'].get('command', '')}`",
                "",
            ]
        )
    return "\n".join(lines)


def _coverage_table(coverage: dict) -> str:
    rows = [
        ("AgentCov", coverage.get("agent_coverage", 0)),
        ("ToolCov", coverage.get("tool_coverage", 0)),
        ("EdgeCov", coverage.get("message_edge_coverage", 0)),
        ("ReqIntentCov", coverage.get("req_intent_coverage", coverage.get("requirement_coverage", 0))),
        ("ReqVerifiedCov", coverage.get("req_verified_coverage", 0)),
        ("StateCov", coverage.get("state_coverage", 0)),
        ("FaultCov", coverage.get("fault_mode_coverage", 0)),
        ("ContractCov", coverage.get("contract_coverage", None)),
        ("EffectiveWorkflowRate", coverage.get("effective_workflow_rate", 0)),
        ("TraceCompleteness", coverage.get("trace_completeness", 0)),
        ("RootCauseEvidenceRate", coverage.get("root_cause_evidence_rate", None)),
        ("MASCov", coverage.get("mascov", 0)),
    ]
    lines = ["| Metric | Value |", "|--------|-------|"]
    lines.extend([f"| {name} | {_format_metric(value)} |" for name, value in rows])
    return "\n".join(lines)


def _format_metric(value: object) -> str:
    if value is None:
        return "N/A"


def _format_code_locations(locations: object) -> str:
    if not isinstance(locations, list) or not locations:
        return "n/a"
    parts = []
    for item in locations[:5]:
        if not isinstance(item, dict):
            continue
        parts.append(f"{item.get('file', '')}:{item.get('line', '')} {item.get('function', '')}".strip())
    return "; ".join(parts) or "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "N/A"


def _agentic_section(agentic_info: dict | None) -> list[str]:
    if not agentic_info:
        return []
    usage = agentic_info.get("model_usage", {}) or {}
    target_usage = agentic_info.get("target_model_usage", {}) or {}
    non_target_issues = agentic_info.get("non_target_issues", []) or []
    narrative = agentic_info.get("report_narrative", {}) or {}
    lines = [
        "## Agentic Testing Workflow",
    ]
    for agent in agentic_info.get("workflow_agents", []) or []:
        lines.append(f"- `{agent}`")
    lines.extend(
        [
            "",
            "## Three-Stage Automation Evidence",
            f"- Human intervention allowed: {agentic_info.get('human_intervention_allowed', True)}",
            f"- Testcase frozen SHA256: `{agentic_info.get('testcases_frozen_sha256', '')}`",
            f"- Second-round extra cases: {(agentic_info.get('second_round', {}) or {}).get('extra_cases', 0)}",
            f"- Non-target issues excluded from target faults: {len(non_target_issues)}",
            f"- Test harness issues excluded from target faults: {len(agentic_info.get('test_harness_issues', []) or [])}",
            "- Artifacts: `run_manifest.json`, `testcases.generated.json`, `testcases.validated.json`, `oracle_results.json`, `non_target_issues.json`, `test_harness_issues.json`, `faults.json`, `false_positive_audit.json`",
            "",
            "## Testing-Agent Model Usage",
            f"- Total agent calls: {usage.get('total_calls', 0)}",
            f"- Successful model calls: {usage.get('successful_calls', 0)}",
            f"- Fallback calls: {usage.get('fallback_calls', 0)}",
            f"- Estimated input tokens: {(usage.get('estimated_tokens', {}) or {}).get('input_tokens', 0)}",
            f"- Estimated output tokens: {(usage.get('estimated_tokens', {}) or {}).get('output_tokens', 0)}",
            "",
            "| Agent | Calls |",
            "|-------|-------|",
        ]
    )
    by_agent = usage.get("by_agent", {}) or {}
    lines.extend([f"| {agent} | {count} |" for agent, count in sorted(by_agent.items())])
    if target_usage:
        lines.extend(
            [
                "",
                "## Target-System Model Usage",
                f"- Scope: `{target_usage.get('scope', '')}`",
                f"- Traced cases: {target_usage.get('cases', 0)}",
                f"- AutoGen model-warning mentions: {target_usage.get('autogen_model_warning_count', 0)}",
                f"- API key envs: {', '.join(f'`{item}`' for item in target_usage.get('target_api_key_envs', []) or []) or 'None'}",
                "",
                "| Target Model | Cases |",
                "|--------------|-------|",
            ]
        )
        by_model = target_usage.get("by_model", {}) or {}
        lines.extend([f"| {model} | {count} |" for model, count in sorted(by_model.items())])
        lines.extend(
            [
                "",
                "| Target Base URL | Cases |",
                "|-----------------|-------|",
            ]
        )
        by_base_url = target_usage.get("by_base_url", {}) or {}
        lines.extend([f"| `{base_url}` | {count} |" for base_url, count in sorted(by_base_url.items())])
    if narrative:
        lines.extend(
            [
                "",
                "## Agentic Analysis",
                _clean_report_text(narrative.get("agentic_workflow_summary", "")),
                "",
                _clean_report_text(narrative.get("effectiveness_analysis", "")),
                "",
                "False positive analysis: " + _clean_report_text(narrative.get("false_positive_analysis", "")),
            ]
        )
        next_steps = narrative.get("next_steps", []) or []
        if next_steps:
            lines.append("")
            lines.append("Agent-proposed next steps:")
            lines.extend([f"- {_clean_report_text(str(item))}" for item in next_steps])
    return lines


def _clean_report_text(value: object, limit: int = 1600) -> str:
    text = str(value or "")
    text = "".join(ch if not unicodedata.category(ch).startswith("C") or ch in "\n\t" else " " for ch in text)
    text = re.sub(r"[^\x00-\x7F\u4e00-\u9FFF，。！？；：（）《》、—…·“”‘’]+", "", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text
