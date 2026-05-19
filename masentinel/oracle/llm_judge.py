from __future__ import annotations

from masentinel.model.model_client import ModelClient


class LLMJudge:
    def __init__(self, model_client: ModelClient | None = None) -> None:
        self.model_client = model_client or ModelClient()

    def judge(self, payload: dict) -> dict:
        if not self.model_client.available:
            return {
                "pass": not payload.get("rule_failures"),
                "fault_confirmed": bool(payload.get("rule_failures")),
                "fault_type": "rule_oracle",
                "layer": "uncertain",
                "severity": "medium",
                "evidence": payload.get("rule_failures", []),
                "root_cause": "LLM judge unavailable; rule oracle fallback used.",
                "suggested_fix": "Inspect rule oracle evidence.",
                "confidence": 0.5,
            }
        return self.model_client.json_chat(
            [
                {
                    "role": "system",
                    "content": "Judge whether rule oracle failures indicate application or AutoGen integration faults. Return JSON only.",
                },
                {"role": "user", "content": str(payload)[:24000]},
            ]
        )
