from __future__ import annotations

import json
import time
from typing import Any, Callable

from masentinel.instrumentation.trace_recorder import TraceRecorder
from masentinel.schema import FaultInjectionSpec


def wrap_tool(
    tool_name: str,
    func: Callable[..., Any],
    trace_recorder: TraceRecorder,
    fault_injection: FaultInjectionSpec | None = None,
) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        trace_recorder.record_tool_call(tool_name, {"args": list(args), "kwargs": kwargs})
        try:
            if fault_injection and fault_injection.tool == tool_name:
                behavior = fault_injection.behavior
                if behavior == "raise_exception":
                    raise RuntimeError(fault_injection.exception_message or "Injected tool exception")
                if behavior == "return_none":
                    result = None
                elif behavior == "return_empty":
                    result = ""
                elif behavior == "return_invalid_json":
                    result = "{invalid json"
                elif behavior == "sleep_timeout":
                    time.sleep(3600)
                    result = None
                else:
                    result = func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            preview = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
            trace_recorder.record_tool_result(tool_name, preview[:500])
            return result
        except Exception as exc:
            trace_recorder.record_tool_error(tool_name, exc.__class__.__name__, str(exc))
            raise

    return wrapped
