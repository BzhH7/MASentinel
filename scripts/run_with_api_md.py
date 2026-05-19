from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def _base_url_from_chat_url(url: str) -> str:
    return re.sub(r"/chat/completions/?$", "", url.rstrip("/"))


def _infer_flash_model(model: str) -> str:
    if "pro" in model.lower():
        return re.sub("pro", "flash", model, flags=re.IGNORECASE)
    return model


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        not lowered
        or lowered in {"...", "sk-...", "sk-令牌", "your api key here", "your_api_key_here"}
        or "令牌" in lowered
        or "token" in lowered and lowered.startswith("sk-")
    )


def _set_env_value(env_values: dict[str, str], name: str, value: str) -> None:
    if _looks_like_placeholder(value):
        return
    if os.getenv(name):
        return
    env_values[name] = value


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


def load_api_settings(api_doc: Path, target_model: str | None = None) -> tuple[dict[str, str], dict[str, str]]:
    text = api_doc.read_text(encoding="utf-8", errors="ignore")
    env_values: dict[str, str] = {}
    overrides: dict[str, str] = {}
    curl_pattern = re.compile(
        r'export\s+\w+\s*=\s*["\']([^"\']+)["\']\s*'
        r"curl\s+(\S+).*?"
        r'"model"\s*:\s*"([^"]+)"',
        flags=re.DOTALL,
    )
    for match in curl_pattern.finditer(text):
        key, url, model = match.groups()
        lowered = model.lower()
        if "pro" in lowered:
            _set_env_value(env_values, "INF_API_KEY_PRO", key)
            overrides["MAS_TESTING_OPENAI_BASE_URL"] = _base_url_from_chat_url(url)
            overrides["MAS_TESTING_API_KEY_ENV"] = "INF_API_KEY_PRO"
            overrides["MAS_TESTING_MODEL"] = model
        elif "flash" in lowered:
            _set_env_value(env_values, "INF_API_KEY_FLASH", key)
            overrides["MAS_TARGET_OPENAI_BASE_URL"] = _base_url_from_chat_url(url)
            overrides["MAS_TARGET_API_KEY_ENV"] = "INF_API_KEY_FLASH"
            overrides["MAS_TARGET_MODEL"] = model

    sdk_base = re.search(r'base_url\s*=\s*["\']([^"\']+)["\']', text)
    sdk_key = re.search(r'api_key\s*=\s*["\']([^"\']+)["\']', text)
    sdk_model = re.search(r'model\s*=\s*["\']([^"\']+)["\']', text)
    if sdk_base and sdk_key and sdk_model:
        key = sdk_key.group(1)
        model = sdk_model.group(1)
        base_url = sdk_base.group(1).rstrip("/")
        _set_env_value(env_values, "BOYUE_API_KEY", key)
        overrides["MAS_TESTING_OPENAI_BASE_URL"] = base_url
        overrides["MAS_TESTING_API_KEY_ENV"] = "BOYUE_API_KEY"
        overrides["MAS_TESTING_MODEL"] = model
        overrides["MAS_TARGET_OPENAI_BASE_URL"] = base_url
        overrides["MAS_TARGET_API_KEY_ENV"] = "BOYUE_API_KEY"
        overrides["MAS_TARGET_MODEL"] = target_model or _infer_flash_model(model)

    return env_values, overrides


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    parser = argparse.ArgumentParser(description="Run MASentinel with API keys loaded from api.md without printing secrets.")
    parser.add_argument("--api-doc", default=str(workspace_root / "api.md"))
    parser.add_argument("--config", default=str(repo_root / "configs" / "all_systems.yaml"))
    parser.add_argument("--test-model", default=None)
    parser.add_argument("--target-model", default=None)
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
    parser.add_argument("--allow-human", action="store_true")
    args = parser.parse_args()

    env_values, overrides = load_api_settings(Path(args.api_doc), target_model=args.target_model)
    extra_body_text = _extra_body_json(args.extra_body_json, args.enable_thinking, args.reasoning_effort)
    if not env_values and not any(os.getenv(name) for name in ("INF_API_KEY_PRO", "INF_API_KEY_FLASH", "BOYUE_API_KEY")):
        raise SystemExit(f"Missing supported non-placeholder API entries in {args.api_doc} or environment")
    os.environ.update(env_values)
    os.environ.update(overrides)
    if args.test_model:
        os.environ["MAS_TESTING_MODEL"] = args.test_model
    if extra_body_text:
        os.environ["MAS_MODEL_EXTRA_BODY_JSON"] = extra_body_text
        os.environ["MAS_TESTING_EXTRA_BODY_JSON"] = extra_body_text
    print(
        "[MASentinel][api] loaded api.md keys: "
        f"pro={'yes' if os.environ.get('INF_API_KEY_PRO') else 'no'} "
        f"flash={'yes' if os.environ.get('INF_API_KEY_FLASH') else 'no'} "
        f"boyue={'yes' if os.environ.get('BOYUE_API_KEY') else 'no'} "
        f"testing_model={os.environ.get('MAS_TESTING_MODEL', 'config')} "
        f"target_model={os.environ.get('MAS_TARGET_MODEL', 'config')} "
        f"extra_body_keys={','.join(sorted(json.loads(extra_body_text))) if extra_body_text else 'none'}",
        flush=True,
    )

    sys.path.insert(0, str(repo_root))
    from run_all import run_all

    run_all(
        args.config,
        agentic=True,
        test_model=args.test_model,
        no_human=not args.allow_human,
    )


if __name__ == "__main__":
    main()
