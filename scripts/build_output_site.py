#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path
from typing import Any


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
ESCAPED_ANSI_RE = re.compile(r"(?:\\u001b|\\x1b)\[[0-9;]*m")

SYSTEM_MARKER_FILES = (
    "coverage.json",
    "faults.json",
    "agentic_summary.json",
    "run_manifest.json",
)

JSON_FILES = (
    "coverage.json",
    "faults.json",
    "fault_groups.json",
    "false_positive_audit.json",
    "non_target_issues.json",
    "test_harness_issues.json",
    "agentic_summary.json",
    "run_manifest.json",
    "runs/run_summary.json",
    "trace_graph.json",
    "profile.json",
    "testcases.generated.json",
    "testcases.validated.json",
    "testcases.executed.json",
    "flaky_report.json",
)

COVERAGE_KEYS = (
    "agent_coverage",
    "tool_coverage",
    "message_edge_coverage",
    "requirement_coverage",
    "state_coverage",
    "fault_mode_coverage",
    "mascov",
)

ARTIFACT_FILES = (
    ("report.html", "open"),
    ("report.md", "download"),
    ("故障报告.md", "download"),
    ("patch_suggestions.md", "download"),
    ("coverage.json", "download"),
    ("faults.json", "download"),
    ("trace_graph.json", "download"),
    ("flaky_report.json", "download"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a static MASentinel output dashboard.")
    parser.add_argument("--output-dir", default="outputs", help="Directory containing MASentinel per-system outputs.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    site_dir = output_dir / "site"
    assets_dir = site_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    systems = [build_system_payload(path, output_dir, site_dir) for path in discover_system_dirs(output_dir)]
    summary = build_global_summary(systems)
    data = {
        "summary": safe_for_html(summary),
        "systems": safe_for_html(systems),
    }

    (site_dir / "index.html").write_text(build_index_html(data, systems, summary), encoding="utf-8")
    (assets_dir / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (assets_dir / "app.js").write_text(APP_JS, encoding="utf-8")

    index_path = site_dir / "index.html"
    print(f"Site generated: {index_path.as_posix()}  ({len(systems)} systems loaded)")


def discover_system_dirs(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    system_dirs = []
    for child in sorted(output_dir.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        if child.name == "site":
            continue
        if any((child / marker).is_file() for marker in SYSTEM_MARKER_FILES):
            system_dirs.append(child)
    return system_dirs


def build_system_payload(system_dir: Path, output_dir: Path, site_dir: Path) -> dict[str, Any]:
    loaded = {name: read_json(system_dir / name) for name in JSON_FILES}
    coverage = as_dict(loaded.get("coverage.json"))
    faults = normalize_records(loaded.get("faults.json"), ("faults", "items"))
    fault_groups = normalize_records(loaded.get("fault_groups.json"), ("fault_groups", "groups", "items"))
    fp_audit = normalize_records(loaded.get("false_positive_audit.json"), ("audits", "items"))
    non_target_issues = normalize_records(loaded.get("non_target_issues.json"), ("issues", "items"))
    harness_issues = normalize_records(loaded.get("test_harness_issues.json"), ("issues", "items"))
    agentic_summary = as_dict(loaded.get("agentic_summary.json"))
    run_manifest = as_dict(loaded.get("run_manifest.json"))
    run_summary = normalize_records(loaded.get("runs/run_summary.json"), ("runs", "results", "cases", "items"))
    trace_graph = normalize_trace_graph(loaded.get("trace_graph.json"))
    profile = as_dict(loaded.get("profile.json"))
    generated_cases = normalize_records(loaded.get("testcases.generated.json"), ("testcases", "cases", "items"))
    validated_cases = normalize_records(loaded.get("testcases.validated.json"), ("testcases", "cases", "items"))
    executed_cases = normalize_records(loaded.get("testcases.executed.json"), ("testcases", "cases", "items"))
    selected_cases = first_non_empty(executed_cases, validated_cases, generated_cases)
    flaky_report = as_dict(loaded.get("flaky_report.json"))

    system_id = first_text(
        profile.get("system_id"),
        run_manifest.get("system_id"),
        agentic_summary.get("system_id"),
        system_dir.name,
    )
    run_status = build_run_status(run_summary, agentic_summary, flaky_report)
    fault_by_case = build_fault_by_case(faults)
    cases = build_testcase_rows(system_id, selected_cases, run_status, fault_by_case)
    metrics = build_system_metrics(
        coverage=coverage,
        faults=faults,
        fault_groups=fault_groups,
        fp_audit=fp_audit,
        non_target_issues=non_target_issues,
        harness_issues=harness_issues,
        agentic_summary=agentic_summary,
        run_summary=run_summary,
        generated_cases=generated_cases,
        selected_cases=selected_cases,
        run_status=run_status,
    )
    artifacts = build_artifacts(system_dir, site_dir)

    return {
        "system_id": system_id,
        "path": relative_path(system_dir, site_dir),
        "metrics": metrics,
        "coverage": normalize_coverage(coverage),
        "faults": build_fault_rows(system_id, faults),
        "fault_groups": build_fault_group_rows(fault_groups),
        "false_positive_audit": build_fp_audit_rows(fp_audit),
        "non_target_issues": build_issue_rows(system_id, non_target_issues),
        "test_harness_issues": build_issue_rows(system_id, harness_issues),
        "trace_graph": trace_graph,
        "testcases": cases,
        "artifacts": artifacts,
    }


def build_global_summary(systems: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "total_systems": len(systems),
        "total_testcases_generated": 0,
        "process_passed": 0,
        "process_failed": 0,
        "oracle_passed": 0,
        "oracle_failed": 0,
        "confirmed_primary_root_causes": 0,
        "suspected_false_positives": 0,
        "non_target_excluded": 0,
        "average_mascov": None,
    }
    mascov_values = []
    for system in systems:
        metrics = system.get("metrics", {})
        totals["total_testcases_generated"] += int_value(metrics.get("cases_generated"))
        totals["process_passed"] += int_value(metrics.get("process_passed"))
        totals["process_failed"] += int_value(metrics.get("process_failed"))
        totals["oracle_passed"] += int_value(metrics.get("oracle_passed"))
        totals["oracle_failed"] += int_value(metrics.get("oracle_failed"))
        totals["confirmed_primary_root_causes"] += int_value(metrics.get("confirmed_primary_root_causes"))
        totals["suspected_false_positives"] += int_value(metrics.get("suspected_false_positives"))
        totals["non_target_excluded"] += int_value(metrics.get("non_target_excluded"))
        mascov = percent_value((system.get("coverage", {}) or {}).get("mascov"))
        if mascov is not None:
            mascov_values.append(mascov)
    if mascov_values:
        totals["average_mascov"] = sum(mascov_values) / len(mascov_values)
    return totals


def build_system_metrics(
    *,
    coverage: dict[str, Any],
    faults: list[dict[str, Any]],
    fault_groups: list[dict[str, Any]],
    fp_audit: list[dict[str, Any]],
    non_target_issues: list[dict[str, Any]],
    harness_issues: list[dict[str, Any]],
    agentic_summary: dict[str, Any],
    run_summary: list[dict[str, Any]],
    generated_cases: list[dict[str, Any]],
    selected_cases: list[dict[str, Any]],
    run_status: dict[str, str],
) -> dict[str, Any]:
    generated_count = first_int(
        deep_get(agentic_summary, ("testcase_generation", "generated")),
        deep_get(agentic_summary, ("testcases", "generated")),
        len(generated_cases) if generated_cases else None,
        len(selected_cases) if selected_cases else None,
        len(run_status) if run_status else None,
    )

    process_passed, process_failed = count_process_results(agentic_summary, run_summary, run_status)
    oracle_passed, oracle_failed = count_oracle_results(
        agentic_summary=agentic_summary,
        run_summary=run_summary,
        faults=faults,
        generated_count=generated_count,
        selected_count=len(selected_cases),
    )
    primary_count = count_confirmed_primary(faults, fault_groups)
    derived_count = count_derived_symptoms(faults, fault_groups)
    suspected_fp_count = count_suspected_false_positives(faults, fp_audit)

    return {
        "cases_generated": generated_count,
        "cases_displayed": len(selected_cases),
        "process_passed": process_passed,
        "process_failed": process_failed,
        "oracle_passed": oracle_passed,
        "oracle_failed": oracle_failed,
        "confirmed_primary_root_causes": primary_count,
        "derived_symptoms": derived_count,
        "suspected_false_positives": suspected_fp_count,
        "non_target_excluded": len(non_target_issues),
        "harness_excluded": len(harness_issues),
        "mascov": coverage.get("mascov"),
    }


def count_process_results(
    agentic_summary: dict[str, Any],
    run_summary: list[dict[str, Any]],
    run_status: dict[str, str],
) -> tuple[int, int]:
    direct_passed = first_int(
        agentic_summary.get("process_passed"),
        deep_get(agentic_summary, ("process", "passed")),
        deep_get(agentic_summary, ("execution", "passed")),
    )
    direct_failed = first_int(
        agentic_summary.get("process_failed"),
        deep_get(agentic_summary, ("process", "failed")),
        deep_get(agentic_summary, ("execution", "failed")),
    )
    if direct_passed is not None or direct_failed is not None:
        return direct_passed or 0, direct_failed or 0

    if run_summary:
        return count_statuses([record.get("status") for record in run_summary])
    if run_status:
        return count_statuses(run_status.values())
    case_summaries = deep_get(agentic_summary, ("target_model_usage", "case_summaries"))
    if isinstance(case_summaries, list):
        return count_statuses([item.get("status") for item in case_summaries if isinstance(item, dict)])
    return 0, 0


def count_oracle_results(
    *,
    agentic_summary: dict[str, Any],
    run_summary: list[dict[str, Any]],
    faults: list[dict[str, Any]],
    generated_count: int,
    selected_count: int,
) -> tuple[int, int]:
    direct_passed = first_int(
        agentic_summary.get("oracle_passed"),
        deep_get(agentic_summary, ("oracle", "passed")),
        deep_get(agentic_summary, ("oracle_results", "passed")),
    )
    direct_failed = first_int(
        agentic_summary.get("oracle_failed"),
        deep_get(agentic_summary, ("oracle", "failed")),
        deep_get(agentic_summary, ("oracle_results", "failed")),
    )
    if direct_passed is not None or direct_failed is not None:
        return direct_passed or 0, direct_failed or 0

    oracle_flags = []
    for record in run_summary:
        oracle = record.get("oracle") or record.get("oracle_result") or record.get("rule_result")
        if isinstance(oracle, dict) and "passed" in oracle:
            oracle_flags.append(oracle.get("passed"))
        elif "oracle_passed" in record:
            oracle_flags.append(record.get("oracle_passed"))
    if oracle_flags:
        passed = len([flag for flag in oracle_flags if truthy(flag)])
        return passed, len(oracle_flags) - passed

    failed_case_ids = {
        str(fault.get("case_id"))
        for fault in faults
        if fault.get("case_id") is not None and not is_non_target_fault(fault)
    }
    failed = len(failed_case_ids)
    total = generated_count or selected_count or max(failed, 0)
    return max(total - failed, 0), failed


def count_confirmed_primary(faults: list[dict[str, Any]], fault_groups: list[dict[str, Any]]) -> int:
    count = 0
    for fault in faults:
        if is_suspected_fp_fault(fault):
            continue
        if is_non_target_fault(fault):
            continue
        if fault.get("is_primary_fault", True) is False or fault.get("cascades_from"):
            continue
        audit = as_dict(fault.get("false_positive_audit"))
        audit_result = str(audit.get("audit_result", "")).lower()
        if audit_result and "false_positive" in audit_result:
            continue
        count += 1
    if count == 0 and fault_groups:
        count = len([group for group in fault_groups if group.get("primary_fault_id")])
    return count


def count_derived_symptoms(faults: list[dict[str, Any]], fault_groups: list[dict[str, Any]]) -> int:
    derived = len(
        [
            fault
            for fault in faults
            if fault.get("cascades_from") or fault.get("is_primary_fault") is False
        ]
    )
    if fault_groups:
        group_symptoms = 0
        for group in fault_groups:
            symptoms = group.get("symptom_fault_ids")
            if isinstance(symptoms, list):
                group_symptoms += len(symptoms)
        return max(derived, group_symptoms)
    return derived


def count_suspected_false_positives(faults: list[dict[str, Any]], fp_audit: list[dict[str, Any]]) -> int:
    fault_ids = set()
    for fault in faults:
        if is_suspected_fp_fault(fault):
            fault_ids.add(str(fault.get("fault_id", len(fault_ids))))
    for item in fp_audit:
        audit = as_dict(item.get("audit"))
        audit_result = str(audit.get("audit_result", item.get("audit_result", ""))).lower()
        if truthy(item.get("suspected_false_positive")) or "false_positive" in audit_result:
            fault_ids.add(str(item.get("fault_id", len(fault_ids))))
    return len(fault_ids)


def is_suspected_fp_fault(fault: dict[str, Any]) -> bool:
    if truthy(fault.get("suspected_false_positive")):
        return True
    audit = as_dict(fault.get("false_positive_audit"))
    audit_result = str(audit.get("audit_result", "")).lower()
    return "false_positive" in audit_result


def is_non_target_fault(fault: dict[str, Any]) -> bool:
    layer = str(fault.get("layer", "")).lower()
    return layer in {"test_harness", "model_service", "external_dependency", "non_target"}


def build_run_status(
    run_summary: list[dict[str, Any]],
    agentic_summary: dict[str, Any],
    flaky_report: dict[str, Any],
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for record in run_summary:
        case_id = first_text(record.get("case_id"), record.get("id"))
        if case_id:
            statuses[case_id] = first_text(record.get("status"), "N/A")
    case_summaries = deep_get(agentic_summary, ("target_model_usage", "case_summaries"))
    if isinstance(case_summaries, list):
        for record in case_summaries:
            if not isinstance(record, dict):
                continue
            case_id = first_text(record.get("case_id"), record.get("id"))
            if case_id and case_id not in statuses:
                statuses[case_id] = first_text(record.get("status"), "N/A")
    history = flaky_report.get("history")
    if isinstance(history, dict):
        for case_id, values in history.items():
            if str(case_id) in statuses:
                continue
            if isinstance(values, list) and values:
                statuses[str(case_id)] = first_text(values[-1], "N/A")
    return statuses


def build_fault_by_case(faults: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = {}
    for fault in faults:
        case_id = fault.get("case_id")
        if case_id is None:
            continue
        mapping.setdefault(str(case_id), []).append(fault)
    return mapping


def build_testcase_rows(
    system_id: str,
    testcases: list[dict[str, Any]],
    run_status: dict[str, str],
    fault_by_case: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = []
    for index, case in enumerate(testcases, start=1):
        case_id = first_text(case.get("case_id"), case.get("id"), f"{system_id}_CASE_{index:03d}")
        faults_for_case = fault_by_case.get(case_id, [])
        failure_code = first_text(
            case.get("failure_code"),
            first_text(*[fault.get("failure_code") for fault in faults_for_case]) if faults_for_case else None,
            "N/A",
        )
        status = first_text(case.get("status"), run_status.get(case_id), "N/A")
        rows.append(
            {
                "system_id": system_id,
                "case_id": case_id,
                "type": first_text(case.get("case_type"), case.get("type"), case.get("metadata", {}).get("generic_pattern") if isinstance(case.get("metadata"), dict) else None, "N/A"),
                "status": status,
                "failure_code": failure_code,
                "description": first_text(case.get("description"), case.get("objective"), case.get("input"), "N/A"),
                "expected": value_to_text(
                    first_existing(
                        case.get("expected"),
                        deep_get(case, ("metadata", "expected_result")),
                        deep_get(case, ("oracle", "expected_keywords")),
                        case.get("oracle"),
                    )
                ),
                "actual": value_to_text(first_existing(case.get("actual"), case.get("result"), case.get("output"), "N/A")),
                "steps": value_to_text(first_existing(case.get("steps"), case.get("input_sequence"), case.get("input"), "N/A")),
            }
        )
    return rows


def build_fault_rows(system_id: str, faults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, fault in enumerate(faults, start=1):
        rows.append(
            {
                "system_id": system_id,
                "fault_id": first_text(fault.get("fault_id"), f"{system_id}_FAULT_{index:03d}"),
                "case_id": first_text(fault.get("case_id"), "N/A"),
                "layer": first_text(fault.get("layer"), "unknown"),
                "fault_type": first_text(fault.get("fault_type"), fault.get("type"), "N/A"),
                "failure_code": first_text(fault.get("failure_code"), fault.get("code"), "N/A"),
                "severity": first_text(fault.get("severity"), "unknown").lower(),
                "confidence": first_text(fault.get("confidence"), "N/A"),
                "summary": first_text(fault.get("summary"), fault.get("message"), "N/A"),
                "root_cause": value_to_text(first_existing(fault.get("root_cause"), "N/A")),
                "suggested_fix": value_to_text(first_existing(fault.get("suggested_fix"), "N/A")),
                "evidence": value_to_text(first_existing(fault.get("evidence"), fault.get("agentic_evidence"), "N/A")),
                "reproduction": value_to_text(first_existing(fault.get("reproduction"), "N/A")),
                "suspected_false_positive": bool(is_suspected_fp_fault(fault)),
            }
        )
    return rows


def build_fault_group_rows(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for group in groups:
        rows.append(
            {
                "group_id": first_text(group.get("group_id"), group.get("id"), "N/A"),
                "title": first_text(group.get("title"), "N/A"),
                "primary_fault_id": first_text(group.get("primary_fault_id"), "N/A"),
                "symptom_fault_ids": normalize_text_list(group.get("symptom_fault_ids")),
                "severity": first_text(group.get("severity"), "N/A"),
                "summary": first_text(group.get("summary"), "N/A"),
            }
        )
    return rows


def build_fp_audit_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        audit = as_dict(item.get("audit"))
        rows.append(
            {
                "fault_id": first_text(item.get("fault_id"), "N/A"),
                "case_id": first_text(item.get("case_id"), "N/A"),
                "suspected_false_positive": bool(truthy(item.get("suspected_false_positive"))),
                "audit_result": first_text(audit.get("audit_result"), item.get("audit_result"), "N/A"),
                "confidence": first_text(audit.get("confidence"), item.get("confidence"), "N/A"),
                "reason": first_text(audit.get("reason"), item.get("reason"), "N/A"),
            }
        )
    return rows


def build_issue_rows(system_id: str, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, issue in enumerate(issues, start=1):
        rows.append(
            {
                "system_id": system_id,
                "issue_id": first_text(issue.get("issue_id"), issue.get("id"), issue.get("case_id"), f"{system_id}_ISSUE_{index:03d}"),
                "type": first_text(issue.get("type"), issue.get("issue_type"), issue.get("code"), "N/A"),
                "description": first_text(issue.get("description"), issue.get("message"), issue.get("summary"), "N/A"),
                "impact": first_text(issue.get("impact"), issue.get("root_cause"), issue.get("suggested_fix"), "N/A"),
            }
        )
    return rows


def build_artifacts(system_dir: Path, site_dir: Path) -> list[dict[str, Any]]:
    artifacts = []
    for filename, mode in ARTIFACT_FILES:
        path = system_dir / filename
        exists = path.is_file()
        artifacts.append(
            {
                "name": filename,
                "exists": exists,
                "href": relative_path(path, site_dir) if exists else "",
                "mode": mode,
            }
        )
    return artifacts


def normalize_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    return {key: coverage.get(key) for key in COVERAGE_KEYS}


def normalize_trace_graph(data: Any) -> dict[str, Any]:
    graph = as_dict(data)
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    return {
        "nodes": [node for node in nodes if isinstance(node, dict)],
        "edges": [edge for edge in edges if isinstance(edge, dict)],
    }


def read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def normalize_records(data: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return normalize_records(value, keys)
        rows = []
        for key, value in data.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("id", key)
                rows.append(row)
        return rows
    return []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_for_html(value: Any) -> Any:
    if isinstance(value, str):
        return html.escape(clean_text(value), quote=True)
    if isinstance(value, list):
        return [safe_for_html(item) for item in value]
    if isinstance(value, dict):
        return {str(safe_for_html(str(key))): safe_for_html(item) for key, item in value.items()}
    return value


def first_non_empty(*values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for value in values:
        if value:
            return value
    return []


def first_existing(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        return clean_text(value_to_text(value))
    return "N/A"


def clean_text(value: str) -> str:
    return ESCAPED_ANSI_RE.sub("", ANSI_RE.sub("", value))


def value_to_text(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return clean_text(json.dumps(strip_ansi_value(value), ensure_ascii=False, indent=2))
    except (TypeError, ValueError):
        return clean_text(str(value))


def strip_ansi_value(value: Any) -> Any:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [strip_ansi_value(item) for item in value]
    if isinstance(value, dict):
        return {key: strip_ansi_value(item) for key, item in value.items()}
    return value


def normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [first_text(item) for item in value]
    if value is None:
        return []
    return [first_text(value)]


def deep_get(data: Any, keys: tuple[str, ...]) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "pass"}
    return bool(value)


def count_statuses(statuses: Any) -> tuple[int, int]:
    passed = 0
    failed = 0
    for status in statuses:
        normalized = str(status).strip().lower()
        if normalized in {"passed", "pass", "success", "succeeded", "ok"}:
            passed += 1
        elif normalized in {"failed", "fail", "failure", "timeout", "error", "crashed", "cancelled"}:
            failed += 1
    return passed, failed


def percent_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 1:
        return number * 100
    return number


def format_count(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "N/A"


def format_percent(value: Any) -> str:
    percent = percent_value(value)
    if percent is None:
        return "N/A"
    return f"{percent:.1f}%"


def relative_path(path: Path, site_dir: Path) -> str:
    return Path(os.path.relpath(path, start=site_dir)).as_posix()


def css_width(value: Any) -> str:
    percent = percent_value(value)
    if percent is None:
        return "0"
    return f"{max(0.0, min(100.0, percent)):.1f}"


def build_index_html(data: dict[str, Any], systems: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    json_data = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MASentinel Output Dashboard</title>
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
  <nav class="top-nav" aria-label="Dashboard sections">
    <a href="#hero" class="nav-link active">Overview</a>
    <a href="#method" class="nav-link">Method</a>
    <a href="#systems" class="nav-link">Systems</a>
    <a href="#coverage" class="nav-link">Coverage</a>
    <a href="#faults" class="nav-link">Faults</a>
    <a href="#issues" class="nav-link">Issues</a>
    <a href="#trace" class="nav-link">Trace</a>
    <a href="#testcases" class="nav-link">Cases</a>
    <a href="#artifacts" class="nav-link">Artifacts</a>
  </nav>
  <main class="page-shell">
    {render_hero(summary)}
    {render_method_section()}
    {render_systems_section(systems)}
    {render_coverage_section(systems)}
    {render_fault_section(systems)}
    {render_issues_section(systems)}
    {render_trace_section(systems)}
    {render_testcase_section()}
    {render_artifacts_section(systems)}
  </main>
  <script>window.MASENTINEL_DATA = {json_data};</script>
  <script src="assets/app.js"></script>
</body>
</html>
"""


def section_title(number: int, title: str) -> str:
    return f"""<div class="section-title"><span class="section-badge">{number:02d}</span><h2>{html.escape(title)}</h2></div>"""


def render_hero(summary: dict[str, Any]) -> str:
    cards = [
        ("Total Systems", format_count(summary.get("total_systems")), "neutral"),
        ("Total Test Cases", format_count(summary.get("total_testcases_generated")), "neutral"),
        ("Process Passed / Failed", f"{format_count(summary.get('process_passed'))} / {format_count(summary.get('process_failed'))}", "success-danger"),
        ("Oracle Passed / Failed", f"{format_count(summary.get('oracle_passed'))} / {format_count(summary.get('oracle_failed'))}", "success-danger"),
        ("Confirmed Primary Root Causes", format_count(summary.get("confirmed_primary_root_causes")), "danger"),
        ("Suspected False Positives", format_count(summary.get("suspected_false_positives")), "warning"),
        ("Non-target Excluded", format_count(summary.get("non_target_excluded")), "neutral"),
        ("Average MASCov", format_percent(summary.get("average_mascov")), "primary"),
    ]
    card_html = "\n".join(
        [
            f"""<article class="metric-card metric-{html.escape(kind)}"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></article>"""
            for label, value, kind in cards
        ]
    )
    return f"""<section id="hero" class="hero-section observed-section">
  <div class="hero-copy">
    <p class="eyebrow">MASentinel Output Site</p>
    <h1>AutoGen Multi-Agent Test Dashboard</h1>
    <p class="hero-subtitle">Static aggregation of generated tests, unattended execution traces, oracle diagnosis, false-positive audit, and final artifacts.</p>
  </div>
  <div class="metric-grid">{card_html}</div>
</section>"""


def render_method_section() -> str:
    steps = [
        ("◈", "Analysis", "Profile code, docs, agents, tools"),
        ("▣", "Test Generation", "Create coverage-targeted cases"),
        ("▶", "Execution", "Run without human input"),
        ("◎", "Trace Collection", "Capture messages and tool calls"),
        ("◇", "Oracle Diagnosis", "Classify observed failures"),
        ("△", "FP Audit", "Separate signal from noise"),
        ("▤", "Report", "Publish evidence and fixes"),
    ]
    nodes = []
    for icon, name, desc in steps:
        nodes.append(
            f"""<div class="method-node"><span class="method-icon">{html.escape(icon)}</span><strong>{html.escape(name)}</strong><small>{html.escape(desc)}</small></div>"""
        )
    return f"""<section id="method" class="observed-section">
  {section_title(2, "Method Overview")}
  <div class="method-flow">{"<span class='flow-arrow'>→</span>".join(nodes)}</div>
</section>"""


def render_systems_section(systems: list[dict[str, Any]]) -> str:
    cards = []
    for system in systems:
        metrics = system.get("metrics", {})
        coverage = system.get("coverage", {})
        metric_line = [
            ("cases", format_count(metrics.get("cases_generated"))),
            ("process passed", format_count(metrics.get("process_passed"))),
            ("failed", format_count(metrics.get("process_failed"))),
            ("oracle passed", format_count(metrics.get("oracle_passed"))),
            ("failed", format_count(metrics.get("oracle_failed"))),
            ("MASCov", format_percent(coverage.get("mascov"))),
        ]
        metric_html = "".join(
            [f"<span><b>{html.escape(label)}</b> {html.escape(value)}</span>" for label, value in metric_line]
        )
        tags = [
            ("confirmed primary root causes", metrics.get("confirmed_primary_root_causes"), "danger"),
            ("derived symptoms", metrics.get("derived_symptoms"), "warning"),
            ("suspected false positives", metrics.get("suspected_false_positives"), "warning"),
            ("non-target excluded", metrics.get("non_target_excluded"), "neutral"),
            ("harness excluded", metrics.get("harness_excluded"), "neutral"),
        ]
        tag_html = "".join(
            [
                f"""<span class="status-pill {html.escape(kind)}"><b>{html.escape(format_count(value))}</b> {html.escape(label)}</span>"""
                for label, value, kind in tags
            ]
        )
        cards.append(
            f"""<article class="system-card">
  <h3>{html.escape(str(system.get("system_id", "N/A")))}</h3>
  <div class="system-metrics">{metric_html}</div>
  <div class="tag-column">{tag_html}</div>
</article>"""
        )
    content = "\n".join(cards) if cards else "<p class=\"empty-state\">No system directories were detected.</p>"
    return f"""<section id="systems" class="observed-section">
  {section_title(3, "Systems Overview")}
  <div class="systems-grid">{content}</div>
</section>"""


def render_coverage_section(systems: list[dict[str, Any]]) -> str:
    labels = {
        "agent_coverage": "Agent Coverage",
        "tool_coverage": "Tool Coverage",
        "message_edge_coverage": "Message Edge Coverage",
        "requirement_coverage": "Requirement Coverage",
        "state_coverage": "State Coverage",
        "fault_mode_coverage": "Fault Mode Coverage",
        "mascov": "MASCov",
    }
    panels = []
    for system in systems:
        bars = []
        coverage = system.get("coverage", {})
        for index, key in enumerate(COVERAGE_KEYS, start=1):
            value = coverage.get(key)
            bars.append(
                f"""<div class="coverage-row">
  <span class="coverage-name">{html.escape(labels[key])}</span>
  <div class="bar-track"><div class="bar-fill bar-{index}" style="width: {html.escape(css_width(value))}%"></div></div>
  <span class="coverage-value">{html.escape(format_percent(value))}</span>
</div>"""
            )
        panels.append(
            f"""<article class="coverage-panel">
  <h3>{html.escape(str(system.get("system_id", "N/A")))}</h3>
  {"".join(bars)}
</article>"""
        )
    content = "\n".join(panels) if panels else "<p class=\"empty-state\">No coverage.json files were loaded.</p>"
    return f"""<section id="coverage" class="observed-section">
  {section_title(4, "Coverage Dashboard")}
  <div class="coverage-grid">{content}</div>
</section>"""


def render_fault_section(systems: list[dict[str, Any]]) -> str:
    faults = []
    for system in systems:
        faults.extend(system.get("faults", []))
    chart_html = render_fault_charts(faults)
    return f"""<section id="faults" class="observed-section">
  {section_title(5, "Fault Analysis")}
  <div class="subsection-label">5a. Aggregate Statistics</div>
  {chart_html}
  <div class="subsection-label">5b. Fault Detail Table</div>
  <div class="table-toolbar">
    <label>Severity <select id="fault-severity-filter"><option value="">All</option></select></label>
    <label>Layer <select id="fault-layer-filter"><option value="">All</option></select></label>
  </div>
  <div class="table-wrap">
    <table class="data-table sortable-table" id="fault-table">
      <thead>
        <tr>
          <th data-sort="fault_id">fault_id</th>
          <th data-sort="case_id">case_id</th>
          <th data-sort="layer">layer</th>
          <th data-sort="fault_type">fault_type</th>
          <th data-sort="failure_code">failure_code</th>
          <th data-sort="severity">severity</th>
          <th data-sort="confidence">confidence</th>
          <th data-sort="summary">summary</th>
        </tr>
      </thead>
      <tbody id="fault-table-body"></tbody>
    </table>
  </div>
  <div class="subsection-label">5c. Severity and Layer Filters</div>
  <p class="section-note">Use the select controls above to filter the table; click any header to sort and any row to expand diagnostic details.</p>
</section>"""


def render_fault_charts(faults: list[dict[str, Any]]) -> str:
    layer_counts = count_by(faults, "layer", ("application", "autogen_framework", "unknown"))
    severity_counts = count_by(faults, "severity", ("high", "medium", "low"))
    failure_counts = sorted(count_by(faults, "failure_code").items(), key=lambda item: (-item[1], item[0]))[:10]
    fp_counts = {"false": 0, "true": 0}
    for fault in faults:
        fp_counts["true" if fault.get("suspected_false_positive") else "false"] += 1
    charts = [
        ("By Layer", layer_counts),
        ("By Severity", severity_counts),
        ("Top Failure Codes", dict(failure_counts)),
        ("Suspected False Positive", fp_counts),
    ]
    return "<div class=\"chart-grid\">" + "".join(render_count_chart(title, counts) for title, counts in charts) + "</div>"


def count_by(rows: list[dict[str, Any]], key: str, defaults: tuple[str, ...] = ()) -> dict[str, int]:
    counts = {item: 0 for item in defaults}
    for row in rows:
        value = str(row.get(key) or "unknown").lower()
        if not value:
            value = "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


def render_count_chart(title: str, counts: dict[str, int]) -> str:
    max_count = max(counts.values()) if counts else 0
    rows = []
    if not counts:
        rows.append("<p class=\"empty-state compact\">N/A</p>")
    for index, (label, count) in enumerate(counts.items(), start=1):
        width = (count / max_count * 100) if max_count else 0
        rows.append(
            f"""<div class="count-row">
  <span class="count-label">{html.escape(str(label))}</span>
  <div class="bar-track"><div class="bar-fill bar-{(index % 7) + 1}" style="width: {width:.1f}%"></div></div>
  <span class="count-value">{html.escape(str(count))}</span>
</div>"""
        )
    return f"""<article class="chart-card"><h3>{html.escape(title)}</h3>{"".join(rows)}</article>"""


def render_issues_section(systems: list[dict[str, Any]]) -> str:
    non_target = []
    harness = []
    for system in systems:
        non_target.extend(system.get("non_target_issues", []))
        harness.extend(system.get("test_harness_issues", []))
    return f"""<section id="issues" class="observed-section">
  {section_title(6, "Non-target & Harness Issues")}
  <p class="section-note">These issues are reported for transparency but are excluded from primary application or AutoGen-framework fault statistics when they point to model service behavior, external dependencies, or the MASentinel harness itself.</p>
  <div class="issue-grid">
    <article class="issue-panel">
      <h3>Non-target Issues</h3>
      {render_issue_list(non_target)}
    </article>
    <article class="issue-panel">
      <h3>Test Harness Issues</h3>
      {render_issue_list(harness)}
    </article>
  </div>
</section>"""


def render_issue_list(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "<p class=\"empty-state\">N/A</p>"
    cards = []
    for issue in issues:
        cards.append(
            f"""<div class="issue-item">
  <div><code>{html.escape(str(issue.get("issue_id", "N/A")))}</code><span>{html.escape(str(issue.get("system_id", "N/A")))}</span></div>
  <strong>{html.escape(str(issue.get("type", "N/A")))}</strong>
  <p>{html.escape(str(issue.get("description", "N/A")))}</p>
  <small>{html.escape(str(issue.get("impact", "N/A")))}</small>
</div>"""
        )
    return "".join(cards)


def render_trace_section(systems: list[dict[str, Any]]) -> str:
    options = "\n".join(
        [
            f"""<option value="{html.escape(str(system.get("system_id", "N/A")))}">{html.escape(str(system.get("system_id", "N/A")))}</option>"""
            for system in systems
        ]
    )
    return f"""<section id="trace" class="observed-section">
  {section_title(7, "Trace Graph")}
  <div class="table-toolbar">
    <label>System <select id="trace-system-select">{options}</select></label>
  </div>
  <div id="trace-graph" class="trace-graph" role="img" aria-label="Trace graph SVG"></div>
</section>"""


def render_testcase_section() -> str:
    return f"""<section id="testcases" class="observed-section">
  {section_title(8, "Test Case Explorer")}
  <div class="table-toolbar testcase-toolbar">
    <label>Case Type <select id="case-type-filter"><option value="">All</option></select></label>
    <label>Status <select id="case-status-filter"><option value="">All</option></select></label>
    <label>Failure Code <select id="case-failure-filter"><option value="">All</option></select></label>
    <label class="search-label">Search <input id="case-search" type="search" placeholder="case_id, description, expected..."></label>
  </div>
  <div class="table-wrap">
    <table class="data-table" id="case-table">
      <thead>
        <tr>
          <th>case_id</th>
          <th>type</th>
          <th>status</th>
          <th>failure_code</th>
          <th>description</th>
        </tr>
      </thead>
      <tbody id="case-table-body"></tbody>
    </table>
  </div>
  <div id="case-pagination" class="pagination"></div>
</section>"""


def render_artifacts_section(systems: list[dict[str, Any]]) -> str:
    panels = []
    for system in systems:
        links = []
        for artifact in system.get("artifacts", []):
            name = str(artifact.get("name", "N/A"))
            if artifact.get("exists"):
                href = str(artifact.get("href", ""))
                if artifact.get("mode") == "open":
                    links.append(
                        f"""<a class="artifact-link" href="{html.escape(href)}" target="_blank" rel="noopener">{html.escape(name)}</a>"""
                    )
                else:
                    links.append(
                        f"""<a class="artifact-link" href="{html.escape(href)}" download>{html.escape(name)}</a>"""
                    )
            else:
                links.append(f"""<span class="artifact-link disabled">{html.escape(name)}</span>""")
        panels.append(
            f"""<article class="artifact-panel">
  <h3>{html.escape(str(system.get("system_id", "N/A")))}</h3>
  <div class="artifact-links">{"".join(links)}</div>
</article>"""
        )
    content = "\n".join(panels) if panels else "<p class=\"empty-state\">No artifacts were detected.</p>"
    return f"""<section id="artifacts" class="observed-section">
  {section_title(9, "Artifacts")}
  <div class="artifact-grid">{content}</div>
</section>"""


STYLE_CSS = r"""
:root {
  --color-bg: #ffffff;
  --color-surface: #f4f6f9;
  --color-border: #dde2eb;
  --color-primary: #1a3a6b;
  --color-primary-light: #2563a8;
  --color-text: #1c2333;
  --color-text-muted: #5a6478;
  --color-success: #1a7a45;
  --color-success-bg: #e6f4ed;
  --color-danger: #b91c1c;
  --color-danger-bg: #fef2f2;
  --color-warning: #92400e;
  --color-warning-bg: #fffbeb;
}

* {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

body {
  margin: 0;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
  line-height: 1.5;
}

a {
  color: var(--color-primary-light);
}

.top-nav {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  gap: 4px;
  justify-content: center;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--color-border);
  background: rgba(255, 255, 255, 0.96);
  padding: 10px 16px;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 10px;
  border-radius: 6px;
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 13px;
  font-weight: 650;
}

.nav-link.active,
.nav-link:hover {
  background: var(--color-primary);
  color: #ffffff;
}

.page-shell {
  width: min(1200px, calc(100% - 32px));
  margin: 0 auto;
  padding: 22px 0 48px;
}

section {
  scroll-margin-top: 76px;
  margin: 22px 0;
  padding: 22px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #ffffff;
}

.hero-section {
  display: grid;
  grid-template-columns: minmax(260px, 0.85fr) 1.4fr;
  gap: 22px;
  align-items: stretch;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.hero-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--color-primary-light);
  font-size: 13px;
  font-weight: 750;
  text-transform: uppercase;
}

h1,
h2,
h3,
p {
  overflow-wrap: anywhere;
}

h1 {
  margin: 0;
  color: var(--color-primary);
  font-size: 38px;
  line-height: 1.1;
  letter-spacing: 0;
}

.hero-subtitle {
  margin: 14px 0 0;
  color: var(--color-text-muted);
  max-width: 52ch;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.section-title h2 {
  margin: 0;
  color: var(--color-primary);
  font-size: 24px;
  letter-spacing: 0;
}

.section-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 28px;
  border-radius: 6px;
  background: var(--color-primary);
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.system-card,
.coverage-panel,
.chart-card,
.issue-panel,
.artifact-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #ffffff;
}

.metric-card {
  min-height: 104px;
  padding: 16px;
}

.metric-card span {
  display: block;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 650;
}

.metric-card strong {
  display: block;
  margin-top: 10px;
  color: var(--color-text);
  font-size: 28px;
  line-height: 1.1;
  font-weight: 800;
}

.metric-primary strong {
  color: var(--color-primary);
}

.metric-success-danger strong,
.metric-danger strong {
  color: var(--color-danger);
}

.metric-warning strong {
  color: var(--color-warning);
}

.method-flow {
  display: flex;
  align-items: stretch;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 6px;
}

.method-node {
  flex: 1 0 140px;
  min-width: 140px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
}

.method-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #ffffff;
  color: var(--color-primary);
  font-weight: 800;
}

.method-node strong,
.method-node small {
  display: block;
}

.method-node strong {
  margin-top: 8px;
  color: var(--color-primary);
}

.method-node small {
  margin-top: 4px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.flow-arrow {
  display: inline-flex;
  align-items: center;
  color: var(--color-primary-light);
  font-weight: 800;
}

.systems-grid,
.coverage-grid,
.chart-grid,
.issue-grid,
.artifact-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.system-card {
  padding: 16px;
  background: var(--color-surface);
}

.system-card h3,
.coverage-panel h3,
.chart-card h3,
.issue-panel h3,
.artifact-panel h3 {
  margin: 0 0 12px;
  color: var(--color-primary);
  font-size: 17px;
}

.system-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--color-text-muted);
  font-size: 13px;
}

.system-metrics b {
  color: var(--color-text);
}

.tag-column {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 650;
}

.status-pill.success,
.status-badge.passed {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-pill.danger,
.status-badge.failed,
.status-badge.timeout {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.status-pill.warning,
.status-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-pill.neutral,
.status-badge.neutral {
  background: #edf1f7;
  color: var(--color-text-muted);
}

.coverage-panel,
.chart-card,
.issue-panel,
.artifact-panel {
  padding: 16px;
}

.coverage-row,
.count-row {
  display: grid;
  grid-template-columns: minmax(120px, 0.9fr) minmax(160px, 2fr) 58px;
  gap: 10px;
  align-items: center;
  min-height: 30px;
}

.coverage-name,
.count-label,
.coverage-value,
.count-value {
  color: var(--color-text-muted);
  font-size: 13px;
}

.coverage-value,
.count-value {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.bar-track {
  height: 18px;
  overflow: hidden;
  border: 1px solid #d8deea;
  border-radius: 999px;
  background: #edf1f7;
}

.bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light));
}

.bar-1 { background: linear-gradient(90deg, #1a3a6b, #2563a8); }
.bar-2 { background: linear-gradient(90deg, #1a7a45, #42a168); }
.bar-3 { background: linear-gradient(90deg, #6b4f1a, #b7832f); }
.bar-4 { background: linear-gradient(90deg, #693b70, #9b5aa5); }
.bar-5 { background: linear-gradient(90deg, #165f68, #2b91a0); }
.bar-6 { background: linear-gradient(90deg, #8f2f2f, #c45a4f); }
.bar-7 { background: linear-gradient(90deg, #1f5a46, #6b8f71); }

.subsection-label {
  margin: 18px 0 10px;
  color: var(--color-primary);
  font-size: 14px;
  font-weight: 800;
}

.table-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin: 10px 0 14px;
}

.table-toolbar label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 700;
}

select,
input[type="search"] {
  min-height: 34px;
  max-width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #ffffff;
  color: var(--color-text);
  padding: 0 10px;
  font: inherit;
}

.search-label {
  flex: 1 1 280px;
}

.search-label input {
  width: 100%;
}

.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 10px;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}

.data-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--color-surface);
  color: var(--color-primary);
  cursor: pointer;
  white-space: nowrap;
}

.data-table tbody tr.clickable {
  cursor: pointer;
}

.data-table tbody tr.clickable:hover {
  background: #f8fafc;
}

.detail-row td {
  padding: 0;
  background: #fbfcfe;
}

.detail-panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.2s ease;
}

.detail-row.open .detail-panel {
  max-height: 520px;
}

.detail-content {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px;
}

.detail-content div,
.case-detail-content div {
  min-width: 0;
}

.detail-content strong,
.case-detail-content strong {
  display: block;
  margin-bottom: 4px;
  color: var(--color-primary);
}

.detail-content pre,
.case-detail-content pre {
  max-height: 180px;
  overflow: auto;
  margin: 0;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #ffffff;
  color: var(--color-text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

code {
  padding: 1px 4px;
  border-radius: 4px;
  background: #edf1f7;
  color: var(--color-primary);
}

.status-badge {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  border-radius: 6px;
  padding: 2px 7px;
  font-size: 12px;
  font-weight: 750;
}

.issue-grid {
  align-items: start;
}

.issue-panel {
  background: #ffffff;
}

.issue-item {
  padding: 12px 0;
  border-top: 1px solid var(--color-border);
}

.issue-item:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.issue-item div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.issue-item span,
.issue-item small,
.section-note,
.empty-state {
  color: var(--color-text-muted);
}

.issue-item strong {
  display: block;
  margin-top: 8px;
}

.issue-item p {
  margin: 6px 0;
}

.trace-graph {
  min-height: 440px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fbfcfe;
  overflow-x: auto;
}

.trace-graph svg {
  display: block;
  width: 100%;
  min-width: 760px;
  height: 440px;
}

.trace-node-agent {
  fill: #dbeafe;
  stroke: var(--color-primary-light);
  stroke-width: 1.4;
}

.trace-node-tool {
  fill: #e7f0e8;
  stroke: #66856f;
  stroke-width: 1.4;
}

.trace-edge {
  fill: none;
  stroke: #798398;
  stroke-width: 1.2;
}

.trace-label {
  fill: var(--color-text-muted);
  font-size: 12px;
}

.trace-node-label {
  fill: var(--color-text);
  font-size: 12px;
  font-weight: 700;
}

.truncate-cell {
  max-width: 360px;
}

.small-button,
.page-button {
  min-height: 30px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #ffffff;
  color: var(--color-primary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 750;
}

.small-button:hover,
.page-button:hover,
.page-button.active {
  background: var(--color-primary);
  color: #ffffff;
}

.case-detail-content {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px;
}

.pagination {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
  margin-top: 12px;
}

.artifact-links {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.artifact-link {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 6px 9px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #ffffff;
  text-decoration: none;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.artifact-link.disabled {
  color: #9aa3b2;
  background: #f1f3f6;
  cursor: not-allowed;
}

.compact {
  margin: 4px 0;
}

.muted-small {
  margin-top: 4px;
  color: var(--color-text-muted);
  font-size: 12px;
}

@media (max-width: 900px) {
  .hero-section,
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-copy {
    grid-column: 1 / -1;
  }
}

@media (max-width: 768px) {
  .page-shell {
    width: min(100% - 20px, 1200px);
  }

  section {
    padding: 16px;
  }

  h1 {
    font-size: 30px;
  }

  .metric-grid,
  .systems-grid,
  .coverage-grid,
  .chart-grid,
  .issue-grid,
  .artifact-grid,
  .detail-content,
  .case-detail-content,
  .artifact-links {
    grid-template-columns: 1fr;
  }

  .coverage-row,
  .count-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .coverage-value,
  .count-value {
    text-align: left;
  }

  .method-flow {
    flex-direction: column;
  }

  .flow-arrow {
    justify-content: center;
    transform: rotate(90deg);
  }
}
"""


APP_JS = r"""
const DATA = window.MASENTINEL_DATA || { summary: {}, systems: [] };

const state = {
  faultSort: { key: 'severity', dir: 'desc' },
  casePage: 1,
  casesPerPage: 20
};

document.addEventListener('DOMContentLoaded', () => {
  initScrollSpy();
  initFaultTable();
  initTraceGraph();
  initTestcaseExplorer();
});

function allFaults() {
  return DATA.systems.flatMap(system => system.faults || []);
}

function allCases() {
  return DATA.systems.flatMap(system => system.testcases || []);
}

function uniqueValues(rows, key) {
  return [...new Set(rows.map(row => row[key]).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
}

function fillSelect(select, values) {
  if (!select) return;
  const current = select.value;
  while (select.options.length > 1) select.remove(1);
  values.forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = decodeEntities(value);
    select.appendChild(option);
  });
  select.value = values.includes(current) ? current : '';
}

function initFaultTable() {
  const rows = allFaults();
  fillSelect(document.getElementById('fault-severity-filter'), uniqueValues(rows, 'severity'));
  fillSelect(document.getElementById('fault-layer-filter'), uniqueValues(rows, 'layer'));

  ['fault-severity-filter', 'fault-layer-filter'].forEach(id => {
    const element = document.getElementById(id);
    if (element) element.addEventListener('change', renderFaultTable);
  });

  document.querySelectorAll('#fault-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.faultSort.key === key) {
        state.faultSort.dir = state.faultSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.faultSort = { key, dir: 'asc' };
      }
      renderFaultTable();
    });
  });

  renderFaultTable();
}

function renderFaultTable() {
  const tbody = document.getElementById('fault-table-body');
  if (!tbody) return;
  const severity = document.getElementById('fault-severity-filter')?.value || '';
  const layer = document.getElementById('fault-layer-filter')?.value || '';
  let rows = allFaults().filter(row => (!severity || row.severity === severity) && (!layer || row.layer === layer));
  const key = state.faultSort.key;
  const dir = state.faultSort.dir === 'asc' ? 1 : -1;
  rows = rows.slice().sort((a, b) => compareValues(a[key], b[key]) * dir);
  tbody.innerHTML = rows.map((row, index) => faultRowHtml(row, index)).join('') || `<tr><td colspan="8">N/A</td></tr>`;
  tbody.querySelectorAll('tr.fault-row').forEach(row => {
    row.addEventListener('click', () => toggleDetailRow(row.nextElementSibling));
  });
}

function faultRowHtml(row, index) {
  const detailId = `fault-detail-${index}`;
  return `
    <tr class="clickable fault-row" aria-controls="${detailId}">
      <td><code>${row.fault_id || 'N/A'}</code></td>
      <td><code>${row.case_id || 'N/A'}</code></td>
      <td>${row.layer || 'N/A'}</td>
      <td>${row.fault_type || 'N/A'}</td>
      <td><code>${row.failure_code || 'N/A'}</code></td>
      <td>${statusBadge(row.severity || 'unknown')}</td>
      <td>${row.confidence || 'N/A'}</td>
      <td>${row.summary || 'N/A'}</td>
    </tr>
    <tr id="${detailId}" class="detail-row">
      <td colspan="8">
        <div class="detail-panel">
          <div class="detail-content">
            ${detailBlock('root_cause', row.root_cause)}
            ${detailBlock('suggested_fix', row.suggested_fix)}
            ${detailBlock('evidence', row.evidence)}
            ${detailBlock('reproduction', row.reproduction)}
          </div>
        </div>
      </td>
    </tr>
  `;
}

function detailBlock(title, value) {
  return `<div><strong>${title}</strong><pre>${value || 'N/A'}</pre></div>`;
}

function toggleDetailRow(row) {
  if (!row) return;
  row.classList.toggle('open');
}

function compareValues(a, b) {
  const na = Number(a);
  const nb = Number(b);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
  return String(a || '').localeCompare(String(b || ''));
}

function statusBadge(value) {
  const normalized = String(value || 'neutral').toLowerCase();
  let klass = 'neutral';
  if (['passed', 'pass', 'success', 'high'].includes(normalized)) klass = normalized === 'high' ? 'failed' : 'passed';
  if (['failed', 'fail', 'timeout', 'error', 'critical'].includes(normalized)) klass = 'failed';
  if (['medium', 'warning', 'suspected'].includes(normalized)) klass = 'warning';
  return `<span class="status-badge ${klass}">${value || 'N/A'}</span>`;
}

function initTraceGraph() {
  const select = document.getElementById('trace-system-select');
  if (select) {
    select.addEventListener('change', () => renderTraceGraph(select.value));
    renderTraceGraph(select.value || DATA.systems[0]?.system_id);
  } else {
    renderTraceGraph(DATA.systems[0]?.system_id);
  }
}

function renderTraceGraph(systemId) {
  const container = document.getElementById('trace-graph');
  if (!container) return;
  const system = DATA.systems.find(item => item.system_id === systemId) || DATA.systems[0];
  const graph = system?.trace_graph || { nodes: [], edges: [] };
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  if (!nodes.length) {
    container.innerHTML = `<p class="empty-state" style="padding: 18px;">N/A</p>`;
    return;
  }

  const agents = nodes.filter(node => node.type === 'agent');
  const tools = nodes.filter(node => node.type === 'tool');
  const others = nodes.filter(node => node.type !== 'agent' && node.type !== 'tool');
  const leftNodes = agents.length ? agents : nodes;
  const rightNodes = tools.length ? tools.concat(others) : others;
  const width = 1000;
  const height = Math.max(420, Math.max(leftNodes.length, rightNodes.length || 1) * 74 + 80);
  const positions = {};

  leftNodes.forEach((node, i) => {
    positions[node.id] = { x: 170, y: 70 + i * 74, type: node.type || 'agent' };
  });
  rightNodes.forEach((node, i) => {
    positions[node.id] = { x: 720, y: 70 + i * 74, type: node.type || 'tool' };
  });
  nodes.forEach((node, i) => {
    if (!positions[node.id]) {
      positions[node.id] = { x: 445, y: 70 + i * 58, type: node.type || 'unknown' };
    }
  });

  const edgeSvg = edges.map((edge, i) => {
    const source = positions[edge.source];
    const target = positions[edge.target];
    if (!source || !target) return '';
    const midX = (source.x + target.x) / 2;
    const yOffset = source.y === target.y ? 0 : (i % 3 - 1) * 8;
    const path = `M ${source.x + 85} ${source.y} L ${midX} ${source.y + yOffset} L ${midX} ${target.y + yOffset} L ${target.x - 85} ${target.y}`;
    const labelX = midX + 8;
    const labelY = (source.y + target.y) / 2 - 4 + yOffset;
    return `<path class="trace-edge" d="${path}" marker-end="url(#arrow)"></path><text class="trace-label" x="${labelX}" y="${labelY}">${edge.source || ''} → ${edge.target || ''} (${edge.count || 1})</text>`;
  }).join('');

  const nodeSvg = nodes.map(node => {
    const pos = positions[node.id];
    const label = truncateMiddle(node.id || 'N/A', 26);
    if (pos.type === 'tool') {
      return `<ellipse class="trace-node-tool" cx="${pos.x}" cy="${pos.y}" rx="96" ry="25"></ellipse><text class="trace-node-label" x="${pos.x}" y="${pos.y + 4}" text-anchor="middle">${label}</text>`;
    }
    return `<rect class="trace-node-agent" x="${pos.x - 96}" y="${pos.y - 24}" width="192" height="48" rx="9"></rect><text class="trace-node-label" x="${pos.x}" y="${pos.y + 4}" text-anchor="middle">${label}</text>`;
  }).join('');

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trace graph for ${system?.system_id || 'system'}">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" fill="#798398"></path>
        </marker>
      </defs>
      <text x="80" y="28" class="trace-label">Agents</text>
      <text x="672" y="28" class="trace-label">Tools / Other Nodes</text>
      ${edgeSvg}
      ${nodeSvg}
    </svg>
  `;
}

function initTestcaseExplorer() {
  const rows = allCases();
  fillSelect(document.getElementById('case-type-filter'), uniqueValues(rows, 'type'));
  fillSelect(document.getElementById('case-status-filter'), uniqueValues(rows, 'status'));
  fillSelect(document.getElementById('case-failure-filter'), uniqueValues(rows, 'failure_code'));

  ['case-type-filter', 'case-status-filter', 'case-failure-filter', 'case-search'].forEach(id => {
    const element = document.getElementById(id);
    if (!element) return;
    const eventName = element.tagName === 'INPUT' ? 'input' : 'change';
    element.addEventListener(eventName, () => {
      state.casePage = 1;
      renderCases();
    });
  });

  renderCases();
}

function filteredCases() {
  const type = document.getElementById('case-type-filter')?.value || '';
  const status = document.getElementById('case-status-filter')?.value || '';
  const failure = document.getElementById('case-failure-filter')?.value || '';
  const search = (document.getElementById('case-search')?.value || '').toLowerCase();
  return allCases().filter(row => {
    if (type && row.type !== type) return false;
    if (status && row.status !== status) return false;
    if (failure && row.failure_code !== failure) return false;
    if (!search) return true;
    return [row.system_id, row.case_id, row.type, row.status, row.failure_code, row.description, row.expected, row.actual, row.steps]
      .join(' ')
      .toLowerCase()
      .includes(search);
  });
}

function renderCases() {
  const tbody = document.getElementById('case-table-body');
  if (!tbody) return;
  const rows = filteredCases();
  const totalPages = Math.max(1, Math.ceil(rows.length / state.casesPerPage));
  state.casePage = Math.min(Math.max(state.casePage, 1), totalPages);
  const start = (state.casePage - 1) * state.casesPerPage;
  const pageRows = rows.slice(start, start + state.casesPerPage);
  tbody.innerHTML = pageRows.map((row, index) => caseRowHtml(row, start + index)).join('') || `<tr><td colspan="5">N/A</td></tr>`;
  tbody.querySelectorAll('tr.case-row').forEach(row => {
    row.addEventListener('click', event => {
      if (event.target.tagName === 'BUTTON') return;
      toggleDetailRow(row.nextElementSibling);
    });
  });
  tbody.querySelectorAll('.case-toggle').forEach(button => {
    button.addEventListener('click', event => {
      event.stopPropagation();
      const row = button.closest('tr');
      toggleDetailRow(row?.nextElementSibling);
    });
  });
  renderPagination(totalPages);
}

function caseRowHtml(row, index) {
  const detailId = `case-detail-${index}`;
  return `
    <tr class="clickable case-row" aria-controls="${detailId}">
      <td><code>${row.case_id || 'N/A'}</code><div class="muted-small">${row.system_id || 'N/A'}</div></td>
      <td>${row.type || 'N/A'}</td>
      <td>${statusBadge(row.status || 'N/A')}</td>
      <td><code>${row.failure_code || 'N/A'}</code></td>
      <td class="truncate-cell">${preview(row.description || 'N/A', 180)} <button type="button" class="small-button case-toggle">expand</button></td>
    </tr>
    <tr id="${detailId}" class="detail-row">
      <td colspan="5">
        <div class="detail-panel">
          <div class="case-detail-content">
            ${detailBlock('description', row.description)}
            ${detailBlock('expected', row.expected)}
            ${detailBlock('actual', row.actual)}
            ${detailBlock('steps', row.steps)}
          </div>
        </div>
      </td>
    </tr>
  `;
}

function renderPagination(totalPages) {
  const container = document.getElementById('case-pagination');
  if (!container) return;
  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }
  const buttons = [];
  for (let page = 1; page <= totalPages; page += 1) {
    buttons.push(`<button type="button" class="page-button ${page === state.casePage ? 'active' : ''}" data-page="${page}">${page}</button>`);
  }
  container.innerHTML = buttons.join('');
  container.querySelectorAll('button').forEach(button => {
    button.addEventListener('click', () => {
      state.casePage = Number(button.dataset.page) || 1;
      renderCases();
    });
  });
}

function initScrollSpy() {
  const links = [...document.querySelectorAll('.nav-link')];
  const sections = [...document.querySelectorAll('.observed-section')];
  if (!('IntersectionObserver' in window) || !sections.length) return;
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      links.forEach(link => link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`));
    });
  }, { rootMargin: '-35% 0px -55% 0px', threshold: 0.01 });
  sections.forEach(section => observer.observe(section));
}

function preview(value, maxLength) {
  const text = String(value || 'N/A');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function truncateMiddle(value, maxLength) {
  const text = String(value || 'N/A');
  if (text.length <= maxLength) return text;
  const keep = Math.floor((maxLength - 3) / 2);
  return `${text.slice(0, keep)}...${text.slice(-keep)}`;
}

function decodeEntities(value) {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = String(value || '');
  return textarea.value;
}
"""


if __name__ == "__main__":
    main()
