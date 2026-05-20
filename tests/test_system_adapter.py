from masentinel.runner.system_adapter import build_command, build_env
from masentinel.schema import TestCase


def test_system_adapter_renders_stock_symbol_from_case_input(tmp_path) -> None:
    config = {
        "entrypoint": str(tmp_path / "main.py"),
        "run": {"command": "python main.py analyze {stock_symbol}", "working_dir": str(tmp_path)},
    }
    case = TestCase(case_id="C1", system_id="finance", case_type="x", objective="", input="Analyze TSLA risk")

    command = build_command(config, case)

    assert command[-1] == "TSLA"


def test_system_adapter_exports_message_template(tmp_path) -> None:
    config = {
        "run": {"message_template": "Task: {input}", "working_dir": str(tmp_path)},
    }
    case = TestCase(case_id="C1", system_id="research", case_type="x", objective="", input="research pricing")

    env = build_env(config, case, str(tmp_path / "trace.json"))

    assert env["MAS_TARGET_MESSAGE"] == "Task: research pricing"


def test_system_adapter_uses_case_command_override(tmp_path) -> None:
    config = {
        "run": {"command": "python main.py analyze AAPL", "working_dir": str(tmp_path)},
    }
    case = TestCase(
        case_id="C1",
        system_id="finance",
        case_type="cli_doc_conformance",
        objective="",
        input="",
        metadata={"command_override": "python -m src.main interactive"},
    )

    command = build_command(config, case)

    assert command[1:] == ["-m", "src.main", "interactive"]


def test_system_adapter_exports_contract_fixture_env(tmp_path) -> None:
    config = {"run": {"working_dir": str(tmp_path)}}
    case = TestCase(
        case_id="C1",
        system_id="research",
        case_type="tool_error_contract",
        objective="",
        input="",
        metadata={"mock_http": True, "http_fixture": {"status_code": 401}},
    )

    env = build_env(config, case, str(tmp_path / "trace.json"))

    assert env["MAS_MOCK_EXTERNAL_HTTP"] == "1"
    assert "MAS_HTTP_FIXTURE_JSON" in env
