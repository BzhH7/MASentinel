from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


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


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run MASentinel against official DeepSeek API without editing system YAML files.")
    parser.add_argument("--config", default=str(repo_root / "configs" / "all_systems.yaml"))
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--testing-model", default="deepseek-v4-pro")
    parser.add_argument("--target-model", default="deepseek-v4-flash")
    parser.add_argument("--timeout", default="45")
    parser.add_argument("--retries", default="1")
    parser.add_argument(
        "--extra-body-json",
        default=os.getenv("MAS_MODEL_EXTRA_BODY_JSON", ""),
        help='Extra JSON object merged into MASentinel testing-agent requests, for example {"reasoning_effort":"high"}.',
    )
    parser.add_argument("--enable-thinking", action="store_true", help="Shortcut for --extra-body-json with enable_thinking=true.")
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high"],
        default="",
        help="Shortcut for adding reasoning_effort to MASentinel testing-agent requests when the gateway supports it.",
    )
    parser.add_argument("--allow-human", action="store_true")
    args = parser.parse_args()

    if not os.getenv(args.api_key_env):
        raise SystemExit(f"Missing official DeepSeek key in environment variable: {args.api_key_env}")

    extra_body_text = _extra_body_json(args.extra_body_json, args.enable_thinking, args.reasoning_effort)
    extra_body = json.loads(extra_body_text) if extra_body_text else {}
    os.environ["MAS_TESTING_OPENAI_BASE_URL"] = args.base_url
    os.environ["MAS_TESTING_API_KEY_ENV"] = args.api_key_env
    os.environ["MAS_TESTING_MODEL"] = args.testing_model
    os.environ["MAS_TESTING_TIMEOUT_SECONDS"] = str(args.timeout)
    os.environ["MAS_TESTING_RETRIES"] = str(args.retries)
    if extra_body_text:
        os.environ["MAS_MODEL_EXTRA_BODY_JSON"] = extra_body_text
        os.environ["MAS_TESTING_EXTRA_BODY_JSON"] = extra_body_text
    os.environ["MAS_TARGET_OPENAI_BASE_URL"] = args.base_url
    os.environ["MAS_TARGET_API_KEY_ENV"] = args.api_key_env
    os.environ["MAS_TARGET_MODEL"] = args.target_model

    print(
        "[MASentinel][official-deepseek] "
        f"base_url={args.base_url} testing_model={args.testing_model} target_model={args.target_model} "
        f"key_env={args.api_key_env} extra_body_keys={','.join(sorted(extra_body)) if extra_body else 'none'}",
        flush=True,
    )

    sys.path.insert(0, str(repo_root))
    from run_all import run_all

    run_all(args.config, agentic=True, test_model=args.testing_model, no_human=not args.allow_human)


if __name__ == "__main__":
    main()
