from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import re
import sys
from typing import Any

from masentinel.agents.agent_trace import AgentTraceLogger
from masentinel.agents.roles import (
    CoverageStrategistAgent,
    ExecutionMonitorAgent,
    FalsePositiveAuditorAgent,
    FaultDiagnoserAgent,
    InteractionAdapterAgent,
    ReportWriterAgent,
    RequirementAnalystAgent,
    SystemModelingAgent,
    TestDesignerAgent,
)
from masentinel.agents.validators import merge_testcases, requirements_from_agent_output, testcases_from_agent_output
from masentinel.analyzer.profile_builder import build_profile_from_config, save_profile_bundle
from masentinel.diagnosis.fault_deduplicator import deduplicate_faults
from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups
from masentinel.diagnosis.fault_classifier import TARGET_LAYERS, classify_faults, classify_non_target_issues
from masentinel.diagnosis.patch_suggester import write_patch_suggestions
from masentinel.generator.testcase_generator import generate_testcases
from masentinel.metrics.coverage import compute_coverage
from masentinel.metrics.flaky import update_flaky_report
from masentinel.model.model_client import ModelClient
from masentinel.oracle.rule_oracle import RuleOracle
from masentinel.reporter.dashboard import build_trace_graph, write_dashboard
from masentinel.reporter.html_report import write_html_report
from masentinel.reporter.markdown_report import write_markdown_reports
from masentinel.run_manifest import build_run_manifest, write_run_manifest
from masentinel.runner.batch_runner import BatchRunner
from masentinel.runner.system_adapter import load_system_config
from masentinel.schema import RunTrace, SystemProfile, TestCase
from masentinel.testcase_generation.freezer import write_generation_artifacts
from masentinel.testcase_generation.regression import load_regression_cases, update_regression_pool
from masentinel.testcase_generation.validator import validate_testcases
from masentinel.utils import dataclass_to_dict, ensure_dir, read_text, write_json

class AgenticTestOrchestrator:
    def __init__(self, test_model: str | None = None, no_human: bool = True, verbose: bool = True) -> None:
        self.test_model = test_model
        self.no_human = no_human
        self.verbose = verbose

    def run_system(self, config_path: str | Path, out_dir: str | Path | None = None) -> dict[str, Any]:
        config_path = Path(config_path)
        config = load_system_config(config_path)
        system_id = str(config.get("system_id") or config_path.stem)
        run_cfg = config.setdefault("run", {})
        run_cfg["no_human"] = self.no_human
        system_out = ensure_dir(out_dir or Path("outputs") / system_id)
        self._stage(system_id, f"start agentic run -> {system_out}")
        manifest = build_run_manifest(config_path, config, " ".join(sys.argv), no_human=self.no_human)
        write_run_manifest(system_out / "run_manifest.json", manifest)
        trace_logger = AgentTraceLogger(system_out)
        model_client = self._model_client(config)
        agents = self._agents(model_client, trace_logger)

        self._stage(system_id, "step 0/3 analyze code, docs, agents and tools")
        profile = build_profile_from_config(config_path, progress=lambda message: self._stage(system_id, message))
        doc_text = read_text(profile.doc_path) if profile.doc_path else ""
        self._stage(system_id, f"RequirementAnalystAgent start doc_chars={len(doc_text)}")
        req_decision = agents["requirements"].run(
            {
                "doc_path": profile.doc_path,
                "doc_text": doc_text[:24000],
                "static_profile": dataclass_to_dict(profile),
                "detected_agents": [agent.name for agent in profile.agents],
                "detected_tools": [tool.name for tool in profile.tools],
            }
        )
        profile.requirements = requirements_from_agent_output(req_decision.output, profile.requirements)
        self._stage(system_id, f"RequirementAnalystAgent done requirements={len(profile.requirements)}")

        self._stage(system_id, "SystemModelingAgent start semantic graph review")
        modeling_decision = agents["modeling"].run({"profile": dataclass_to_dict(profile)})
        profile.raw_notes.setdefault("agentic", {})["semantic_graph_review"] = modeling_decision.output
        self._apply_additional_edges(profile, modeling_decision.output)
        save_profile_bundle(profile, system_out / "profile.json")
        self._stage(system_id, "SystemModelingAgent done semantic graph saved")
        self._stage(system_id, f"profile ready: agents={len(profile.agents)} tools={len(profile.tools)} requirements={len(profile.requirements)}")

        interaction_decision = self._plan_interaction_adapter(
            agents["interaction"],
            profile,
            config,
            system_out,
            system_id,
        )

        self._stage(system_id, "step 1/3 generate, validate and freeze testcases")
        testing = config.get("testing", {}) or {}
        agent_api_workers = self._agent_api_workers(config)
        self._stage(system_id, f"agent API parallel workers={agent_api_workers}")
        num_cases = int(testing.get("num_cases", 40))
        max_input_chars = int(testing.get("max_case_input_chars", 1200) or 1200)
        agent_design_cases = min(int(testing.get("agent_design_cases", 4) or 4), num_cases)
        agent_batch_size = max(1, int(testing.get("agent_design_batch_size", 2) or 2))
        agent_cases = self._run_test_designer_batches(
            agents["designer"],
            profile,
            modeling_decision.output,
            total_cases=agent_design_cases,
            batch_size=agent_batch_size,
            workers=agent_api_workers,
            system_id=system_id,
        )
        self._stage(system_id, f"TestDesignerAgent done agent_cases={len(agent_cases)}, merging deterministic and regression cases")
        deterministic_cases = generate_testcases(profile, num_cases=num_cases, seed=int(testing.get("random_seed", 42)))
        regression_cases = load_regression_cases(profile.system_id, system_out)
        generated_cases = merge_testcases(agent_cases, deterministic_cases + regression_cases, limit=None)
        generated_valid, _generated_validation = validate_testcases(generated_cases, profile, system_out, max_input_chars=max_input_chars)
        cases = merge_testcases([], generated_valid, limit=num_cases)
        cases, validation_report = validate_testcases(cases, profile, system_out, max_input_chars=max_input_chars)
        testcase_hash = write_generation_artifacts(generated_cases, cases, system_out)
        write_json(
            system_out / "step1_generation_summary.json",
            {
                "generated_cases": len(generated_cases),
                "validated_cases": len(cases),
                "validation_report": validation_report,
                "testcases_frozen_sha256": testcase_hash,
                "case_types": sorted({case.case_type for case in cases}),
                "human_intervention_allowed": False if self.no_human else True,
                "agent_api_workers": agent_api_workers,
            },
        )
        self._stage(system_id, f"testcases frozen: generated={len(generated_cases)} validated={len(cases)} sha256={testcase_hash[:12]}")

        self._stage(system_id, "step 2/3 execute frozen testcases and evaluate oracle")
        traces = BatchRunner(config, system_out / "runs", workers=int(testing.get("workers", 4))).run(cases)
        rule_results = self._rule_results(profile, cases, traces)
        non_target_issues = classify_non_target_issues(profile, cases, traces)
        write_json(system_out / "rule_results.json", rule_results)
        write_json(system_out / "oracle_results.json", rule_results)
        write_json(system_out / "non_target_issues.json", non_target_issues)
        write_json(system_out / "test_harness_issues.json", self._test_harness_issues(non_target_issues))
        self._stage(system_id, f"execution complete: traces={len(traces)} oracle_results={len(rule_results)}")

        monitor_decision = agents["monitor"].run(
            {
                "rule_results": rule_results,
                "trace_summaries": [self._trace_summary(trace) for trace in traces if trace.status != "passed" or trace.timeout],
            }
        )
        write_json(system_out / "execution_monitor.json", monitor_decision.output)

        self._stage(system_id, "step 3/3 diagnose faults, audit false positives and report")
        self._stage(system_id, "rule classifier start")
        deterministic_faults = classify_faults(profile, cases, traces)
        write_json(system_out / "faults.raw.json", deterministic_faults)
        self._stage(system_id, f"rule classifier done raw_faults={len(deterministic_faults)}")
        dedup_candidates = deduplicate_faults(deterministic_faults)
        write_json(system_out / "faults.dedup_pre_agent.json", dedup_candidates)
        self._stage(system_id, f"pre-agent fault dedup done dedup_faults={len(dedup_candidates)}")
        diagnosed_faults = self._diagnose_and_audit_faults(
            agents["diagnoser"],
            agents["auditor"],
            dedup_candidates,
            cases,
            traces,
            system_id=system_id,
            phase="initial",
            workers=agent_api_workers,
        )
        diagnosed_faults = annotate_fault_groups(diagnosed_faults)
        write_json(system_out / "faults.json", diagnosed_faults)
        write_json(system_out / "fault_groups.json", build_fault_groups(diagnosed_faults))
        self._write_false_positive_audit(system_out, diagnosed_faults)
        self._stage(system_id, f"agent diagnosis/audit done faults={len(diagnosed_faults)}")

        self._stage(system_id, "coverage metrics start")
        coverage = compute_coverage(profile, cases, traces, diagnosed_faults)
        write_json(system_out / "coverage.json", coverage)
        self._stage(system_id, "CoverageStrategistAgent start")
        coverage_decision = agents["coverage"].run(
            {
                "profile": dataclass_to_dict(profile),
                "coverage": coverage,
                "testcases": [dataclass_to_dict(case) for case in cases],
                "faults_count": len(diagnosed_faults),
            }
        )
        write_json(system_out / "coverage_strategy.json", coverage_decision.output)
        self._stage(system_id, f"initial coverage: MASCov={_fmt_metric(coverage.get('mascov'))} faults={len(diagnosed_faults)}")

        second_round = self._maybe_run_second_round(
            profile,
            config,
            system_out,
            testing,
            cases,
            traces,
            coverage,
        )
        if second_round["extra_cases"]:
            self._stage(system_id, f"coverage-guided second round: extra_cases={len(second_round['extra_cases'])}")
            cases.extend(second_round["extra_cases"])
            traces.extend(second_round["extra_traces"])
            rule_results = self._rule_results(profile, cases, traces)
            non_target_issues = classify_non_target_issues(profile, cases, traces)
            write_json(system_out / "rule_results.json", rule_results)
            write_json(system_out / "oracle_results.json", rule_results)
            write_json(system_out / "non_target_issues.json", non_target_issues)
            write_json(system_out / "test_harness_issues.json", self._test_harness_issues(non_target_issues))
            self._stage(system_id, f"second-round oracle evaluation done oracle_results={len(rule_results)}")
            self._stage(system_id, "second-round rule classifier start")
            deterministic_faults = classify_faults(profile, cases, traces)
            write_json(system_out / "faults.raw.json", deterministic_faults)
            self._stage(system_id, f"second-round rule classifier done raw_faults={len(deterministic_faults)}")
            dedup_candidates = deduplicate_faults(deterministic_faults)
            write_json(system_out / "faults.dedup_pre_agent.json", dedup_candidates)
            self._stage(system_id, f"second-round pre-agent dedup done dedup_faults={len(dedup_candidates)}")
            diagnosed_faults = self._diagnose_and_audit_faults(
                agents["diagnoser"],
                agents["auditor"],
                dedup_candidates,
                cases,
                traces,
                system_id=system_id,
                phase="second-round",
                workers=agent_api_workers,
            )
            diagnosed_faults = annotate_fault_groups(diagnosed_faults)
            write_json(system_out / "faults.json", diagnosed_faults)
            write_json(system_out / "fault_groups.json", build_fault_groups(diagnosed_faults))
            self._write_false_positive_audit(system_out, diagnosed_faults)
            self._stage(system_id, f"second-round agent diagnosis/audit done faults={len(diagnosed_faults)}")
            self._stage(system_id, "second-round coverage metrics start")
            coverage = compute_coverage(profile, cases, traces, diagnosed_faults)
            write_json(system_out / "coverage.json", coverage)
            self._stage(system_id, "second-round CoverageStrategistAgent start")
            coverage_decision = agents["coverage"].run(
                {
                    "profile": dataclass_to_dict(profile),
                    "coverage": coverage,
                    "testcases": [dataclass_to_dict(case) for case in cases],
                    "faults_count": len(diagnosed_faults),
                    "second_round": second_round["summary"],
                }
            )
            write_json(system_out / "coverage_strategy.json", coverage_decision.output)
            self._stage(system_id, f"second-round coverage: MASCov={_fmt_metric(coverage.get('mascov'))} faults={len(diagnosed_faults)}")
        self._stage(system_id, "write regression pool, trace graph, flaky report and patch suggestions")
        update_regression_pool(diagnosed_faults, system_out)
        write_json(system_out / "runs" / "run_summary.json", traces)
        trace_graph = build_trace_graph(traces, system_out)
        flaky_report = update_flaky_report(traces, system_out)
        write_patch_suggestions(diagnosed_faults, system_out)
        write_json(system_out / "testcases.executed.json", cases)
        target_model_usage = self._target_model_usage(traces)
        write_json(system_out / "target_model_usage.json", target_model_usage)

        self._stage(system_id, "ReportWriterAgent start")
        report_decision = agents["report"].run(
            {
                "profile": dataclass_to_dict(profile),
                "coverage": coverage,
                "faults": diagnosed_faults,
                "model_usage": trace_logger.usage,
                "rule_results_count": len(rule_results),
            }
        )
        agentic_info = {
            "workflow_agents": [agent.name for agent in agents.values()],
            "model_usage": trace_logger.usage,
            "target_model_usage": target_model_usage,
            "non_target_issues": non_target_issues,
            "test_harness_issues": self._test_harness_issues(non_target_issues),
            "run_manifest": manifest,
            "testcases_frozen_sha256": testcase_hash,
            "human_intervention_allowed": not self.no_human,
            "agent_api_workers": agent_api_workers,
            "semantic_graph_review": modeling_decision.output,
            "interaction_adapter": interaction_decision.output,
            "coverage_strategy": coverage_decision.output,
            "second_round": second_round["summary"],
            "trace_graph": {"nodes": len(trace_graph.get("nodes", [])), "edges": len(trace_graph.get("edges", []))},
            "flaky_report": flaky_report,
            "report_narrative": report_decision.output,
            "fallback_calls": trace_logger.usage.get("fallback_calls", 0),
        }
        write_json(system_out / "agentic_summary.json", agentic_info)
        self._stage(system_id, "writing markdown/html/dashboard reports")
        write_markdown_reports(profile, cases, traces, diagnosed_faults, coverage, system_out, agentic_info=agentic_info)
        write_html_report(profile, cases, traces, diagnosed_faults, coverage, system_out, agentic_info=agentic_info)

        passed = len([trace for trace in traces if trace.status == "passed"])
        oracle_passed = len([item for item in rule_results if item.get("passed")])
        oracle_failed = len(rule_results) - oracle_passed
        fault_groups = build_fault_groups(diagnosed_faults)
        primary_confirmed = [
            fault
            for fault in diagnosed_faults
            if fault.get("is_primary_fault", True)
            and not fault.get("suspected_false_positive")
            and fault.get("layer") in TARGET_LAYERS
        ]
        derived_symptoms = [fault for fault in diagnosed_faults if fault.get("cascades_from")]
        result = {
            "system_id": system_id,
            "cases": len(cases),
            "passed": passed,
            "failed": len(traces) - passed,
            "process_passed": passed,
            "process_failed": len(traces) - passed,
            "oracle_passed": oracle_passed,
            "oracle_failed": oracle_failed,
            "coverage": coverage,
            "faults": len(diagnosed_faults),
            "fault_groups": len(fault_groups),
            "suspected_fp": len([fault for fault in diagnosed_faults if fault.get("suspected_false_positive")]),
            "confirmed_primary_root_causes": len(primary_confirmed),
            "derived_symptoms": len(derived_symptoms),
            "agentic": agentic_info,
        }
        write_dashboard(system_out, result)
        self._stage(
            system_id,
            f"done: cases={result['cases']} process_passed={passed} process_failed={result['failed']} "
            f"oracle_passed={oracle_passed} oracle_failed={oracle_failed} faults={result['faults']} "
            f"primary_root_causes={result['confirmed_primary_root_causes']} report={system_out / 'report.html'}",
        )
        return result

    def _model_client(self, config: dict[str, Any]) -> ModelClient:
        model = config.get("model", {}) or {}
        return ModelClient(
            base_url=model.get("testing_openai_base_url") or model.get("openai_base_url"),
            api_key_env=model.get("testing_api_key_env") or model.get("openai_api_key_env"),
            model=self.test_model or model.get("testing_model") or model.get("default_model") or "ds-v4-pro",
            timeout=int(model.get("testing_timeout_seconds", 45) or 45),
            retries=int(model.get("testing_retries", 1) or 1),
            extra_body=model.get("testing_extra_body") or model.get("testing_extra_body_json") or model.get("extra_body"),
        )

    def _agent_api_workers(self, config: dict[str, Any]) -> int:
        testing = config.get("testing", {}) or {}
        model = config.get("model", {}) or {}
        raw = (
            os.getenv("MAS_AGENT_API_WORKERS")
            or testing.get("agent_api_workers")
            or model.get("testing_parallel_calls")
            or 1
        )
        try:
            workers = int(raw or 1)
        except (TypeError, ValueError):
            workers = 1
        return max(1, min(workers, 16))

    def _agents(self, model_client: ModelClient, trace_logger: AgentTraceLogger) -> dict[str, Any]:
        model_name = self.test_model or model_client.model or "ds-v4-pro"
        return {
            "requirements": RequirementAnalystAgent(model_client, trace_logger, model_name),
            "modeling": SystemModelingAgent(model_client, trace_logger, model_name),
            "designer": TestDesignerAgent(model_client, trace_logger, model_name),
            "interaction": InteractionAdapterAgent(model_client, trace_logger, model_name),
            "coverage": CoverageStrategistAgent(model_client, trace_logger, model_name),
            "monitor": ExecutionMonitorAgent(model_client, trace_logger, model_name),
            "diagnoser": FaultDiagnoserAgent(model_client, trace_logger, model_name),
            "auditor": FalsePositiveAuditorAgent(model_client, trace_logger, model_name),
            "report": ReportWriterAgent(model_client, trace_logger, model_name),
        }

    def _plan_interaction_adapter(
        self,
        adapter: InteractionAdapterAgent,
        profile: SystemProfile,
        config: dict[str, Any],
        system_out: Path,
        system_id: str,
    ) -> Any:
        testing = config.get("testing", {}) or {}
        if not bool(testing.get("enable_agent_interaction_adapter", True)):
            decision = {
                "prompt_responses": ((config.get("run", {}) or {}).get("interaction", {}) or {}).get("prompt_responses", []),
                "isolated_paths": (config.get("run", {}) or {}).get("isolated_paths", []),
                "risk_notes": ["InteractionAdapterAgent disabled by testing.enable_agent_interaction_adapter."],
                "confidence": 1.0,
            }
            write_json(system_out / "interaction_adapter.json", decision)
            self._stage(system_id, "InteractionAdapterAgent skipped: disabled_by_config")
            from masentinel.agents.base import AgentDecision

            return AgentDecision(
                agent_name="InteractionAdapterAgent",
                task="plan_interaction_adapter",
                output=decision,
                confidence=1.0,
                model=self.test_model or "deterministic",
            )

        run_cfg = config.get("run", {}) or {}
        excerpts = self._collect_interaction_excerpts(profile)
        self._stage(system_id, f"InteractionAdapterAgent start input_sites={len(excerpts)} input_mode={run_cfg.get('input_mode')}")
        decision = adapter.run(
            {
                "system_id": profile.system_id,
                "entrypoint": profile.entrypoint,
                "run_config": {
                    "command": run_cfg.get("command"),
                    "input_mode": run_cfg.get("input_mode"),
                    "interaction": run_cfg.get("interaction", {}),
                    "isolated_paths": run_cfg.get("isolated_paths", []),
                    "clean_isolated_paths_before_case": run_cfg.get("clean_isolated_paths_before_case", False),
                    "timeout_seconds": run_cfg.get("timeout_seconds"),
                },
                "input_call_excerpts": excerpts,
                "instruction": "Return only safe prompt-response and isolation suggestions for automated no-human evaluation.",
            }
        )
        applied = self._apply_interaction_plan(config, decision.output)
        payload = dict(decision.output)
        payload["applied"] = applied
        write_json(system_out / "interaction_adapter.json", payload)
        self._stage(
            system_id,
            f"InteractionAdapterAgent done rules={len(((config.get('run', {}) or {}).get('interaction', {}) or {}).get('prompt_responses', []))} applied={applied}",
        )
        decision.output = payload
        return decision

    def _collect_interaction_excerpts(self, profile: SystemProfile) -> list[dict[str, Any]]:
        root = Path(profile.root_path or ".")
        if not root.exists():
            return []
        excerpts: list[dict[str, Any]] = []
        for path in self._interaction_relevant_files(profile, root):
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for index, line in enumerate(lines):
                if "input(" not in line:
                    continue
                start = max(0, index - 2)
                end = min(len(lines), index + 3)
                excerpts.append(
                    {
                        "path": str(path),
                        "line": index + 1,
                        "excerpt": "\n".join(f"{line_no + 1}: {lines[line_no]}" for line_no in range(start, end))[:1200],
                    }
                )
                if len(excerpts) >= 20:
                    return excerpts
        return excerpts

    def _interaction_relevant_files(self, profile: SystemProfile, root: Path) -> list[Path]:
        entrypoint = Path(profile.entrypoint or "")
        if not entrypoint.is_absolute():
            entrypoint = (root / entrypoint).resolve()
        if not entrypoint.exists():
            return [
                path
                for path in sorted(root.rglob("*.py"))
                if not any(part in {".git", "__pycache__", ".venv", "venv", "site-packages"} for part in path.parts)
            ][:20]
        relevant: list[Path] = []
        queue = [entrypoint]
        seen: set[Path] = set()
        while queue and len(relevant) < 20:
            path = queue.pop(0).resolve()
            if path in seen or not path.exists():
                continue
            seen.add(path)
            relevant.append(path)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for module_name in self._local_import_names(text):
                module_path = root / f"{module_name}.py"
                if module_path.exists() and module_path.resolve() not in seen:
                    queue.append(module_path)
        return relevant

    def _local_import_names(self, text: str) -> list[str]:
        import ast

        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.append(node.module.split(".", 1)[0])
        return names

    def _apply_interaction_plan(self, config: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        run_cfg = config.setdefault("run", {})
        interaction_cfg = run_cfg.setdefault("interaction", {})
        existing_rules = list(interaction_cfg.get("prompt_responses", []) or [])
        added_rules = []
        seen = {(str(rule.get("trigger")), str(rule.get("response"))) for rule in existing_rules if isinstance(rule, dict)}
        for rule in plan.get("prompt_responses", []) if isinstance(plan, dict) else []:
            sanitized = self._sanitize_interaction_rule(rule)
            if not sanitized:
                continue
            key = (sanitized["trigger"], sanitized["response"])
            if key in seen:
                continue
            existing_rules.append(sanitized)
            added_rules.append(sanitized)
            seen.add(key)
        if existing_rules:
            interaction_cfg["prompt_responses"] = existing_rules

        existing_paths = list(run_cfg.get("isolated_paths", []) or [])
        added_paths = []
        for raw_path in plan.get("isolated_paths", []) if isinstance(plan, dict) else []:
            path = str(raw_path)
            if len(path) > 180 or not path:
                continue
            if ".masentinel" not in path:
                continue
            if path not in existing_paths:
                existing_paths.append(path)
                added_paths.append(path)
        if existing_paths:
            run_cfg["isolated_paths"] = existing_paths
        if added_paths:
            run_cfg["clean_isolated_paths_before_case"] = True
        return {"added_prompt_responses": added_rules, "added_isolated_paths": added_paths}

    def _sanitize_interaction_rule(self, rule: Any) -> dict[str, Any] | None:
        if not isinstance(rule, dict):
            return None
        trigger = str(rule.get("trigger", "")).strip()
        response = str(rule.get("response", "")).strip()
        if not trigger or not response:
            return None
        if len(trigger) > 240 or len(response) > 2000:
            return None
        allowed_placeholders = {"{input}", "{case_id}", "{safe_case_id}", "{system_id}"}
        placeholders = {item for item in ("{" + part.split("}", 1)[0] + "}" for part in response.split("{")[1:]) if item}
        if placeholders - allowed_placeholders:
            return None
        sanitized = {
            "trigger": trigger,
            "response": response,
            "regex": bool(rule.get("regex", False)),
            "max_count": max(1, min(int(rule.get("max_count", 1) or 1), 20)),
        }
        return sanitized

    def _apply_additional_edges(self, profile: SystemProfile, output: dict[str, Any]) -> None:
        from masentinel.schema import MessageEdge

        existing = {(edge.source, edge.target) for edge in profile.message_edges}
        for item in output.get("additional_edges", []) if isinstance(output, dict) else []:
            if isinstance(item, dict):
                source, target = item.get("source"), item.get("target")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                source, target = item[0], item[1]
            else:
                continue
            if source and target and (str(source), str(target)) not in existing:
                profile.message_edges.append(MessageEdge(str(source), str(target), "SystemModelingAgent additional edge"))
                existing.add((str(source), str(target)))

    def _compact_profile(self, profile: SystemProfile) -> dict[str, Any]:
        return {
            "system_id": profile.system_id,
            "agents": [
                {
                    "name": agent.name,
                    "class_name": agent.class_name,
                    "tools": agent.tools,
                    "system_message": (agent.system_message or "")[:500],
                }
                for agent in profile.agents
            ],
            "tools": [
                {
                    "name": tool.name,
                    "signature": tool.signature,
                    "docstring": (tool.docstring or "")[:300],
                }
                for tool in profile.tools
            ],
            "requirements": [
                {
                    "id": req.id,
                    "description": req.description[:400],
                    "expected_agents": req.expected_agents,
                    "expected_tools": req.expected_tools,
                    "negative_cases": req.negative_cases[:3],
                }
                for req in profile.requirements[:12]
            ],
            "message_edges": [
                {"source": edge.source, "target": edge.target, "evidence": (edge.evidence or "")[:120]}
                for edge in profile.message_edges[:24]
            ],
            "termination_conditions": profile.termination_conditions,
        }

    def _compact_modeling_output(self, output: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(output, dict):
            return {}
        return {
            "semantic_graph_review": str(output.get("semantic_graph_review", ""))[:800],
            "suspected_risk_points": output.get("suspected_risk_points", [])[:8] if isinstance(output.get("suspected_risk_points"), list) else [],
            "additional_edges": output.get("additional_edges", [])[:8] if isinstance(output.get("additional_edges"), list) else [],
            "confidence": output.get("confidence"),
        }

    def _run_test_designer_batches(
        self,
        designer: TestDesignerAgent,
        profile: SystemProfile,
        modeling_output: dict[str, Any],
        total_cases: int,
        batch_size: int,
        workers: int,
        system_id: str,
    ) -> list[TestCase]:
        if total_cases <= 0:
            return []
        agent_cases: list[TestCase] = []
        compact_profile = self._compact_profile(profile)
        compact_modeling = self._compact_modeling_output(modeling_output)
        batches = (total_cases + batch_size - 1) // batch_size
        if workers > 1 and batches > 1:
            return self._run_test_designer_batches_parallel(
                designer,
                profile,
                compact_profile,
                compact_modeling,
                total_cases=total_cases,
                batch_size=batch_size,
                batches=batches,
                workers=workers,
                system_id=system_id,
            )
        for batch_index in range(batches):
            remaining = total_cases - len(agent_cases)
            current_size = min(batch_size, remaining)
            if current_size <= 0:
                break
            existing_intents = [
                {
                    "case_type": case.case_type,
                    "objective": case.objective,
                    "input": case.input[:200],
                }
                for case in agent_cases
            ]
            self._stage(
                system_id,
                f"TestDesignerAgent batch {batch_index + 1}/{batches} start batch_size={current_size} collected={len(agent_cases)}",
            )
            decision = designer.run(
                {
                    "profile": compact_profile,
                    "semantic_graph_review": compact_modeling,
                    "num_cases": current_size,
                    "existing_agent_cases": existing_intents,
                    "instruction": (
                        "Generate only this small batch. Return compact JSON only. "
                        "Keep objective/input strings short and directly executable by the target system. "
                        "Avoid dialogue transcripts, markdown, explanations, and duplicated existing_agent_cases. "
                        "Deterministic generator will fill the remaining suite."
                    ),
                }
            )
            batch_cases = testcases_from_agent_output(decision.output, profile)
            agent_cases = merge_testcases(agent_cases, batch_cases, limit=total_cases)
            self._stage(
                system_id,
                f"TestDesignerAgent batch {batch_index + 1}/{batches} done new_cases={len(batch_cases)} collected={len(agent_cases)} fallback={decision.fallback_used}",
            )
            if decision.fallback_used and not batch_cases:
                break
        return agent_cases[:total_cases]

    def _run_test_designer_batches_parallel(
        self,
        designer: TestDesignerAgent,
        profile: SystemProfile,
        compact_profile: dict[str, Any],
        compact_modeling: dict[str, Any],
        total_cases: int,
        batch_size: int,
        batches: int,
        workers: int,
        system_id: str,
    ) -> list[TestCase]:
        max_workers = min(workers, batches)
        self._stage(system_id, f"TestDesignerAgent parallel start batches={batches} workers={max_workers}")
        agent_cases: list[TestCase] = []
        focuses = [
            "requirement_positive",
            "message_edge_coverage",
            "tool_call_coverage",
            "fault_injection",
            "metamorphic_relation",
            "property_boundary",
            "regression_probe",
            "negative_case",
        ]
        results: dict[int, tuple[list[TestCase], bool]] = {}

        def run_batch(batch_index: int) -> tuple[int, list[TestCase], bool]:
            start = batch_index * batch_size
            current_size = min(batch_size, total_cases - start)
            focus = focuses[batch_index % len(focuses)]
            self._stage(
                system_id,
                f"TestDesignerAgent batch {batch_index + 1}/{batches} start batch_size={current_size} focus={focus}",
            )
            decision = designer.run(
                {
                    "profile": compact_profile,
                    "semantic_graph_review": compact_modeling,
                    "num_cases": current_size,
                    "batch_index": batch_index + 1,
                    "batch_count": batches,
                    "coverage_focus": focus,
                    "existing_agent_cases": [],
                    "instruction": (
                        "Generate only this independent small batch. Return compact JSON only. "
                        "Use coverage_focus to make this batch different from other parallel batches. "
                        "Keep objective/input strings short and directly executable by the target system. "
                        "Avoid dialogue transcripts, markdown, explanations, and duplicated case intents. "
                        "Deterministic generator will fill the remaining suite."
                    ),
                }
            )
            batch_cases = testcases_from_agent_output(decision.output, profile)
            self._stage(
                system_id,
                f"TestDesignerAgent batch {batch_index + 1}/{batches} done new_cases={len(batch_cases)} fallback={decision.fallback_used}",
            )
            return batch_index, batch_cases, decision.fallback_used

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(run_batch, batch_index): batch_index for batch_index in range(batches)}
            for future in as_completed(future_map):
                batch_index = future_map[future]
                try:
                    index, batch_cases, fallback_used = future.result()
                    results[index] = (batch_cases, fallback_used)
                except Exception as exc:
                    results[batch_index] = ([], True)
                    self._stage(system_id, f"TestDesignerAgent batch {batch_index + 1}/{batches} failed: {exc}")

        for index in sorted(results):
            batch_cases, _fallback_used = results[index]
            agent_cases = merge_testcases(agent_cases, batch_cases, limit=total_cases)
            if len(agent_cases) >= total_cases:
                break
        self._stage(system_id, f"TestDesignerAgent parallel complete collected={len(agent_cases)}")
        return agent_cases[:total_cases]

    def _rule_results(self, profile: SystemProfile, cases: list[TestCase], traces: list[RunTrace]) -> list[dict[str, Any]]:
        oracle = RuleOracle(registered_tools={tool.name for tool in profile.tools})
        trace_by_case = {trace.case_id: trace for trace in traces}
        results = []
        for case in cases:
            trace = trace_by_case.get(case.case_id)
            if not trace:
                continue
            results.append(dataclass_to_dict(oracle.evaluate(case, trace)))
        return results

    def _test_harness_issues(self, non_target_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [issue for issue in non_target_issues if issue.get("layer") == "test_harness"]

    def _maybe_run_second_round(
        self,
        profile: SystemProfile,
        config: dict[str, Any],
        system_out: Path,
        testing: dict[str, Any],
        existing_cases: list[TestCase],
        existing_traces: list[RunTrace],
        coverage: dict[str, Any],
    ) -> dict[str, Any]:
        target = float(testing.get("target_mascov", 0.8) or 0.8)
        enabled = bool(testing.get("enable_second_round", True))
        summary = {
            "enabled": enabled,
            "target_mascov": target,
            "initial_mascov": coverage.get("mascov", 0),
            "extra_cases": 0,
            "reason": "",
        }
        if not enabled:
            summary["reason"] = "disabled_by_config"
            write_json(system_out / "second_round_summary.json", summary)
            self._stage(profile.system_id, "second round skipped: disabled_by_config")
            return {"extra_cases": [], "extra_traces": [], "summary": summary}
        if float(coverage.get("mascov", 0) or 0) >= target:
            summary["reason"] = "target_reached"
            write_json(system_out / "second_round_summary.json", summary)
            self._stage(profile.system_id, f"second round skipped: target_reached MASCov={_fmt_metric(coverage.get('mascov'))} target={target:.4f}")
            return {"extra_cases": [], "extra_traces": [], "summary": summary}
        extra_limit = int(testing.get("second_round_cases", 8) or 8)
        seed = int(testing.get("random_seed", 42)) + 101
        self._stage(profile.system_id, f"second round candidate generation start target_mascov={target:.4f} extra_limit={extra_limit}")
        candidates = generate_testcases(profile, num_cases=max(extra_limit * 2, 12), seed=seed)
        existing_keys = {(case.case_type, case.input) for case in existing_cases}
        priority_types = {"coverage_guided", "property_boundary", "fuzz_tool_failure", "metamorphic"}
        ordered = [case for case in candidates if case.case_type in priority_types] + [case for case in candidates if case.case_type not in priority_types]
        extra_cases: list[TestCase] = []
        for case in ordered:
            key = (case.case_type, case.input)
            if key in existing_keys:
                continue
            case.metadata["coverage_guided_round"] = 2
            extra_cases.append(case)
            existing_keys.add(key)
            if len(extra_cases) >= extra_limit:
                break
        max_input_chars = int(testing.get("max_case_input_chars", 1200) or 1200)
        extra_cases, validation_report = validate_testcases(extra_cases, profile, max_input_chars=max_input_chars)
        for index, case in enumerate(extra_cases, start=1):
            case.case_id = f"{profile.system_id}_R2_{index:03d}"
        write_json(system_out / "extra_testcases.generated.json", candidates)
        write_json(system_out / "extra_testcases.validated.json", extra_cases)
        write_json(system_out / "extra_testcases.validation_report.json", validation_report)
        self._stage(profile.system_id, f"second round validation done candidates={len(candidates)} valid_extra={len(extra_cases)}")
        if not extra_cases:
            summary["reason"] = "no_new_valid_cases"
            write_json(system_out / "second_round_summary.json", summary)
            return {"extra_cases": [], "extra_traces": [], "summary": summary}
        self._stage(profile.system_id, f"second round execution start extra_cases={len(extra_cases)}")
        extra_traces = BatchRunner(config, system_out / "runs", workers=int(testing.get("workers", 4))).run(extra_cases)
        self._stage(profile.system_id, f"second round execution done extra_traces={len(extra_traces)}")
        summary.update(
            {
                "extra_cases": len(extra_cases),
                "extra_traces": len(extra_traces),
                "reason": "coverage_below_target",
                "initial_failed": len([trace for trace in existing_traces if trace.status != "passed"]),
            }
        )
        write_json(system_out / "second_round_summary.json", summary)
        return {"extra_cases": extra_cases, "extra_traces": extra_traces, "summary": summary}

    def _write_false_positive_audit(self, system_out: Path, faults: list[dict[str, Any]]) -> None:
        write_json(
            system_out / "false_positive_audit.json",
            [
                {
                    "fault_id": fault.get("fault_id"),
                    "case_id": fault.get("case_id"),
                    "suspected_false_positive": fault.get("suspected_false_positive", False),
                    "audit": fault.get("false_positive_audit", {}),
                }
                for fault in faults
            ],
        )

    def _target_model_usage(self, traces: list[RunTrace]) -> dict[str, Any]:
        by_model: dict[str, int] = {}
        by_base_url: dict[str, int] = {}
        case_summaries: list[dict[str, Any]] = []
        warning_count = 0
        stdout_model_mentions = 0
        stderr_model_mentions = 0
        for trace in traces:
            metadata = trace.metadata or {}
            model = metadata.get("target_model")
            base_url = metadata.get("target_base_url")
            key_env = metadata.get("target_api_key_env")
            stdout = trace.stdout or ""
            stderr = trace.stderr or ""
            model_names = [str(model)] if model else []
            model_names.extend(re.findall(r"Model\s+([A-Za-z0-9_.:/-]+)\s+is not found", stdout + "\n" + stderr))
            model_names = [name for name in model_names if name]
            for name in sorted(set(model_names)):
                by_model[name] = by_model.get(name, 0) + 1
            if base_url:
                by_base_url[str(base_url)] = by_base_url.get(str(base_url), 0) + 1
            stdout_hits = sum(stdout.count(name) for name in set(model_names))
            stderr_hits = sum(stderr.count(name) for name in set(model_names))
            stdout_model_mentions += stdout_hits
            stderr_model_mentions += stderr_hits
            warnings = len(re.findall(r"WARNING\s+-\s+Model\s+", stdout + "\n" + stderr))
            warning_count += warnings
            case_summaries.append(
                {
                    "case_id": trace.case_id,
                    "status": trace.status,
                    "target_model": model,
                    "target_base_url": base_url,
                    "target_api_key_env": key_env,
                    "stdout_model_mentions": stdout_hits,
                    "stderr_model_mentions": stderr_hits,
                    "autogen_model_warning_count": warnings,
                }
            )
        return {
            "scope": "target_system_subprocess",
            "note": (
                "Target-system LLM calls run inside the evaluated subprocess and are not routed through "
                "MASentinel ModelClient, so this is evidence from injected environment metadata and captured stdout/stderr."
            ),
            "cases": len(traces),
            "by_model": by_model,
            "by_base_url": by_base_url,
            "target_api_key_envs": sorted(
                {
                    str((trace.metadata or {}).get("target_api_key_env"))
                    for trace in traces
                    if (trace.metadata or {}).get("target_api_key_env")
                }
            ),
            "stdout_model_mentions": stdout_model_mentions,
            "stderr_model_mentions": stderr_model_mentions,
            "autogen_model_warning_count": warning_count,
            "case_summaries": case_summaries,
        }

    def _stage(self, system_id: str, message: str) -> None:
        if self.verbose:
            print(f"[MASentinel][{system_id}] {message}", flush=True)

    def _diagnose_and_audit_faults(
        self,
        diagnoser: FaultDiagnoserAgent,
        auditor: FalsePositiveAuditorAgent,
        faults: list[dict[str, Any]],
        cases: list[TestCase],
        traces: list[RunTrace],
        system_id: str,
        phase: str,
        workers: int = 1,
    ) -> list[dict[str, Any]]:
        case_by_id = {case.case_id: case for case in cases}
        trace_by_id = {trace.case_id: trace for trace in traces}
        total = len(faults)
        self._stage(system_id, f"{phase} agent diagnosis/audit start faults={total}")
        if not faults:
            return []

        max_workers = min(max(1, workers), total)
        if max_workers <= 1:
            audited: list[dict[str, Any]] = []
            for index, fault in enumerate(faults, start=1):
                merged = self._diagnose_and_audit_one(
                    diagnoser,
                    auditor,
                    fault,
                    case_by_id,
                    trace_by_id,
                    index=index,
                    total=total,
                    system_id=system_id,
                    phase=phase,
                )
                if merged is not None:
                    audited.append(merged)
            self._stage(system_id, f"{phase} agent diagnosis/audit complete faults={len(audited)}")
            return audited

        self._stage(system_id, f"{phase} agent diagnosis/audit parallel workers={max_workers}")
        results: dict[int, dict[str, Any] | None] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    self._diagnose_and_audit_one,
                    diagnoser,
                    auditor,
                    fault,
                    case_by_id,
                    trace_by_id,
                    index=index,
                    total=total,
                    system_id=system_id,
                    phase=phase,
                ): index
                for index, fault in enumerate(faults, start=1)
            }
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    results[index] = None
                    self._stage(system_id, f"{phase} fault {index}/{total} agent diagnosis/audit failed: {exc}")
        audited = [results[index] for index in sorted(results) if results[index] is not None]
        self._stage(system_id, f"{phase} agent diagnosis/audit complete faults={len(audited)}")
        return audited

    def _diagnose_and_audit_one(
        self,
        diagnoser: FaultDiagnoserAgent,
        auditor: FalsePositiveAuditorAgent,
        fault: dict[str, Any],
        case_by_id: dict[str, TestCase],
        trace_by_id: dict[str, RunTrace],
        index: int,
        total: int,
        system_id: str,
        phase: str,
    ) -> dict[str, Any] | None:
        case = case_by_id.get(fault.get("case_id", ""))
        trace = trace_by_id.get(fault.get("case_id", ""))
        self._stage(
            system_id,
            f"{phase} FaultDiagnoserAgent {index}/{total} "
            f"case={fault.get('case_id')} code={fault.get('failure_code')} type={fault.get('fault_type')}",
        )
        diagnosis = diagnoser.run(
            {
                "fault": fault,
                "testcase": dataclass_to_dict(case) if case else {},
                "trace_summary": self._trace_summary(trace) if trace else {},
            }
        ).output
        merged = dict(fault)
        for key in ("layer", "fault_type", "severity", "root_cause", "suggested_fix", "summary"):
            if diagnosis.get(key):
                merged[key] = diagnosis[key]
        if diagnosis.get("confidence") is not None:
            try:
                merged["confidence"] = float(diagnosis["confidence"])
            except (TypeError, ValueError):
                pass
        if diagnosis.get("evidence"):
            merged["agentic_evidence"] = diagnosis["evidence"]
        self._stage(system_id, f"{phase} FalsePositiveAuditorAgent {index}/{total} fault={merged.get('fault_id')}")
        audit = auditor.run({"fault": merged, "trace_summary": self._trace_summary(trace) if trace else {}}).output
        merged["false_positive_audit"] = audit
        if audit.get("audit_result") == "likely_false_positive":
            merged["suspected_false_positive"] = True
        elif audit.get("audit_result") == "confirmed_fault":
            merged["suspected_false_positive"] = False
        if str(merged.get("layer", "")) not in TARGET_LAYERS:
            self._stage(
                system_id,
                f"{phase} fault {index}/{total} excluded non_target_layer={merged.get('layer')} fault={merged.get('fault_id')}",
            )
            return None
        self._stage(
            system_id,
            f"{phase} fault {index}/{total} done suspected_fp={merged.get('suspected_false_positive', False)} "
            f"confidence={merged.get('confidence')}",
        )
        return merged

    def _trace_summary(self, trace: RunTrace | None) -> dict[str, Any]:
        if trace is None:
            return {}
        return {
            "case_id": trace.case_id,
            "status": trace.status,
            "timeout": trace.timeout,
            "terminated": trace.terminated,
            "turn_count": trace.turn_count,
            "returncode": trace.returncode,
            "stderr_tail": "\n".join((trace.stderr or "").splitlines()[-8:]),
            "stdout_tail": "\n".join((trace.stdout or "").splitlines()[-8:]),
            "events_count": len(trace.events),
        }


def _fmt_metric(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "N/A"
