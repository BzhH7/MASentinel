from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class ScalableBudgetPattern:
    name = "scalable_budget"
    case_type = "scalable_budget"
    fault_modes = ["scalable_budget_error"]

    def applicable(self, profile: SystemProfile) -> bool:
        text = profile_text(profile)
        return has_any(text, ("max_round", "max turns", "records", "companies", "items", "batch", "list", "分页", "记录"))

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        return limited(
            [
                TestCase(
                    case_id=f"{profile.system_id}_BUDGET_001",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective="Round/turn budget should scale with multi-record work or batch it inside tools.",
                    input="请处理五条独立记录，每条都需要一次检索和一次更新；完成全部记录后结束。",
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=40),
                    metadata={
                        **base_metadata("scalable_budget", "profile mentions records/items and fixed round/turn budgets", "scalable_budget_error", "medium"),
                        "fixture": {"record_count": 5},
                        "required_steps_estimate": 10,
                        "assertions": ["required_steps_estimate_within_configured_budget", "all_records_processed", "termination_reason_is_completion"],
                    },
                )
            ],
            budget,
        )
