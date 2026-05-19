from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from masentinel.schema import RunTrace, TraceEvent
from masentinel.utils import utc_now_iso, write_json


class TraceRecorder:
    def __init__(self, case_id: str, system_id: str) -> None:
        self.case_id = case_id
        self.system_id = system_id
        self.started_at = utc_now_iso()
        self.events: list[TraceEvent] = []
        self.turn_count = 0

    def record_message(self, sender: str | None, receiver: str | None, content: str | None, turn: int | None = None) -> None:
        self.turn_count = max(self.turn_count, turn or self.turn_count + 1)
        self.events.append(TraceEvent(type="message", timestamp=time.time(), turn=turn or self.turn_count, sender=sender, receiver=receiver, content=content))

    def record_tool_call(self, tool: str, arguments: dict[str, Any] | None = None) -> None:
        self.events.append(TraceEvent(type="tool_call", timestamp=time.time(), tool=tool, arguments=arguments or {}))

    def record_tool_result(self, tool: str, result_preview: str | None = None) -> None:
        self.events.append(TraceEvent(type="tool_result", timestamp=time.time(), tool=tool, result_preview=result_preview))

    def record_tool_error(self, tool: str, error_type: str, error_message: str) -> None:
        self.events.append(TraceEvent(type="tool_error", timestamp=time.time(), tool=tool, error_type=error_type, error_message=error_message))

    def record_exception(self, error_type: str, error_message: str) -> None:
        self.events.append(TraceEvent(type="exception", timestamp=time.time(), error_type=error_type, error_message=error_message))

    def finalize(
        self,
        status: str = "passed",
        terminated: bool = True,
        timeout: bool = False,
        final_output: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        returncode: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RunTrace:
        return RunTrace(
            case_id=self.case_id,
            system_id=self.system_id,
            started_at=self.started_at,
            ended_at=utc_now_iso(),
            status=status,
            terminated=terminated,
            timeout=timeout,
            turn_count=self.turn_count,
            events=self.events,
            final_output=final_output,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            metadata=metadata or {},
        )

    def save(self, path: str | Path, trace: RunTrace) -> None:
        write_json(path, trace)
