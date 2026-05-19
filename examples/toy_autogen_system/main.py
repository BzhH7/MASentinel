from __future__ import annotations

import json
import sys
import time
import traceback


class AssistantAgent:
    def __init__(self, name: str, system_message: str = "") -> None:
        self.name = name
        self.system_message = system_message


class UserProxyAgent:
    def __init__(self, name: str, function_map: dict | None = None, human_input_mode: str = "NEVER") -> None:
        self.name = name
        self.function_map = function_map or {}
        self.human_input_mode = human_input_mode


class GroupChat:
    def __init__(self, agents: list, messages: list | None = None, max_round: int = 8) -> None:
        self.agents = agents
        self.messages = messages or []
        self.max_round = max_round


def search_tool(query: str) -> str:
    """Return a tiny deterministic search result."""
    return f"result for {query}: one relevant item"


user_proxy = UserProxyAgent(name="user_proxy", function_map={"search_tool": search_tool}, human_input_mode="NEVER")
planner = AssistantAgent(name="planner", system_message="Plan the user task and delegate executable work.")
executor = AssistantAgent(name="executor", system_message="Execute tool-backed tasks and return concise results.")
groupchat = GroupChat(agents=[user_proxy, planner, executor], messages=[], max_round=8)


def emit(event: dict) -> None:
    event.setdefault("timestamp", time.time())
    print("MAS_TRACE:" + json.dumps(event, ensure_ascii=False), flush=True)


def main() -> int:
    task = sys.stdin.read().strip()
    emit({"type": "message", "turn": 1, "sender": "user_proxy", "receiver": "planner", "content": task})
    if "schema" in task.lower() or "bad_tool_args" in task.lower():
        emit({"type": "message", "turn": 2, "sender": "planner", "receiver": "executor", "content": "Call search_tool with wrong argument."})
        emit({"type": "tool_call", "tool": "search_tool", "arguments": {"term": task}})
        try:
            search_tool(term=task)  # type: ignore[call-arg]
        except TypeError:
            traceback.print_exc()
            return 1
    if not task:
        emit({"type": "message", "turn": 2, "sender": "planner", "receiver": "executor", "content": "Handle empty input safely."})
        print("No task provided. Please provide a concrete research request.")
        return 0
    emit({"type": "message", "turn": 2, "sender": "planner", "receiver": "executor", "content": "Use search_tool and summarize."})
    emit({"type": "tool_call", "tool": "search_tool", "arguments": {"query": task}})
    result = search_tool(task)
    emit({"type": "tool_result", "tool": "search_tool", "result_preview": result})
    emit({"type": "message", "turn": 3, "sender": "executor", "receiver": "user_proxy", "content": result})
    print(f"FINAL: planner delegated to executor; search_tool returned: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
