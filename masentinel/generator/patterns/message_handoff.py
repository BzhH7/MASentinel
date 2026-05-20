from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class MessageHandoffPattern:
    name = "message_handoff_integrity"
    case_type = "message_handoff_integrity"
    fault_modes = ["message_handoff_terminate_only", "message_handoff_empty"]

    def applicable(self, profile: SystemProfile) -> bool:
        text = profile_text(profile)
        return "last_message(" in text or "last_message" in text or len(profile.message_edges) >= 2 or has_any(text, ("handoff", "downstream", "previous analysis"))

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        return limited(
            [
                TestCase(
                    case_id=f"{profile.system_id}_HANDOFF_001",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective="Downstream agent must receive substantive prior assistant output, not TERMINATE, empty content, or an auto-reply.",
                    input="请完成一个需要多阶段分析的任务，前一阶段结果必须交给后一阶段；最终给出汇总结论。",
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=35),
                    metadata={
                        **base_metadata("message_handoff_integrity", "profile has chained workflow or last_message style handoff", "message_handoff_error"),
                        "assertions": [
                            "forwarded_content_not_terminate_only",
                            "forwarded_content_from_expected_sender",
                            "forwarded_content_non_empty",
                        ],
                    },
                )
            ],
            budget,
        )
