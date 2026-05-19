from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from masentinel.schema import RunTrace
from masentinel.utils import ensure_dir, write_json, write_text


def build_trace_graph(traces: list[RunTrace], out_dir: str | Path) -> dict[str, Any]:
    nodes: set[str] = set()
    edges: dict[tuple[str, str], int] = {}
    tools: set[str] = set()
    for trace in traces:
        for event in trace.events:
            if event.sender:
                nodes.add(event.sender)
            if event.receiver:
                nodes.add(event.receiver)
            if event.sender and event.receiver:
                edges[(event.sender, event.receiver)] = edges.get((event.sender, event.receiver), 0) + 1
            if event.tool:
                tools.add(event.tool)
    graph = {
        "nodes": [{"id": node, "type": "agent"} for node in sorted(nodes)] + [{"id": tool, "type": "tool"} for tool in sorted(tools)],
        "edges": [{"source": s, "target": t, "count": c, "type": "message"} for (s, t), c in sorted(edges.items())],
    }
    write_json(Path(out_dir) / "trace_graph.json", graph)
    write_text(Path(out_dir) / "trace_graph.dot", _to_dot(graph))
    return graph


def write_dashboard(out_dir: str | Path, summary: dict[str, Any]) -> None:
    out_dir = ensure_dir(out_dir)
    coverage = summary.get("coverage", {}) or {}
    cards = "".join(
        f"<div class='card'><span>{html.escape(k)}</span><strong>{v}</strong></div>"
        for k, v in {
            "Cases": summary.get("cases", 0),
            "Faults": summary.get("faults", 0),
            "Root Groups": summary.get("fault_groups", 0),
            "MASCov": coverage.get("mascov", 0),
            "Fallback Calls": (summary.get("agentic", {}) or {}).get("fallback_calls", 0),
        }.items()
    )
    content = f"""<!doctype html><html><head><meta charset='utf-8'><title>MASentinel Dashboard</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#f7f8fa;color:#17202a}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}.card{{background:#fff;border:1px solid #dce2e8;border-radius:8px;padding:16px}}strong{{display:block;font-size:28px;margin-top:8px}}a{{color:#1558b0}}</style>
</head><body><h1>MASentinel Dashboard</h1><div class='grid'>{cards}</div>
<p><a href='report.html'>Report</a> · <a href='trace_graph.json'>Trace graph JSON</a> · <a href='trace_graph.dot'>Trace graph DOT</a> · <a href='patch_suggestions.md'>Patch suggestions</a> · <a href='flaky_report.json'>Flaky report</a></p>
</body></html>"""
    write_text(out_dir / "dashboard.html", content)


def _to_dot(graph: dict[str, Any]) -> str:
    lines = ["digraph MASentinelTrace {"]
    for node in graph.get("nodes", []):
        shape = "box" if node.get("type") == "tool" else "ellipse"
        lines.append(f'  "{node["id"]}" [shape={shape}];')
    for edge in graph.get("edges", []):
        lines.append(f'  "{edge["source"]}" -> "{edge["target"]}" [label="{edge.get("count", 1)}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"
