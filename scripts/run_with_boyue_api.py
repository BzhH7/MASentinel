from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        not lowered
        or lowered in {"...", "sk-...", "sk-令牌", "your api key here", "your_api_key_here"}
        or "令牌" in lowered
    )


def _extra_body_json(raw: str, enable_thinking: bool, reasoning_effort: str) -> str:
    extra: dict[str, object] = {}
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--extra-body-json is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SystemExit("--extra-body-json must be a JSON object")
        extra.update(parsed)
    if enable_thinking:
        extra.setdefault("enable_thinking", True)
    if reasoning_effort:
        extra.setdefault("reasoning_effort", reasoning_effort)
    return json.dumps(extra, ensure_ascii=False) if extra else ""


def _check_api(base_url: str, model: str, api_key: str, timeout: int, extra_body: dict[str, object]) -> None:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "stream": False,
    }
    for key, value in extra_body.items():
        if key not in {"model", "messages", "stream"}:
            payload[key] = value
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key.strip()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        print(f"[MASentinel][boyue-api] check ok model={model} response_preview={content[:40]!r}", flush=True)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:500].replace("\n", " ")
        raise SystemExit(f"[MASentinel][boyue-api] check failed HTTP {exc.code} {exc.reason}: {detail}") from exc
    except Exception as exc:
        raise SystemExit(f"[MASentinel][boyue-api] check failed: {exc}") from exc


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run MASentinel with the Boyue OpenAI-compatible DeepSeek endpoint.")
    parser.add_argument("--config", default=str(repo_root / "configs" / "all_systems.yaml"))
    parser.add_argument("--base-url", default="https://apicz.boyuerichdata.com/v1/")
    parser.add_argument("--api-key-env", default="BOYUE_API_KEY")
    parser.add_argument("--testing-model", default="deepseek-v4-pro")
    parser.add_argument("--target-model", default="deepseek-v4-flash")
    parser.add_argument(
        "--check-models",
        default="",
        help="Comma-separated model names to probe with --check-only. Defaults to --testing-model.",
    )
    parser.add_argument("--timeout", default="90")
    parser.add_argument("--retries", default="2")
    parser.add_argument(
        "--extra-body-json",
        default=os.getenv("MAS_MODEL_EXTRA_BODY_JSON", ""),
        help='Extra JSON object merged into MASentinel testing-agent requests, for example {"enable_thinking":true}.',
    )
    parser.add_argument("--enable-thinking", action="store_true", help="Shortcut for --extra-body-json with enable_thinking=true.")
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high"],
        default="",
        help="Shortcut for adding reasoning_effort to MASentinel testing-agent requests when the gateway supports it.",
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--allow-human", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing API key in environment variable: {args.api_key_env}")
    if _looks_like_placeholder(api_key):
        raise SystemExit(f"Environment variable {args.api_key_env} looks like a placeholder, not a real API key.")

    base_url = args.base_url.rstrip("/")
    extra_body_text = _extra_body_json(args.extra_body_json, args.enable_thinking, args.reasoning_effort)
    extra_body = json.loads(extra_body_text) if extra_body_text else {}
    if args.check_only:
        models = [item.strip() for item in args.check_models.split(",") if item.strip()] or [args.testing_model]
        print(
            "[MASentinel][boyue-api] check start "
            f"base_url={base_url} models={models} key_env={args.api_key_env} "
            f"extra_body_keys={','.join(sorted(extra_body)) if extra_body else 'none'}",
            flush=True,
        )
        failures = 0
        for model in models:
            try:
                _check_api(base_url, model, api_key, timeout=min(int(args.timeout), 30), extra_body=extra_body)
            except SystemExit as exc:
                failures += 1
                print(exc, flush=True)
        if failures:
            raise SystemExit(f"[MASentinel][boyue-api] check finished with {failures}/{len(models)} failure(s)")
        return

    os.environ["MAS_TESTING_OPENAI_BASE_URL"] = base_url
    os.environ["MAS_TESTING_API_KEY_ENV"] = args.api_key_env
    os.environ["MAS_TESTING_MODEL"] = args.testing_model
    os.environ["MAS_TESTING_TIMEOUT_SECONDS"] = str(args.timeout)
    os.environ["MAS_TESTING_RETRIES"] = str(args.retries)
    if extra_body_text:
        os.environ["MAS_MODEL_EXTRA_BODY_JSON"] = extra_body_text
        os.environ["MAS_TESTING_EXTRA_BODY_JSON"] = extra_body_text
    os.environ["MAS_TARGET_OPENAI_BASE_URL"] = base_url
    os.environ["MAS_TARGET_API_KEY_ENV"] = args.api_key_env
    os.environ["MAS_TARGET_MODEL"] = args.target_model

    print(
        "[MASentinel][boyue-api] "
        f"base_url={base_url} testing_model={args.testing_model} target_model={args.target_model} "
        f"key_env={args.api_key_env} extra_body_keys={','.join(sorted(extra_body)) if extra_body else 'none'}",
        flush=True,
    )

    sys.path.insert(0, str(repo_root))
    from run_all import run_all

    run_all(args.config, agentic=True, test_model=args.testing_model, no_human=not args.allow_human)


if __name__ == "__main__":
    main()
