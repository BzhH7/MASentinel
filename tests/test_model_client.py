import json

from masentinel.model.model_client import ModelClient


def test_model_client_merges_extra_body_without_overriding_core_payload(monkeypatch) -> None:
    client = ModelClient(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="deepseek-v4-pro",
        extra_body={"enable_thinking": True, "reasoning_effort": "high", "stream": True},
    )
    captured: dict[str, object] = {}

    def fake_urlopen_json(req):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    monkeypatch.setattr(client, "_urlopen_json", fake_urlopen_json)

    assert client.chat([{"role": "user", "content": "ping"}], json_mode=True) == "{}"

    payload = captured["payload"]
    assert payload["model"] == "deepseek-v4-pro"
    assert payload["enable_thinking"] is True
    assert payload["reasoning_effort"] == "high"
    assert payload["stream"] is False
    assert payload["response_format"] == {"type": "json_object"}


def test_model_client_reads_extra_body_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MAS_MODEL_EXTRA_BODY_JSON", '{"enable_thinking":true}')

    client = ModelClient(base_url="https://example.test/v1", api_key="test-key", model="deepseek-v4-pro")

    assert client.extra_body == {"enable_thinking": True}
