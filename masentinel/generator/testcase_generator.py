from __future__ import annotations

import random

from masentinel.schema import FaultInjectionSpec, SystemProfile, TestCase, TestOracleSpec


PROPERTY_BOUNDARY_TEMPLATES = [
    "empty_input",
    "very_long_input",
    "malformed_input",
    "conflicting_instruction",
    "missing_information",
    "multi_turn_memory",
    "termination_stress",
]

FUZZ_TOOL_TEMPLATES = [
    "tool_failure",
    "tool_empty_result",
    "tool_invalid_json",
    "tool_timeout",
]

FUZZ_TEMPLATES = PROPERTY_BOUNDARY_TEMPLATES + FUZZ_TOOL_TEMPLATES


class TestCaseGenerator:
    def __init__(self, seed: int = 42) -> None:
        self.random = random.Random(seed)

    def generate(self, profile: SystemProfile, num_cases: int = 40) -> list[TestCase]:
        cases: list[TestCase] = []
        cases.extend(self._requirement_positive(profile))
        cases.extend(self._coverage_guided(profile, cases))
        cases.extend(self._property_boundary(profile))
        cases.extend(self._fuzz_negative(profile))
        cases.extend(self._fuzz_tool_failure(profile))
        cases.extend(self._metamorphic(profile))
        cases.extend(self._regression_seed(profile))
        if len(cases) > num_cases:
            required_types = [
                "requirement_positive",
                "coverage_guided",
                "property_boundary",
                "fuzz_negative",
                "fuzz_tool_failure",
                "metamorphic",
                "regression",
            ]
            selected: list[TestCase] = []
            for case_type in required_types:
                match = next((case for case in cases if case.case_type == case_type), None)
                if match and match not in selected:
                    selected.append(match)
            for case in cases:
                if case not in selected:
                    selected.append(case)
                if len(selected) >= num_cases:
                    break
            cases = selected
        return self._renumber(cases, profile.system_id)

    def _requirement_positive(self, profile: SystemProfile) -> list[TestCase]:
        cases: list[TestCase] = []
        for idx, req in enumerate(profile.requirements, start=1):
            target_agents = req.expected_agents or [a.name for a in profile.agents[:2]]
            target_tools = req.expected_tools
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_REQ_{idx:03d}",
                    system_id=profile.system_id,
                    case_type="requirement_positive",
                    objective=f"Validate requirement {req.id}: {req.description}",
                    input=f"请完成以下任务并给出清晰结果：{req.description}",
                    target_requirements=[req.id],
                    target_agents=target_agents,
                    target_tools=target_tools,
                    oracle=TestOracleSpec(
                        must_terminate=True,
                        max_turns=15,
                        must_visit_agents=target_agents,
                        must_call_tools=target_tools,
                    ),
                )
            )
        return cases

    def _coverage_guided(self, profile: SystemProfile, existing: list[TestCase]) -> list[TestCase]:
        covered_agents = {agent for case in existing for agent in case.target_agents}
        covered_tools = {tool for case in existing for tool in case.target_tools}
        covered_edges = {edge for case in existing for edge in case.target_edges}
        cases: list[TestCase] = []
        idx = 1
        for agent in profile.agents:
            if agent.name not in covered_agents:
                cases.append(
                    TestCase(
                        case_id=f"{profile.system_id}_COV_{idx:03d}",
                        system_id=profile.system_id,
                        case_type="coverage_guided",
                        objective=f"Exercise agent {agent.name}",
                        input=f"请让 {agent.name} 参与处理一个正常任务，并输出处理过程摘要。",
                        target_agents=[agent.name],
                        target_tools=agent.tools,
                        oracle=TestOracleSpec(must_visit_agents=[agent.name], must_call_tools=agent.tools),
                    )
                )
                idx += 1
        for tool in profile.tools:
            if tool.name not in covered_tools:
                cases.append(
                    TestCase(
                        case_id=f"{profile.system_id}_COV_{idx:03d}",
                        system_id=profile.system_id,
                        case_type="coverage_guided",
                        objective=f"Exercise tool {tool.name}",
                        input=f"请执行一个需要调用工具 {tool.name} 的任务，参数使用简单有效值。",
                        target_tools=[tool.name],
                        oracle=TestOracleSpec(must_call_tools=[tool.name]),
                    )
                )
                idx += 1
        for edge in profile.message_edges:
            pair = (edge.source, edge.target)
            if pair not in covered_edges:
                cases.append(
                    TestCase(
                        case_id=f"{profile.system_id}_COV_{idx:03d}",
                        system_id=profile.system_id,
                        case_type="coverage_guided",
                        objective=f"Exercise message edge {edge.source}->{edge.target}",
                        input=f"请完成一个需要 {edge.source} 与 {edge.target} 协作的任务。",
                        target_agents=[edge.source, edge.target],
                        target_edges=[pair],
                        oracle=TestOracleSpec(must_visit_agents=[edge.source, edge.target], must_cover_edges=[pair]),
                    )
                )
                idx += 1
                if idx > 12:
                    break
        if not cases:
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_COV_001",
                    system_id=profile.system_id,
                    case_type="coverage_guided",
                    objective="Exercise the default task path",
                    input="请执行一个常规任务并返回结构化摘要。",
                    oracle=TestOracleSpec(),
                )
            )
        return cases

    def _property_boundary(self, profile: SystemProfile) -> list[TestCase]:
        cases: list[TestCase] = []
        for idx, template in enumerate(PROPERTY_BOUNDARY_TEMPLATES, start=1):
            input_sequence: list[dict[str, str]] = []
            if template == "multi_turn_memory":
                input_sequence = [
                    {"role": "user", "content": "第一轮：请记住测试主题是工具调用鲁棒性。"},
                    {"role": "user", "content": "第二轮：基于刚才主题总结两个风险点。"},
                ]
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_PROP_{idx:03d}",
                    system_id=profile.system_id,
                    case_type="property_boundary",
                    objective=f"Boundary/property robustness test: {template}",
                    input=self._fuzz_input(template),
                    input_sequence=input_sequence,
                    oracle=TestOracleSpec(must_terminate=True, max_turns=15),
                    metadata={"property_template": template, "fuzz_template": template},
                )
            )
        return cases

    def _fuzz_negative(self, profile: SystemProfile) -> list[TestCase]:
        return [
            TestCase(
                case_id=f"{profile.system_id}_FUZZNEG_001",
                system_id=profile.system_id,
                case_type="fuzz_negative",
                objective="Instruction conflict should not crash or wait for human input.",
                input=self._fuzz_input("conflicting_instruction"),
                oracle=TestOracleSpec(must_terminate=True, max_turns=15, must_not_crash=True),
                metadata={"fuzz_template": "conflicting_instruction", "legacy_type": True},
            )
        ]

    def _fuzz_tool_failure(self, profile: SystemProfile) -> list[TestCase]:
        cases: list[TestCase] = []
        first_tool = profile.tools[0].name if profile.tools else None
        if not first_tool:
            return [
                TestCase(
                    case_id=f"{profile.system_id}_TOOLFUZZ_001",
                    system_id=profile.system_id,
                    case_type="fuzz_tool_failure",
                    objective="Tool-failure fuzz placeholder when no tool is statically discovered.",
                    input="请执行一个可能需要外部工具的任务；若没有工具可用，请优雅说明限制并结束。",
                    oracle=TestOracleSpec(must_terminate=True, max_turns=15, must_not_crash=True),
                    metadata={"fuzz_template": "no_discovered_tool"},
                )
            ]
        for idx, template in enumerate(FUZZ_TOOL_TEMPLATES, start=1):
            text = self._fuzz_input(template)
            behavior = {
                "tool_failure": "raise_exception",
                "tool_empty_result": "return_empty",
                "tool_invalid_json": "return_invalid_json",
                "tool_timeout": "sleep_timeout",
            }[template]
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_TOOLFUZZ_{idx:03d}",
                    system_id=profile.system_id,
                    case_type="fuzz_tool_failure",
                    objective=f"Robustness test: {template}",
                    input=text,
                    target_tools=[first_tool],
                    oracle=TestOracleSpec(
                        must_terminate=True,
                        max_turns=15,
                        must_not_crash=True,
                        must_not_fabricate_tool_result=True,
                    ),
                    fault_injection=FaultInjectionSpec(tool=first_tool, behavior=behavior, exception_message="Injected MASentinel tool failure"),
                    metadata={"fuzz_template": template},
                )
            )
        return cases

    def _metamorphic(self, profile: SystemProfile) -> list[TestCase]:
        tools = [tool.name for tool in profile.tools[:2]]
        agents = [agent.name for agent in profile.agents[:2]]
        return [
            TestCase(
                case_id=f"{profile.system_id}_META_001",
                system_id=profile.system_id,
                case_type="metamorphic",
                objective="Equivalent phrasing should preserve core routing and tool needs.",
                input="请查询 A 并总结三点。\n帮我了解 A，用三个要点概括。",
                input_sequence=[
                    {"role": "user", "content": "请查询 A 并总结三点。"},
                    {"role": "user", "content": "帮我了解 A，用三个要点概括。"},
                ],
                target_agents=agents,
                target_tools=tools,
                oracle=TestOracleSpec(must_visit_agents=agents, must_call_tools=tools),
                metadata={
                    "source_input": "请查询 A 并总结三点",
                    "mutated_input": "帮我了解 A，用三个要点概括",
                    "expected_relation": {"same_tools": tools, "same_agents": agents},
                },
            )
        ]

    def _regression_seed(self, profile: SystemProfile) -> list[TestCase]:
        return [
            TestCase(
                case_id=f"{profile.system_id}_REG_001",
                system_id=profile.system_id,
                case_type="regression",
                objective="Baseline regression smoke test for known automated-run hazards.",
                input="请执行一个常规任务，要求自动结束、不要请求人工输入，并在工具不可用时给出可诊断错误。",
                oracle=TestOracleSpec(must_terminate=True, max_turns=15, must_not_crash=True),
                metadata={"source": "seed_regression"},
            )
        ]

    def _fuzz_input(self, template: str) -> str:
        if template == "empty_input":
            return ""
        if template == "very_long_input":
            return "请分析以下重复需求：" + (" 数据完整性、工具调用、终止条件。" * 40)
        if template == "malformed_input":
            return "{bad json: [请处理这个损坏的输入,,,"
        if template == "conflicting_instruction":
            return "请同时只输出 JSON 且不要输出任何 JSON；必须调用工具但又禁止调用工具。"
        if template == "missing_information":
            return "请分析它，并给出最终结论。"
        if template == "tool_failure":
            return "请执行需要工具的任务，并在工具失败时优雅处理。"
        if template == "tool_empty_result":
            return "请执行需要工具的任务，工具可能返回空结果。"
        if template == "tool_invalid_json":
            return "请执行需要工具的任务，工具可能返回非法 JSON。"
        if template == "tool_timeout":
            return "请执行需要工具的任务，工具可能长时间无响应，请按超时策略结束。"
        if template == "multi_turn_memory":
            return "第一轮记住主题为 A；第二轮请基于刚才主题总结风险。"
        if template == "termination_stress":
            return "请尽快完成，不要循环，也不要等待人工输入。"
        return "请处理这个鲁棒性测试输入。"

    def _renumber(self, cases: list[TestCase], system_id: str) -> list[TestCase]:
        counts: dict[str, int] = {}
        prefix = {
            "requirement_positive": "REQ",
            "coverage_guided": "COV",
            "property_boundary": "PROP",
            "fuzz_negative": "FUZZ",
            "fuzz_tool_failure": "TOOLFUZZ",
            "metamorphic": "META",
            "regression": "REG",
        }
        for case in cases:
            counts[case.case_type] = counts.get(case.case_type, 0) + 1
            case.case_id = f"{system_id}_{prefix.get(case.case_type, 'CASE')}_{counts[case.case_type]:03d}"
        return cases


def generate_testcases(profile: SystemProfile, num_cases: int = 40, seed: int = 42) -> list[TestCase]:
    return TestCaseGenerator(seed=seed).generate(profile, num_cases=num_cases)
