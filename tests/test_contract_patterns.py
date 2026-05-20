from pathlib import Path

from masentinel.generator.patterns import extract_documented_commands
from masentinel.analyzer.feature_extractor import extract_system_features
from masentinel.generator.pattern_selector import build_test_plan, pattern_budgets, selected_pattern_names
from masentinel.generator.testcase_generator import generate_testcases
from masentinel.agents.validators import merge_testcases
from masentinel.runner.system_adapter import render_case_template
from masentinel.schema import AgentInfo, RequirementInfo, SystemProfile, ToolInfo


def rich_profile(tmp_path: Path) -> SystemProfile:
    root = tmp_path / "target"
    root.mkdir()
    (root / "README.md").write_text(
        "AutoGen multi-agent CLI\n\n```bash\npython -m src.main analyze AAPL\npython -m src.main interactive\n```\n",
        encoding="utf-8",
    )
    (root / "app.py").write_text(
        """
import os, requests, pandas as pd
from autogen import AssistantAgent, GroupChat

def get_airtable_records():
    return requests.get("https://api.airtable.com/v0/base/table").json()

def calculate_risk_metrics(df):
    return {"var_95": -0.05}

def conduct_analysis(agent):
    return agent.last_message()

orchestrator = AgentOrchestrator({})
open(os.path.join(project_name, "script_v1.py"), "w")
""",
        encoding="utf-8",
    )
    return SystemProfile(
        system_id="rich",
        root_path=str(root),
        doc_path=str(root / "README.md"),
        entrypoint=str(root / "app.py"),
        agents=[
            AgentInfo(name="data", class_name="AssistantAgent"),
            AgentInfo(name="risk", class_name="AssistantAgent"),
            AgentInfo(name="advisor", class_name="AssistantAgent"),
        ],
        tools=[ToolInfo(name="get_airtable_records", function_name="get_airtable_records", source_file=str(root / "app.py"))],
        requirements=[RequirementInfo(id="R1", description="Generate code, report artifacts, financial risk analysis, and API records.")],
        message_edges=[],
        raw_notes={"autogen_wiring_risks": [{"file": str(root / "app.py"), "line": "12", "risk": "AgentOrchestrator({})"}]},
    )


def iterative_coding_profile(tmp_path: Path) -> SystemProfile:
    root = tmp_path / "iterative"
    root.mkdir()
    (root / "README.md").write_text("AutoGen iterative coding demo with planner and programmer agents.\n", encoding="utf-8")
    (root / "main.py").write_text(
        """
from autogen import AssistantAgent, UserProxyAgent

def write_latest_iteration(project_name, code):
    open(f"{project_name}/latest.py", "w").write(code)

def write_settled_plan(plan):
    return plan
""",
        encoding="utf-8",
    )
    return SystemProfile(
        system_id="iterative",
        root_path=str(root),
        doc_path=str(root / "README.md"),
        entrypoint=str(root / "main.py"),
        agents=[
            AgentInfo(name="planner", class_name="AssistantAgent"),
            AgentInfo(name="programmer", class_name="AssistantAgent"),
            AgentInfo(name="manager", class_name="UserProxyAgent"),
        ],
        tools=[
            ToolInfo(name="write_latest_iteration", function_name="write_latest_iteration", source_file=str(root / "main.py")),
            ToolInfo(name="write_settled_plan", function_name="write_settled_plan", source_file=str(root / "main.py")),
        ],
        requirements=[RequirementInfo(id="R1", description="Generate Python code and keep an iteration history.")],
        message_edges=[],
    )


def test_contract_patterns_are_generated_from_profile(tmp_path: Path) -> None:
    cases = generate_testcases(rich_profile(tmp_path), num_cases=60)
    case_types = {case.case_type for case in cases}

    assert {
        "artifact_contract",
        "filesystem_safety",
        "tool_api_contract",
        "tool_error_contract",
        "message_handoff_integrity",
        "data_invariant",
        "cli_doc_conformance",
        "autogen_wiring",
    } <= case_types
    assert any(case.metadata.get("command_override") for case in cases if case.case_type == "cli_doc_conformance")


def test_low_case_budget_keeps_core_contract_patterns(tmp_path: Path) -> None:
    cases = generate_testcases(rich_profile(tmp_path), num_cases=8)
    case_types = {case.case_type for case in cases}

    assert {"positive_smoke", "automation_no_human", "requirement_positive"} <= case_types
    assert {"artifact_contract", "filesystem_safety", "tool_api_contract"} <= case_types


def test_merge_limit_keeps_contract_patterns(tmp_path: Path) -> None:
    cases = generate_testcases(rich_profile(tmp_path), num_cases=40)
    selected = merge_testcases([], cases, limit=8)
    case_types = {case.case_type for case in selected}

    assert {"artifact_contract", "filesystem_safety", "tool_api_contract"} <= case_types


def test_domain_specific_contracts_do_not_attach_to_iterative_coding_profile(tmp_path: Path) -> None:
    profile = iterative_coding_profile(tmp_path)
    plan = build_test_plan(extract_system_features(profile))
    cases = generate_testcases(
        profile,
        num_cases=40,
        selected_patterns=selected_pattern_names(plan),
        pattern_budgets=pattern_budgets(plan),
    )
    case_types = {case.case_type for case in cases}

    assert "data_invariant" not in case_types
    assert "tool_api_contract" not in case_types
    assert "tool_error_contract" not in case_types


def test_project_name_template_uses_case_metadata(tmp_path: Path) -> None:
    case = generate_testcases(iterative_coding_profile(tmp_path), num_cases=40)
    fs_case = next(item for item in case if item.case_type == "filesystem_safety")

    assert render_case_template("{project_name}", fs_case) == "../escaped_project"


def test_project_name_template_defaults_to_safe_case_id(tmp_path: Path) -> None:
    case = generate_testcases(iterative_coding_profile(tmp_path), num_cases=1)[0]

    assert render_case_template("{project_name}", case).startswith("mas_")


def test_feature_backed_plan_selects_financial_and_http_patterns(tmp_path: Path) -> None:
    profile = rich_profile(tmp_path)
    plan = build_test_plan(extract_system_features(profile))
    selected = set(selected_pattern_names(plan))

    assert {"data_invariant", "tool_api_contract", "tool_error_contract", "autogen_wiring"} <= selected


def test_feature_backed_plan_rejects_resume_without_state_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "simple"
    root.mkdir()
    (root / "app.py").write_text("from autogen import AssistantAgent\nagent = AssistantAgent('a')\n", encoding="utf-8")
    profile = SystemProfile(
        system_id="simple",
        root_path=str(root),
        doc_path=None,
        entrypoint=str(root / "app.py"),
        agents=[AgentInfo(name="a", class_name="AssistantAgent")],
        tools=[],
        requirements=[RequirementInfo(id="R1", description="Run a simple agent task.")],
        message_edges=[],
    )
    plan = build_test_plan(extract_system_features(profile))

    assert "state_resume_contract" not in set(selected_pattern_names(plan))


def test_extract_documented_commands() -> None:
    commands = extract_documented_commands(
        "$ python -m src.main analyze AAPL\n"
        "`python app.py --help`\n"
        "The Manager is asked to request a Python creation.\n"
        "python -m venv venv\n"
        "python bad ..."
    )
    assert commands == ["python -m src.main analyze AAPL", "python app.py --help"]
