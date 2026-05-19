from __future__ import annotations

from masentinel.schema import SystemProfile


def build_semantic_graph(profile: SystemProfile) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    for agent in profile.agents:
        nodes.append({"id": agent.name, "type": "agent", "var_name": agent.var_name, "class_name": agent.class_name})
        for tool in agent.tools:
            edges.append({"source": agent.name, "target": tool, "type": "tool_call"})
    for tool in profile.tools:
        nodes.append({"id": tool.name, "type": "tool", "function_name": tool.function_name})
    for req in profile.requirements:
        nodes.append({"id": req.id, "type": "requirement", "description": req.description})
        for agent in req.expected_agents:
            edges.append({"source": req.id, "target": agent, "type": "requires_agent"})
        for tool in req.expected_tools:
            edges.append({"source": req.id, "target": tool, "type": "requires_tool"})
    for edge in profile.message_edges:
        edges.append({"source": edge.source, "target": edge.target, "type": "message", "evidence": edge.evidence})
    seen_nodes = set()
    dedup_nodes = []
    for node in nodes:
        key = (node["id"], node["type"])
        if key not in seen_nodes:
            seen_nodes.add(key)
            dedup_nodes.append(node)
    seen_edges = set()
    dedup_edges = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge["type"])
        if key not in seen_edges:
            seen_edges.add(key)
            dedup_edges.append(edge)
    return {"nodes": dedup_nodes, "edges": dedup_edges}
