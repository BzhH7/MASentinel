from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from masentinel.utils import ensure_dir, shorten, utc_now_iso, write_json


class AgentTraceLogger:
    def __init__(self, out_dir: str | Path, run_id: str | None = None) -> None:
        self.out_dir = ensure_dir(out_dir)
        self.run_id = run_id or f"agentic_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.trace_path = self.out_dir / "agent_trace.jsonl"
        self.usage_path = self.out_dir / "model_usage.json"
        self.trace_path.write_text("", encoding="utf-8")
        self.usage: dict[str, Any] = {
            "run_id": self.run_id,
            "total_calls": 0,
            "successful_calls": 0,
            "fallback_calls": 0,
            "failed_calls": 0,
            "by_agent": {},
            "by_purpose": {},
            "by_model": {},
            "estimated_tokens": {"input_tokens": 0, "output_tokens": 0},
        }

    def record(
        self,
        agent: str,
        model: str,
        purpose: str,
        input_summary: str,
        output_summary: str,
        success: bool,
        fallback: bool = False,
        token_usage: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        token_usage = token_usage or {"input_tokens": 0, "output_tokens": 0}
        event = {
            "run_id": self.run_id,
            "timestamp": utc_now_iso(),
            "agent": agent,
            "model": model,
            "purpose": purpose,
            "input_summary": shorten(input_summary, 700),
            "output_summary": shorten(output_summary, 700),
            "success": success,
            "fallback": fallback,
            "token_usage": token_usage,
            "error": error,
        }
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._update_usage(event)
        write_json(self.usage_path, self.usage)

    def _update_usage(self, event: dict[str, Any]) -> None:
        self.usage["total_calls"] += 1
        if event["success"]:
            self.usage["successful_calls"] += 1
        else:
            self.usage["failed_calls"] += 1
        if event["fallback"]:
            self.usage["fallback_calls"] += 1
        for key in ("agent", "purpose", "model"):
            bucket_name = f"by_{key}"
            value = event[key]
            self.usage[bucket_name][value] = self.usage[bucket_name].get(value, 0) + 1
        self.usage["estimated_tokens"]["input_tokens"] += int(event["token_usage"].get("input_tokens", 0))
        self.usage["estimated_tokens"]["output_tokens"] += int(event["token_usage"].get("output_tokens", 0))
