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
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/results`
- `GET /api/runs/{run_id}/trace?case_id=xxx`
- `GET /api/runs/{run_id}/coverage`
- `GET /api/reports/{system_id}`
- `GET /api/reports/{system_id}/file/{filename}`
- `GET /api/bugs?project_id=xxx`
- `PUT /api/bugs/{id}`

Bug status/severity updates are stored in memory only for the demo and do not mutate `faults.json`.
