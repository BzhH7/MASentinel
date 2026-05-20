from __future__ import annotations

from typing import Any

from masentinel.agents.base import BaseTestingAgent
from masentinel.agents import prompts


class RequirementAnalystAgent(BaseTestingAgent):
    name = "RequirementAnalystAgent"
    role = "requirement_analysis"
    purpose = "extract_requirements"

    def prompt(self) -> str:
        return prompts.REQUIREMENT_ANALYST_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        profile = task.get("static_profile", {}) or {}
        return {
            "requirements": profile.get("requirements", []),
            "confidence": 0.35,
            "fallback": True,
            "error": error,
        }


class SystemModelingAgent(BaseTestingAgent):
    name = "SystemModelingAgent"
    role = "system_modeling"
    purpose = "review_semantic_graph"

    def prompt(self) -> str:
        return prompts.SYSTEM_MODELING_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        return {
            "semantic_graph_review": "Fallback: static semantic graph accepted without LLM revision.",
            "suspected_risk_points": [],
            "additional_edges": [],
            "confidence": 0.35,
            "fallback": True,
            "error": error,
        }


class TestDesignerAgent(BaseTestingAgent):
    name = "TestDesignerAgent"
    role = "test_design"
    purpose = "generate_testcases"

    def prompt(self) -> str:
        return prompts.TEST_DESIGNER_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        return {"testcases": [], "confidence": 0.3, "fallback": True, "error": error}


class PatternApplicabilityAgent(BaseTestingAgent):
    name = "PatternApplicabilityAgent"
    role = "test_planning"
    purpose = "select_applicable_test_patterns"

    def prompt(self) -> str:
        return prompts.PATTERN_APPLICABILITY_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        from masentinel.generator.pattern_selector import build_test_plan

        features = task.get("system_features", {}) if isinstance(task, dict) else {}
        plan = build_test_plan(features if isinstance(features, dict) else {})
        plan.update({"fallback": True, "error": error})
        return plan


class CoverageStrategistAgent(BaseTestingAgent):
    name = "CoverageStrategistAgent"
    role = "coverage_strategy"
    purpose = "analyze_coverage_gaps"

    def prompt(self) -> str:
        return prompts.COVERAGE_STRATEGIST_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        coverage = task.get("coverage", {}) or {}
        gaps = []
        thresholds = [
            ("agent_coverage", "missing_agent_coverage"),
            ("tool_coverage", "missing_tool_coverage"),
            ("message_edge_coverage", "missing_edge_coverage"),
            ("state_coverage", "missing_state_coverage"),
            ("fault_mode_coverage", "missing_fault_mode_coverage"),
        ]
        for key, gap_type in thresholds:
            value = coverage.get(key, 1.0)
            if value is None:
                continue
            if float(value or 0.0) < 0.8:
                gaps.append({"gap_type": gap_type, "target": key, "suggested_test_intent": f"Generate additional cases to improve {key}."})
        return {"coverage_gaps": gaps, "new_test_requests": [], "confidence": 0.35, "fallback": True, "error": error}


class InteractionAdapterAgent(BaseTestingAgent):
    name = "InteractionAdapterAgent"
    role = "interaction_adaptation"
    purpose = "plan_interaction_adapter"

    def prompt(self) -> str:
        return prompts.INTERACTION_ADAPTER_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        run_cfg = task.get("run_config", {}) or {}
        interaction = run_cfg.get("interaction", {}) if isinstance(run_cfg, dict) else {}
        prompt_responses = interaction.get("prompt_responses", []) if isinstance(interaction, dict) else []
        return {
            "prompt_responses": prompt_responses,
            "isolated_paths": run_cfg.get("isolated_paths", []) if isinstance(run_cfg, dict) else [],
            "risk_notes": ["Fallback interaction plan uses deterministic run configuration only."],
            "confidence": 0.35,
            "fallback": True,
            "error": error,
        }


class ExecutionMonitorAgent(BaseTestingAgent):
    name = "ExecutionMonitorAgent"
    role = "execution_monitoring"
    purpose = "summarize_execution"

    def prompt(self) -> str:
        return prompts.EXECUTION_MONITOR_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        suspicious = []
        for result in task.get("rule_results", []) or []:
            failures = result.get("failures", [])
            if failures:
                suspicious.append(
                    {
                        "case_id": result.get("case_id"),
                        "reason": ", ".join(f.get("code", "") for f in failures),
                        "rule_failures": failures,
                        "trace_summary": "Fallback summary from rule oracle failures.",
                    }
                )
        return {"suspicious_cases": suspicious, "confidence": 0.35, "fallback": True, "error": error}


class FaultDiagnoserAgent(BaseTestingAgent):
    name = "FaultDiagnoserAgent"
    role = "fault_diagnosis"
    purpose = "diagnose_fault"

    def prompt(self) -> str:
        return prompts.FAULT_DIAGNOSER_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        fault = task.get("fault", {}) or {}
        return {
            "fault_confirmed": not fault.get("suspected_false_positive", False),
            "layer": fault.get("layer", "uncertain"),
            "fault_type": fault.get("fault_type", "Unknown"),
            "severity": fault.get("severity", "medium"),
            "confidence": fault.get("confidence", 0.35),
            "evidence": fault.get("evidence", []),
            "root_cause": fault.get("root_cause", "Fallback diagnosis from deterministic oracle."),
            "suggested_fix": fault.get("suggested_fix", "Inspect deterministic oracle evidence."),
            "fallback": True,
            "error": error,
        }


class FalsePositiveAuditorAgent(BaseTestingAgent):
    name = "FalsePositiveAuditorAgent"
    role = "false_positive_audit"
    purpose = "audit_false_positive"

    def prompt(self) -> str:
        return prompts.FALSE_POSITIVE_AUDITOR_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        fault = task.get("fault", {}) or {}
        suspected = bool(fault.get("suspected_false_positive", False))
        return {
            "audit_result": "likely_false_positive" if suspected else "confirmed_fault",
            "reason": "Fallback audit based on deterministic confidence threshold.",
            "false_positive_risk": "high" if suspected else "low",
            "confidence": 0.35,
            "fallback": True,
            "error": error,
        }


class ReportWriterAgent(BaseTestingAgent):
    name = "ReportWriterAgent"
    role = "report_writing"
    purpose = "write_report_narrative"

    def prompt(self) -> str:
        return prompts.REPORT_WRITER_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        return {
            "agentic_workflow_summary": "MASentinel used testing agents with deterministic tool fallbacks to complete requirement analysis, test design, execution monitoring, diagnosis, audit, and reporting.",
            "effectiveness_analysis": "Coverage and fault counts are computed by deterministic metrics and oracle modules.",
            "false_positive_analysis": "Potential GroupChat-only missing-edge findings are marked as suspected false positives when confidence is low.",
            "next_steps": ["Enable DeepSeek V4 pro credentials for full semantic agent reasoning.", "Add target-system instrumentation for richer AutoGen traces."],
            "confidence": 0.35,
            "fallback": True,
            "error": error,
        }


class ProjectReportAgent(BaseTestingAgent):
    name = "ProjectReportAgent"
    role = "project_reporting"
    purpose = "write_competition_project_report"

    def prompt(self) -> str:
        return prompts.PROJECT_REPORT_PROMPT

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        evidence = task.get("evidence", {}) if isinstance(task, dict) else {}
        systems = evidence.get("systems", []) if isinstance(evidence, dict) else []
        system_analyses = []
        for system in systems if isinstance(systems, list) else []:
            if not isinstance(system, dict):
                continue
            coverage = system.get("coverage", {}) or {}
            counts = system.get("fault_counts", {}) or {}
            system_analyses.append(
                {
                    "system_id": system.get("system_id", ""),
                    "coverage_interpretation": (
                        f"MASCov={_format_metric(coverage.get('mascov'))}，"
                        f"AgentCov={_format_metric(coverage.get('agent_coverage'))}，"
                        f"ToolCov={_format_metric(coverage.get('tool_coverage'))}，"
                        f"EdgeCov={_format_metric(coverage.get('message_edge_coverage'))}，"
                        f"ReqVerifiedCov={_format_metric(coverage.get('req_verified_coverage'))}，"
                        f"EffectiveWorkflowRate={_format_metric(coverage.get('effective_workflow_rate'))}，"
                        f"TraceCompleteness={_format_metric(coverage.get('trace_completeness'))}。"
                        "该解读由确定性覆盖率产物汇总得到。"
                    ),
                    "fault_report_summary": (
                        f"检测到故障条目 {counts.get('total', 0)} 个，其中确认主根因 "
                        f"{counts.get('confirmed_primary_root_causes', counts.get('confirmed', 0))} 个，"
                        f"派生症状 {counts.get('derived_symptoms', 0)} 个，疑似误报 {counts.get('suspected_false_positive', 0)} 个，"
                        f"根因组 {counts.get('root_groups', 0)} 个。"
                    ),
                    "true_fault_summary": "确认/真实故障按 false_positive_audit 未标记为 suspected_false_positive 的 findings 统计。",
                    "false_positive_summary": "疑似误报来自 FalsePositiveAuditorAgent 或确定性审计标签，主要用于避免把观测不足、模型服务或测试框架问题计入目标故障。",
                }
            )
        return {
            "scheme_design": "MASentinel 将静态画像、agent 辅助测试设计、确定性用例生成、无人值守执行、规则 oracle、故障诊断、误报审计和报告生成串成闭环。测试系统不修改被测系统源码，而是通过环境变量、运行时 patch、交互适配和隔离目录尽量让被测系统跑起来，并把应用层与 AutoGen 框架层问题作为主要检测对象。",
            "coverage_metric_design": "MASCov 从多智能体系统的语义结构出发，综合 AgentCov、ToolCov、EdgeCov、ReqIntentCov、StateCov 和 FaultCov；同时补充 ReqVerifiedCov、EffectiveWorkflowRate、TraceCompleteness 和 EvidenceStrength，用于说明需求是否被有效验证、工作流是否真实进入、trace 是否足以支撑故障判断以及故障证据强度。",
            "system_analyses": system_analyses,
            "effectiveness_analysis": "从当前三套系统的产物看，MASentinel 已经能够自动完成画像、用例冻结、执行、oracle 判定、故障分类、误报审计和汇总报告生成。效果优势在于证据链完整、覆盖率指标贴合多智能体交互，且能把非目标问题和疑似误报从最终故障中区分出来；当前不足主要是长耗时系统和深层 AutoGen trace 仍会影响覆盖率与误报率。",
            "next_steps": [
                "继续增强交互式和长耗时系统的输入适配、超时预算和分批执行策略。",
                "强化 AutoGen send、receive、tool_call、tool_result 级别的运行时 trace 采集。",
                "结合回归池和误报审计结果持续校准 oracle，降低观测不足导致的疑似误报。",
            ],
            "confidence": 0.35,
            "fallback": True,
            "error": error,
        }


def _format_metric(value: object) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"
