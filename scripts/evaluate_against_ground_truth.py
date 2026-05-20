#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SYSTEM_DIR_HINTS = {
    "system_1": "system1_iterative_coding",
    "system_2": "system2_research_agents",
    "system_3": "system3_financial_analysis",
}

GT_MATCHERS = {
    "GT-S1-001": {"codes": {"MARKDOWN_ARTIFACT_CORRUPTION"}, "keywords": {"fence", "markdown", "script_v1", "artifact"}},
    "GT-S1-002": {"codes": {"RESUME_STATE_INCOMPLETE"}, "keywords": {"resume", "script_v1", "masterplan", "comments_v1"}},
    "GT-S1-003": {"codes": {"ARTIFACT_SCHEMA_MISMATCH"}, "keywords": {"artifact_schema_mismatch", "comments_v", ".txt", ".log"}},
    "GT-S1-004": {"codes": {"FILESYSTEM_ESCAPE"}, "keywords": {"path", "escape", "project", "../"}},
    "GT-S2-001": {"codes": {"HUMAN_INPUT_REQUESTED"}, "keywords": {"human_input_mode", "human input", "always"}},
    "GT-S2-002": {"codes": {"VIEW_PARAMETER_IGNORED", "PAGINATION_NOT_FOLLOWED"}, "keywords": {"airtable", "view", "offset", "pagination"}},
    "GT-S2-003": {"codes": {"TOOL_UNSTRUCTURED_ERROR", "TOOL_RETURNED_NONE", "HTTP_STATUS_NOT_CHECKED", "TOOL_RAW_HTTP_ERROR"}, "keywords": {"status", "401", "structured", "none"}},
    "GT-S2-004": {"codes": {"SPEAKER_SELECTION_LOOP", "MISSING_TOOL_CALL"}, "keywords": {"speaker", "routing", "groupchat", "tool"}},
    "GT-S2-005": {"codes": {"SCALABLE_BUDGET_EXCEEDED"}, "keywords": {"max_round", "budget", "record", "round"}},
    "GT-S3-001": {"codes": {"MESSAGE_HANDOFF_TERMINATE_ONLY", "MESSAGE_HANDOFF_EMPTY"}, "keywords": {"terminate", "handoff", "last_message", "analysis"}},
    "GT-S3-002": {"codes": {"PARTIAL_METRIC_ZEROED"}, "keywords": {"metric", "revenue", "net income", "zero"}},
    "GT-S3-003": {"codes": {"NUMERIC_SIGN_CONVENTION_ERROR"}, "keywords": {"var_95", "drawdown", "negative", "sign"}},
    "GT-S3-004": {"codes": {"DOCUMENTED_ENTRYPOINT_BROKEN"}, "keywords": {"entrypoint", "src.main", "import", "constructor"}},
    "GT-S3-005": {"codes": {"DOCUMENTED_CLI_COMMAND_MISSING"}, "keywords": {"interactive", "portfolio", "invalid choice"}},
    "GT-S3-006": {"codes": {"AUTOGEN_WIRING_MISSING"}, "keywords": {"orchestrator", "factory", "agent", "wiring"}},
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MASentinel outputs against ground-truth defect metadata.")
    parser.add_argument("--ground-truth", default="../analysis/ground_truth_defects.json")
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--out", default="outputs/ground_truth_alignment.md")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    ground_truth_path = Path(args.ground_truth)
    outputs_dir = Path(args.outputs)
    gt_items = _read_json(ground_truth_path, [])
    rows = []
    for item in gt_items:
        rows.append(_evaluate_item(item, outputs_dir))
    markdown = _to_markdown(rows, ground_truth_path, outputs_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[MASentinel][ground-truth] wrote {out_path} strict_tp={sum(1 for row in rows if row['status']=='strict_match')} partial={sum(1 for row in rows if row['status']=='partial_match')} missed={sum(1 for row in rows if row['status']=='missed')}")


def _evaluate_item(item: dict[str, Any], outputs_dir: Path) -> dict[str, Any]:
    defect_id = str(item.get("defect_id", ""))
    system = str(item.get("system", ""))
    faults = _load_faults(outputs_dir / SYSTEM_DIR_HINTS.get(system, system) / "faults.json")
    matcher = GT_MATCHERS.get(defect_id, {"codes": set(), "keywords": set()})
    strict = []
    partial = []
    for fault in faults:
        if fault.get("suspected_false_positive"):
            continue
        code = str(fault.get("failure_code", ""))
        haystack = _fault_text(fault)
        code_match = code in matcher["codes"]
        keyword_score = sum(1 for keyword in matcher["keywords"] if keyword.lower() in haystack)
        if code_match:
            strict.append(fault)
        elif keyword_score >= _partial_threshold(defect_id):
            partial.append(fault)
    if strict:
        status = "strict_match"
        matches = strict
    elif partial:
        status = "partial_match"
        matches = partial
    else:
        status = "missed"
        matches = []
    return {
        "defect_id": defect_id,
        "system": system,
        "defect_type": item.get("defect_type"),
        "severity": item.get("severity"),
        "status": status,
        "matched_faults": [
            {
                "fault_id": fault.get("fault_id"),
                "case_id": fault.get("case_id"),
                "failure_code": fault.get("failure_code"),
                "fault_type": fault.get("fault_type"),
                "confidence": fault.get("confidence"),
            }
            for fault in matches[:3]
        ],
    }


def _load_faults(path: Path) -> list[dict[str, Any]]:
    value = _read_json(path, [])
    return value if isinstance(value, list) else []


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _fault_text(fault: dict[str, Any]) -> str:
    parts = [
        fault.get("failure_code"),
        fault.get("fault_type"),
        fault.get("summary"),
        fault.get("root_cause"),
        fault.get("suggested_fix"),
        " ".join(str(item) for item in fault.get("evidence", []) or []),
    ]
    return "\n".join(str(part or "") for part in parts).lower()


def _partial_threshold(defect_id: str) -> int:
    if defect_id in {"GT-S1-003", "GT-S2-005"}:
        return 4
    return 2


def _to_markdown(rows: list[dict[str, Any]], gt_path: Path, outputs_dir: Path) -> str:
    strict = sum(1 for row in rows if row["status"] == "strict_match")
    partial = sum(1 for row in rows if row["status"] == "partial_match")
    missed = sum(1 for row in rows if row["status"] == "missed")
    lines = [
        "# Ground Truth Alignment",
        "",
        f"- Ground truth: `{gt_path}`",
        f"- Outputs: `{outputs_dir}`",
        f"- Strict matches: {strict}",
        f"- Partial matches: {partial}",
        f"- Missed: {missed}",
        "",
        "| Defect | System | Type | Severity | Status | Matched Faults |",
        "|--------|--------|------|----------|--------|----------------|",
    ]
    for row in rows:
        matches = ", ".join(
            f"`{fault.get('fault_id')}`/{fault.get('failure_code')}" for fault in row.get("matched_faults", [])
        )
        lines.append(
            f"| `{row['defect_id']}` | {row['system']} | {row.get('defect_type', '')} | {row.get('severity', '')} | "
            f"{row['status']} | {matches or '-'} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
