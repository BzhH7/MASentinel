from pathlib import Path

from masentinel.generator.patterns import extract_documented_commands
from masentinel.analyzer.feature_extractor import extract_system_features
from masentinel.generator.pattern_selector import active_pattern_names, build_test_plan, pattern_budgets, pattern_strengths, selected_pattern_names
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


def cases_from_plan(profile: SystemProfile, num_cases: int = 60):
    plan = build_test_plan(extract_system_features(profile))
    return generate_testcases(
        profile,
        num_cases=num_cases,
        selected_patterns=active_pattern_names(plan),
        pattern_budgets=pattern_budgets(plan),
        pattern_strengths=pattern_strengths(plan),
    )


def test_contract_patterns_are_generated_from_profile(tmp_path: Path) -> None:
    cases = cases_from_plan(rich_profile(tmp_path), num_cases=60)
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
    cases = cases_from_plan(rich_profile(tmp_path), num_cases=8)
    case_types = {case.case_type for case in cases}

    assert {"positive_smoke", "automation_no_human", "requirement_positive"} <= case_types
    assert {"artifact_contract", "filesystem_safety", "tool_api_contract"} <= case_types


def test_merge_limit_keeps_contract_patterns(tmp_path: Path) -> None:
    cases = cases_from_plan(rich_profile(tmp_path), num_cases=40)
    selected = merge_testcases([], cases, limit=8)
    case_types = {case.case_type for case in selected}

    assert {"artifact_contract", "filesystem_safety", "tool_api_contract"} <= case_types


def test_domain_specific_contracts_do_not_attach_to_iterative_coding_profile(tmp_path: Path) -> None:
    profile = iterative_coding_profile(tmp_path)
    plan = build_test_plan(extract_system_features(profile))
    cases = generate_testcases(
        profile,
        num_cases=40,
        selected_patterns=active_pattern_names(plan),
        pattern_budgets=pattern_budgets(plan),
        pattern_strengths=pattern_strengths(plan),
    )
    case_types = {case.case_type for case in cases}

    assert "data_invariant" not in case_types
    assert "tool_api_contract" not in case_types
    assert "tool_error_contract" not in case_types


def test_project_name_template_uses_case_metadata(tmp_path: Path) -> None:
    case = cases_from_plan(iterative_coding_profile(tmp_path), num_cases=40)
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
    assert plan["selection_mode"] == "deterministic_fallback"


def test_generator_without_test_plan_preserves_baseline_but_no_contract_patterns(tmp_path: Path) -> None:
    cases = generate_testcases(rich_profile(tmp_path), num_cases=60)
    case_types = {case.case_type for case in cases}

    assert {"positive_smoke", "automation_no_human", "requirement_positive"} <= case_types
    assert "tool_api_contract" not in case_types
    assert "data_invariant" not in case_types


def test_agent_selected_patterns_are_not_auto_expanded_by_verifier(tmp_path: Path) -> None:
    profile = rich_profile(tmp_path)
    plan = build_test_plan(
        extract_system_features(profile),
        {
            "selected_patterns": [
                {"pattern": "data_invariant", "reasons": ["Financial metric code is present."]},
            ],
            "rejected_patterns": [],
            "diagnostic_only_patterns": [],
        },
    )
    selected = set(selected_pattern_names(plan))
    omitted = {item["pattern"] for item in plan["verifier_omitted_applicable_patterns"]}

    assert plan["selection_mode"] == "agent_verified"
    assert selected == {"data_invariant"}
    assert {"tool_api_contract", "tool_error_contract", "autogen_wiring"} <= omitted


def test_agent_selected_pattern_must_pass_feature_verifier(tmp_path: Path) -> None:
    profile = iterative_coding_profile(tmp_path)
    plan = build_test_plan(
        extract_system_features(profile),
        {
            "selected_patterns": [
                {"pattern": "data_invariant", "reasons": ["Agent guessed this incorrectly."]},
            ],
            "rejected_patterns": [],
            "diagnostic_only_patterns": [],
        },
    )

    assert "data_invariant" not in set(selected_pattern_names(plan))
    assert any(
        item.get("pattern") == "data_invariant" and item.get("rejected_by_verifier")
        for item in plan["rejected_patterns"]
    )


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


def test_system1_like_profile_selects_artifact_filesystem_resume_and_rejects_data_tool(tmp_path: Path) -> None:
    root = tmp_path / "system1_like"
    root.mkdir()
    (root / "README.md").write_text("AutoGen iterative coding demo. Resume latest iteration from script_v and comments_v artifacts.\n", encoding="utf-8")
    (root / "main.py").write_text(
        """
from autogen import AssistantAgent, UserProxyAgent
import os

def write_latest_iteration(project_name, code):
    os.makedirs(project_name, exist_ok=True)
    open(os.path.join(project_name, "script_v1.py"), "w").write(code)

def write_comments(project_name, text):
    open(os.path.join(project_name, "comments_v1.txt"), "w").write(text)

def write_settled_plan(project_name, plan):
    open(os.path.join(project_name, "masterplan.md"), "w").write(plan)
""",
        encoding="utf-8",
    )
    profile = SystemProfile(
        system_id="s1_like",
        root_path=str(root),
        doc_path=str(root / "README.md"),
        entrypoint=str(root / "main.py"),
        agents=[AgentInfo(name="planner", class_name="AssistantAgent"), AgentInfo(name="programmer", class_name="AssistantAgent")],
        tools=[ToolInfo(name="write_latest_iteration", source_file=str(root / "main.py"))],
        requirements=[RequirementInfo(id="R1", description="Generate versioned code artifacts and resume state.")],
        message_edges=[],
    )

    plan = build_test_plan(extract_system_features(profile))
    selected = set(selected_pattern_names(plan))
    rejected = {item["pattern"] for item in plan["rejected_patterns"]}

    assert {"artifact_contract", "filesystem_safety", "state_resume_contract"} <= selected
    assert {"data_invariant", "tool_api_contract"} <= rejected


def test_system2_like_profile_selects_tool_scalable_speaker_and_rejects_data_resume(tmp_path: Path) -> None:
    root = tmp_path / "system2_like"
    root.mkdir()
    (root / "README.md").write_text("AutoGen GroupChat researches all Airtable records with multiple agents.\n", encoding="utf-8")
    (root / "app.py").write_text(
        """
import requests
from autogen import AssistantAgent, GroupChat, GroupChatManager

def get_airtable_records():
    return requests.get("https://api.airtable.com/v0/base/table").json()["records"]

agents = [AssistantAgent("researcher"), AssistantAgent("writer")]
chat = GroupChat(agents=agents, messages=[], max_round=8, speaker_selection_method="auto")
manager = GroupChatManager(groupchat=chat)
""",
        encoding="utf-8",
    )
    profile = SystemProfile(
        system_id="s2_like",
        root_path=str(root),
        doc_path=str(root / "README.md"),
        entrypoint=str(root / "app.py"),
        agents=[AgentInfo(name="researcher", class_name="AssistantAgent"), AgentInfo(name="writer", class_name="AssistantAgent")],
        tools=[ToolInfo(name="get_airtable_records", source_file=str(root / "app.py"))],
        requirements=[RequirementInfo(id="R1", description="Research all company records from Airtable.")],
        message_edges=[],
    )

    plan = build_test_plan(extract_system_features(profile))
    selected = set(selected_pattern_names(plan))
    rejected = {item["pattern"] for item in plan["rejected_patterns"]}

    assert {"tool_api_contract", "tool_error_contract", "scalable_budget", "speaker_selection"} <= selected
    assert {"data_invariant", "state_resume_contract"} <= rejected


def test_system3_like_profile_selects_handoff_data_cli_wiring_and_rejects_resume(tmp_path: Path) -> None:
    root = tmp_path / "system3_like"
    root.mkdir()
    (root / "README.md").write_text(
        "Financial AutoGen multi-agent CLI\n\n```bash\npython -m src.main analyze AAPL\npython -m src.main portfolio AAPL MSFT\n```\n",
        encoding="utf-8",
    )
    (root / "app.py").write_text(
        """
import argparse
import pandas as pd
from autogen import AssistantAgent

def calculate_financial_metrics(df: pd.DataFrame):
    return {"profit_margin": df["net_income"].sum() / df["revenue"].sum()}

def calculate_risk_metrics(prices: pd.DataFrame):
    returns = prices.pct_change()
    return {"var_95": returns.quantile(0.05), "max_drawdown": prices.max() - prices.min()}

def conduct_analysis(data_agent, risk_agent):
    data = data_agent.last_message()
    return risk_agent.generate_reply(messages=[{"content": "analysis results: " + data}])
""",
        encoding="utf-8",
    )
    profile = SystemProfile(
        system_id="s3_like",
        root_path=str(root),
        doc_path=str(root / "README.md"),
        entrypoint=str(root / "app.py"),
        agents=[AgentInfo(name="data", class_name="AssistantAgent"), AgentInfo(name="risk", class_name="AssistantAgent")],
        tools=[],
        requirements=[RequirementInfo(id="R1", description="Analyze financial and risk metrics from CLI.")],
        message_edges=[],
        raw_notes={"autogen_wiring_risks": [{"file": str(root / "app.py"), "line": "1", "risk": "orchestrator not wired"}]},
    )

    plan = build_test_plan(extract_system_features(profile))
    selected = set(selected_pattern_names(plan))
    rejected = {item["pattern"] for item in plan["rejected_patterns"]}

    assert {"message_handoff_integrity", "data_invariant", "cli_doc_conformance", "autogen_wiring"} <= selected
    assert "state_resume_contract" in rejected


def test_extract_documented_commands() -> None:
    commands = extract_documented_commands(
        "$ python -m src.main analyze AAPL\n"
        "`python app.py --help`\n"
        "The Manager is asked to request a Python creation.\n"
        "python -m venv venv\n"
        "python bad ..."
    )
    assert commands == ["python -m src.main analyze AAPL", "python app.py --help"]
