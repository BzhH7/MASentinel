from __future__ import annotations

import argparse
from pathlib import Path

from masentinel.analyzer.profile_builder import build_profile_from_config, save_profile_bundle
from masentinel.agents.orchestrator import AgenticTestOrchestrator
from masentinel.diagnosis.fault_classifier import classify_faults
from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups
from masentinel.generator.testcase_generator import generate_testcases
from masentinel.metrics.coverage import compute_coverage
from masentinel.reporter.html_report import write_html_report
from masentinel.reporter.markdown_report import write_markdown_reports
from masentinel.runner.batch_runner import BatchRunner
from masentinel.runner.system_adapter import load_system_config
from masentinel.schema import profile_from_dict, testcase_from_dict, trace_from_dict
from masentinel.utils import ensure_dir, read_json, write_json


def cmd_analyze(args: argparse.Namespace) -> None:
    profile = build_profile_from_config(args.config)
    save_profile_bundle(profile, args.out)


def cmd_generate(args: argparse.Namespace) -> None:
    profile = profile_from_dict(read_json(args.profile, {}))
    cases = generate_testcases(profile, num_cases=args.num_cases)
    write_json(args.out, cases)


def cmd_run(args: argparse.Namespace) -> None:
    config = load_system_config(args.config)
    cases = [testcase_from_dict(item) for item in read_json(args.testcases, [])]
    workers = int((config.get("testing", {}) or {}).get("workers", args.workers or 4))
    BatchRunner(config, args.out, workers=workers).run(cases)


def cmd_diagnose(args: argparse.Namespace) -> None:
    profile = profile_from_dict(read_json(args.profile, {}))
    cases = [testcase_from_dict(item) for item in read_json(args.testcases, [])]
    traces = _load_traces(args.traces)
    faults = annotate_fault_groups(classify_faults(profile, cases, traces))
    write_json(args.out, faults)


def cmd_report(args: argparse.Namespace) -> None:
    profile = profile_from_dict(read_json(args.profile, {}))
    cases = [testcase_from_dict(item) for item in read_json(args.testcases, [])]
    traces = _load_traces(args.traces)
    faults = read_json(args.faults, [])
    faults = annotate_fault_groups(faults)
    coverage = compute_coverage(profile, cases, traces, faults)
    out_dir = ensure_dir(args.out)
    system_dir = out_dir.parent if out_dir.name == "report" else out_dir
    write_json(system_dir / "coverage.json", coverage)
    write_json(system_dir / "fault_groups.json", build_fault_groups(faults))
    write_json(system_dir / "faults.json", faults)
    write_markdown_reports(profile, cases, traces, faults, coverage, system_dir)
    write_html_report(profile, cases, traces, faults, coverage, system_dir)


def cmd_run_agentic(args: argparse.Namespace) -> None:
    AgenticTestOrchestrator(test_model=args.test_model, no_human=not args.allow_human).run_system(args.config, args.out)


def _load_traces(path: str | Path) -> list:
    root = Path(path)
    files = sorted(root.glob("*.json")) if root.is_dir() else [root]
    traces = []
    for file in files:
        data = read_json(file, None)
        if isinstance(data, dict) and data.get("case_id"):
            traces.append(trace_from_dict(data))
    return traces


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="masentinel", description="Semantic-coverage testing for AutoGen systems")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--config", required=True)
    analyze.add_argument("--out", required=True)
    analyze.set_defaults(func=cmd_analyze)
    generate = sub.add_parser("generate")
    generate.add_argument("--profile", required=True)
    generate.add_argument("--num-cases", type=int, default=40)
    generate.add_argument("--out", required=True)
    generate.set_defaults(func=cmd_generate)
    run = sub.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--testcases", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--workers", type=int, default=None)
    run.set_defaults(func=cmd_run)
    diagnose = sub.add_parser("diagnose")
    diagnose.add_argument("--profile", required=True)
    diagnose.add_argument("--testcases", required=True)
    diagnose.add_argument("--traces", required=True)
    diagnose.add_argument("--out", required=True)
    diagnose.set_defaults(func=cmd_diagnose)
    report = sub.add_parser("report")
    report.add_argument("--profile", required=True)
    report.add_argument("--testcases", required=True)
    report.add_argument("--traces", required=True)
    report.add_argument("--faults", required=True)
    report.add_argument("--out", required=True)
    report.set_defaults(func=cmd_report)
    agentic = sub.add_parser("run-agentic")
    agentic.add_argument("--config", required=True)
    agentic.add_argument("--out", required=True)
    agentic.add_argument("--test-model", default=None)
    agentic.add_argument("--allow-human", action="store_true", help="Allow target systems to request human input during this run")
    agentic.set_defaults(func=cmd_run_agentic)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
