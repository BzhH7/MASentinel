from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .json_repair import parse_json_object


class ModelClient:
    """Tiny OpenAI-compatible chat client with deterministic fallback behavior."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        model: str | None = None,
        timeout: int = 30,
        retries: int = 1,
        extra_body: dict[str, Any] | str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.getenv(api_key_env or "") or os.getenv("OPENAI_API_KEY") or ""
        self.model = model or os.getenv("MAS_MODEL_NAME") or "qwen2.5-coder:7b"
        self.timeout = timeout
        self.retries = retries
        self.extra_body = _parse_extra_body(extra_body, os.getenv("MAS_MODEL_EXTRA_BODY_JSON"))
        self.last_usage: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        json_mode: bool = False,
        label: str | None = None,
    ) -> str:
        if not self.available:
            raise RuntimeError("ModelClient is not configured")
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        last_error: Exception | None = None
        use_json_mode = json_mode and os.getenv("MAS_DISABLE_RESPONSE_FORMAT", "0").strip().lower() not in {"1", "true", "yes", "on"}
        self.last_usage = {}
        call_label = label or "model_call"
        progress = os.getenv("MAS_MODEL_PROGRESS", "1").strip().lower() not in {"0", "false", "no", "off"}
        model_name = model or self.model
        payload_chars = len(json.dumps(self._request_payload(payload, use_json_mode), ensure_ascii=False))
        extra_keys = ",".join(sorted(self.extra_body)) if self.extra_body else "none"
        for attempt in range(self.retries + 1):
            if progress:
                print(
                    f"[MASentinel][model] {call_label} attempt {attempt + 1}/{self.retries + 1} "
                    f"model={model_name} timeout={self.timeout}s json_mode={use_json_mode} "
                    f"extra_body_keys={extra_keys} payload_chars={payload_chars}",
                    flush=True,
                )
            request_payload = self._request_payload(payload, use_json_mode)
            body = json.dumps(request_payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                data = self._urlopen_json(req)
                self.last_usage = data.get("usage", {}) if isinstance(data, dict) else {}
                if progress:
                    usage = self.last_usage or {}
                    print(
                        f"[MASentinel][model] {call_label} success "
                        f"prompt_tokens={usage.get('prompt_tokens', usage.get('input_tokens', 'n/a'))} "
                        f"completion_tokens={usage.get('completion_tokens', usage.get('output_tokens', 'n/a'))}",
                        flush=True,
                    )
                return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as exc:
                last_error = RuntimeError(self._http_error_message(exc))
                if progress:
                    print(f"[MASentinel][model] {call_label} attempt {attempt + 1} failed: {last_error}", flush=True)
                if use_json_mode and exc.code in {400, 404, 422}:
                    use_json_mode = False
                    continue
                if attempt < self.retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
            except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError, socket.timeout) as exc:
                last_error = exc
                if progress:
                    print(f"[MASentinel][model] {call_label} attempt {attempt + 1} failed: {exc}", flush=True)
                if attempt < self.retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
        raise RuntimeError(f"Model call failed after {self.retries + 1} attempt(s): {last_error}")

    def _request_payload(self, payload: dict[str, Any], use_json_mode: bool) -> dict[str, Any]:
        request_payload = dict(payload)
        for key, value in self.extra_body.items():
            if key in {"model", "messages", "stream"}:
                continue
            request_payload[key] = value
        if use_json_mode:
            request_payload["response_format"] = {"type": "json_object"}
        return request_payload

    def _urlopen_json(self, req: urllib.request.Request) -> dict[str, Any]:
        result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                result_queue.put((True, self._urlopen_json_blocking(req)), block=False)
            except Exception as exc:
                result_queue.put((False, exc), block=False)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            ok, value = result_queue.get(timeout=self.timeout + 2)
        except queue.Empty as exc:
            raise TimeoutError(f"hard timeout after {self.timeout}s") from exc
        if ok:
            return value
        raise value

    def _urlopen_json_blocking(self, req: urllib.request.Request) -> dict[str, Any]:
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def json_chat(self, messages: list[dict[str, str]], schema_hint: str | None = None, model: str | None = None) -> dict[str, Any]:
        full_messages = list(messages)
        if schema_hint:
            full_messages.append({"role": "system", "content": f"Schema hint: {schema_hint}"})
        try:
            return parse_json_object(self.chat(full_messages, model=model, temperature=0.0, json_mode=True, label="json_chat"))
        except Exception:
            return {}

    def _http_error_message(self, exc: urllib.error.HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        body = body[:500].replace("\n", " ").strip()
        return f"HTTP {exc.code} {exc.reason}: {body}"


def _parse_extra_body(*values: dict[str, Any] | str | None) -> dict[str, Any]:
    for value in values:
        if not value:
            continue
        if isinstance(value, dict):
            return dict(value)
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}
