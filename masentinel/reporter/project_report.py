from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from masentinel.agents.agent_trace import AgentTraceLogger
from masentinel.agents.roles import ProjectReportAgent
from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups
from masentinel.model.model_client import ModelClient
from masentinel.utils import ensure_dir, read_json, write_json, write_text


def write_project_report(
    output_dir: str | Path,
    results: list[dict[str, Any]] | None = None,
    model_config: dict[str, Any] | None = None,
    test_model: str | None = None,
) -> Path:
    output_dir = ensure_dir(output_dir)
    evidence = collect_project_evidence(output_dir, results or [])
    trace_logger = AgentTraceLogger(output_dir / "project_report_agent")
    model_client = _model_client(model_config or {}, test_model)
    decision = ProjectReportAgent(model_client, trace_logger, model_client.model).run(
        {
            "report_requirements": [
                "算法代码与说明文档",
                "方案设计",
                "测试覆盖率指标设计",
                "三个多智能体系统上的测试覆盖率与故障报告",
                "检测到的真实故障与误报",
                "效果分析与下一步改进计划",
            ],
            "evidence": evidence,
        }
    )
    agent_output = decision.output
    write_json(output_dir / "project_report.agent.json", agent_output)
    write_system_fault_reports(output_dir, evidence, agent_output)
    report_path = output_dir / "项目报告.md"
    write_text(report_path, render_project_report(evidence, agent_output))
    return report_path


def collect_project_evidence(output_dir: str | Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    output_dir = Path(output_dir)
    systems = []
    result_by_id = {str(item.get("system_id")): item for item in results if isinstance(item, dict)}
    for system_dir in sorted(path for path in output_dir.iterdir() if path.is_dir() and not path.name.startswith(".")):
        system_id = system_dir.name
        if system_id == "project_report_agent":
            continue
        coverage = read_json(system_dir / "coverage.json", {}) or {}
        faults = annotate_fault_groups(read_json(system_dir / "faults.json", []) or [])
        false_positive_audit = read_json(system_dir / "false_positive_audit.json", []) or []
        non_target_issues = read_json(system_dir / "non_target_issues.json", []) or []
        harness_issues = read_json(system_dir / "test_harness_issues.json", []) or []
        run_summary = read_json(system_dir / "runs" / "run_summary.json", []) or []
        agentic_summary = read_json(system_dir / "agentic_summary.json", {}) or {}
        model_usage = read_json(system_dir / "model_usage.json", {}) or {}
        rule_results = read_json(system_dir / "rule_results.json", []) or []
        manifest = read_json(system_dir / "run_manifest.json", {}) or {}
        true_faults = [fault for fault in faults if not fault.get("suspected_false_positive", False)]
        primary_true_faults = [fault for fault in true_faults if fault.get("is_primary_fault", True)]
        derived_symptoms = [fault for fault in faults if fault.get("cascades_from")]
        suspected_false_positives = [fault for fault in faults if fault.get("suspected_false_positive", False)]
        systems.append(
            {
                "system_id": system_id,
                "summary": _result_summary(result_by_id.get(system_id, {}), run_summary, rule_results),
                "coverage": _coverage_summary(coverage),
                "fault_counts": {
                    "total": len(faults),
                    "confirmed": len(true_faults),
                    "confirmed_primary_root_causes": len(primary_true_faults),
                    "derived_symptoms": len(derived_symptoms),
                    "suspected_false_positive": len(suspected_false_positives),
                    "root_groups": len(build_fault_groups(faults)),
                    "non_target_excluded": len(non_target_issues),
                    "harness_excluded": len(harness_issues),
                },
                "true_faults": [_fault_brief(fault) for fault in primary_true_faults[:12]],
                "derived_faults": [_fault_brief(fault) for fault in derived_symptoms[:20]],
                "suspected_false_positives": [_fault_brief(fault) for fault in suspected_false_positives[:12]],
                "non_target_issues": [_issue_brief(issue) for issue in non_target_issues[:20]],
                "false_positive_audit": false_positive_audit[:12],
                "model_usage": {
                    "total_calls": model_usage.get("total_calls", 0),
                    "successful_calls": model_usage.get("successful_calls", 0),
                    "fallback_calls": model_usage.get("fallback_calls", 0),
                    "by_agent": model_usage.get("by_agent", {}),
                    "by_model": model_usage.get("by_model", {}),
                },
                "target_model_usage": agentic_summary.get("target_model_usage", {}),
                "human_intervention_allowed": agentic_summary.get("human_intervention_allowed", manifest.get("no_human") is False),
                "testcases_frozen_sha256": agentic_summary.get("testcases_frozen_sha256", ""),
                "report_artifacts": {
                    "report_md": str(system_dir / "report.md"),
                    "report_html": str(system_dir / "report.html"),
                    "fault_report_md": str(system_dir / "故障报告.md"),
                    "dashboard_html": str(system_dir / "dashboard.html"),
                    "faults_json": str(system_dir / "faults.json"),
                    "coverage_json": str(system_dir / "coverage.json"),
                },
            }
        )
    return {
        "project": "MASentinel",
        "output_dir": str(output_dir),
        "summary_md": str(output_dir / "summary.md"),
        "index_html": str(output_dir / "index.html"),
        "code_and_docs": _code_and_doc_inventory(),
        "systems": systems,
    }


def render_project_report(evidence: dict[str, Any], agent_output: dict[str, Any]) -> str:
    systems = evidence.get("systems", []) or []
    analysis_by_system = {
        str(item.get("system_id")): item
        for item in agent_output.get("system_analyses", []) or []
        if isinstance(item, dict)
    }
    lines = [
        "# MASentinel 项目报告",
        "",
        f"> 本报告由 MASentinel `ProjectReportAgent` 基于 `{evidence.get('output_dir', 'outputs')}/` 中的确定性运行产物自动生成；覆盖率、故障数量和误报数量均来自程序输出。",
        "",
        "## 算法代码与说明文档",
    ]
    for item in evidence.get("code_and_docs", []) or []:
        lines.append(f"- `{item['path']}`：{item['description']}")
    lines.extend(
        [
            "",
            "## 方案设计",
            _clean(agent_output.get("scheme_design"))
            or "MASentinel 采用静态分析、测试生成、无人值守执行、规则 oracle、故障诊断、误报审计和报告生成的闭环方案。",
            "",
            "核心流程：",
            "- `RequirementAnalystAgent` 抽取可验证需求。",
            "- `SystemModelingAgent` 复核 agent、tool 与 message edge 语义图。",
            "- `TestDesignerAgent` 分批生成补充测试，确定性生成器补齐覆盖类型。",
            "- `InteractionAdapterAgent` 为交互式目标系统规划无人值守输入适配。",
            "- `ExecutionMonitorAgent`、`FaultDiagnoserAgent`、`FalsePositiveAuditorAgent` 完成异常归纳、故障定位与误报审计。",
            "- `ProjectReportAgent` 汇总三套系统的最终提交报告。",
            "",
            "## 测试覆盖率指标设计",
            _clean(agent_output.get("coverage_metric_design"))
            or "MASCov 综合 AgentCov、ToolCov、EdgeCov、ReqCov、StateCov 和 FaultCov，用于衡量多智能体系统的语义覆盖情况。",
            "",
            "| 指标 | 含义 |",
            "|------|------|",
            "| AgentCov | 测试 trace 覆盖到的目标 agent 比例 |",
            "| ToolCov | 触发或观测到的工具调用覆盖比例 |",
            "| EdgeCov | agent 间消息边覆盖比例 |",
            "| ReqCov | 需求点被测试用例绑定并执行的比例 |",
            "| ReqVerifiedCov | 需求至少被一个无目标故障、无非目标阻塞的用例有效验证的比例 |",
            "| ContractCov | 通用契约测试模式（artifact/filesystem/tool/handoff/CLI 等）的覆盖比例 |",
            "| EffectiveWorkflowRate | 非阻塞用例中真正进入 agent/tool/message 工作流的比例 |",
            "| TraceCompleteness | 当前 trace 是否包含支撑 missing 类故障判断的关键观测类型 |",
            "| RootCauseEvidenceRate | 确认故障中具备代码证据或强 trace 证据的比例 |",
            "| StateCov | 正常、异常、超时、终止等执行状态覆盖 |",
            "| FaultCov | 已覆盖的故障模式类型比例 |",
            "| MASCov | 上述指标的综合语义覆盖分数 |",
            "",
            "## 三个多智能体系统测试覆盖率与结果汇总",
            "",
            "| 系统 | Cases | 进程通过 | 进程失败 | Oracle 通过 | Oracle 失败 | AgentCov | ToolCov | EdgeCov | ReqIntent | ReqVerified | ContractCov | EffWorkflow | TraceComplete | EvidenceRate | MASCov | 确认主根因 | 派生症状 | 疑似误报 | 非目标排除 |",
            "|------|-------|----------|----------|-------------|-------------|----------|---------|---------|-----------|-------------|-------------|-------------|---------------|--------------|--------|------------|----------|----------|------------|",
        ]
    )
    for system in systems:
        summary = system.get("summary", {})
        coverage = system.get("coverage", {})
        counts = system.get("fault_counts", {})
        lines.append(
            f"| {system['system_id']} | {summary.get('cases', 0)} | {summary.get('process_passed', 0)} | {summary.get('process_failed', 0)} | "
            f"{summary.get('oracle_passed', 0)} | {summary.get('oracle_failed', 0)} | "
            f"{_format_metric(coverage.get('agent_coverage'))} | {_format_metric(coverage.get('tool_coverage'))} | {_format_metric(coverage.get('message_edge_coverage'))} | "
            f"{_format_metric(coverage.get('req_intent_coverage', coverage.get('requirement_coverage')))} | {_format_metric(coverage.get('req_verified_coverage'))} | "
            f"{_format_metric(coverage.get('contract_coverage'))} | {_format_metric(coverage.get('effective_workflow_rate'))} | "
            f"{_format_metric(coverage.get('trace_completeness'))} | {_format_metric(coverage.get('root_cause_evidence_rate'))} | "
            f"{_format_metric(coverage.get('mascov'))} | {counts.get('confirmed_primary_root_causes', counts.get('confirmed', 0))} | "
            f"{counts.get('derived_symptoms', 0)} | {counts.get('suspected_false_positive', 0)} | "
            f"{counts.get('non_target_excluded', 0)} |"
        )
    lines.append("")
    lines.append("## 故障报告")
    lines.append("")
    lines.append("故障报告按被测系统分别生成，每个系统一份；本节汇总三份报告的关键数字和路径。")
    lines.append("")
    lines.append("| 被测系统 | 故障报告 | 确认主根因 | 派生症状 | 疑似误报 | 非目标排除 |")
    lines.append("|----------|----------|------------|----------|----------|------------|")
    for system in systems:
        counts = system.get("fault_counts", {})
        artifacts = system.get("report_artifacts", {})
        lines.append(
            f"| {system.get('system_id', '')} | `{artifacts.get('fault_report_md', '')}` | "
            f"{counts.get('confirmed_primary_root_causes', counts.get('confirmed', 0))} | "
            f"{counts.get('derived_symptoms', 0)} | {counts.get('suspected_false_positive', 0)} | "
            f"{counts.get('non_target_excluded', 0)} |"
        )
    for system in systems:
        analysis = analysis_by_system.get(system["system_id"], {})
        counts = system.get("fault_counts", {})
        lines.extend(
            [
                "",
                f"### {system['system_id']}",
                f"- 故障总数：{counts.get('total', 0)}",
                f"- 确认主根因：{counts.get('confirmed_primary_root_causes', counts.get('confirmed', 0))}",
                f"- 派生症状：{counts.get('derived_symptoms', 0)}",
                f"- 疑似误报：{counts.get('suspected_false_positive', 0)}",
                f"- 根因组：{counts.get('root_groups', 0)}",
                f"- 非目标问题排除：{counts.get('non_target_excluded', 0)}",
                f"- 其中测试框架/软预算问题：{counts.get('harness_excluded', 0)}",
                f"- 覆盖率解读：{_clean(analysis.get('coverage_interpretation'))}",
                f"- 故障概要：{_clean(analysis.get('fault_report_summary'))}",
            ]
        )
        _append_fault_table(lines, "真实故障", system.get("true_faults", []))
        _append_fault_table(lines, "疑似误报", system.get("suspected_false_positives", []))
    lines.extend(
        [
            "",
            "## 效果分析",
            _clean(agent_output.get("effectiveness_analysis"))
            or "从当前运行结果看，MASentinel 已能自动完成三套系统的分析、生成、执行、诊断、审计和报告汇总，并显式区分目标故障、疑似误报与非目标问题。",
            "",
            "## 下一步改进计划",
        ]
    )
    next_steps = agent_output.get("next_steps", []) if isinstance(agent_output, dict) else []
    if next_steps:
        lines.extend([f"- {_clean(item)}" for item in next_steps])
    else:
        lines.extend(
            [
                "- 继续增强 AutoGen send/receive/tool_call 级 trace 采集。",
                "- 针对长耗时系统优化分批执行、超时预算和报告上下文压缩。",
                "- 扩展回归池，让已确认故障在后续运行中自动复测。",
            ]
        )
    lines.extend(
        [
            "",
            "## 产物索引",
            f"- 总览 Markdown：`{evidence.get('summary_md', '')}`",
            f"- 总览 HTML：`{evidence.get('index_html', '')}`",
        ]
    )
    for system in systems:
        artifacts = system.get("report_artifacts", {})
        lines.append(
            f"- `{system['system_id']}`：`{artifacts.get('fault_report_md', '')}` / "
            f"`{artifacts.get('report_html', '')}` / `{artifacts.get('faults_json', '')}` / `{artifacts.get('coverage_json', '')}`"
        )
    return "\n".join(lines) + "\n"


def write_system_fault_reports(output_dir: Path, evidence: dict[str, Any], agent_output: dict[str, Any]) -> None:
    analysis_by_system = {
        str(item.get("system_id")): item
        for item in agent_output.get("system_analyses", []) or []
        if isinstance(item, dict)
    }
    for system in evidence.get("systems", []) or []:
        artifacts = system.get("report_artifacts", {}) if isinstance(system, dict) else {}
        path = Path(artifacts.get("fault_report_md") or "")
        if not path:
            continue
        if not path.is_absolute():
            path = output_dir.parent / path if str(path).startswith(str(output_dir.name) + "/") else path
        write_text(path, render_system_fault_report(system, analysis_by_system.get(str(system.get("system_id", "")), {})))


def render_system_fault_report(system: dict[str, Any], analysis: dict[str, Any] | None = None) -> str:
    analysis = analysis or {}
    system_id = str(system.get("system_id", ""))
    counts = system.get("fault_counts", {})
    coverage = system.get("coverage", {})
    summary = system.get("summary", {})
    lines = [
        f"# MASentinel 故障报告：{system_id}",
        "",
        "> 本报告由 MASentinel 自动化测试系统基于该被测系统的 `coverage.json`、`faults.json`、`false_positive_audit.json`、`non_target_issues.json` 和运行 trace 自动生成。",
        "",
        "## 测试结果概览",
        "",
        "| Cases | 进程通过 | 进程失败 | Oracle 通过 | Oracle 失败 | 确认主根因 | 派生症状 | 疑似误报 | 非目标排除 |",
        "|-------|----------|----------|-------------|-------------|------------|----------|----------|------------|",
        f"| {summary.get('cases', 0)} | {summary.get('process_passed', 0)} | {summary.get('process_failed', 0)} | "
        f"{summary.get('oracle_passed', 0)} | {summary.get('oracle_failed', 0)} | "
        f"{counts.get('confirmed_primary_root_causes', counts.get('confirmed', 0))} | {counts.get('derived_symptoms', 0)} | "
        f"{counts.get('suspected_false_positive', 0)} | {counts.get('non_target_excluded', 0)} |",
        "",
        "## 覆盖率",
        "",
        "| AgentCov | ToolCov | EdgeCov | ReqIntent | ReqVerified | ContractCov | EffWorkflow | TraceComplete | EvidenceRate | StateCov | FaultCov | MASCov |",
        "|----------|---------|---------|-----------|-------------|-------------|-------------|---------------|--------------|----------|----------|--------|",
        f"| {_format_metric(coverage.get('agent_coverage'))} | {_format_metric(coverage.get('tool_coverage'))} | "
        f"{_format_metric(coverage.get('message_edge_coverage'))} | {_format_metric(coverage.get('req_intent_coverage', coverage.get('requirement_coverage')))} | "
        f"{_format_metric(coverage.get('req_verified_coverage'))} | {_format_metric(coverage.get('contract_coverage'))} | "
        f"{_format_metric(coverage.get('effective_workflow_rate'))} | {_format_metric(coverage.get('trace_completeness'))} | "
        f"{_format_metric(coverage.get('root_cause_evidence_rate'))} | {_format_metric(coverage.get('state_coverage'))} | {_format_metric(coverage.get('fault_mode_coverage'))} | "
        f"{_format_metric(coverage.get('mascov'))} |",
        "",
        f"- 覆盖率解读：{_clean(analysis.get('coverage_interpretation'))}",
        f"- 故障概要：{_clean(analysis.get('fault_report_summary'))}",
        f"- 测试框架/软预算类排除：{counts.get('harness_excluded', 0)}",
    ]
    _append_fault_table(lines, "真实故障 / 确认主根因", system.get("true_faults", []))
    _append_fault_table(lines, "疑似误报", system.get("suspected_false_positives", []))
    _append_fault_table(lines, "派生症状", system.get("derived_faults", []))
    _append_issue_table(lines, "非目标排除", system.get("non_target_issues", []))
    lines.extend(
        [
            "",
            "## 判定口径",
            "- 真实故障：未被误报审计标记为 suspected false positive，且属于 application 或 autogen_framework 层的主根因。",
            "- 派生症状：由同一主根因级联产生的附带失败，不重复计为新的主根因。",
            "- 疑似误报：FalsePositiveAuditorAgent 或确定性规则标记为 suspected_false_positive 的目标层发现。",
            "- 非目标排除：模型/API provider 超时、鉴权、测试框架软预算、未观测到有效工作流等，不计入目标系统真实故障。",
        ]
    )
    return "\n".join(lines) + "\n"


def _model_client(model_config: dict[str, Any], test_model: str | None) -> ModelClient:
    return ModelClient(
        base_url=os.getenv("MAS_TESTING_OPENAI_BASE_URL") or model_config.get("testing_openai_base_url") or model_config.get("openai_base_url"),
        api_key_env=os.getenv("MAS_TESTING_API_KEY_ENV") or model_config.get("testing_api_key_env") or model_config.get("openai_api_key_env"),
        model=test_model or os.getenv("MAS_TESTING_MODEL") or model_config.get("testing_model") or model_config.get("default_model") or "ds-v4-pro",
        timeout=int(os.getenv("MAS_TESTING_TIMEOUT_SECONDS") or model_config.get("testing_timeout_seconds", 90) or 90),
        retries=int(os.getenv("MAS_TESTING_RETRIES") or model_config.get("testing_retries", 1) or 1),
        extra_body=os.getenv("MAS_TESTING_EXTRA_BODY_JSON") or model_config.get("testing_extra_body_json") or model_config.get("testing_extra_body") or model_config.get("extra_body"),
    )


def _result_summary(result: dict[str, Any], run_summary: list[Any], rule_results: list[Any]) -> dict[str, int]:
    process_passed = int(result.get("process_passed", result.get("passed", 0)) or 0)
    process_failed = int(result.get("process_failed", result.get("failed", 0)) or 0)
    if not result and run_summary:
        process_passed = len([item for item in run_summary if isinstance(item, dict) and item.get("status") == "passed"])
        process_failed = len(run_summary) - process_passed
    oracle_passed = int(result.get("oracle_passed", 0) or 0)
    oracle_failed = int(result.get("oracle_failed", 0) or 0)
    if rule_results:
        oracle_passed = len([item for item in rule_results if isinstance(item, dict) and item.get("passed")])
        oracle_failed = len(rule_results) - oracle_passed
    return {
        "cases": int(result.get("cases", len(run_summary) or len(rule_results)) or 0),
        "process_passed": process_passed,
        "process_failed": process_failed,
        "oracle_passed": oracle_passed,
        "oracle_failed": oracle_failed,
    }


def _coverage_summary(coverage: dict[str, Any]) -> dict[str, float | None]:
    keys = [
        "agent_coverage",
        "tool_coverage",
        "message_edge_coverage",
        "requirement_coverage",
        "req_intent_coverage",
        "req_verified_coverage",
        "state_coverage",
        "fault_mode_coverage",
        "contract_coverage",
        "effective_workflow_rate",
        "trace_completeness",
        "root_cause_evidence_rate",
        "mascov",
    ]
    summary: dict[str, float | None] = {}
    for key in keys:
        value = coverage.get(key)
        summary[key] = None if value is None else float(value or 0.0)
    return summary


def _fault_brief(fault: dict[str, Any]) -> dict[str, Any]:
    return {
        "fault_id": fault.get("fault_id", ""),
        "case_id": fault.get("case_id", ""),
        "layer": fault.get("layer", ""),
        "fault_type": fault.get("fault_type", ""),
        "severity": fault.get("severity", ""),
        "confidence": fault.get("confidence", ""),
        "evidence_strength": fault.get("evidence_strength", ""),
        "root_cause_confidence": fault.get("root_cause_confidence", ""),
        "not_model_fault_because": _clean(fault.get("not_model_fault_because", ""), limit=220),
        "code_locations": fault.get("code_locations", [])[:5] if isinstance(fault.get("code_locations"), list) else [],
        "summary": _clean(fault.get("summary", ""), limit=220),
        "root_cause": _clean(fault.get("root_cause", ""), limit=260),
        "suggested_fix": _clean(fault.get("suggested_fix", ""), limit=260),
        "root_cause_group_id": fault.get("root_cause_group_id", ""),
    }


def _issue_brief(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": issue.get("case_id", ""),
        "code": issue.get("code", ""),
        "layer": issue.get("layer", ""),
        "issue_type": issue.get("issue_type", ""),
        "message": _clean(issue.get("message", ""), limit=220),
        "suggested_fix": _clean(issue.get("suggested_fix", ""), limit=260),
    }


def _append_fault_table(lines: list[str], title: str, faults: list[dict[str, Any]]) -> None:
    lines.append("")
    lines.append(f"#### {title}")
    if not faults:
        lines.append("- 无")
        return
    lines.extend(
        [
            "| Fault ID | Case | Layer | Type | Severity | Confidence | EvidenceStrength | RootCauseConfidence | Summary | Suggested Fix |",
            "|----------|------|-------|------|----------|------------|------------------|---------------------|---------|---------------|",
        ]
    )
    for fault in faults:
        lines.append(
            f"| `{fault.get('fault_id', '')}` | `{fault.get('case_id', '')}` | {fault.get('layer', '')} | "
            f"{fault.get('fault_type', '')} | {fault.get('severity', '')} | {fault.get('confidence', '')} | "
            f"{fault.get('evidence_strength', '')} | {fault.get('root_cause_confidence', '')} | "
            f"{_clean(fault.get('summary', ''), limit=160)} | {_clean(fault.get('suggested_fix', ''), limit=180)} |"
        )


def _append_issue_table(lines: list[str], title: str, issues: list[dict[str, Any]]) -> None:
    lines.append("")
    lines.append(f"#### {title}")
    if not issues:
        lines.append("- 无")
        return
    lines.extend(
        [
            "| Case | Code | Layer | Type | Message | Suggested Fix |",
            "|------|------|-------|------|---------|---------------|",
        ]
    )
    for issue in issues:
        lines.append(
            f"| `{issue.get('case_id', '')}` | `{issue.get('code', '')}` | {issue.get('layer', '')} | "
            f"{issue.get('issue_type', '')} | {_clean(issue.get('message', ''), limit=160)} | "
            f"{_clean(issue.get('suggested_fix', ''), limit=180)} |"
        )


def _format_metric(value: object) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _code_and_doc_inventory() -> list[dict[str, str]]:
    return [
        {"path": "masentinel/agents/orchestrator.py", "description": "多智能体自动化测试编排主流程。"},
        {"path": "masentinel/analyzer/profile_builder.py", "description": "代码、文档、agent、tool 与消息边静态画像构建。"},
        {"path": "masentinel/generator/testcase_generator.py", "description": "确定性测试用例生成与覆盖类型补齐。"},
        {"path": "masentinel/agents/validators.py", "description": "agent 生成测试用例的结构化校验与容错转换。"},
        {"path": "masentinel/runner/case_runner.py", "description": "无人值守子进程执行、交互适配与 trace 采集。"},
        {"path": "masentinel/oracle/rule_oracle.py", "description": "终止、崩溃、agent、tool、消息边与输出契约 oracle。"},
        {"path": "masentinel/metrics/coverage.py", "description": "MASCov 多智能体语义覆盖率计算。"},
        {"path": "masentinel/diagnosis/fault_classifier.py", "description": "应用层与 AutoGen 框架层故障分类，并排除非目标问题。"},
        {"path": "masentinel/reporter/project_report.py", "description": "赛题要求项目报告的 agent 化汇总生成。"},
        {"path": "scripts/rebuild_reports_from_outputs.py", "description": "基于已保存 trace 离线重算 oracle、coverage、faults 和汇总报告。"},
        {"path": "README.md", "description": "运行方法、API 配置和产物说明。"},
        {"path": "项目技术路线与方案汇报.md", "description": "技术路线和方案说明文档。"},
    ]


def _clean(value: object, limit: int = 1200) -> str:
    text = str(value or "")
    text = "".join(ch if not unicodedata.category(ch).startswith("C") or ch in "\n\t" else " " for ch in text)
    text = re.sub(r"[^\x00-\x7F\u4e00-\u9FFF，。！？；：（）《》、—…·“”‘’]+", "", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text
