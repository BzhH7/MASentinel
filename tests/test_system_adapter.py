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
