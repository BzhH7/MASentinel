from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from masentinel.runner.case_runner import CaseRunner
from masentinel.schema import RunTrace, TestCase
from masentinel.utils import ensure_dir, write_json


class BatchRunner:
    def __init__(self, config: dict[str, Any], out_dir: str | Path, workers: int = 4) -> None:
        self.config = config
        self.out_dir = ensure_dir(out_dir)
        self.traces_dir = ensure_dir(self.out_dir / "traces")
        self.workers = max(1, workers)

    def run(self, testcases: list[TestCase]) -> list[RunTrace]:
        traces: list[RunTrace] = []
        runner = CaseRunner(self.config, self.traces_dir)
        system_id = str(self.config.get("system_id") or "system")
        total = len(testcases)
        self._log(system_id, f"batch execution start cases={total} workers={self.workers}")
        if self.workers == 1:
            for index, case in enumerate(testcases, start=1):
                traces.append(self._run_one(runner, case, index, total, system_id))
        else:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {
                    pool.submit(self._run_one, runner, case, index, total, system_id): case
                    for index, case in enumerate(testcases, start=1)
                }
                for future in as_completed(futures):
                    traces.append(future.result())
        traces.sort(key=lambda trace: trace.case_id)
        write_json(self.out_dir / "run_summary.json", traces)
        passed = len([trace for trace in traces if trace.status == "passed"])
        self._log(system_id, f"batch execution done traces={len(traces)} passed={passed} failed={len(traces) - passed}")
        return traces

    def _run_one(self, runner: CaseRunner, case: TestCase, index: int, total: int, system_id: str) -> RunTrace:
        started = time.time()
        self._log(system_id, f"case {index}/{total} start {case.case_id} type={case.case_type}")
        trace = runner.run_case(case)
        elapsed = time.time() - started
        self._log(
            system_id,
            f"case {index}/{total} done {case.case_id} status={trace.status} "
            f"returncode={trace.returncode} timeout={trace.timeout} elapsed={elapsed:.1f}s",
        )
        return trace

    def _log(self, system_id: str, message: str) -> None:
        print(f"[MASentinel][{system_id}][runner] {message}", flush=True)
