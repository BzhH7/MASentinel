from __future__ import annotations

import threading

from masentinel.agents.base import AgentDecision
from masentinel.agents.orchestrator import AgenticTestOrchestrator
from masentinel.schema import AgentInfo, SystemProfile


class _FakeDesigner:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tasks: list[dict] = []

    def run(self, task: dict) -> AgentDecision:
        with self.lock:
            self.tasks.append(task)
        batch_index = int(task["batch_index"])
        return AgentDecision(
            agent_name="TestDesignerAgent",
            task="generate_testcases",
            output={
                "testcases": [
                    {
                        "case_id": f"C{batch_index}",
                        "case_type": str(task["coverage_focus"]),
                        "objective": f"case {batch_index}",
                        "input": f"input {batch_index}",
                    }
                ],
                "confidence": 0.9,
            },
            confidence=0.9,
            model="fake",
        )


def test_parallel_test_designer_batches_collect_independent_cases() -> None:
    profile = SystemProfile(
        system_id="sys",
        root_path=".",
        doc_path=None,
        entrypoint=None,
        agents=[AgentInfo(name="a")],
        tools=[],
        requirements=[],
        message_edges=[],
    )
    designer = _FakeDesigner()

    cases = AgenticTestOrchestrator(verbose=False)._run_test_designer_batches(
        designer,
        profile,
        {},
        total_cases=4,
        batch_size=1,
        workers=3,
        system_id="sys",
    )

    assert len(cases) == 4
    assert len(designer.tasks) == 4
    assert {task["batch_index"] for task in designer.tasks} == {1, 2, 3, 4}
    assert all(task["existing_agent_cases"] == [] for task in designer.tasks)
