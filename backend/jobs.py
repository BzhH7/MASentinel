from __future__ import annotations

import contextlib
import io
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from masentinel.utils import load_yaml, write_text
from run_all import run_all


ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = ROOT / "configs"
OUTPUTS_DIR = ROOT / "outputs"
RUNTIME_DIR = OUTPUTS_DIR / "_backend_jobs"


@dataclass
class RunJob:
    id: str
    system_id: str
    config_path: str
    status: str = "pending"
    progress: int = 0
    logs: list[str] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "system_id": self.system_id,
            "config_path": self.config_path,
            "status": self.status,
            "progress": self.progress,
            "logs": self.logs[-200:],
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


class LogSink(io.TextIOBase):
    def __init__(self, job: RunJob) -> None:
        self.job = job
        self.buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            append_log(self.job, line)
        return len(text)

    def flush(self) -> None:
        if self.buffer:
            append_log(self.job, self.buffer)
            self.buffer = ""


JOBS: dict[str, RunJob] = {}
JOBS_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()


def create_run_job(system_id: str, *, agentic: bool = False, clean_output: bool = False, no_human: bool = True) -> RunJob:
    config_path = find_system_config(system_id)
    if config_path is None:
        raise FileNotFoundError(f"No config file found for system_id={system_id}")
    job = RunJob(id=f"job_{uuid.uuid4().hex[:12]}", system_id=system_id, config_path=str(config_path))
    with JOBS_LOCK:
        JOBS[job.id] = job
    thread = threading.Thread(
        target=run_job,
        args=(job, config_path),
        kwargs={"agentic": agentic, "clean_output": clean_output, "no_human": no_human},
        daemon=True,
    )
    thread.start()
    return job


def get_job(job_id: str) -> RunJob | None:
    with JOBS_LOCK:
        return JOBS.get(job_id)


def list_jobs() -> list[RunJob]:
    with JOBS_LOCK:
        return sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)


def find_system_config(system_id: str) -> Path | None:
    if not CONFIGS_DIR.is_dir():
        return None
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        data = load_yaml(path)
        if str(data.get("system_id") or "") == system_id:
            return path
    return None


def list_configured_systems() -> list[dict[str, Any]]:
    systems: list[dict[str, Any]] = []
    if not CONFIGS_DIR.is_dir():
        return systems
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        data = load_yaml(path)
        system_id = str(data.get("system_id") or "")
        if not system_id:
            continue
        systems.append(
            {
                "id": system_id,
                "system_id": system_id,
                "config_path": str(path),
                "root_path": data.get("root_path"),
                "entrypoint": data.get("entrypoint"),
                "adapter_type": "config",
                "status": "configured",
            }
        )
    return systems


def validate_system_runtime(system_id: str) -> list[str]:
    config_path = find_system_config(system_id)
    if config_path is None:
        return [f"No config file found for system_id={system_id}"]
    from masentinel.runner.system_adapter import load_system_config

    config = load_system_config(config_path)
    errors: list[str] = []
    for key in ("root_path", "entrypoint"):
        value = config.get(key)
        if value and not Path(str(value)).exists():
            errors.append(f"{key} does not exist: {value}")
    working_dir = (config.get("run", {}) or {}).get("working_dir")
    if working_dir and not Path(str(working_dir)).is_dir():
        errors.append(f"run.working_dir is not a directory: {working_dir}")
    return errors


def run_job(job: RunJob, system_config_path: Path, *, agentic: bool, clean_output: bool, no_human: bool) -> None:
    job.status = "running"
    job.started_at = time.time()
    job.progress = 3
    append_log(job, f"queued system_id={job.system_id}")
    with RUN_LOCK:
        try:
            append_log(job, "runtime lock acquired")
            runtime_errors = validate_system_runtime(job.system_id)
            if runtime_errors:
                raise RuntimeError("; ".join(runtime_errors))
            aggregate_config = write_single_system_config(job, system_config_path)
            job.progress = 8
            append_log(job, f"run_all config={aggregate_config}")
            sink = LogSink(job)
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                result = run_all(
                    aggregate_config,
                    agentic=agentic,
                    no_human=no_human,
                    build_site=True,
                    clean_output=clean_output,
                )
            sink.flush()
            job.result = result
            job.progress = 100
            job.status = "succeeded"
            append_log(job, "run completed")
        except Exception as exc:
            job.error = str(exc)
            job.status = "failed"
            job.progress = 100
            append_log(job, f"run failed: {exc}")
        finally:
            job.ended_at = time.time()


def write_single_system_config(job: RunJob, system_config_path: Path) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    target = RUNTIME_DIR / f"{job.id}.yaml"
    config_text = "\n".join(
        [
            "systems:",
            f"  - {system_config_path.resolve().as_posix()}",
            "",
            f"output_dir: {OUTPUTS_DIR.resolve().as_posix()}",
            "",
        ]
    )
    write_text(target, config_text)
    return target


def append_log(job: RunJob, line: str) -> None:
    clean = str(line).strip()
    if not clean:
        return
    job.logs.append(clean)
    job.progress = max(job.progress, infer_progress(clean, job.progress))


def infer_progress(line: str, current: int) -> int:
    lower = line.lower()
    if "all systems complete" in lower:
        return 100
    if "output site generated" in lower:
        return 96
    if "step 3/3" in lower or "diagnose faults" in lower:
        return 88
    if "case " in lower and (" start " in lower or " done " in lower):
        return max(current, 60)
    if "step 2/3" in lower or "execute testcases" in lower:
        return 55
    if "step 1/3" in lower or "generate testcases" in lower:
        return 35
    if "step 0/3" in lower or "analyze code" in lower:
        return 15
    return current
