from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from masentinel.analyzer.code_analyzer import analyze_code
from masentinel.analyzer.doc_analyzer import DocAnalyzer
from masentinel.graph.semantic_graph import build_semantic_graph
from masentinel.model.model_client import ModelClient
from masentinel.runner.system_adapter import load_system_config
from masentinel.schema import SystemProfile
from masentinel.utils import write_json

ProgressFn = Callable[[str], None]


def build_profile(
    system_id: str,
    root_path: str,
    doc_path: str | None = None,
    entrypoint: str | None = None,
    model_client: ModelClient | None = None,
    progress: ProgressFn | None = None,
    use_doc_model: bool = False,
) -> SystemProfile:
    _progress(progress, f"profile builder: static analysis start system_id={system_id}")
    code = analyze_code(root_path, progress=progress)
    agents = code["agents"]
    tools = code["tools"]
    _progress(progress, f"profile builder: documentation analysis start doc_path={doc_path}")
    requirements = DocAnalyzer(
        doc_path,
        model_client=model_client,
        known_agents=[a.name for a in agents],
        known_tools=[t.name for t in tools],
        progress=progress,
        use_model=use_doc_model,
    ).analyze()
    raw_notes: dict[str, Any] = dict(code.get("raw_notes", {}))
    raw_notes["analyzer"] = "deterministic_ast_plus_doc_heuristic"
    _progress(progress, f"profile builder: profile complete requirements={len(requirements)}")
    return SystemProfile(
        system_id=system_id,
        root_path=str(root_path),
        doc_path=str(doc_path) if doc_path else None,
        entrypoint=str(entrypoint) if entrypoint else None,
        agents=agents,
        tools=tools,
        requirements=requirements,
        message_edges=code["message_edges"],
        termination_conditions=["TERMINATE", "max_turns", "process_exit"],
        raw_notes=raw_notes,
    )


def build_profile_from_config(config_path: str | Path, progress: ProgressFn | None = None) -> SystemProfile:
    config = load_system_config(config_path)
    config_path = Path(config_path)
    model_cfg = config.get("model", {}) or {}
    analyzer_cfg = config.get("analyzer", {}) or {}
    client = ModelClient(
        base_url=model_cfg.get("testing_openai_base_url") or model_cfg.get("openai_base_url"),
        api_key_env=model_cfg.get("testing_api_key_env") or model_cfg.get("openai_api_key_env"),
        api_key=None,
        model=model_cfg.get("testing_model") or model_cfg.get("default_model"),
        timeout=int(model_cfg.get("testing_timeout_seconds", 30) or 30),
        retries=int(model_cfg.get("testing_retries", 1) or 1),
        extra_body=model_cfg.get("testing_extra_body") or model_cfg.get("testing_extra_body_json") or model_cfg.get("extra_body"),
    )
    return build_profile(
        system_id=str(config.get("system_id") or config_path.stem),
        root_path=config.get("root_path") or ".",
        doc_path=config.get("doc_path"),
        entrypoint=config.get("entrypoint"),
        model_client=client,
        progress=progress,
        use_doc_model=bool(analyzer_cfg.get("doc_model_enabled", model_cfg.get("doc_model_enabled", False))),
    )


def save_profile_bundle(profile: SystemProfile, out_path: str | Path) -> None:
    out_path = Path(out_path)
    write_json(out_path, profile)
    graph_path = out_path.with_name("semantic_graph.json")
    write_json(graph_path, build_semantic_graph(profile))


def _progress(progress: ProgressFn | None, message: str) -> None:
    if progress:
        progress(message)
