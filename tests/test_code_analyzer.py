from pathlib import Path

from masentinel.analyzer.code_analyzer import analyze_code


def test_code_analyzer_detects_toy_agents_and_tool() -> None:
    root = Path(__file__).resolve().parents[1] / "examples" / "toy_autogen_system"
    result = analyze_code(root)
    agent_names = {agent.name for agent in result["agents"]}
    tool_names = {tool.name for tool in result["tools"]}
    assert {"user_proxy", "planner", "executor"} <= agent_names
    assert "search_tool" in tool_names
    assert result["message_edges"]
