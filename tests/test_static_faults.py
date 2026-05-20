from __future__ import annotations

from pathlib import Path

from masentinel.diagnosis.fault_classifier import classify_faults
from masentinel.diagnosis.static_faults import detect_static_faults
from masentinel.schema import AgentInfo, SystemProfile, ToolInfo


def make_profile(root: Path, code: str, docs: str = "", raw_notes: dict | None = None, tools: list[ToolInfo] | None = None) -> SystemProfile:
    root.mkdir()
    app = root / "app.py"
    app.write_text(code, encoding="utf-8")
    readme = root / "README.md"
    readme.write_text(docs, encoding="utf-8")
    return SystemProfile(
        system_id="generic_static",
        root_path=str(root),
        doc_path=str(readme),
        entrypoint=str(app),
        agents=[AgentInfo(name="agent", class_name="AssistantAgent")],
        tools=tools or [],
        requirements=[],
        message_edges=[],
        raw_notes={"files": [str(app)], **(raw_notes or {})},
    )


def test_static_faults_detect_generic_artifact_and_resume_contracts(tmp_path: Path) -> None:
    profile = make_profile(
        tmp_path / "artifact_resume",
        """
import os

def write_script(version, code):
    open(f"script_v{version}.py", "w").write(code)

def write_review(version, text):
    open(f"review_v{version}.log", "w").write(text)

def does_version_exist(version):
    return os.path.exists(f"review_v{version}.log")
""",
        "The workflow writes script_vn.py and review_vn.txt, and can resume previous versions.\n",
    )

    codes = {fault["failure_code"] for fault in detect_static_faults(profile)}

    assert "ARTIFACT_SCHEMA_MISMATCH" in codes
    assert "RESUME_STATE_INCOMPLETE" in codes


def test_static_faults_detect_external_tool_contracts_without_specific_system_names(tmp_path: Path) -> None:
    profile = make_profile(
        tmp_path / "tool_contract",
        """
import requests

def get_records():
    response = requests.get("https://api.airtable.com/v0/base/table")
    if response.status_code == 200:
        return response.text
    return None
""",
        "The agents collect all records from an external table API.\n",
        tools=[ToolInfo(name="get_records", function_name="get_records")],
    )

    faults = detect_static_faults(profile)
    codes = {fault["failure_code"] for fault in faults}
    tool_fault = next(fault for fault in faults if fault["failure_code"] == "TOOL_UNSTRUCTURED_ERROR")

    assert {"VIEW_PARAMETER_IGNORED", "PAGINATION_NOT_FOLLOWED", "TOOL_UNSTRUCTURED_ERROR"} <= codes
    assert tool_fault["confirmation_status"] == "suspected_fault"
    assert tool_fault["suspected_false_positive"] is True


def test_static_faults_detect_data_cli_and_wiring_contracts(tmp_path: Path) -> None:
    root = tmp_path / "data_cli_wiring"
    profile = make_profile(
        root,
        """
import argparse
import numpy as np

def calculate_financial_metrics(financials, balance_sheet):
    metrics = {}
    try:
        metrics["revenue"] = financials.loc["Total Revenue"].iloc[0]
        metrics["debt_ratio"] = balance_sheet.loc["Total Debt"].iloc[0] / balance_sheet.loc["Total Assets"].iloc[0]
    except Exception:
        metrics = {"revenue": 0, "debt_ratio": 0}
    return metrics

def calculate_risk_metrics(returns, prices):
    drawdown = prices / prices.cummax() - 1
    return {"var_95": np.percentile(returns, 5), "max_drawdown": drawdown.min()}

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparsers.add_parser("analyze")
    args = parser.parse_args()
    if args.command == "analyze":
        pass
    elif args.command == "portfolio":
        pass
    AgentOrchestrator({})
""",
        "```bash\npython -m package.main analyze AAPL\npython -m package.main portfolio AAPL MSFT\n```\n",
        raw_notes={"autogen_wiring_risks": [{"file": str(root / "app.py"), "line": "22", "risk": "empty orchestrator mapping"}]},
    )

    codes = {fault["failure_code"] for fault in detect_static_faults(profile)}

    assert {
        "PARTIAL_METRIC_ZEROED",
        "NUMERIC_SIGN_CONVENTION_ERROR",
        "DOCUMENTED_CLI_COMMAND_MISSING",
        "AUTOGEN_WIRING_MISSING",
    } <= codes


def test_classify_faults_includes_static_code_evidence(tmp_path: Path) -> None:
    profile = make_profile(
        tmp_path / "autogen_input",
        """
from autogen import UserProxyAgent

user = UserProxyAgent("user", human_input_mode="ALWAYS")
""",
    )

    faults = classify_faults(profile, [], [])

    assert [fault["failure_code"] for fault in faults] == ["HUMAN_INPUT_REQUESTED"]
    assert faults[0]["confirmation_status"] == "confirmed_fault"
    assert faults[0]["confirmation_source"] == "deterministic_static_code_evidence"
