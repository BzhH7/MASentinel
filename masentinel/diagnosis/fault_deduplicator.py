from __future__ import annotations

from typing import Any


def deduplicate_faults(faults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fault in faults:
        key = (
            str(fault.get("layer", "uncertain")),
            str(fault.get("fault_type", "Unknown")),
            str(fault.get("root_cause", ""))[:160],
        )
        if key not in grouped:
            item = dict(fault)
            item["affected_cases"] = [fault.get("case_id")]
            item["duplicate_fault_ids"] = []
            grouped[key] = item
        else:
            grouped[key]["affected_cases"].append(fault.get("case_id"))
            grouped[key]["duplicate_fault_ids"].append(fault.get("fault_id"))
            grouped[key]["evidence"] = list({*(grouped[key].get("evidence", []) or []), *(fault.get("evidence", []) or [])})[:12]
            grouped[key]["confidence"] = max(float(grouped[key].get("confidence", 0) or 0), float(fault.get("confidence", 0) or 0))
            grouped[key]["evidence_strength"] = max(
                float(grouped[key].get("evidence_strength", 0) or 0),
                float(fault.get("evidence_strength", 0) or 0),
            )
            grouped[key]["root_cause_confidence"] = _stronger_root_cause_confidence(
                str(grouped[key].get("root_cause_confidence", "") or ""),
                str(fault.get("root_cause_confidence", "") or ""),
            )
            grouped[key]["diagnostic_only"] = bool(grouped[key].get("diagnostic_only")) and bool(fault.get("diagnostic_only"))
            grouped[key]["suspected_false_positive"] = grouped[key].get("suspected_false_positive", False) and fault.get("suspected_false_positive", False)
    deduped = list(grouped.values())
    for index, fault in enumerate(deduped, start=1):
        system_prefix = str(fault.get("fault_id", "SYS_FAULT")).split("_FAULT_")[0]
        fault["fault_id"] = f"{system_prefix}_FAULT_{index:03d}"
    return deduped


def _stronger_root_cause_confidence(left: str, right: str) -> str:
    rank = {"uncertain": 0, "oracle_assumption": 1, "trace_only": 2, "code_evidence": 3}
    return left if rank.get(left, 0) >= rank.get(right, 0) else right
