from __future__ import annotations

import os
from typing import Any

from masentinel.instrumentation.trace_recorder import TraceRecorder


def install_autogen_patch(trace_recorder: TraceRecorder) -> list[str]:
    """Best-effort monkey patch for old AutoGen. Safe to call when AutoGen is absent."""

    warnings: list[str] = []
    try:
        import autogen  # type: ignore
    except Exception as exc:
        warnings.append(f"autogen import failed: {exc}")
        return warnings

    try:
        conversable = autogen.agentchat.conversable_agent.ConversableAgent
    except Exception as exc:
        warnings.append(f"ConversableAgent lookup failed: {exc}")
        return warnings

    def patch_method(name: str) -> None:
        original = getattr(conversable, name, None)
        if original is None or getattr(original, "_masentinel_patched", False):
            return

        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            other = None
            if args:
                other = getattr(args[0], "name", None)
            sender = getattr(self, "name", None)
            if name == "send":
                trace_recorder.record_message(sender, other, str(args[0])[:500] if args else str(kwargs)[:500])
            result = original(self, *args, **kwargs)
            if name == "receive":
                trace_recorder.record_message(other, sender, str(args[0])[:500] if args else str(kwargs)[:500])
            return result

        wrapped._masentinel_patched = True  # type: ignore[attr-defined]
        setattr(conversable, name, wrapped)

    try:
        patch_method("send")
        patch_method("receive")
        patch_method("initiate_chat")
    except Exception as exc:
        warnings.append(f"autogen patch failed: {exc}")
    if os.getenv("MAS_TRACE_PATH"):
        warnings.append("Patch installed, but target process must import this module to activate tracing.")
    return warnings
