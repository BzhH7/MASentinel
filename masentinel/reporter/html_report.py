from __future__ import annotations

import html
from pathlib import Path

from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups
from masentinel.reporter.markdown_report import _clean_report_text
from masentinel.schema import RunTrace, SystemProfile, TestCase
from masentinel.utils import ensure_dir, write_text


STYLE = """
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:0;color:#17202a;background:#f7f8fa}
main{max-width:1120px;margin:0 auto;padding:28px}
h1,h2{letter-spacing:0;margin:0 0 12px}
section{background:#fff;border:1px solid #dde2e8;border-radius:8px;padding:18px;margin:16px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.card{border:1px solid #dde2e8;border-radius:8px;padding:14px;background:#fbfcfd}
.num{font-size:24px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border-bottom:1px solid #e6eaf0;padding:8px;text-align:left;vertical-align:top}
.bad{color:#9b1c1c}.ok{color:#136f3a}.muted{color:#607080}
code{background:#eef2f6;padding:2px 4px;border-radius:4px}
"""


def write_html_report(
    profile: SystemProfile,
    testcases: list[TestCase],
    traces: list[RunTrace],
    faults: list[dict],
    coverage: dict,
    out_dir: str | Path,
    agentic_info: dict | None = None,
) -> None:
    out_dir = ensure_dir(out_dir)
    write_text(out_dir / "report.html", build_html_report(profile, testcases, traces, faults, coverage, agentic_info=agentic_info))


def build_html_report(
    profile: SystemProfile,
    testcases: list[TestCase],
    traces: list[RunTrace],
    faults: list[dict],
    coverage: dict,
    agentic_info: dict | None = None,
) -> str:
    faults = annotate_fault_groups(faults)
    trace_rows = []
    for trace in traces:
        cls = "ok" if trace.status == "passed" else "bad"
        trace_rows.append(
            f"<tr><td><code>{html.escape(trace.case_id)}</code></td><td class='{cls}'>{html.escape(trace.status)}</td><td>{trace.turn_count}</td><td><a href='runs/traces/{html.escape(trace.case_id)}.json'>trace</a></td></tr>"
        )
    fault_rows = []
    for fault in faults:
        marker = "primary" if fault.get("is_primary_fault", True) else "derived"
        fault_rows.append(
            f"<tr><td><code>{html.escape(fault['fault_id'])}</code></td><td><code>{html.escape(fault['case_id'])}</code></td>"
            f"<td><code>{html.escape(str(fault.get('root_cause_group_id', '')))}</code></td>"
            f"<td>{html.escape(marker)}</td><td>{html.escape(fault['layer'])}</td><td>{html.escape(fault['fault_type'])}</td>"
            f"<td>{html.escape(_clean_report_text(fault['summary']))}</td></tr>"
        )
    group_rows = []
    for group in build_fault_groups(faults):
        group_rows.append(
            f"<tr><td><code>{html.escape(str(group['group_id']))}</code></td><td>{html.escape(str(group['title']))}</td>"
            f"<td><code>{html.escape(str(group['primary_fault_id']))}</code></td><td>{len(group['affected_cases'])}</td>"
            f"<td>{len(group['symptom_fault_ids'])}</td><td>{html.escape(', '.join(group['failure_codes']))}</td></tr>"
        )
    metrics = [
        ("Agent", coverage.get("agent_coverage", 0)),
        ("Tool", coverage.get("tool_coverage", 0)),
        ("Edge", coverage.get("message_edge_coverage", 0)),
        ("Req Intent", coverage.get("req_intent_coverage", coverage.get("requirement_coverage", 0))),
        ("Req Verified", coverage.get("req_verified_coverage", 0)),
        ("Contract", coverage.get("contract_coverage", None)),
        ("State", coverage.get("state_coverage", 0)),
        ("Fault Mode", coverage.get("fault_mode_coverage", 0)),
        ("Effective Workflow", coverage.get("effective_workflow_rate", 0)),
        ("Trace Completeness", coverage.get("trace_completeness", 0)),
        ("Evidence Rate", coverage.get("root_cause_evidence_rate", None)),
        ("MASCov", coverage.get("mascov", 0)),
    ]
    metric_cards = "".join([f"<div class='card'><div class='muted'>{name}</div><div class='num'>{_format_metric(value)}</div></div>" for name, value in metrics])
    agentic_section = _agentic_html(agentic_info)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>MASentinel {html.escape(profile.system_id)}</title><style>{STYLE}</style></head>
<body><main>
<h1>MASentinel Report: {html.escape(profile.system_id)}</h1>
<section><div class="grid">{metric_cards}</div></section>
<section><h2>System</h2><p>Agents: {len(profile.agents)} · Tools: {len(profile.tools)} · Requirements: {len(profile.requirements)} · Cases: {len(testcases)} · Faults: {len(faults)} · Root-cause groups: {len(group_rows)}</p></section>
{agentic_section}
<section><h2>Case Runs</h2><table><tr><th>Case</th><th>Status</th><th>Turns</th><th>Trace</th></tr>{''.join(trace_rows)}</table></section>
<section><h2>Root-Cause Groups</h2><table><tr><th>Group</th><th>Title</th><th>Primary Fault</th><th>Cases</th><th>Derived Symptoms</th><th>Codes</th></tr>{''.join(group_rows) or '<tr><td colspan="6">No faults detected.</td></tr>'}</table></section>
<section><h2>Faults</h2><table><tr><th>Fault</th><th>Case</th><th>Group</th><th>Class</th><th>Layer</th><th>Type</th><th>Summary</th></tr>{''.join(fault_rows) or '<tr><td colspan="7">No faults detected.</td></tr>'}</table></section>
</main></body></html>"""


def _agentic_html(agentic_info: dict | None) -> str:
    if not agentic_info:
        return ""
    usage = agentic_info.get("model_usage", {}) or {}
    target_usage = agentic_info.get("target_model_usage", {}) or {}
    agents = "".join([f"<li><code>{html.escape(str(agent))}</code></li>" for agent in agentic_info.get("workflow_agents", []) or []])
    by_agent = usage.get("by_agent", {}) or {}
    rows = "".join([f"<tr><td>{html.escape(str(agent))}</td><td>{count}</td></tr>" for agent, count in sorted(by_agent.items())])
    target_model_rows = "".join(
        [
            f"<tr><td><code>{html.escape(str(model))}</code></td><td>{count}</td></tr>"
            for model, count in sorted((target_usage.get("by_model", {}) or {}).items())
        ]
    )
    target_url_rows = "".join(
        [
            f"<tr><td><code>{html.escape(str(base_url))}</code></td><td>{count}</td></tr>"
            for base_url, count in sorted((target_usage.get("by_base_url", {}) or {}).items())
        ]
    )
    target_key_envs = ", ".join([f"<code>{html.escape(str(item))}</code>" for item in target_usage.get("target_api_key_envs", []) or []])
    non_target_issues = agentic_info.get("non_target_issues", []) or []
    harness_issues = agentic_info.get("test_harness_issues", []) or []
    narrative = agentic_info.get("report_narrative", {}) or {}
    interaction = agentic_info.get("interaction_adapter", {}) or {}
    interaction_rules = interaction.get("prompt_responses", []) if isinstance(interaction, dict) else []
    return f"""<section><h2>Agentic Testing Workflow</h2><ul>{agents}</ul>
<h2>Testing-Agent Model Usage</h2>
<p>Total calls: {usage.get('total_calls', 0)} · Successful: {usage.get('successful_calls', 0)} · Fallback: {usage.get('fallback_calls', 0)}</p>
<table><tr><th>Agent</th><th>Calls</th></tr>{rows}</table>
<h2>Target-System Model Usage</h2>
<p>Cases: {target_usage.get('cases', 0)} · AutoGen model-warning mentions: {target_usage.get('autogen_model_warning_count', 0)} · API key envs: {target_key_envs or 'None'}</p>
<table><tr><th>Target Model</th><th>Cases</th></tr>{target_model_rows or '<tr><td colspan="2">No target model metadata captured.</td></tr>'}</table>
<table><tr><th>Target Base URL</th><th>Cases</th></tr>{target_url_rows or '<tr><td colspan="2">No target base URL metadata captured.</td></tr>'}</table>
<p>Non-target issues excluded from target faults: {len(non_target_issues)}</p>
<p>Test harness issues excluded from target faults: {len(harness_issues)}</p>
<p>Interaction adapter rules: {len(interaction_rules)}</p>
<p>{html.escape(_clean_report_text(narrative.get('agentic_workflow_summary', '')))}</p></section>"""


def write_global_index(results: list[dict], output_dir: str | Path) -> None:
    output_dir = ensure_dir(output_dir)
    rows = []
    for result in results:
        cov = result.get("coverage", {})
        rows.append(
            "<tr>"
            f"<td><a href='{html.escape(result['system_id'])}/report.html'>{html.escape(result['system_id'])}</a></td>"
            f"<td>{result.get('cases', 0)}</td>"
            f"<td>{result.get('process_passed', result.get('passed', 0))}</td>"
            f"<td>{result.get('process_failed', result.get('failed', 0))}</td>"
            f"<td>{result.get('oracle_passed', '')}</td>"
            f"<td>{result.get('oracle_failed', '')}</td>"
            f"<td>{_format_metric(cov.get('mascov'))}</td>"
            f"<td>{_format_metric(cov.get('contract_coverage'))}</td>"
            f"<td>{_format_metric(cov.get('effective_workflow_rate'))}</td>"
            f"<td>{_format_metric(cov.get('trace_completeness'))}</td>"
            f"<td>{_format_metric(cov.get('root_cause_evidence_rate'))}</td>"
            f"<td>{result.get('confirmed_primary_root_causes', result.get('faults', 0))}</td>"
            f"<td>{result.get('derived_symptoms', '')}</td>"
            f"<td>{result.get('fault_groups', '')}</td>"
            f"<td>{len(((result.get('agentic', {}) or {}).get('non_target_issues', []) or []))}</td>"
            f"<td>{len(((result.get('agentic', {}) or {}).get('test_harness_issues', []) or []))}</td>"
            "</tr>"
        )
    content = f"""<!doctype html><html><head><meta charset="utf-8"><title>MASentinel Summary</title><style>{STYLE}</style></head>
<body><main><h1>MASentinel Summary</h1><section><table><tr><th>System</th><th>Cases</th><th>Proc Passed</th><th>Proc Failed</th><th>Oracle Passed</th><th>Oracle Failed</th><th>MASCov</th><th>ContractCov</th><th>Eff Workflow</th><th>Trace Complete</th><th>EvidenceRate</th><th>Primary Root Causes</th><th>Derived Symptoms</th><th>Root Groups</th><th>Non-target Excluded</th><th>Harness Excluded</th></tr>{''.join(rows)}</table></section></main></body></html>"""
    write_text(output_dir / "index.html", content)


def _format_metric(value: object) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"
