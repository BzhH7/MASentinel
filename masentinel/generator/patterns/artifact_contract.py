from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class ArtifactContractPattern:
    name = "artifact_contract"
    case_type = "artifact_contract"
    fault_modes = ["artifact_corruption", "artifact_schema_mismatch"]

    def applicable(self, profile: SystemProfile) -> bool:
        text = profile_text(profile)
        return has_any(
            text,
            (
                "write_",
                "open(",
                "save",
                "persist",
                "artifact",
                "file",
                "script",
                "code block",
                "markdown",
                "report",
                "comments_",
                "保存",
                "输出文件",
                "代码",
                "报告",
            ),
        )

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        cases = [
            TestCase(
                case_id=f"{profile.system_id}_ARTIFACT_001",
                system_id=profile.system_id,
                case_type=self.case_type,
                objective="Persisted code artifact should preserve a valid Markdown code block body without fence corruption.",
                input="Create a one-line Python script that prints hello. A valid answer may use an unlabeled, py, or python Markdown fence.",
                oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=30),
                metadata={
                    **base_metadata("artifact_contract", "profile mentions persisted files, code, reports, or artifact output", "artifact_corruption"),
                    "artifact_kind": "python_script",
                    "fence_variants": ["unlabeled", "py", "python"],
                    "assertions": [
                        "artifact_exists",
                        "no_markdown_fence_markers",
                        "python_compile_succeeds",
                        "artifact_content_preserves_first_code_token",
                    ],
                },
            ),
            TestCase(
                case_id=f"{profile.system_id}_ARTIFACT_002",
                system_id=profile.system_id,
                case_type=self.case_type,
                objective="Generated artifact names and extensions should match the documented/profile schema.",
                input="Run one normal iteration or task and persist every documented output artifact.",
                oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=30),
                metadata={
                    **base_metadata("artifact_schema_contract", "profile/doc mentions named output artifacts", "artifact_schema_mismatch", "medium"),
                    "assertions": ["artifact_extension_matches_docs", "documented_artifact_exists"],
                },
            ),
        ]
        return limited(cases, budget)
