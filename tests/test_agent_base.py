import json

from masentinel.agents.agent_trace import AgentTraceLogger
from masentinel.agents.base import BaseTestingAgent
from masentinel.model.model_client import ModelClient


def test_agent_prompt_payload_is_compacted(tmp_path) -> None:
    agent = BaseTestingAgent(ModelClient(), AgentTraceLogger(tmp_path))
    messages = agent._messages(
        {
            "doc_text": "d" * 25000,
            "stdout": "x" * 10000,
            "events": [{"content": "y" * 7000} for _ in range(20)],
        }
    )

    payload = json.loads(messages[1]["content"])

    assert len(payload["doc_text"]) < 21000
    assert "truncated" in payload["doc_text"]
    assert len(payload["stdout"]) < 3200
    assert "truncated" in payload["stdout"]
    assert len(payload["events"]) == 13
    assert payload["events"][-1]["_truncated_items"] == 8
    assert len(payload["events"][0]["content"]) < 3200
