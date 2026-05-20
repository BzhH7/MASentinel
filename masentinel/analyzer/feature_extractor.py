from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from masentinel.generator.patterns.cli_doc_conformance import extract_documented_commands
from masentinel.schema import SystemProfile
from masentinel.utils import read_text


EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".cache",
    ".masentinel_fixture",
    ".masentinel_projects",
    "outputs",
    "output",
    "site-packages",
    "node_modules",
}


def extract_system_features(profile: SystemProfile) -> dict[str, Any]:
    """Extract deterministic, code-backed features for test-pattern selection."""

    root = Path(profile.root_path or ".").resolve()
    doc_text = read_text(profile.doc_path) if profile.doc_path else ""
    code_text = _read_code_corpus(root)
    tool_text = _tool_source_text(profile, root, code_text)
    combined = "\n".join([doc_text, code_text, str(profile.raw_notes or {})])
    lowered = combined.lower()
    code_lower = code_text.lower()
    tool_lower = tool_text.lower()
    commands = extract_documented_commands(doc_text)

    uses_autogen = _has_any(code_lower, ("autogen", "assistantagent", "userproxyagent", "groupchat", "groupchatmanager"))
    uses_groupchat = _has_any(code_lower, ("groupchat", "groupchatmanager"))
    has_fixed_round_budget = bool(re.search(r"\bmax_round\s*=\s*\d+", code_text, flags=re.IGNORECASE)) or "max_round" in code_lower
    has_http_tools = bool(profile.tools) and _has_any(
        tool_lower,
        (
            "requests.",
            "requests.get",
            "requests.post",
            "requests.patch",
            "httpx",
            "aiohttp",
            "urllib.request",
            "api.airtable.com",
            "serper",
            "browserless",
        ),
    )
    has_airtable_tools = bool(profile.tools) and "airtable" in tool_lower
    has_external_api_tools = bool(profile.tools) and (
        has_http_tools
        or has_airtable_tools
        or _has_any(tool_lower, ("api", "http", "serper", "browserless", "yfinance", "external"))
    )
    has_request_like_code = _has_any(code_lower, ("requests.", "httpx", "aiohttp", "urllib.request", "api.airtable.com"))
    has_pagination_risk = has_airtable_tools and ("offset" not in tool_lower or "view" not in tool_lower)
    has_multi_record_work = _has_any(
        "\n".join([doc_text, code_text]).lower(),
        ("airtable", "records", "companies", "record_count", "all records", "per company", "多条", "记录"),
    )
    writes_files = _has_any(
        code_lower,
        ("open(", ".write(", "write_text(", "mkdir(", "makedirs(", "path(", "os.path.join", "with open"),
    )
    has_user_controlled_path = writes_files and (
        _has_any(code_lower, ("project_name", "filename", "file_name", "path_name", "project dir"))
        or bool(re.search(r"input\s*\([^)]*\).*?(path|dir|folder|file|project)", code_lower, flags=re.DOTALL))
    )
    has_documented_artifacts = _has_any(
        doc_text.lower(),
        ("script_v", "comments_v", "masterplan", "report.json", "report.md", "output file", "输出文件"),
    )
    has_resume_state = _has_any(
        lowered,
        ("resume", "continue", "latest iteration", "masterplan", "script_v", "comments_v", "恢复", "继续"),
    ) and _has_any(code_lower, ("script_v", "comments_v", "masterplan"))
    has_versioned_artifacts = _has_any(code_lower, ("script_v", "comments_v", "version", "latest_iteration", "latest.py"))
    has_pandas = _has_any(code_lower, ("import pandas", "pd.", "dataframe"))
    has_financial_metrics = _has_any(
        code_lower,
        (
            "calculate_financial_metrics",
            "financial_metrics",
            "total revenue",
            "net income",
            "profit_margin",
            "net_margin",
            "debt_ratio",
            "current_ratio",
            "financials",
            "balance_sheet",
        ),
    )
    has_risk_metrics = _has_any(
        code_lower,
        ("calculate_risk_metrics", "var_95", "value_at_risk", "max_drawdown", "maximum_drawdown", "sharpe", "drawdown"),
    )
    has_dataframe_metrics = bool(has_pandas and _has_any(code_lower, ("sum(", "mean(", "pct_change", "rolling(", "financials", "balance_sheet", "metrics")))
    has_last_message_calls = "last_message" in code_lower
    has_multistage_handoff = has_last_message_calls or _has_any(
        code_lower,
        ("previous analysis", "analysis results", "downstream", "financial analysis:", "risk assessment:"),
    )
    claims_multi_agent = _has_any(
        "\n".join([doc_text, code_text]).lower(),
        ("autogen", "multi-agent", "multi agent", "多智能体", "agentorchestrator", "agentfactory", "groupchat"),
    )
    has_orchestrator_static_risk = bool(profile.raw_notes.get("autogen_wiring_risks"))

    nested = {
        "system_id": profile.system_id,
        "source_summary": {
            "root_path": str(root),
            "doc_path": profile.doc_path,
            "python_files_scanned": _count_python_files(root),
            "doc_chars": len(doc_text),
            "code_chars": len(code_text),
        },
        "framework": {
            "uses_autogen": uses_autogen,
            "uses_groupchat": uses_groupchat,
            "uses_user_proxy": "userproxyagent" in code_lower,
            "has_speaker_selection": _has_any(code_lower, ("speaker_selection", "select_speaker", "speaker_selection_method")),
            "has_human_input_mode": "human_input_mode" in code_lower,
            "has_fixed_round_budget": has_fixed_round_budget,
        },
        "tools": {
            "has_tools": bool(profile.tools),
            "tool_names": [tool.name for tool in profile.tools],
            "has_http_tools": has_http_tools,
            "has_airtable_tools": has_airtable_tools,
            "has_external_api_tools": has_external_api_tools,
            "has_request_like_code": has_request_like_code,
            "has_pagination_risk": has_pagination_risk,
            "has_multi_record_work": has_multi_record_work,
            "has_structured_error_contract": _has_any(tool_lower, ("status_code", "raise_for_status", "\"error\"", "'error'", "success")),
        },
        "artifacts": {
            "writes_files": writes_files,
            "has_documented_artifacts": has_documented_artifacts,
            "has_resume_state": has_resume_state,
            "has_versioned_artifacts": has_versioned_artifacts,
            "has_user_controlled_path": has_user_controlled_path,
        },
        "data_processing": {
            "has_pandas": has_pandas,
            "has_financial_metrics": has_financial_metrics,
            "has_risk_metrics": has_risk_metrics,
            "has_dataframe_metrics": has_dataframe_metrics,
            "has_yfinance": "yfinance" in code_lower,
        },
        "cli": {
            "has_documented_commands": bool(commands),
            "documented_commands": commands,
            "uses_argparse": "argparse" in code_lower,
        },
        "message_flow": {
            "has_last_message_calls": has_last_message_calls,
            "has_multistage_handoff": has_multistage_handoff,
        },
        "docs": {
            "claims_multi_agent": claims_multi_agent,
            "claims_financial_analysis": _has_any(doc_text.lower(), ("financial", "finance", "stock", "portfolio", "risk", "财务", "股票")),
        },
        "static_risks": {
            "has_autogen_wiring_risk": has_orchestrator_static_risk,
            "autogen_wiring_risks": profile.raw_notes.get("autogen_wiring_risks", []) or [],
        },
    }
    nested["flat"] = {
        "uses_autogen": uses_autogen,
        "uses_groupchat": uses_groupchat,
        "has_speaker_selection": nested["framework"]["has_speaker_selection"],
        "has_human_input_mode": nested["framework"]["has_human_input_mode"],
        "has_http_tools": has_http_tools,
        "has_airtable_tools": has_airtable_tools,
        "has_external_api_tools": has_external_api_tools,
        "writes_files": writes_files,
        "has_user_controlled_path": has_user_controlled_path,
        "has_resume_state": has_resume_state,
        "has_versioned_artifacts": has_versioned_artifacts,
        "has_last_message_calls": has_last_message_calls,
        "has_multistage_handoff": has_multistage_handoff,
        "has_financial_metrics": has_financial_metrics,
        "has_risk_metrics": has_risk_metrics,
        "has_dataframe_metrics": has_dataframe_metrics,
        "documented_cli_commands": commands,
        "docs_claim_multi_agent": claims_multi_agent,
        "enterprise_orchestrator_risks": profile.raw_notes.get("autogen_wiring_risks", []) or [],
    }
    return nested


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.lower() in text for marker in markers)


def _read_code_corpus(root: Path, max_chars: int = 400_000) -> str:
    if not root.exists():
        return ""
    chunks: list[str] = []
    total = 0
    for path in sorted(root.rglob("*.py")):
        if _skip_path(path):
            continue
        text = read_text(path)
        if not text:
            continue
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        chunk = f"\n# FILE: {rel}\n{text}\n"
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_chars:
            break
    return "".join(chunks)


def _tool_source_text(profile: SystemProfile, root: Path, fallback_code: str) -> str:
    chunks: list[str] = []
    for tool in profile.tools:
        chunks.extend(str(item or "") for item in (tool.name, tool.function_name, tool.signature, tool.docstring))
        if not tool.source_file:
            continue
        path = Path(tool.source_file)
        if not path.is_absolute():
            path = root / path
        if path.exists() and not _skip_path(path):
            chunks.append(read_text(path))
    return "\n".join(chunks) if chunks else fallback_code


def _count_python_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*.py") if not _skip_path(path))


def _skip_path(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS or part.startswith(".ipynb_checkpoints") for part in path.parts)
