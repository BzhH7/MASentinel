from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class StateResumePattern:
    name = "state_resume_contract"
    case_type = "state_resume_contract"
    fault_modes = ["resume_state_incomplete"]

    def applicable(self, profile: SystemProfile) -> bool:
        text = profile_text(profile)
        return has_any(text, ("resume", "continue", "latest", "version", "iteration", "masterplan", "script_v", "comments_v", "继续", "恢复"))

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        return limited(
            [
                TestCase(
                    case_id=f"{profile.system_id}_RESUME_001",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective="A partial on-disk state should be resumed or reported explicitly instead of silently ignored.",
                    input="Continue the existing project from the latest script and preserve existing state.",
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=30),
                    metadata={
                        **base_metadata("partial_resume_state", "profile mentions resume/version/iteration state artifacts", "resume_state_incomplete"),
                        "fixture": {
                            "root": ".masentinel_fixture/{safe_case_id}",
                            "create_files": {
                                "MasterPlan.txt": "Plan content\n",
                                "script_v1.py": "print('old')\n",
                            },
                            "omit_files": ["comments_v1.log", "comments_v1.txt"],
                        },
                        "assertions": ["existing_script_not_ignored", "existing_file_not_overwritten", "recovery_path_explicit"],
                    },
                )
            ],
            budget,
        )
