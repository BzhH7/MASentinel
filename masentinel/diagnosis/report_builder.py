from __future__ import annotations


def summarize_faults(faults: list[dict]) -> dict:
    summary = {"total": len(faults), "by_layer": {}, "by_type": {}, "suspected_false_positive": 0}
    for fault in faults:
        summary["by_layer"][fault["layer"]] = summary["by_layer"].get(fault["layer"], 0) + 1
        summary["by_type"][fault["fault_type"]] = summary["by_type"].get(fault["fault_type"], 0) + 1
        if fault.get("suspected_false_positive"):
            summary["suspected_false_positive"] += 1
    return summary
