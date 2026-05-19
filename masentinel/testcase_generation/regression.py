from __future__ import annotations

from pathlib import Path
from typing import Any

from masentinel.schema import TestCase, TestOracleSpec
from masentinel.utils import read_json, write_json


def load_regression_cases(system_id: str, out_dir: str | Path) -> list[TestCase]:
    pool = read_json(Path(out_dir) / "regression_pool.json", []) or []
    cases: list[TestCase] = []
    for idx, item in enumerate(pool, start=1):
        if not isinstance(item, dict) or not item.get("input"):
            continue
        cases.append(
            TestCase(
                case_id=f"{system_id}_REGRESSION_{idx:03d}",
                system_id=system_id,
                case_type="regression",
                objective=item.get("objective") or f"Reproduce {item.get('fault_type', 'previous fault')}",
                input=item["input"],
                target_requirements=list(item.get("target_requirements", [])),
                target_agents=list(item.get("target_agents", [])),
                target_tools=list(item.get("target_tools", [])),
                oracle=TestOracleSpec(must_terminate=True, max_turns=int(item.get("max_turns", 15))),
                metadata={"derived_from": item.get("case_id"), "source": "regression_pool"},
            )
        )
    return cases


def update_regression_pool(faults: list[dict[str, Any]], out_dir: str | Path, limit: int = 30) -> list[dict[str, Any]]:
    existing = read_json(Path(out_dir) / "regression_pool.json", []) or []
    pool = list(existing)
    seen = {(item.get("case_id"), item.get("input")) for item in pool if isinstance(item, dict)}
    for fault in faults:
        if fault.get("suspected_false_positive"):
            continue
        reproduction = fault.get("reproduction", {}) or {}
        key = (fault.get("case_id"), reproduction.get("input"))
        if key in seen or not reproduction.get("input"):
            continue
        pool.append(
            {
                "case_id": fault.get("case_id"),
                "fault_type": fault.get("fault_type"),
                "objective": f"Reproduce confirmed fault: {fault.get('summary', fault.get('fault_type'))}",
                "input": reproduction.get("input"),
                "max_turns": 15,
            }
        )
        seen.add(key)
    pool = pool[-limit:]
    write_json(Path(out_dir) / "regression_pool.json", pool)
    return pool
