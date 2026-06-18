from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.repository import (
    get_coverage,
    get_faults,
    get_oracle_results,
    get_profile,
    get_run_summary,
    list_reports,
    read_report_text,
    get_testcases,
    get_trace,
    list_system_ids,
    project_summary,
)
from backend.jobs import create_run_job, get_job, list_configured_systems, list_jobs, validate_system_runtime


app = FastAPI(title="MASentinel Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Demo simplification: bug status/severity changes are stored in memory only.
# Restarting the API process resets these overrides and never mutates faults.json.
BUG_STATE: dict[str, dict[str, Any]] = {}


def ensure_project(system_id: str) -> None:
    if system_id not in list_system_ids():
        raise HTTPException(status_code=404, detail=f"Unknown system_id: {system_id}")


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    by_id = {item["id"]: item for item in list_configured_systems()}
    for system_id in list_system_ids():
        by_id[system_id] = {**by_id.get(system_id, {}), **project_summary(system_id)}
    return list(by_id.values())


@app.get("/api/runtime/{system_id}/validate")
def validate_runtime(system_id: str) -> dict[str, Any]:
    errors = validate_system_runtime(system_id)
    return {"system_id": system_id, "runnable": not errors, "errors": errors}


@app.get("/api/projects/{system_id}")
def get_project(system_id: str) -> dict[str, Any]:
    ensure_project(system_id)
    return get_profile(system_id)


@app.get("/api/projects/{system_id}/testcases")
def list_testcases(system_id: str) -> list[dict[str, Any]]:
    ensure_project(system_id)
    return get_testcases(system_id)


@app.post("/api/runs")
def create_run(payload: dict[str, Any]) -> dict[str, Any]:
    system_id = str(payload.get("system_id") or payload.get("project_id") or "").strip()
    if not system_id:
        raise HTTPException(status_code=400, detail="system_id or project_id is required")
    try:
        job = create_run_job(
            system_id,
            agentic=bool(payload.get("agentic", False)),
            clean_output=bool(payload.get("clean_output", False)),
            no_human=bool(payload.get("no_human", True)),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job.snapshot()


@app.get("/api/jobs")
def get_jobs() -> list[dict[str, Any]]:
    return [job.snapshot() for job in list_jobs()]


@app.get("/api/jobs/{job_id}")
def get_run_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return job.snapshot()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    ensure_project(run_id)
    testcases = get_testcases(run_id)
    oracle_results = get_oracle_results(run_id)
    run_summary = get_run_summary(run_id)
    passed = len([item for item in oracle_results if item.get("passed") is True])
    failed = len([item for item in oracle_results if item.get("passed") is False])
    total = len(testcases)
    if oracle_results:
        if total == 0:
            total = len(oracle_results)
    elif run_summary:
        passed = len([item for item in run_summary if item.get("status") == "passed"])
        failed = len(run_summary) - passed
        total = len(run_summary)
    if total and passed + failed < total:
        failed = total - passed
    return {
        "run_id": run_id,
        "system_id": run_id,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / total) if total else 0,
    }


@app.get("/api/runs/{run_id}/results")
def get_run_results(run_id: str) -> list[dict[str, Any]]:
    ensure_project(run_id)
    testcases = get_testcases(run_id)
    oracle_by_case = {str(item.get("case_id")): item for item in get_oracle_results(run_id)}
    summary_by_case = {str(item.get("case_id")): item for item in get_run_summary(run_id)}
    rows: list[dict[str, Any]] = []
    for testcase in testcases:
        case_id = str(testcase.get("case_id", ""))
        oracle = oracle_by_case.get(case_id, {})
        summary = summary_by_case.get(case_id, {})
        process_passed = summary.get("status") == "passed" if summary else None
        oracle_passed = oracle.get("passed")
        rows.append(
            {
                **testcase,
                "oracle_result": oracle,
                "run_trace": summary,
                "passed": oracle_passed if oracle_passed is not None else process_passed,
                "failures": oracle.get("failures", []),
            }
        )
    if not rows and summary_by_case:
        for case_id, summary in summary_by_case.items():
            rows.append(
                {
                    "case_id": case_id,
                    "system_id": run_id,
                    "case_type": "executed",
                    "objective": summary.get("final_output") or "",
                    "run_trace": summary,
                    "passed": summary.get("status") == "passed",
                    "failures": [],
                }
            )
    return rows


@app.get("/api/runs/{run_id}/trace")
def get_run_trace(run_id: str, case_id: str = Query(...)) -> list[dict[str, Any]]:
    ensure_project(run_id)
    trace = get_trace(run_id, case_id)
    events = trace.get("events", [])
    return events if isinstance(events, list) else []


@app.get("/api/runs/{run_id}/coverage")
def get_run_coverage(run_id: str) -> dict[str, Any]:
    ensure_project(run_id)
    return get_coverage(run_id)


@app.get("/api/reports/{system_id}")
def get_reports(system_id: str) -> dict[str, Any]:
    ensure_project(system_id)
    reports = list_reports(system_id)
    previews: dict[str, str] = {}
    for report in reports:
        name = str(report["name"])
        if name in {"report.html", "dashboard.html", "report.md", "fault_report.md", "故障报告.md"}:
            previews[name] = read_report_text(system_id, name)
    return {"system_id": system_id, "reports": reports, "previews": previews}


@app.get("/api/reports/{system_id}/file/{filename}")
def get_report_file(system_id: str, filename: str):
    ensure_project(system_id)
    try:
        text = read_report_text(system_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Report not found: {filename}") from exc
    if filename.endswith(".html"):
        return HTMLResponse(text)
    return PlainTextResponse(text)


@app.get("/api/bugs")
def list_bugs(project_id: str = Query(...)) -> list[dict[str, Any]]:
    ensure_project(project_id)
    bugs: list[dict[str, Any]] = []
    for fault in get_faults(project_id):
        fault_id = str(fault.get("fault_id", ""))
        override = BUG_STATE.get(fault_id, {})
        bugs.append(
            {
                "id": fault_id,
                "title": fault.get("summary"),
                "bug_type": fault.get("fault_type"),
                "severity": override.get("severity", fault.get("severity")),
                "status": override.get("status", "Open"),
                "description": fault.get("summary"),
                "evidence": fault.get("evidence"),
                "case_id": fault.get("case_id"),
                "layer": fault.get("layer"),
                "failure_code": fault.get("failure_code"),
                "confidence": fault.get("confidence"),
            }
        )
    return bugs


@app.put("/api/bugs/{bug_id}")
def update_bug(bug_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    current = BUG_STATE.setdefault(bug_id, {})
    for key in ("status", "severity"):
        if key in patch:
            current[key] = patch[key]
    return {"id": bug_id, **current}
