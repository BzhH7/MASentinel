from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class ToolErrorContractPattern:
    name = "tool_error_contract"
    case_type = "tool_error_contract"
    fault_modes = ["tool_unstructured_error"]

    def applicable(self, profile: SystemProfile) -> bool:
        if not profile.tools:
            return False
        return has_any(
            profile_text(profile),
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
                    case_id=f"{profile.system_id}_TOOLERR_{idx:03d}",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective=f"External tool {tool.name} should return structured errors for invalid auth/non-200/timeout/empty/malformed responses.",
                    input=f"请调用工具 {tool.name}，模拟外部服务鉴权失败或非 200 响应，并以结构化错误结束。",
                    target_tools=[tool.name],
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=25),
                    metadata={
                        **base_metadata("tool_error_envelope", "profile has external API-like tools", "tool_unstructured_error"),
                        "tool_name": tool.name,
                        "mock_http": True,
                        "http_fixture": {"fixture_id": "invalid_auth", "status_code": 401, "json_body": {"error": "invalid key"}},
                        "assertions": ["tool_result_not_none", "tool_error_is_structured", "http_status_recorded"],
                    },
                )
            )
        return limited(cases, budget)
