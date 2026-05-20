from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from masentinel.agents.orchestrator import AgenticTestOrchestrator
from masentinel.analyzer.profile_builder import build_profile_from_config, save_profile_bundle
from masentinel.diagnosis.fault_classifier import classify_faults
from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups
from masentinel.generator.testcase_generator import generate_testcases
from masentinel.metrics.coverage import compute_coverage
from masentinel.reporter.html_report import write_global_index, write_html_report
from masentinel.reporter.markdown_report import write_markdown_reports
from masentinel.reporter.project_report import write_project_report
from masentinel.runner.batch_runner import BatchRunner
from masentinel.runner.system_adapter import load_system_config
from masentinel.utils import ensure_dir, load_yaml, read_json, resolve_path, write_json, write_text
from scripts.build_output_site import build_output_site, build_system_payload, discover_system_dirs


def run_all(
    config_path: str | Path,
    agentic: bool = False,
    test_model: str | None = None,
    no_human: bool = True,
    build_site: bool = True,
    clean_output: bool = True,
) -> list[dict]:
    config_path = Path(config_path)
    all_config = load_yaml(config_path)
    base_dir = config_path.parent
    output_dir = ensure_dir(resolve_path(all_config.get("output_dir", "./outputs"), base_dir) or "./outputs")
    results: list[dict] = []
    systems = list(all_config.get("systems", []))
    loaded_system_configs: list[dict] = []
    _log(f"config={config_path} systems={len(systems)} output_dir={output_dir} agentic={agentic} no_human={no_human}")
    for index, item in enumerate(systems, start=1):
        system_config_path = Path(resolve_path(str(item), base_dir) or item)
        system_config = load_system_config(system_config_path)
        loaded_system_configs.append(system_config)
        system_config.setdefault("run", {})["no_human"] = no_human
        system_id = str(system_config.get("system_id") or system_config_path.stem)
        system_out = _prepare_system_output(output_dir, system_id, clean_output)
        _log(f"system {index}/{len(systems)} start: {system_id} -> {system_out}")
        if agentic:
            result = AgenticTestOrchestrator(test_model=test_model, no_human=no_human).run_system(system_config_path, system_out)
            results.append(result)
            _log(
                f"system {system_id} done: cases={result['cases']} process_passed={result.get('process_passed', result['passed'])} "
                f"process_failed={result.get('process_failed', result['failed'])} oracle_passed={result.get('oracle_passed', 'n/a')} "
                f"oracle_failed={result.get('oracle_failed', 'n/a')} faults={result['faults']} "
                f"primary_root_causes={result.get('confirmed_primary_root_causes', 'n/a')} mascov={_fmt_metric(result['coverage'].get('mascov'))}"
            )
            continue
        _log(f"{system_id} step 0/3 analyze code and docs")
        profile = build_profile_from_config(system_config_path, progress=lambda message, sid=system_id: _log(f"{sid} {message}"))
        save_profile_bundle(profile, system_out / "profile.json")
        testing = system_config.get("testing", {}) or {}
        _log(f"{system_id} step 1/3 generate testcases")
        cases = generate_testcases(profile, num_cases=int(testing.get("num_cases", 40)), seed=int(testing.get("random_seed", 42)))
        write_json(system_out / "testcases.json", cases)
        _log(f"{system_id} generated cases={len(cases)}")
        _log(f"{system_id} step 2/3 execute testcases")
        traces = BatchRunner(system_config, system_out / "runs", workers=int(testing.get("workers", 4))).run(cases)
        _log(f"{system_id} executed traces={len(traces)}")
        _log(f"{system_id} step 3/3 diagnose faults and report")
        faults = annotate_fault_groups(classify_faults(profile, cases, traces))
        write_json(system_out / "faults.json", faults)
        fault_groups = build_fault_groups(faults)
        write_json(system_out / "fault_groups.json", fault_groups)
        coverage = compute_coverage(profile, cases, traces, faults)
        write_json(system_out / "coverage.json", coverage)
        write_markdown_reports(profile, cases, traces, faults, coverage, system_out)
        write_html_report(profile, cases, traces, faults, coverage, system_out)
        passed = len([trace for trace in traces if trace.status == "passed"])
        primary_confirmed = [
            fault
            for fault in faults
            if fault.get("is_primary_fault", True)
            and not fault.get("suspected_false_positive")
            and fault.get("layer") in {"application", "autogen_framework"}
        ]
        derived_symptoms = [fault for fault in faults if fault.get("cascades_from")]
        result = {
            "system_id": system_id,
            "cases": len(cases),
            "passed": passed,
            "failed": len(traces) - passed,
            "process_passed": passed,
            "process_failed": len(traces) - passed,
            "coverage": coverage,
            "faults": len(faults),
            "fault_groups": len(fault_groups),
            "suspected_fp": len([fault for fault in faults if fault.get("suspected_false_positive")]),
            "confirmed_primary_root_causes": len(primary_confirmed),
            "derived_symptoms": len(derived_symptoms),
        }
        results.append(result)
        _log(
            f"system {system_id} done: cases={result['cases']} passed={result['passed']} failed={result['failed']} "
            f"faults={result['faults']} primary_root_causes={result['confirmed_primary_root_causes']} "
            f"mascov={_fmt_metric(result['coverage'].get('mascov'))}"
        )
    # Recompute final public summary from the same persisted artifacts used by
    # outputs/site/index.html.  This keeps summary.md, index.html, project
    # report, and the dashboard on one counting policy even when oracle
    # post-processing excludes non-target or harness issues.
    public_results = _collect_public_results(output_dir) or results
    _write_summary_md(public_results, output_dir)
    write_global_index(public_results, output_dir)
    if agentic:
        project_report_path = write_project_report(
            output_dir,
            public_results,
            model_config=(loaded_system_configs[0].get("model", {}) if loaded_system_configs else {}),
            test_model=test_model,
        )
        _log(f"project report generated: {project_report_path}")
    site_index = None
    if build_site:
        _log("output site build start")
        site_index = build_output_site(output_dir)
        _log(f"output site generated: {site_index}")
    site_suffix = f" site={site_index}" if site_index else ""
    _log(f"all systems complete: summary={output_dir / 'summary.md'} index={output_dir / 'index.html'}{site_suffix}")
    return results


def _log(message: str) -> None:
    print(f"[MASentinel][run_all] {message}", flush=True)


def _prepare_system_output(output_dir: Path, system_id: str, clean_output: bool) -> Path:
    system_out = output_dir / system_id
    if clean_output and system_out.exists():
        shutil.rmtree(system_out)
    return ensure_dir(system_out)


def _collect_public_results(output_dir: Path) -> list[dict]:
    site_dir = output_dir / "site"
    public_results: list[dict] = []
    for system_dir in discover_system_dirs(output_dir):
        payload = build_system_payload(system_dir, output_dir, site_dir)
        metrics = payload.get("metrics", {}) or {}
        coverage = read_json(system_dir / "coverage.json", {}) or {}
        public_results.append(
            {
                "system_id": payload.get("system_id") or system_dir.name,
                "cases": metrics.get("cases_generated", 0),
                "passed": metrics.get("process_passed", 0),
                "failed": metrics.get("process_failed", 0),
                "process_passed": metrics.get("process_passed", 0),
                "process_failed": metrics.get("process_failed", 0),
                "oracle_passed": metrics.get("oracle_passed", 0),
                "oracle_failed": metrics.get("oracle_failed", 0),
                "coverage": coverage,
                "faults": len(payload.get("faults", []) or []),
                "fault_groups": len(payload.get("fault_groups", []) or []),
                "suspected_fp": metrics.get("suspected_false_positives", 0),
                "confirmed_primary_root_causes": metrics.get("confirmed_primary_root_causes", 0),
                "derived_symptoms": metrics.get("derived_symptoms", 0),
                "agentic": {
                    "non_target_issues": payload.get("non_target_issues", []) or [],
                    "test_harness_issues": payload.get("test_harness_issues", []) or [],
                },
            }
        )
    return public_results


def _write_summary_md(results: list[dict], output_dir: Path) -> None:
    lines = [
        "# MASentinel Summary",
        "",
        "> Cases 表示生成测例数；Proc Passed/Failed 表示最终实际执行测例的进程结果；Oracle Passed/Failed 采用目标故障口径，已排除 model provider、外部依赖、test harness、non-target 和 soft budget 等非目标问题。",
        "",
        "| System | Cases | Proc Passed | Proc Failed | Oracle Passed | Oracle Failed | AgentCov | ToolCov | EdgeCov | ReqIntent | ReqVerified | ContractCov | EffWorkflow | TraceComplete | EvidenceRate | MASCov | Confirmed Primary Root Causes | Derived Symptoms | Root Groups | Suspected FP | Non-target Excluded | Harness Excluded |",
        "|--------|-------|-------------|-------------|---------------|---------------|----------|---------|---------|-----------|-------------|-------------|-------------|---------------|--------------|--------|-------------------------------|------------------|-------------|--------------|---------------------|------------------|",
    ]
    for result in results:
        cov = result["coverage"]
        agentic = result.get("agentic", {}) or {}
        non_target = len(agentic.get("non_target_issues", []) or [])
        harness = len(agentic.get("test_harness_issues", []) or [])
        lines.append(
            f"| {result['system_id']} | {result['cases']} | {result.get('process_passed', result['passed'])} | {result.get('process_failed', result['failed'])} | "
            f"{result.get('oracle_passed', '')} | {result.get('oracle_failed', '')} | "
            f"{_fmt_metric(cov.get('agent_coverage'), 2)} | {_fmt_metric(cov.get('tool_coverage'), 2)} | {_fmt_metric(cov.get('message_edge_coverage'), 2)} | "
            f"{_fmt_metric(cov.get('req_intent_coverage', cov.get('requirement_coverage')), 2)} | {_fmt_metric(cov.get('req_verified_coverage'), 2)} | "
            f"{_fmt_metric(cov.get('contract_coverage'), 2)} | {_fmt_metric(cov.get('effective_workflow_rate'), 2)} | "
            f"{_fmt_metric(cov.get('trace_completeness'), 2)} | {_fmt_metric(cov.get('root_cause_evidence_rate'), 2)} | "
            f"{_fmt_metric(cov.get('mascov'), 2)} | {result.get('confirmed_primary_root_causes', result['faults'] - result['suspected_fp'])} | "
            f"{result.get('derived_symptoms', '')} | {result.get('fault_groups', '')} | {result['suspected_fp']} | {non_target} | {harness} |"
        )
    write_text(output_dir / "summary.md", "\n".join(lines) + "\n")


def _fmt_metric(value: object, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MASentinel for all configured systems")
    parser.add_argument("--config", default="configs/all_systems.yaml")
    parser.add_argument("--agentic", action="store_true", help="Run the internal multi-agent testing workflow")
    parser.add_argument("--no-human", dest="no_human", action="store_true", help="Forbid human intervention during automated evaluation")
    parser.add_argument("--allow-human", dest="no_human", action="store_false", help="Allow target systems to request human input")
    parser.add_argument("--test-model", default=None, help="Override the testing-agent model name")
    parser.add_argument("--no-site", dest="build_site", action="store_false", help="Skip building outputs/site static dashboard")
    parser.add_argument("--clean-output", dest="clean_output", action="store_true", help="Clear each system output directory before running")
    parser.add_argument("--keep-output", dest="clean_output", action="store_false", help="Keep existing output files and regression pools")
    parser.set_defaults(no_human=True)
    parser.set_defaults(build_site=True)
    parser.set_defaults(clean_output=True)
    args = parser.parse_args()
    run_all(
        args.config,
        agentic=args.agentic,
        test_model=args.test_model,
        no_human=args.no_human,
        build_site=args.build_site,
        clean_output=args.clean_output,
    )


if __name__ == "__main__":
    main()
