# MASentinel Backend API

This directory is a thin FastAPI wrapper around existing MASentinel CLI outputs.
It does not rewrite or modify `masentinel/` core code.

## Start

From the MASentinel repository root:

```bash
uvicorn backend.main:app --reload --port 8000
```

If `uvicorn` or `fastapi` is missing:

```bash
python -m pip install fastapi uvicorn
```

## Demo System IDs

The API scans `outputs/<system_id>/profile.json`. Current demo candidates include:

- `system1_iterative_coding`
- `system2_research_agents`
- `system3_financial_analysis`

## Endpoints

- `GET /api/projects`
- `GET /api/projects/{id}`
- `GET /api/projects/{id}/testcases`
- `POST /api/runs`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/results`
- `GET /api/runs/{run_id}/trace?case_id=xxx`
- `GET /api/runs/{run_id}/coverage`
- `GET /api/reports/{system_id}`
- `GET /api/reports/{system_id}/file/{filename}`
- `GET /api/bugs?project_id=xxx`
- `PUT /api/bugs/{id}`

Bug status/severity updates are stored in memory only for the demo and do not mutate `faults.json`.

## Realtime Runs

`POST /api/runs` starts a background MASentinel job by resolving `system_id` / `project_id` to a matching `configs/*.yaml` file and calling the existing `run_all.run_all()` pipeline. It defaults to `clean_output=false` so existing demo artifacts are not cleared before a run; pass `clean_output=true` only when you deliberately want to rebuild that system output from scratch. Job progress can be monitored with `GET /api/jobs/{job_id}`.
