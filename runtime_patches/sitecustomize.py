from __future__ import annotations

import builtins
import copy
import functools
import importlib
import inspect
import json
import os
import sys
import time
import types


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _log(message: str) -> None:
    if _flag("MAS_RUNTIME_PATCH_VERBOSE", False):
        print(f"[MASentinel][runtime_patch] {message}", flush=True)


def _emit_trace_event(event: dict) -> None:
    if not os.getenv("MAS_TRACE_PATH"):
        return
    payload = dict(event)
    payload.setdefault("timestamp", time.time())
    print("MAS_TRACE:" + json.dumps(payload, ensure_ascii=False), flush=True)


def _supports_kwarg(func, key: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return True
    if key in signature.parameters:
        return True
    return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())


def _termination_msg(message) -> bool:
    if not isinstance(message, dict):
        return False
    content = str(message.get("content") or "").lower()
    markers = [
        "terminate",
        "nothing more for me to do",
        "fully settled",
        "written into memory",
        "plan has been saved",
        "programmer should now implement",
    ]
    return any(marker in content for marker in markers)


def _safe_json_loads(value: str, fallback):
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _patch_input() -> None:
    if not _flag("MAS_NO_HUMAN", False):
        return
    original_input = builtins.input
    defaults = _safe_json_loads(os.getenv("MAS_INPUT_DEFAULTS_JSON", "[]"), [])
    if not isinstance(defaults, list):
        defaults = []
    fallback = os.getenv("MAS_INPUT_DEFAULT") or os.getenv("MAS_TEST_CASE_ID") or "1"

    @functools.wraps(original_input)
    def patched_input(prompt: str = "") -> str:
        try:
            return original_input(prompt)
        except EOFError:
            value = str(defaults.pop(0)) if defaults else fallback
            _log(f"input EOF -> automated default for prompt={prompt[:60]!r}")
            return value

    builtins.input = patched_input


def _target_config_entry() -> dict[str, str]:
    entry: dict[str, str] = {}
    if os.getenv("MAS_MODEL_NAME"):
        entry["model"] = os.environ["MAS_MODEL_NAME"]
    if os.getenv("OPENAI_API_KEY"):
        entry["api_key"] = os.environ["OPENAI_API_KEY"]
    if os.getenv("OPENAI_BASE_URL"):
        entry["base_url"] = os.environ["OPENAI_BASE_URL"]
    return entry


def _normalize_config_entry(entry) -> dict:
    if not isinstance(entry, dict):
        entry = {}
    normalized = dict(entry)
    normalized.pop("request_timeout", None)
    target = _target_config_entry()
    force = _flag("MAS_FORCE_TARGET_LLM_CONFIG", True)
    placeholder_key = str(normalized.get("api_key", "")).strip().lower() in {"", "your api key here", "your_api_key_here", "none"}
    if force or placeholder_key:
        normalized.update(target)
    return normalized


def _normalize_llm_config(llm_config):
    if llm_config in (None, False):
        return llm_config
    if isinstance(llm_config, list):
        return [_normalize_config_entry(item) for item in llm_config]
    if not isinstance(llm_config, dict):
        return llm_config
    normalized = copy.deepcopy(llm_config)
    normalized.pop("request_timeout", None)
    if "config_list" in normalized:
        normalized["config_list"] = [_normalize_config_entry(item) for item in normalized.get("config_list") or []]
    else:
        target = _target_config_entry()
        if target:
            normalized["config_list"] = [target]
    if os.getenv("MAS_MODEL_NAME"):
        normalized["model"] = os.environ["MAS_MODEL_NAME"]
    return normalized


def _patch_agent_class(cls) -> None:
    if getattr(cls, "_masentinel_patched", False):
        return
    original_init = cls.__init__
    original_initiate_chat = getattr(cls, "initiate_chat", None)
    original_send = getattr(cls, "send", None)
    original_receive = getattr(cls, "receive", None)

    @functools.wraps(original_init)
    def patched_init(self, *args, **kwargs):
        if "llm_config" in kwargs:
            kwargs["llm_config"] = _normalize_llm_config(kwargs["llm_config"])
        class_name = getattr(cls, "__name__", "")
        default_reply = os.getenv("MAS_AUTOGEN_DEFAULT_REPLY", "TERMINATE")
        should_force_human_mode = class_name == "UserProxyAgent" or "human_input_mode" in kwargs
        if _flag("MAS_NO_HUMAN", False) and should_force_human_mode and _supports_kwarg(original_init, "human_input_mode"):
            kwargs["human_input_mode"] = "NEVER"
        if _flag("MAS_NO_HUMAN", False) and should_force_human_mode and _supports_kwarg(original_init, "is_termination_msg"):
            if not kwargs.get("is_termination_msg"):
                kwargs["is_termination_msg"] = _termination_msg
        if (
            _flag("MAS_NO_HUMAN", False)
            and should_force_human_mode
            and _supports_kwarg(original_init, "max_consecutive_auto_reply")
            and kwargs.get("max_consecutive_auto_reply") is None
        ):
            kwargs["max_consecutive_auto_reply"] = int(os.getenv("MAS_AUTOGEN_MAX_CONSECUTIVE_AUTO_REPLY", "3"))
        if (
            _flag("MAS_NO_HUMAN", False)
            and should_force_human_mode
            and _supports_kwarg(original_init, "default_auto_reply")
            and not kwargs.get("default_auto_reply")
        ):
            kwargs["default_auto_reply"] = default_reply
        if _supports_kwarg(original_init, "code_execution_config") and isinstance(kwargs.get("code_execution_config"), dict):
            if _flag("MAS_AUTOGEN_DISABLE_CODE_EXECUTION", False):
                kwargs["code_execution_config"] = False
            else:
                code_cfg = dict(kwargs["code_execution_config"])
                code_cfg["use_docker"] = _flag("MAS_AUTOGEN_USE_DOCKER", False)
                if os.getenv("MAS_AUTOGEN_CODE_WORK_DIR"):
                    code_cfg["work_dir"] = os.environ["MAS_AUTOGEN_CODE_WORK_DIR"]
                kwargs["code_execution_config"] = code_cfg
        result = original_init(self, *args, **kwargs)
        if _flag("MAS_NO_HUMAN", False) and should_force_human_mode:
            try:
                if not getattr(self, "_default_auto_reply", None):
                    self._default_auto_reply = default_reply
            except Exception:
                pass
        return result

    cls.__init__ = patched_init
    if callable(original_initiate_chat):

        @functools.wraps(original_initiate_chat)
        def patched_initiate_chat(self, recipient, *args, **kwargs):
            target_message = os.getenv("MAS_TARGET_MESSAGE", "").strip()
            if target_message:
                kwargs["message"] = target_message
                _emit_trace_event(
                    {
                        "type": "input_adapter",
                        "sender": getattr(self, "name", self.__class__.__name__),
                        "receiver": getattr(recipient, "name", recipient.__class__.__name__),
                        "content": target_message[:500],
                        "metadata": {
                            "adapter": "initiate_chat_message_override",
                            "case_id": os.getenv("MAS_TEST_CASE_ID", ""),
                        },
                    }
                )
            return original_initiate_chat(self, recipient, *args, **kwargs)

        cls.initiate_chat = patched_initiate_chat
    if callable(original_send):

        @functools.wraps(original_send)
        def patched_send(self, message, recipient, *args, **kwargs):
            _emit_trace_event(
                {
                    "type": "message",
                    "sender": getattr(self, "name", self.__class__.__name__),
                    "receiver": getattr(recipient, "name", recipient.__class__.__name__),
                    "content": _message_content(message)[:1000],
                }
            )
            return original_send(self, message, recipient, *args, **kwargs)

        cls.send = patched_send
    if callable(original_receive):

        @functools.wraps(original_receive)
        def patched_receive(self, message, sender, *args, **kwargs):
            _emit_trace_event(
                {
                    "type": "message",
                    "sender": getattr(sender, "name", sender.__class__.__name__),
                    "receiver": getattr(self, "name", self.__class__.__name__),
                    "content": _message_content(message)[:1000],
                }
            )
            return original_receive(self, message, sender, *args, **kwargs)

        cls.receive = patched_receive
    cls._masentinel_patched = True


def _message_content(message) -> str:
    if isinstance(message, dict):
        content = message.get("content", "")
        if content:
            return str(content)
        return json.dumps(message, ensure_ascii=False)[:1000]
    return str(message)


def _patch_autogen_module(module) -> None:
    patched_any = False
    for name in ("AssistantAgent", "UserProxyAgent", "ConversableAgent", "GroupChatManager"):
        cls = getattr(module, name, None)
        if cls is not None:
            already = getattr(cls, "_masentinel_patched", False)
            _patch_agent_class(cls)
            patched_any = patched_any or not already
    original_config_list_from_json = getattr(module, "config_list_from_json", None)
    if original_config_list_from_json and not getattr(original_config_list_from_json, "_masentinel_patched", False):

        @functools.wraps(original_config_list_from_json)
        def patched_config_list_from_json(*args, **kwargs):
            return _normalize_llm_config(original_config_list_from_json(*args, **kwargs))

        patched_config_list_from_json._masentinel_patched = True
        module.config_list_from_json = patched_config_list_from_json
        patched_any = True
    if patched_any:
        module._masentinel_patched = True
        _log("patched autogen module")


def _patch_gpt_assistant_module(module) -> None:
    if not _flag("MAS_FORCE_LOCAL_AUTOGEN", False):
        return
    if getattr(module, "_masentinel_gpt_patched", False):
        return
    try:
        import autogen
    except Exception:
        return

    class CompatGPTAssistantAgent(autogen.AssistantAgent):
        def __init__(self, name, llm_config=None, system_message="", **kwargs):
            cfg = dict(llm_config or {})
            cfg.pop("assistant_id", None)
            super().__init__(
                name=name,
                system_message=system_message or f"You are {name}, an AutoGen assistant running under MASentinel compatibility mode.",
                llm_config=_normalize_llm_config(cfg),
            )

    module.GPTAssistantAgent = CompatGPTAssistantAgent
    module._masentinel_gpt_patched = True
    _log("patched GPTAssistantAgent -> local AssistantAgent")


def _install_gpt_assistant_stub() -> None:
    if not _flag("MAS_FORCE_LOCAL_AUTOGEN", False):
        return
    try:
        import autogen
    except Exception as exc:
        _log(f"failed to import autogen for GPTAssistantAgent stub: {exc}")
        return
    _patch_autogen_module(autogen)
    module = types.ModuleType("autogen.agentchat.contrib.gpt_assistant_agent")

    class CompatGPTAssistantAgent(autogen.AssistantAgent):
        def __init__(self, name, llm_config=None, system_message="", **kwargs):
            cfg = dict(llm_config or {})
            cfg.pop("assistant_id", None)
            super().__init__(
                name=name,
                system_message=system_message or f"You are {name}, an AutoGen assistant running under MASentinel compatibility mode.",
                llm_config=_normalize_llm_config(cfg),
            )

    module.GPTAssistantAgent = CompatGPTAssistantAgent
    module._masentinel_gpt_patched = True
    sys.modules["autogen.agentchat.contrib.gpt_assistant_agent"] = module
    _log("installed GPTAssistantAgent compatibility stub")


def _patch_iterative_tools(module) -> None:
    if getattr(module, "_masentinel_patched", False):
        return
    cls = getattr(module, "IterativeCoding", None)
    if cls is None:
        return
    original_init = cls.__init__
    original_set_project_dir = cls.setProjectDir
    original_read_text_file = cls.read_text_file
    original_write_latest_iteration_manual = cls.write_latest_iteration_manual

    def trace_tool(method_name, original_method):
        @functools.wraps(original_method)
        def wrapped(self, *args, **kwargs):
            _emit_trace_event(
                {
                    "type": "tool_call",
                    "tool": method_name,
                    "arguments": {
                        "args_count": len(args),
                        "kwargs": sorted(str(key) for key in kwargs),
                    },
                }
            )
            try:
                result = original_method(self, *args, **kwargs)
            except Exception as exc:
                _emit_trace_event(
                    {
                        "type": "tool_error",
                        "tool": method_name,
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    }
                )
                raise
            _emit_trace_event(
                {
                    "type": "tool_result",
                    "tool": method_name,
                    "result_preview": str(result)[:300] if result is not None else "",
                }
            )
            return result

        return wrapped

    @functools.wraps(original_init)
    def patched_init(self, *args, **kwargs):
        result = original_init(self, *args, **kwargs)
        if os.getenv("MAS_SYSTEM1_ITERATIONS"):
            self.n_code_iterations = int(os.environ["MAS_SYSTEM1_ITERATIONS"])
        return result

    @functools.wraps(original_set_project_dir)
    def patched_set_project_dir(self, project_dir):
        project_dir = os.getenv("MAS_SYSTEM1_PROJECT_DIR", project_dir)
        if not project_dir.endswith("/"):
            project_dir += "/"
        return original_set_project_dir(self, project_dir)

    @functools.wraps(original_read_text_file)
    def patched_read_text_file(self, file_path):
        value = original_read_text_file(self, file_path)
        if value is None and _flag("MAS_NO_HUMAN", False) and str(file_path).endswith("MasterPlan.txt"):
            return (
                "The manager has asked us to complete the requested Python task.\n"
                "Build a small executable Python script and keep the implementation simple.\n"
            )
        return value

    @functools.wraps(original_write_latest_iteration_manual)
    def patched_write_latest_iteration_manual(self, code_message):
        if not code_message:
            code_message = "# No code was returned by the coding agent.\n"
        return original_write_latest_iteration_manual(self, code_message)

    cls.__init__ = patched_init
    cls.setProjectDir = patched_set_project_dir
    cls.read_text_file = patched_read_text_file
    cls.write_latest_iteration_manual = patched_write_latest_iteration_manual
    for method_name in (
        "write_latest_iteration",
        "write_settled_plan",
        "write_latest_iteration_comments",
        "retrieve_latest_iteration",
        "retrieve_latest_iteration_comment",
    ):
        original_method = getattr(cls, method_name, None)
        if original_method is not None and not getattr(original_method, "_masentinel_trace_patched", False):
            wrapped = trace_tool(method_name, original_method)
            wrapped._masentinel_trace_patched = True
            setattr(cls, method_name, wrapped)
    module._masentinel_patched = True
    _log("patched IterativeTools")


def _install_langchain_shims() -> None:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except Exception:
        return
    module = types.ModuleType("langchain.text_splitter")
    module.RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter
    sys.modules.setdefault("langchain.text_splitter", module)


class _MockResponse:
    status_code = 200

    def __init__(self, payload=None):
        self._payload = payload or {"masentinel_mock": True, "message": "External HTTP disabled by MASentinel."}
        self.text = json.dumps(self._payload, ensure_ascii=False)
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._payload


def _patch_requests_module(module) -> None:
    if not _flag("MAS_MOCK_EXTERNAL_HTTP", False) or getattr(module, "_masentinel_patched", False):
        return

    def mocked_request(method, url, *args, **kwargs):
        return _MockResponse({"masentinel_mock": True, "method": method, "url": url})

    module.request = mocked_request
    module.get = lambda url, *args, **kwargs: mocked_request("GET", url, *args, **kwargs)
    module.post = lambda url, *args, **kwargs: mocked_request("POST", url, *args, **kwargs)
    module.patch = lambda url, *args, **kwargs: mocked_request("PATCH", url, *args, **kwargs)
    module._masentinel_patched = True
    _log("patched requests module")


def _mock_ticker_class():
    import numpy as np
    import pandas as pd

    class MockTicker:
        def __init__(self, symbol):
            self.symbol = str(symbol)
            report_date = pd.Timestamp("2025-12-31")
            self.financials = pd.DataFrame(
                {
                    report_date: {
                        "Net Income": 98_000_000_000,
                        "Total Revenue": 385_000_000_000,
                        "Gross Profit": 170_000_000_000,
                    }
                }
            )
            self.balance_sheet = pd.DataFrame(
                {
                    report_date: {
                        "Total Assets": 352_000_000_000,
                        "Total Liabilities": 285_000_000_000,
                        "Total Stockholder Equity": 67_000_000_000,
                        "Current Assets": 143_000_000_000,
                        "Current Liabilities": 129_000_000_000,
                    }
                }
            )
            self.info = {"longName": f"{self.symbol.upper()} Mock Holdings", "sector": "Technology"}

        def history(self, period="1y"):
            dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=120, freq="B")
            base_price = 120 + (sum(ord(ch) for ch in self.symbol.upper()) % 40)
            trend = np.linspace(base_price, base_price * 1.18, len(dates))
            wave = np.sin(np.linspace(0, 8, len(dates))) * 2.5
            close = trend + wave
            return pd.DataFrame(
                {
                    "Open": close * 0.995,
                    "High": close * 1.012,
                    "Low": close * 0.988,
                    "Close": close,
                    "Volume": np.full(len(dates), 10_000_000),
                },
                index=dates,
            )

    return MockTicker


def _install_yfinance_mock_module() -> None:
    if not _flag("MAS_USE_MOCK_DATA", False):
        return
    try:
        mock_module = types.ModuleType("yfinance")
        mock_module.Ticker = _mock_ticker_class()
        mock_module._masentinel_patched = True
        sys.modules["yfinance"] = mock_module
        _log("installed yfinance mock module")
    except Exception as exc:
        _log(f"failed to install yfinance mock module: {exc}")


def _patch_yfinance_module(module) -> None:
    if not _flag("MAS_USE_MOCK_DATA", False) or getattr(module, "_masentinel_patched", False) or getattr(module, "_masentinel_patching", False):
        return
    module._masentinel_patching = True
    try:
        MockTicker = _mock_ticker_class()
    except Exception:
        module._masentinel_patching = False
        return

    module.Ticker = MockTicker
    module._masentinel_patched = True
    module._masentinel_patching = False
    _log("patched yfinance module")


_original_import = builtins.__import__


def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    for loaded_name, loaded_module in list(sys.modules.items()):
        if loaded_module is None:
            continue
        if loaded_name == "autogen.agentchat.contrib.gpt_assistant_agent":
            _patch_gpt_assistant_module(loaded_module)
        elif loaded_name == "autogen":
            _patch_autogen_module(loaded_module)
        elif loaded_name.startswith("autogen."):
            _patch_autogen_module(loaded_module)
        elif loaded_name == "IterativeTools":
            _patch_iterative_tools(loaded_module)
        elif loaded_name == "requests":
            _patch_requests_module(loaded_module)
        elif loaded_name == "yfinance":
            _patch_yfinance_module(loaded_module)
    return module


if _flag("MAS_ENABLE_RUNTIME_PATCHES", True):
    _patch_input()
    _install_langchain_shims()
    _install_yfinance_mock_module()
    _install_gpt_assistant_stub()
    builtins.__import__ = _patched_import
    for existing_name, existing_module in list(sys.modules.items()):
        if existing_name == "autogen":
            _patch_autogen_module(existing_module)
        elif existing_name == "requests":
            _patch_requests_module(existing_module)
        elif existing_name == "yfinance":
            _patch_yfinance_module(existing_module)
