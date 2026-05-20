from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class AutoGenWiringPattern:
    name = "autogen_wiring"
    case_type = "autogen_wiring"
    fault_modes = ["autogen_wiring_missing"]

    def applicable(self, profile: SystemProfile) -> bool:
        text = profile_text(profile)
        doc_claims_agents = has_any(text, ("autogen", "multi-agent", "multi agent", "多智能体", "agentorchestrator", "agentfactory", "groupchat"))
        code_has_agents = bool(profile.agents) or has_any(text, ("AssistantAgent", "UserProxyAgent", "GroupChat", "AgentOrchestrator", "AgentFactory"))
        return doc_claims_agents and code_has_agents

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        expected_agents = [agent.name for agent in profile.agents[:4]]
        return limited(
            [
                TestCase(
                    case_id=f"{profile.system_id}_WIRING_001",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective="Documented AutoGen/multi-agent workflow should initialize and route through non-empty agents.",
                    input="请运行一个需要文档中多智能体协作的正常任务，并输出各角色的处理摘要。",
                    target_agents=expected_agents,
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=35, must_visit_agents=expected_agents),
                    metadata={
                        **base_metadata("autogen_wiring_conformance", "profile/doc claims AutoGen or multi-agent orchestration", "autogen_wiring_missing", "hard"),
                        "assertions": [
                            "agent_factory_creates_nonempty_agents",
                            "orchestrator_has_nonempty_agent_map",
                            "runtime_trace_contains_documented_agents",
                        ],
                        "static_risks": profile.raw_notes.get("autogen_wiring_risks", []),
                    },
                )
            ],
            budget,
        )
