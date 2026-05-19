from __future__ import annotations

from pathlib import Path
from typing import Any

from masentinel.schema import RunTrace
from masentinel.utils import read_json, write_json


def update_flaky_report(traces: list[RunTrace], out_dir: str | Path) -> dict[str, Any]:
    path = Path(out_dir) / "flaky_history.json"
    history = read_json(path, {}) or {}
    for trace in traces:
        history.setdefault(trace.case_id, []).append(trace.status)
        history[trace.case_id] = history[trace.case_id][-10:]
    flaky = {
        case_id: statuses
        for case_id, statuses in history.items()
        if len(set(statuses)) > 1
    }
    report = {"history": history, "flaky_cases": flaky, "flaky_count": len(flaky)}
    write_json(path, history)
    write_json(Path(out_dir) / "flaky_report.json", report)
    return report
