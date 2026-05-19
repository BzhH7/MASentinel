from __future__ import annotations


def fault_detection_rate(faults: list[dict], cases_count: int) -> float:
    return 0.0 if cases_count <= 0 else round(len({f["case_id"] for f in faults}) / cases_count, 4)
