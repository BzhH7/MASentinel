from __future__ import annotations

import os
import re
import shlex
import sys
import zlib
from pathlib import Path
from typing import Any

from masentinel.schema import TestCase
from masentinel.utils import load_yaml, resolve_path


def load_system_config(config_path: str | Path) -> dict[str, Any]:
    config_path = Path(config_path)
    config = load_yaml(config_path)
    base_dir = config_path.parent
    config["_config_path"] = str(config_path.resolve())
    config["_base_dir"] = str(base_dir.resolve())
    config["root_path"] = resolve_path(config.get("root_path"), base_dir)
    config["doc_path"] = resolve_path(config.get("doc_path"), base_dir)
    config["entrypoint"] = resolve_path(config.get("entrypoint"), base_dir)
    run = config.setdefault("run", {})
    run["working_dir"] = resolve_path(run.get("working_dir") or config.get("root_path"), base_dir)
    _apply_model_env_overrides(config)
    return config


def build_command(config: dict[str, Any], testcase: TestCase) -> list[str]:
    run = config.get("run", {}) or {}
    command = run.get("command")
    if not command:
        entrypoint = config.get("entrypoint")
        command = f"python {Path(entrypoint).name}" if entrypoint else "python main.py"
    command_text = " ".join(str(item) for item in command) if isinstance(command, list) else str(command)
    if isinstance(command, list):
        parts = [render_case_template(str(x), testcase) for x in command]
    else:
        rendered = render_case_template(command_text, testcase)
        parts = shlex.split(rendered)
    if parts and parts[0] in {"python", "python3"}:
        parts[0] = sys.executable
    case_markers = ("{input}", "{stock_symbol}", "{case_id}", "{safe_case_id}", "{system_id}")
    if run.get("input_mode") == "argv" and not any(marker in command_text for marker in case_markers):
        parts.append(_case_input(testcase))
    return parts


def _apply_model_env_overrides(config: dict[str, Any]) -> None:
    model = config.setdefault("model", {})
    overrides = {
        "MAS_TESTING_OPENAI_BASE_URL": "testing_openai_base_url",
        "MAS_TESTING_API_KEY_ENV": "testing_api_key_env",
        "MAS_TESTING_MODEL": "testing_model",
        "MAS_TESTING_TIMEOUT_SECONDS": "testing_timeout_seconds",
        "MAS_TESTING_RETRIES": "testing_retries",
        "MAS_TESTING_EXTRA_BODY_JSON": "testing_extra_body_json",
        "MAS_TARGET_OPENAI_BASE_URL": "target_openai_base_url",
        "MAS_TARGET_API_KEY_ENV": "target_api_key_env",
        "MAS_TARGET_MODEL": "target_model",
    }
    for env_name, key in overrides.items():
        value = os.getenv(env_name)
        if value:
            model[key] = value


def build_env(config: dict[str, Any], testcase: TestCase, trace_path: str) -> dict[str, str]:
    env = os.environ.copy()
    run = config.get("run", {}) or {}
    model = config.get("model", {}) or {}
    base_url = model.get("target_openai_base_url") or model.get("openai_base_url")
    model_name = model.get("target_model") or model.get("default_model")
    key_env = model.get("target_api_key_env") or model.get("openai_api_key_env")
    if base_url:
        env["OPENAI_BASE_URL"] = str(base_url)
        env["OPENAI_API_BASE"] = str(base_url)
    if key_env and os.getenv(str(key_env)):
        env["OPENAI_API_KEY"] = os.getenv(str(key_env), "")
    if model_name:
        env["MAS_MODEL_NAME"] = str(model_name)
    if base_url and model_name and env.get("OPENAI_API_KEY"):
        env["OAI_CONFIG_LIST"] = json_config_list(str(model_name), str(base_url), env["OPENAI_API_KEY"])
    if run.get("message_template"):
        env["MAS_TARGET_MESSAGE"] = render_case_template(str(run["message_template"]), testcase)
    env["MAS_TEST_CASE_ID"] = testcase.case_id
    env["MAS_TRACE_PATH"] = trace_path
    env["MAS_MAX_TURNS"] = str(testcase.oracle.max_turns)
    env["MAS_NO_HUMAN"] = "1" if run.get("no_human", True) else "0"
    if run.get("runtime_patches", True):
        patch_dir = Path(__file__).resolve().parents[2] / "runtime_patches"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(patch_dir) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env.setdefault("MAS_ENABLE_RUNTIME_PATCHES", "1")
        env.setdefault("MAS_FORCE_TARGET_LLM_CONFIG", "1")
    for key, value in (run.get("env", {}) or {}).items():
        env[str(key)] = render_case_template(str(value), testcase)
    if testcase.fault_injection:
        import json
        from masentinel.utils import dataclass_to_dict

        env["MAS_FAULT_INJECTION"] = json.dumps(dataclass_to_dict(testcase.fault_injection), ensure_ascii=False)
    return env


def target_model_context(config: dict[str, Any]) -> dict[str, str | None]:
    model = config.get("model", {}) or {}
    return {
        "target_model": model.get("target_model") or model.get("default_model"),
        "target_base_url": model.get("target_openai_base_url") or model.get("openai_base_url"),
        "target_api_key_env": model.get("target_api_key_env") or model.get("openai_api_key_env"),
    }


def _case_input(testcase: TestCase) -> str:
    if testcase.input_sequence:
        return "\n".join(str(item.get("content", "")) for item in testcase.input_sequence if item.get("content")).strip()
    return testcase.input


def render_case_template(template: str, testcase: TestCase) -> str:
    safe_case_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", testcase.case_id)
    replacements = {
        "input": _case_input(testcase),
        "case_id": testcase.case_id,
        "safe_case_id": safe_case_id,
        "system_id": testcase.system_id,
        "stock_symbol": _stock_symbol(testcase),
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def _stock_symbol(testcase: TestCase) -> str:
    metadata = testcase.metadata if isinstance(testcase.metadata, dict) else {}
    if metadata.get("stock_symbol"):
        return _safe_stock_symbol(str(metadata["stock_symbol"]))
    text = " ".join(
        str(part)
        for part in (
            testcase.input,
            testcase.objective,
            metadata.get("symbol", ""),
            metadata.get("stock", ""),
        )
        if part
    )
    for match in re.finditer(r"\b[A-Z]{1,5}\b", text):
        value = match.group(0)
        if value not in {"JSON", "HTTP", "API", "LLM", "MAS"}:
            return _safe_stock_symbol(value)
    symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META", "JPM"]
    index = zlib.crc32(testcase.case_id.encode("utf-8")) % len(symbols)
    return symbols[index]


def _safe_stock_symbol(value: str) -> str:
    match = re.search(r"[A-Za-z]{1,5}", value)
    return match.group(0).upper() if match else "AAPL"


def json_config_list(model_name: str, base_url: str, api_key: str) -> str:
    import json

    return json.dumps(
        [
            {
                "model": model_name,
                "base_url": base_url,
                "api_key": api_key,
            }
        ],
        ensure_ascii=False,
    )
