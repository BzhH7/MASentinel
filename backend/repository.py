from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = ROOT / "outputs"


def read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def system_dir(system_id: str) -> Path:
    return OUTPUTS_DIR / system_id


def list_system_ids() -> list[str]:
    if not OUTPUTS_DIR.is_dir():
        return []
    ids: list[str] = []
    for child in sorted(OUTPUTS_DIR.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir() and (child / "profile.json").is_file():
            ids.append(child.name)
    return ids


def get_profile(system_id: str) -> dict[str, Any]:
    return read_json(system_dir(system_id) / "profile.json", {})


def get_testcases(system_id: str) -> list[dict[str, Any]]:
    data = read_json(system_dir(system_id) / "testcases.json", [])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("testcases", "cases", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def get_oracle_results(system_id: str) -> list[dict[str, Any]]:
    data = read_json(system_dir(system_id) / "oracle_results.json", [])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        value = data.get("results") or data.get("items")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def get_run_summary(system_id: str) -> list[dict[str, Any]]:
    data = read_json(system_dir(system_id) / "runs" / "run_summary.json", [])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("runs", "results", "cases", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def get_coverage(system_id: str) -> dict[str, Any]:
    return read_json(system_dir(system_id) / "coverage.json", {})


def get_faults(system_id: str) -> list[dict[str, Any]]:
    data = read_json(system_dir(system_id) / "faults.json", [])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        value = data.get("faults") or data.get("items")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def get_trace(system_id: str, case_id: str) -> dict[str, Any]:
    traces_dir = system_dir(system_id) / "runs" / "traces"
    candidates = [
        traces_dir / f"{system_id}_{case_id}.json",
        traces_dir / f"{case_id}.json",
    ]
    for candidate in candidates:
        data = read_json(candidate, None)
        if isinstance(data, dict):
            return data
    if traces_dir.is_dir():
        for file in sorted(traces_dir.glob("*.json")):
            if case_id in file.stem:
                data = read_json(file, None)
                if isinstance(data, dict):
                    return data
    return {}


def project_summary(system_id: str) -> dict[str, Any]:
    profile = get_profile(system_id)
    coverage = get_coverage(system_id)
    testcases = get_testcases(system_id)
    faults = get_faults(system_id)
    return {
        "id": system_id,
        "system_id": profile.get("system_id", system_id),
        "root_path": profile.get("root_path"),
        "doc_path": profile.get("doc_path"),
        "entrypoint": profile.get("entrypoint"),
        "agents_count": len(profile.get("agents", []) or []),
        "tools_count": len(profile.get("tools", []) or []),
        "requirements_count": len(profile.get("requirements", []) or []),
        "testcases_count": len(testcases),
        "faults_count": len(faults),
        "mascov": coverage.get("mascov"),
    }


REPORT_FILES = (
    "report.html",
    "dashboard.html",
    "report.md",
    "fault_report.md",
    "故障报告.md",
    "patch_suggestions.md",
    "coverage.md",
)


def list_reports(system_id: str) -> list[dict[str, Any]]:
    root = system_dir(system_id)
    reports: list[dict[str, Any]] = []
    for name in REPORT_FILES:
        path = root / name
        if not path.is_file():
            continue
        reports.append(
            {
                "name": name,
                "type": report_type(name),
                "size": path.stat().st_size,
                "url": f"/api/reports/{system_id}/file/{name}",
            }
        )
    return reports


def report_type(name: str) -> str:
    if name.endswith(".html"):
        return "html"
    if name.endswith(".md"):
        return "markdown"
    return "file"


def read_report_text(system_id: str, name: str) -> str:
    path = safe_report_path(system_id, name)
    return path.read_text(encoding="utf-8")


def safe_report_path(system_id: str, name: str) -> Path:
    if name not in REPORT_FILES:
        raise FileNotFoundError(name)
    path = (system_dir(system_id) / name).resolve()
    root = system_dir(system_id).resolve()
    if root not in path.parents and path != root:
        raise FileNotFoundError(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    return path
