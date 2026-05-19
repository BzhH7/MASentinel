from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from masentinel.diagnosis.fault_classifier import classify_faults, classify_non_target_issues
    from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups
    from masentinel.diagnosis.patch_suggester import write_patch_suggestions
    from masentinel.metrics.coverage import compute_coverage
    from masentinel.oracle.rule_oracle import RuleOracle
    from masentinel.reporter.dashboard import build_trace_graph, write_dashboard
    from masentinel.reporter.html_report import write_global_index, write_html_report
    from masentinel.reporter.markdown_report import write_markdown_reports
    from masentinel.reporter.project_report import write_project_report
    from masentinel.schema import profile_from_dict, testcase_from_dict, trace_from_dict
    from masentinel.utils import read_json, write_json
    from run_all import _write_summary_md

    parser = argparse.ArgumentParser(description="Recompute MASentinel reports from saved outputs without rerunning target systems.")
    parser.add_argument("--output-dir", default=str(repo_root / "outputs"))
    parser.add_argument("--project-report", action="store_true", help="Also regenerate outputs/项目报告.md from rebuilt artifacts.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    results = []
    for system_dir in sorted(path for path in output_dir.iterdir() if path.is_dir() and not path.name.startswith(".") and path.name != "project_report_agent"):
        profile_data = read_json(system_dir / "profile.json", None)
        cases_data = read_json(system_dir / "testcases.executed.json", None) or read_json(system_dir / "testcases.json", None)
        traces_data = read_json(system_dir / "runs" / "run_summary.json", None)
        if not profile_data or not cases_data or not traces_data:
            continue
        profile = profile_from_dict(profile_data)
        cases = [testcase_from_dict(item) for item in cases_data if isinstance(item, dict)]
        traces = [trace_from_dict(item) for item in traces_data if isinstance(item, dict)]
        trace_by_case = _trace_by_case(traces)

        oracle = RuleOracle(registered_tools={tool.name for tool in profile.tools})
        rule_results = [oracle.evaluate(case, trace_by_case[case.case_id]) for case in cases if case.case_id in trace_by_case]
        rule_result_dicts = [_dataclass_to_dict(item) for item in rule_results]
        write_json(system_dir / "rule_results.json", rule_result_dicts)
        write_json(system_dir / "oracle_results.json", rule_result_dicts)

        non_target_issues = classify_non_target_issues(profile, cases, traces)
        faults = annotate_fault_groups(classify_faults(profile, cases, traces))
        fault_groups = build_fault_groups(faults)
        coverage = compute_coverage(profile, cases, traces, faults)
        agentic_info = read_json(system_dir / "agentic_summary.json", {}) or {}
        agentic_info["non_target_issues"] = non_target_issues
        agentic_info["test_harness_issues"] = [issue for issue in non_target_issues if issue.get("layer") == "test_harness"]

        write_json(system_dir / "non_target_issues.json", non_target_issues)
        write_json(system_dir / "test_harness_issues.json", agentic_info["test_harness_issues"])
        write_json(system_dir / "faults.raw.json", faults)
        write_json(system_dir / "faults.dedup_pre_agent.json", faults)
        write_json(system_dir / "faults.json", faults)
        write_json(system_dir / "fault_groups.json", fault_groups)
        write_json(system_dir / "coverage.json", coverage)
        write_json(system_dir / "agentic_summary.json", agentic_info)
        write_json(
            system_dir / "false_positive_audit.json",
            [
                {
                    "fault_id": fault.get("fault_id"),
                    "case_id": fault.get("case_id"),
                    "suspected_false_positive": fault.get("suspected_false_positive", False),
                    "audit": {"audit_result": "deterministic_rebuild", "confidence": fault.get("confidence")},
                }
                for fault in faults
            ],
        )
        build_trace_graph(traces, system_dir)
        write_patch_suggestions(faults, system_dir)
        write_markdown_reports(profile, cases, traces, faults, coverage, system_dir, agentic_info=agentic_info)
        write_html_report(profile, cases, traces, faults, coverage, system_dir, agentic_info=agentic_info)

        passed = len([trace for trace in traces if trace.status == "passed"])
        oracle_passed = len([item for item in rule_result_dicts if item.get("passed")])
        primary_confirmed = [
            fault
            for fault in faults
            if fault.get("is_primary_fault", True)
            and not fault.get("suspected_false_positive")
            and fault.get("layer") in {"application", "autogen_framework"}
        ]
        derived_symptoms = [fault for fault in faults if fault.get("cascades_from")]
        result = {
            "system_id": profile.system_id,
            "cases": len(cases),
            "passed": passed,
            "failed": len(traces) - passed,
            "process_passed": passed,
            "process_failed": len(traces) - passed,
            "oracle_passed": oracle_passed,
            "oracle_failed": len(rule_result_dicts) - oracle_passed,
            "coverage": coverage,
            "faults": len(faults),
            "fault_groups": len(fault_groups),
            "suspected_fp": len([fault for fault in faults if fault.get("suspected_false_positive")]),
            "confirmed_primary_root_causes": len(primary_confirmed),
            "derived_symptoms": len(derived_symptoms),
            "agentic": agentic_info,
        }
        write_dashboard(system_dir, result)
        results.append(result)
        print(
            f"[MASentinel][rebuild] {profile.system_id}: cases={result['cases']} oracle_failed={result['oracle_failed']} "
            f"primary_root_causes={result['confirmed_primary_root_causes']} non_target={len(non_target_issues)}",
            flush=True,
        )

    _write_summary_md(results, output_dir)
    write_global_index(results, output_dir)
    if args.project_report:
        report_path = write_project_report(output_dir, results)
        print(f"[MASentinel][rebuild] project_report={report_path}", flush=True)
    print(f"[MASentinel][rebuild] summary={output_dir / 'summary.md'}", flush=True)


def _trace_by_case(traces: list[Any]) -> dict[str, Any]:
    return {trace.case_id: trace for trace in traces}


def _dataclass_to_dict(value: Any) -> Any:
    from masentinel.utils import dataclass_to_dict

    return dataclass_to_dict(value)


if __name__ == "__main__":
    main()
