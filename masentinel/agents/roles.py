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
            if float(coverage.get(key, 1.0) or 0.0) < 0.8:
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
