from pathlib import Path

from masentinel.runner.case_runner import CaseRunner
from masentinel.schema import TestCase


def test_interactive_runner_answers_prompt_sequence(tmp_path: Path) -> None:
    script = tmp_path / "ask.py"
    script.write_text(
        "choice = input('Selection:')\n"
        "task = input('What python creation would you like?')\n"
        "name = input('What name would you like to give this project?')\n"
        "print(f'CHOICE={choice};TASK={task};NAME={name}')\n",
        encoding="utf-8",
    )
    config = {
        "system_id": "toy",
        "root_path": str(tmp_path),
        "run": {
            "command": "python ask.py",
            "working_dir": str(tmp_path),
            "input_mode": "interactive",
            "timeout_seconds": 5,
            "interaction": {
                "prompt_responses": [
                    {"trigger": "Selection:", "response": "1"},
                    {"trigger": "What python creation would you like?", "response": "{input}"},
                    {"trigger": "What name would you like to give this project?", "response": "mas_{safe_case_id}"},
                ]
            },
        },
    }
    case = TestCase(case_id="C 1", system_id="toy", case_type="interactive", objective="", input="build a calculator")

    trace = CaseRunner(config, tmp_path / "traces").run_case(case)

    assert trace.status == "passed"
    assert "CHOICE=1" in (trace.stdout or "")
    assert "TASK=build a calculator" in (trace.stdout or "")
    assert "NAME=mas_C_1" in (trace.stdout or "")
    assert len(trace.metadata["interaction_responses"]) == 3


def test_case_runner_cleans_only_masentinel_isolated_paths(tmp_path: Path) -> None:
    isolated = tmp_path / ".masentinel_projects" / "C1"
    isolated.mkdir(parents=True)
    (isolated / "old.txt").write_text("old", encoding="utf-8")
    script = tmp_path / "ok.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    config = {
        "system_id": "toy",
        "root_path": str(tmp_path),
        "run": {
            "command": "python ok.py",
            "working_dir": str(tmp_path),
            "input_mode": "stdin",
            "timeout_seconds": 5,
            "clean_isolated_paths_before_case": True,
            "isolated_paths": [".masentinel_projects/{safe_case_id}", "."],
        },
    }
    case = TestCase(case_id="C1", system_id="toy", case_type="cleanup", objective="", input="")

    trace = CaseRunner(config, tmp_path / "traces").run_case(case)

    assert trace.status == "passed"
    statuses = {item["path"]: item["status"] for item in trace.metadata["isolated_cleanup"]}
    assert statuses[str(isolated.resolve())] == "removed"
    assert statuses[str(tmp_path.resolve())] == "skipped_unsafe"
