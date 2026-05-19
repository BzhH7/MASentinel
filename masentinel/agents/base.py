from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from masentinel.agents.agent_trace import AgentTraceLogger
from masentinel.agents.prompts import GLOBAL_GUARDRAILS
from masentinel.model.json_repair import parse_json_object
from masentinel.model.model_client import ModelClient
from masentinel.utils import shorten


@dataclass
class AgentMessage:
    sender: str
    receiver: str
    content: str
    message_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentDecision:
    agent_name: str
    task: str
    output: dict[str, Any]
    confidence: float
    model: str
    raw_response: str | None = None
    fallback_used: bool = False
    success: bool = True
    error: str | None = None


class BaseTestingAgent:
    name = "BaseTestingAgent"
    role = "base"
    purpose = "agent_task"
    model_name = "ds-v4-pro"

    def __init__(
        self,
        model_client: ModelClient,
        trace_logger: AgentTraceLogger,
        model_name: str | None = None,
    ) -> None:
        self.model_client = model_client
        self.trace_logger = trace_logger
        self.model_name = model_name or self.model_name

    def run(self, task: dict[str, Any]) -> AgentDecision:
        prompt_task = _prompt_json(task)
        task_summary = json.dumps(prompt_task, ensure_ascii=False)[:12000]
        raw_response: str | None = None
        try:
            if not self.model_client.available:
                raise RuntimeError("DeepSeek V4 pro client is not configured")
            raw_response = self.model_client.chat(
                self._messages(task),
                model=self.model_name,
                temperature=0.0,
                json_mode=True,
                label=f"{self.name}.{self.purpose}",
            )
            parsed = parse_json_object(raw_response)
            if not parsed:
                raise ValueError("Agent returned non-JSON or empty JSON")
            confidence = float(parsed.get("confidence", 0.75))
            decision = AgentDecision(
                agent_name=self.name,
                task=self.purpose,
                output=parsed,
                confidence=confidence,
                model=self.model_name,
                raw_response=raw_response,
            )
            self.trace_logger.record(
                agent=self.name,
                model=self.model_name,
                purpose=self.purpose,
                input_summary=task_summary,
                output_summary=json.dumps(_safe_json(parsed), ensure_ascii=False),
                success=True,
                fallback=False,
                token_usage=self._token_usage(task_summary, raw_response),
            )
            return decision
        except Exception as exc:
            error = str(exc)
            if raw_response and "non-JSON" in error:
                error = f"{error}; raw_preview={shorten(raw_response, 300)}"
            fallback = self.fallback(task, error)
            self.trace_logger.record(
                agent=self.name,
                model=self.model_name,
                purpose=self.purpose,
                input_summary=task_summary,
                output_summary=json.dumps(_safe_json(fallback), ensure_ascii=False),
                success=False,
                fallback=True,
                token_usage=self._token_usage(task_summary, raw_response or ""),
                error=error,
            )
            return AgentDecision(
                agent_name=self.name,
                task=self.purpose,
                output=fallback,
                confidence=float(fallback.get("confidence", 0.35)),
                model=self.model_name,
                raw_response=raw_response,
                fallback_used=True,
                success=False,
                error=error,
            )

    def _messages(self, task: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": GLOBAL_GUARDRAILS + "\n\n" + self.prompt()},
            {"role": "user", "content": json.dumps(_prompt_json(task), ensure_ascii=False)},
        ]

    def prompt(self) -> str:
        return "Return JSON."

    def fallback(self, task: dict[str, Any], error: str) -> dict[str, Any]:
        return {"confidence": 0.2, "fallback": True, "error": error}

    def _token_usage(self, input_text: str, output_text: str) -> dict[str, int]:
        usage = getattr(self.model_client, "last_usage", None) or {}
        if usage:
            return {
                "input_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
                "output_tokens": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
            }
        return {
            "input_tokens": max(1, len(input_text) // 4),
            "output_tokens": max(1, len(output_text) // 4) if output_text else 0,
        }


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_json(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        from masentinel.utils import dataclass_to_dict

        return dataclass_to_dict(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return shorten(str(value), 1000)


def _prompt_json(value: Any) -> Any:
    return _compact_for_prompt(_safe_json(value))


def _compact_for_prompt(value: Any, key: str = "", depth: int = 0) -> Any:
    if depth > 8:
        return {"_truncated": True, "reason": "max_depth"}
    if isinstance(value, dict):
        return {str(k): _compact_for_prompt(v, str(k), depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        limit = _list_limit(key)
        compacted = [_compact_for_prompt(item, key, depth + 1) for item in value[:limit]]
        if len(value) > limit:
            compacted.append({"_truncated_items": len(value) - limit, "_original_items": len(value)})
        return compacted
    if isinstance(value, str):
        limit = _string_limit(key)
        if len(value) <= limit:
            return value
        return value[:limit] + f"\n...[truncated {len(value) - limit} chars]"
    return value


def _list_limit(key: str) -> int:
    if key in {"events", "case_summaries"}:
        return 12
    if key in {"trace_summaries", "rule_results", "testcases", "faults"}:
        return 20
    if key in {"requirements", "agents", "tools", "message_edges"}:
        return 40
    return 30


def _string_limit(key: str) -> int:
    if key in {"doc_text", "source_text", "code_text", "readme_text"}:
        return 20000
    if key in {"stdout", "stderr", "stdout_tail", "stderr_tail", "raw_response", "content", "evidence", "agentic_evidence"}:
        return 3000
    return 6000
