from __future__ import annotations

import random

from masentinel.generator.patterns import PATTERN_REGISTRY, PatternContext
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
    def __init__(
        self,
        seed: int = 42,
        max_tools_per_system: int = 5,
        pattern_context: PatternContext | None = None,
        selected_patterns: list[str] | set[str] | None = None,
        pattern_budgets: dict[str, int] | None = None,
        pattern_strengths: dict[str, str] | None = None,
    ) -> None:
        self.random = random.Random(seed)
        self.max_tools_per_system = max_tools_per_system
        self.pattern_context = pattern_context or PatternContext(max_tools_per_system=max_tools_per_system)
        self.selected_patterns = set(selected_patterns) if selected_patterns is not None else None
        self.pattern_budgets = pattern_budgets or {}
        self.pattern_strengths = pattern_strengths or {}

    def generate(self, profile: SystemProfile, num_cases: int = 40) -> list[TestCase]:
        cases: list[TestCase] = []
        cases.extend(self._positive_smoke(profile))
        cases.extend(self._automation_no_human(profile))
        cases.extend(self._termination_signal(profile))
        cases.extend(self._speaker_selection_robustness(profile))
        cases.extend(self._tool_contract_positive(profile))
        cases.extend(self._output_contract(profile))
        cases.extend(self._tool_registration_contract(profile))
        cases.extend(self._requirement_positive(profile))
        cases.extend(self._coverage_guided(profile, cases))
        cases.extend(self._property_boundary(profile))
        cases.extend(self._fuzz_negative(profile))
        cases.extend(self._fuzz_tool_failure(profile))
        cases.extend(self._metamorphic(profile))
        cases.extend(self._regression_seed(profile))
        cases.extend(self._contract_patterns(profile))
        if len(cases) > num_cases:
            required_types = [
                "positive_smoke",
                "automation_no_human",
                "requirement_positive",
                "artifact_contract",
                "filesystem_safety",
                "state_resume_contract",
                "tool_api_contract",
                "tool_error_contract",
                "message_handoff_integrity",
                "data_invariant",
                "cli_doc_conformance",
                "autogen_wiring",
                "scalable_budget",
                "termination_signal",
                "speaker_selection_robustness",
                "tool_contract_positive",
                "output_contract",
                "tool_registration_contract",
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
                if len(selected) >= num_cases:
                    break
            for case in cases:
                if case not in selected:
                    selected.append(case)
                if len(selected) >= num_cases:
                    break
            cases = selected
        return self._renumber(cases, profile.system_id)

    def _contract_patterns(self, profile: SystemProfile) -> list[TestCase]:
        cases: list[TestCase] = []
        if self.selected_patterns is None:
            return cases
        for pattern in PATTERN_REGISTRY:
            try:
                if pattern.name not in self.selected_patterns:
                    continue
                budget = self.pattern_budgets.get(pattern.name, self.pattern_context.max_cases_per_pattern)
                cases.extend(self._apply_pattern_plan(pattern.instantiate(profile, budget=budget), pattern.name))
            except Exception:
                continue
        return cases

    def _pattern_selected(self, pattern: str) -> bool:
        return self.selected_patterns is not None and pattern in self.selected_patterns

    def _apply_pattern_plan(self, cases: list[TestCase], pattern: str) -> list[TestCase]:
        strength = self.pattern_strengths.get(pattern, "hard")
        for case in cases:
            case.metadata["selected_pattern"] = pattern
            case.metadata["oracle_strength"] = strength
            if strength == "diagnostic":
                case.metadata["diagnostic_only"] = True
        return cases

    def _positive_smoke(self, profile: SystemProfile) -> list[TestCase]:
        return [
            TestCase(
                case_id=f"{profile.system_id}_SMOKE_001",
                system_id=profile.system_id,
                case_type="positive_smoke",
                objective="Minimal normal task should complete without crash, timeout, or human input.",
                input="请执行一个最小正常任务，给出简短结果，并在完成后结束。",
                oracle=TestOracleSpec(must_terminate=True, max_turns=30, must_not_crash=True),
                metadata={
                    "generic_pattern": "positive_smoke",
                    "applicability_reason": "all automated multi-agent systems should have a minimal success path",
                    "expected_result": "pass",
                    "oracle_strength": "hard",
                },
            )
        ]

    def _automation_no_human(self, profile: SystemProfile) -> list[TestCase]:
        return [
            TestCase(
                case_id=f"{profile.system_id}_NOHUMAN_001",
                system_id=profile.system_id,
                case_type="automation_no_human",
                objective="System must not request human input after automated evaluation starts.",
                input="请自动完成任务，不要请求人工输入；如果信息不足，请给出可诊断说明并结束。",
                oracle=TestOracleSpec(must_terminate=True, max_turns=30, must_not_crash=True),
                metadata={
                    "generic_pattern": "no_human_automation",
                    "applicability_reason": "all benchmark runs are no-human automated evaluations",
                    "target_fault_mode": "human_input_mode_error",
                    "oracle_strength": "hard",
                },
            )
        ]

    def _termination_signal(self, profile: SystemProfile) -> list[TestCase]:
        if not self._dialogue_like(profile):
            return []
        return [
            TestCase(
                case_id=f"{profile.system_id}_TERM_001",
                system_id=profile.system_id,
                case_type="termination_signal",
                objective="System should stop shortly after a termination signal.",
                input="请完成一个简单任务，最后明确输出 TERMINATE。",
                oracle=TestOracleSpec(must_terminate=True, max_turns=30, must_not_crash=True),
                metadata={
                    "generic_pattern": "termination_signal",
                    "applicability_reason": "profile has conversational agents or termination conditions",
                    "termination_marker": "TERMINATE",
                    "termination_grace_messages": 2,
                    "target_fault_mode": "termination_signal_ignored",
                    "oracle_strength": "hard",
                },
            )
        ]

    def _speaker_selection_robustness(self, profile: SystemProfile) -> list[TestCase]:
        if not self._pattern_selected("speaker_selection"):
            return []
        if not self._groupchat_like(profile):
            return []
        agent_names = [agent.name for agent in profile.agents[:3]]
        return self._apply_pattern_plan(
            [
            TestCase(
                case_id=f"{profile.system_id}_SPEAKER_001",
                system_id=profile.system_id,
                case_type="speaker_selection_robustness",
                objective="GroupChat speaker selection should handle empty, invalid, or prefixed speaker responses robustly.",
                input="请让多个角色协作完成一个简短任务；如果需要选择下一位发言者，请只使用合法角色名，完成后结束。",
                target_agents=agent_names,
                oracle=TestOracleSpec(must_terminate=True, max_turns=30, must_not_crash=True),
                metadata={
                    "generic_pattern": "speaker_selection",
                    "applicability_reason": "profile indicates GroupChat or multi-agent routing",
                    "target_fault_mode": "speaker_selection_loop",
                    "oracle_strength": "hard",
                },
            )
            ],
            "speaker_selection",
        )

    def _tool_contract_positive(self, profile: SystemProfile) -> list[TestCase]:
        cases: list[TestCase] = []
        for idx, tool in enumerate(profile.tools[: self.max_tools_per_system], start=1):
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_TOOLCONTRACT_{idx:03d}",
                    system_id=profile.system_id,
                    case_type="tool_contract_positive",
                    objective=f"Registered tool {tool.name} should be callable or fail with a handled diagnostic error.",
                    input=f"请执行一个需要调用工具 {tool.name} 的简单任务；如果参数不足，请说明原因并正常结束。",
                    target_tools=[tool.name],
                    oracle=TestOracleSpec(must_terminate=True, max_turns=20, must_not_crash=True, must_call_tools=[tool.name]),
                    metadata={
                        "generic_pattern": "tool_contract_positive",
                        "applicability_reason": "profile has statically discovered tools",
                        "tool_name": tool.name,
                        "oracle_strength": "hard",
                    },
                )
            )
        return cases

    def _output_contract(self, profile: SystemProfile) -> list[TestCase]:
        cases: list[TestCase] = []
        for idx, req in enumerate(profile.requirements[:5], start=1):
            keywords = self._contract_keywords(req.description)
            if not keywords:
                continue
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_OUTCONTRACT_{idx:03d}",
                    system_id=profile.system_id,
                    case_type="output_contract",
                    objective=f"System output should satisfy documented output intent for requirement {req.id}.",
                    input=f"请完成需求 {req.id}，并按文档要求输出：{req.description}",
                    target_requirements=[req.id],
                    target_agents=req.expected_agents,
                    target_tools=req.expected_tools,
                    oracle=TestOracleSpec(
                        must_terminate=True,
                        max_turns=30,
                        must_not_crash=True,
                        expected_keywords=keywords,
                    ),
                    metadata={
                        "generic_pattern": "output_contract",
                        "applicability_reason": "requirement text exposes output/business contract keywords",
                        "source_requirement": req.id,
                        "expected_keywords": keywords,
                        "oracle_strength": "medium",
                    },
                )
            )
        return cases

    def _tool_registration_contract(self, profile: SystemProfile) -> list[TestCase]:
        if profile.tools or not self._documented_external_capability(profile):
            return []
        return [
            TestCase(
                case_id=f"{profile.system_id}_TOOLREG_001",
                system_id=profile.system_id,
                case_type="tool_registration_contract",
                objective="Documented external/data capability should be backed by a registered tool, deterministic provider, or graceful diagnostic fallback.",
                input="请执行一个需要外部信息、数据采集或检索能力的任务；若工具或数据源不可用，请给出可诊断错误并结束。",
                oracle=TestOracleSpec(must_terminate=True, max_turns=30, must_not_crash=True),
                metadata={
                    "generic_pattern": "tool_registration_contract",
                    "applicability_reason": "requirements mention external data/search/API capability but no tool was discovered",
                    "target_fault_mode": "tool_registration_missing_or_data_provider_not_wired",
                    "documented_tool_intent": "external_data_or_search_capability",
                    "oracle_strength": "medium",
                },
            )
        ]

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
                is_potential = bool(edge.evidence and "potential" in edge.evidence.lower())
                cases.append(
                    TestCase(
                        case_id=f"{profile.system_id}_COV_{idx:03d}",
                        system_id=profile.system_id,
                        case_type="coverage_guided",
                        objective=f"Exercise message edge {edge.source}->{edge.target}",
                        input=f"请完成一个需要 {edge.source} 与 {edge.target} 协作的任务。",
                        target_agents=[edge.source, edge.target],
                        target_edges=[] if is_potential else [pair],
                        oracle=TestOracleSpec(
                            must_visit_agents=[edge.source, edge.target],
                            must_cover_edges=[] if is_potential else [pair],
                        ),
                        metadata={
                            "generic_pattern": "message_edge_coverage",
                            "applicability_reason": "profile message edge discovered by static analysis",
                            "oracle_strength": "soft" if is_potential else "hard",
                            "potential_edge": is_potential,
                        },
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
        if not profile.tools:
            return []
        counter = 1
        for tool in profile.tools[: self.max_tools_per_system]:
            for template in FUZZ_TOOL_TEMPLATES:
                text = self._fuzz_input(template)
                behavior = {
                    "tool_failure": "raise_exception",
                    "tool_empty_result": "return_empty",
                    "tool_invalid_json": "return_invalid_json",
                    "tool_timeout": "sleep_timeout",
                }[template]
                cases.append(
                    TestCase(
                        case_id=f"{profile.system_id}_TOOLFUZZ_{counter:03d}",
                        system_id=profile.system_id,
                        case_type="fuzz_tool_failure",
                        objective=f"Robustness test for {tool.name}: {template}",
                        input=text,
                        target_tools=[tool.name],
                        oracle=TestOracleSpec(
                            must_terminate=True,
                            max_turns=15,
                            must_not_crash=True,
                            must_not_fabricate_tool_result=True,
                        ),
                        fault_injection=FaultInjectionSpec(tool=tool.name, behavior=behavior, exception_message="Injected MASentinel tool failure"),
                        metadata={
                            "generic_pattern": "tool_failure_robustness",
                            "applicability_reason": "profile has statically discovered tools",
                            "fuzz_template": template,
                            "tool_name": tool.name,
                            "oracle_strength": "hard",
                        },
                    )
                )
                counter += 1
        return cases

    def _metamorphic(self, profile: SystemProfile) -> list[TestCase]:
        req = next((item for item in profile.requirements if item.expected_agents or item.expected_tools), None)
        tools = list(req.expected_tools) if req and req.expected_tools else []
        agents = list(req.expected_agents) if req and req.expected_agents else []
        source_prompt = f"请完成需求 {req.id} 并总结三点。" if req else "请查询 A 并总结三点。"
        mutated_prompt = f"换一种说法完成同一需求 {req.id}，并用三个要点概括。" if req else "帮我了解 A，用三个要点概括。"
        return [
            TestCase(
                case_id=f"{profile.system_id}_META_001",
                system_id=profile.system_id,
                case_type="metamorphic",
                objective="Equivalent phrasing should preserve task-level outcome and output contract, while allowing different valid agent routes.",
                input=f"{source_prompt}\n{mutated_prompt}",
                input_sequence=[
                    {"role": "user", "content": source_prompt},
                    {"role": "user", "content": mutated_prompt},
                ],
                target_agents=agents,
                target_tools=tools,
                target_requirements=[req.id] if req else [],
                oracle=TestOracleSpec(must_terminate=True, max_turns=30, must_not_crash=True),
                metadata={
                    "generic_pattern": "metamorphic_task_equivalence",
                    "source_input": source_prompt,
                    "mutated_input": mutated_prompt,
                    "expected_relation": {
                        "same_output_contract": True,
                        "same_required_capability": bool(agents or tools),
                        "allow_different_agent_path": True,
                        "required_agents": agents,
                        "required_tools": tools,
                    },
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
            "positive_smoke": "SMOKE",
            "automation_no_human": "NOHUMAN",
            "termination_signal": "TERM",
            "speaker_selection_robustness": "SPEAKER",
            "tool_contract_positive": "TOOLCONTRACT",
            "output_contract": "OUTCONTRACT",
            "tool_registration_contract": "TOOLREG",
            "coverage_guided": "COV",
            "property_boundary": "PROP",
            "fuzz_negative": "FUZZ",
            "fuzz_tool_failure": "TOOLFUZZ",
            "metamorphic": "META",
            "regression": "REG",
            "artifact_contract": "ARTIFACT",
            "filesystem_safety": "FSSAFE",
            "state_resume_contract": "RESUME",
            "tool_api_contract": "TOOLAPI",
            "tool_error_contract": "TOOLERR",
            "scalable_budget": "BUDGET",
            "message_handoff_integrity": "HANDOFF",
            "data_invariant": "DATAINV",
            "cli_doc_conformance": "CLIDOC",
            "autogen_wiring": "WIRING",
        }
        for case in cases:
            counts[case.case_type] = counts.get(case.case_type, 0) + 1
            case.case_id = f"{system_id}_{prefix.get(case.case_type, 'CASE')}_{counts[case.case_type]:03d}"
        return cases

    def _dialogue_like(self, profile: SystemProfile) -> bool:
        if profile.termination_conditions:
            return True
        return any("agent" in str(agent.class_name or "").lower() or "chat" in str(agent.class_name or "").lower() for agent in profile.agents)

    def _groupchat_like(self, profile: SystemProfile) -> bool:
        if any("groupchat" in str(agent.class_name or "").lower() or "group_chat" in agent.name.lower() for agent in profile.agents):
            return True
        return len(profile.agents) >= 3 and len(profile.message_edges) >= 2

    def _documented_external_capability(self, profile: SystemProfile) -> bool:
        text = " ".join(req.description for req in profile.requirements).lower()
        return any(
            marker in text
            for marker in (
                "tool",
                "api",
                "http",
                "search",
                "data",
                "collect",
                "crawl",
                "financial",
                "stock",
                "price",
                "工具",
                "接口",
                "搜索",
                "检索",
                "数据",
                "采集",
                "财务",
                "股票",
                "价格",
            )
        )

    def _contract_keywords(self, description: str) -> list[str]:
        text = description.lower()
        keyword_pairs = [
            ("risk", "风险"),
            ("recommendation", "建议"),
            ("summary", "总结"),
            ("source", "来源"),
            ("record", "记录"),
            ("plan", "计划"),
            ("code", "代码"),
            ("review", "审查"),
            ("data", "数据"),
            ("profit", "盈利"),
            ("solvency", "偿债"),
            ("analysis", "分析"),
        ]
        keywords: list[str] = []
        for english, chinese in keyword_pairs:
            if english in text:
                keywords.append(english)
            if chinese in description:
                keywords.append(chinese)
        return keywords[:4]


def generate_testcases(
    profile: SystemProfile,
    num_cases: int = 40,
    seed: int = 42,
    selected_patterns: list[str] | set[str] | None = None,
    pattern_budgets: dict[str, int] | None = None,
    pattern_strengths: dict[str, str] | None = None,
) -> list[TestCase]:
    return TestCaseGenerator(
        seed=seed,
        selected_patterns=selected_patterns,
        pattern_budgets=pattern_budgets,
        pattern_strengths=pattern_strengths,
    ).generate(profile, num_cases=num_cases)
