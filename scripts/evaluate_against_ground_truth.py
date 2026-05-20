from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STRICT_CODE_HINTS = {
    "wrong_output_schema": {"MARKDOWN_ARTIFACT_CORRUPTION", "ARTIFACT_SCHEMA_MISMATCH", "OUTPUT_SCHEMA_VIOLATION"},
    "missing_state": {"RESUME_STATE_INCOMPLETE"},
    "input_validation_error": {"FILESYSTEM_ESCAPE"},
    "human_input_blocking": {"HUMAN_INPUT_REQUESTED"},
    "tool_semantics_error": {"VIEW_PARAMETER_IGNORED", "PAGINATION_NOT_FOLLOWED"},
    "tool_error_handling_missing": {"TOOL_RAW_HTTP_ERROR", "TOOL_RETURNED_NONE", "TOOL_UNSTRUCTURED_ERROR", "HTTP_STATUS_NOT_CHECKED", "RUNTIME_EXCEPTION"},
    "wrong_routing": {"SPEAKER_SELECTION_LOOP", "MISSING_MESSAGE_EDGE", "MISSING_AGENT"},
    "termination_error": {"SCALABLE_BUDGET_EXCEEDED", "TERMINATION_SIGNAL_IGNORED", "NON_TERMINATION"},
    "message_passing_error": {"MESSAGE_HANDOFF_TERMINATE_ONLY", "MESSAGE_HANDOFF_EMPTY"},
    "data_processing_error": {"PARTIAL_METRIC_ZEROED", "NUMERIC_SIGN_CONVENTION_ERROR"},
    "documented_entrypoint_broken": {"DOCUMENTED_ENTRYPOINT_BROKEN"},
    "missing_feature": {"DOCUMENTED_CLI_COMMAND_MISSING"},
    "agent_orchestration_missing": {"AUTOGEN_WIRING_MISSING"},
}

PARTIAL_CODE_HINTS = {
    "tool_error_handling_missing": {"BUSINESS_TASK_FAILED", "RUNTIME_EXCEPTION"},
    "message_passing_error": {"BUSINESS_TASK_FAILED", "MISSING_AGENT"},
    "agent_orchestration_missing": {"MISSING_AGENT", "TARGET_WORKFLOW_NOT_OBSERVED"},
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MASentinel outputs against seeded/independent ground-truth defects.")
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    ground_truth = json.loads(Path(args.ground_truth).read_text(encoding="utf-8"))
    outputs = Path(args.outputs)
    faults_by_system = _load_faults(outputs)
    rows = []
    strict_hits = 0
    partial_hits = 0
    for defect in ground_truth:
        system = str(defect.get("system", "")).replace("system_", "system")
        defect_type = str(defect.get("defect_type", ""))
        candidates = faults_by_system.get(system, []) + faults_by_system.get(_system_alias(system), [])
        strict_codes = STRICT_CODE_HINTS.get(defect_type, set())
        partial_codes = PARTIAL_CODE_HINTS.get(defect_type, set())
        strict_match = _find_match(candidates, strict_codes, defect)
        partial_match = strict_match or _find_match(candidates, partial_codes, defect)
        if strict_match:
            judgment = "TP"
            strict_hits += 1
            partial_hits += 1
            matched = strict_match
        elif partial_match:
            judgment = "Partial"
            partial_hits += 1
            matched = partial_match
        else:
            judgment = "FN"
            matched = {}
        rows.append((defect, judgment, matched))

    total = len(ground_truth)
    strict_recall = strict_hits / total if total else 0
    partial_recall = partial_hits / total if total else 0
    report = _render(rows, strict_hits, partial_hits, total, strict_recall, partial_recall)
    out_path = Path(args.out) if args.out else outputs / "ground_truth_alignment.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"wrote {out_path} strict={strict_hits}/{total} partial_adjusted={partial_hits}/{total}")


def _load_faults(outputs: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    if not outputs.exists():
        return result
    for path in outputs.glob("*/faults.json"):
        try:
            faults = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            faults = []
        result[path.parent.name] = [fault for fault in faults if isinstance(fault, dict)]
    return result


def _system_alias(system: str) -> str:
    aliases = {
        "system1": "system1_iterative_coding",
        "system2": "system2_research_agents",
        "system3": "system3_financial_analysis",
    }
    return aliases.get(system, system)


def _find_match(faults: list[dict[str, Any]], codes: set[str], defect: dict[str, Any]) -> dict[str, Any] | None:
    if not codes:
        return None
    haystack_terms = " ".join(
        str(item.get("line_or_function", "")) + " " + str(item.get("evidence", ""))
        for item in defect.get("file_locations", []) or []
        if isinstance(item, dict)
    ).lower()
    for fault in faults:
        if fault.get("suspected_false_positive"):
            continue
        if str(fault.get("failure_code")) in codes:
            return fault
        fault_text = " ".join(str(fault.get(key, "")) for key in ("fault_type", "summary", "root_cause", "suggested_fix")).lower()
        if haystack_terms and any(term in fault_text for term in _salient_terms(haystack_terms)):
            return fault
    return None


def _salient_terms(text: str) -> list[str]:
    terms = []
    for term in (
        "last_message",
        "comments_v",
        "script_v1",
        "project_name",
        "airtable",
        "pagination",
        "browserless",
        "max_round",
        "agentorchestrator",
        "interactive",
        "drawdown",
        "total revenue",
    ):
        if term in text:
            terms.append(term)
    return terms


def _render(rows: list[tuple[dict[str, Any], str, dict[str, Any]]], strict_hits: int, partial_hits: int, total: int, strict_recall: float, partial_recall: float) -> str:
    lines = [
        "# MASentinel Ground-Truth Alignment",
        "",
        f"- Strict recall: {strict_hits}/{total} = {strict_recall:.4f}",
        f"- Partial-adjusted recall: {partial_hits}/{total} = {partial_recall:.4f}",
        "",
        "| Defect ID | System | Type | Judgment | Matched Fault | Failure Code | Evidence |",
        "|-----------|--------|------|----------|---------------|--------------|----------|",
    ]
    for defect, judgment, fault in rows:
        lines.append(
            f"| {defect.get('defect_id', '')} | {defect.get('system', '')} | {defect.get('defect_type', '')} | "
            f"{judgment} | {fault.get('fault_id', 'N/A')} | {fault.get('failure_code', 'N/A')} | "
            f"{_clean(fault.get('summary', '')) if fault else 'No matching MASentinel fault'} |"
        )
    return "\n".join(lines) + "\n"


def _clean(value: Any) -> str:
    text = " ".join(str(value or "").split())
    text = text.replace("|", "/")
    return text[:220]


if __name__ == "__main__":
    main()
