from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class ToolAPIContractPattern:
    name = "tool_api_contract"
    case_type = "tool_api_contract"
    fault_modes = ["tool_api_semantics", "pagination_not_followed"]

    def applicable(self, profile: SystemProfile) -> bool:
        if not profile.tools:
            return False
        text = profile_text(profile)
        return has_any(
            text,
            (
                "requests.",
                "requests.get",
                "requests.post",
                "httpx",
                "aiohttp",
                "urllib.request",
                "api.airtable.com",
                "airtable",
                "serper",
                "browserless",
                "pagination",
                "offset",
                "next_page",
                "status_code",
                "response.json",
                "response.text",
                "scrape",
                "web search",
            ),
        )

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        cases: list[TestCase] = []
        for idx, tool in enumerate(profile.tools[:5], start=1):
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_TOOLAPI_{idx:03d}",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective=f"External API tool {tool.name} should preserve semantic parameters and follow pagination.",
                    input="请使用一个包含筛选视图和多页结果的外部数据源完成任务。",
                    target_tools=[tool.name],
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=30),
                    metadata={
                        **base_metadata("external_api_contract", "profile has HTTP/API-like tools", "tool_api_semantics"),
                        "tool_name": tool.name,
                        "mock_http": True,
                        "http_fixture": {
                            "fixture_id": "airtable_101_records",
                            "expected_query_params": {"view": "viwMASentinel"},
                            "pagination_pages": 2,
                            "record_count": 101,
                        },
                        "assertions": [
                            "http_status_recorded",
                            "query_params_preserved",
                            "pagination_followed",
                            "structured_error_on_non_200",
                        ],
                    },
                )
            )
        return limited(cases, budget)
