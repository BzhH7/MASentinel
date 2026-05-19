from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from masentinel.schema import OracleFailure, OracleResult, RunTrace, TestCase

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
AUTOGEN_MESSAGE_RE = re.compile(r"^([A-Za-z_][\w.-]*)\s+\(to\s+([A-Za-z_][\w.-]*)\):\s*$")
AGENT_ALIASES = {
    "chat_manager": "group_chat_manager",
    "GroupChatManager": "group_chat_manager",
    "groupchat_manager": "group_chat_manager",
}
ORACLE_WARNING_CODES = {"TURN_BUDGET_EXCEEDED"}


class RuleOracle:
    def __init__(self, registered_tools: set[str] | None = None) -> None:
        self.registered_tools = registered_tools or set()

    def evaluate(self, testcase: TestCase, trace: RunTrace) -> OracleResult:
        failures: list[OracleFailure] = []
        text = f"{trace.stdout or ''}\n{trace.stderr or ''}\n{trace.final_output or ''}"
        provider_failure = self._model_provider_failure(text)
        if provider_failure:
            failures.append(
                OracleFailure(
                    "MODEL_PROVIDER_FAILURE",
                    "The run failed because the model/API provider timed out, was unavailable, unauthorized, or rate-limited.",
                    "low",
                    provider_failure,
                )
            )
        if self._human_input_requested(trace, text):
            failures.append(
                OracleFailure(
                    "HUMAN_INPUT_REQUESTED",
                    "The target system requested human input during an automated no-human run.",
                    "high",
                    self._evidence(text),
                )
            )
        if (
            not provider_failure
            and testcase.oracle.must_not_crash
            and ("Traceback (most recent call last)" in text or (trace.returncode not in (0, None) and trace.stderr))
        ):
            failures.append(OracleFailure("RUNTIME_EXCEPTION", "The process ended with an unhandled runtime error.", "high", self._evidence(text)))
        business_failure = [] if provider_failure else self._business_task_failure(text)
        if business_failure:
            failures.append(
                OracleFailure(
                    "BUSINESS_TASK_FAILED",
                    "The process completed but the target task reported a business-level failure.",
                    "high",
                    business_failure,
                )
            )
        workflow_observed = self._workflow_observed(trace, text)
        expects_workflow = bool(
            testcase.oracle.must_visit_agents
            or testcase.oracle.must_call_tools
            or testcase.oracle.must_cover_edges
        )
        workflow_issue_added = False
        if expects_workflow and not workflow_observed and not provider_failure:
            failures.append(
                OracleFailure(
                    "TARGET_WORKFLOW_NOT_OBSERVED",
                    "The test run did not observe a meaningful target agent workflow, so routing/tool expectations cannot be judged as target faults.",
                    "low",
                    [
                        f"turn_count={trace.turn_count}",
                        f"returncode={trace.returncode}",
                        f"timeout={trace.timeout}",
                        f"command={' '.join(str(item) for item in trace.metadata.get('command', []) or [])}",
                    ],
                )
            )
            workflow_issue_added = True
        overlong_generated_input_timeout = self._overlong_generated_input_timeout(testcase, trace)
        can_judge_workflow_expectations = workflow_observed and not provider_failure and not trace.timeout and trace.returncode in (0, None)
        if trace.timeout:
            if overlong_generated_input_timeout:
                failures.append(
                    OracleFailure(
                        "TESTCASE_SETUP_TIMEOUT",
                        "The generated test input exceeded the automated execution budget before a meaningful target workflow could be observed.",
                        "low",
                        [f"input_length={len(testcase.input or '')}", f"timeout_seconds={trace.metadata.get('timeout_seconds', '')}"],
                    )
                )
            elif not workflow_observed and not workflow_issue_added:
                failures.append(
                    OracleFailure(
                        "TARGET_WORKFLOW_NOT_OBSERVED",
                        "The process timed out before MASentinel observed a meaningful target agent workflow.",
                        "low",
                        [f"timeout_seconds={trace.metadata.get('timeout_seconds', '')}"],
                    )
                )
            else:
                failures.append(OracleFailure("TIMEOUT", "The process exceeded the configured timeout.", "high", [str(trace.metadata.get("timeout_seconds", ""))]))
        if testcase.oracle.must_terminate and not provider_failure:
            if not trace.timeout and workflow_observed and not trace.terminated:
                failures.append(OracleFailure("NON_TERMINATION", "The run did not terminate.", "high", [f"turn_count={trace.turn_count}"]))
            elif (
                not trace.timeout
                and trace.terminated
                and trace.turn_count > testcase.oracle.max_turns
            ):
                failures.append(
                    OracleFailure(
                        "TURN_BUDGET_EXCEEDED",
                        "The run terminated, but exceeded the expected soft turn budget.",
                        "low",
                        [f"turn_count={trace.turn_count}", f"max_turns={testcase.oracle.max_turns}"],
                    )
                )
        visited_agents = self._visited_agents(trace, text)
        if can_judge_workflow_expectations:
            for agent in testcase.oracle.must_visit_agents:
                canonical = _canon_agent(agent)
                if canonical and canonical not in visited_agents and agent.lower() not in text.lower():
                    failures.append(OracleFailure("MISSING_AGENT", f"Expected agent was not observed: {agent}", "medium", [agent]))
        called_tools = self._called_tools(trace, text)
        if can_judge_workflow_expectations:
            for tool in testcase.oracle.must_call_tools:
                if tool and tool not in called_tools and tool.lower() not in text.lower():
                    failures.append(OracleFailure("MISSING_TOOL_CALL", f"Expected tool was not called: {tool}", "medium", [tool]))
        for tool in testcase.oracle.must_not_call_tools:
            if tool in called_tools or tool.lower() in text.lower():
                failures.append(OracleFailure("FORBIDDEN_TOOL_CALL", f"Forbidden tool was called: {tool}", "high", [tool]))
        observed_edges = self._observed_edges(trace, text)
        if can_judge_workflow_expectations:
            for edge in testcase.oracle.must_cover_edges:
                canonical_edge = (_canon_agent(edge[0]), _canon_agent(edge[1]))
                if canonical_edge not in observed_edges:
                    failures.append(OracleFailure("MISSING_MESSAGE_EDGE", f"Expected message edge was not observed: {edge[0]}->{edge[1]}", "medium", [str(edge)]))
        if self.registered_tools:
            for tool in self._called_tools(trace, text, llm_only=True):
                if tool not in self.registered_tools:
                    failures.append(OracleFailure("TOOL_HALLUCINATION", f"Unregistered tool was called: {tool}", "high", [tool]))
        if testcase.oracle.must_not_fabricate_tool_result:
            fabricated = self._fabricated_tool_results(trace)
            for tool in fabricated:
                failures.append(OracleFailure("TOOL_HALLUCINATION", f"Tool result appeared without a matching tool call: {tool}", "high", [tool]))
        if re.search(r"TypeError: .*unexpected keyword argument|TypeError: .*missing .*required positional argument", text):
            failures.append(OracleFailure("TOOL_SCHEMA_MISMATCH", "A TypeError suggests tool argument schema mismatch.", "high", self._evidence(text)))
        if not provider_failure and workflow_observed and not (trace.final_output or "").strip() and not trace.timeout:
            failures.append(OracleFailure("OUTPUT_EMPTY", "The run produced no final output.", "medium", []))
        if testcase.oracle.output_contract and "json" in testcase.oracle.output_contract.lower():
            try:
                json.loads(trace.final_output or "")
            except json.JSONDecodeError:
                failures.append(OracleFailure("OUTPUT_SCHEMA_VIOLATION", "Output contract requires JSON but final output is not valid JSON.", "medium", [trace.final_output or ""]))
        if can_judge_workflow_expectations and not trace.terminated and self._has_repetitive_loop(trace):
            failures.append(OracleFailure("REPETITIVE_LOOP", "Trace contains highly repetitive consecutive messages.", "medium", []))
        metamorphic_failure = self._metamorphic_failure(testcase, trace, visited_agents, called_tools) if can_judge_workflow_expectations else None
        if metamorphic_failure:
            failures.append(metamorphic_failure)
        hard_failures = [failure for failure in failures if failure.code not in ORACLE_WARNING_CODES]
        return OracleResult(case_id=testcase.case_id, passed=not hard_failures, failures=failures)

    def _visited_agents(self, trace: RunTrace, text: str = "") -> set[str]:
        agents: set[str] = set()
        for event in trace.events:
            if event.sender:
                agents.add(_canon_agent(event.sender))
            if event.receiver:
                agents.add(_canon_agent(event.receiver))
            if event.metadata.get("agent"):
                agents.add(_canon_agent(str(event.metadata["agent"])))
        for sender, receiver in self._stdout_edges(text):
            agents.add(_canon_agent(sender))
            agents.add(_canon_agent(receiver))
        return agents

    def _called_tools(self, trace: RunTrace, text: str = "", llm_only: bool = False) -> set[str]:
        tools = set()
        for event in trace.events:
            if not event.tool or event.type not in {"tool_call", "tool_result", "tool_error"}:
                continue
            if llm_only and not event.metadata.get("llm_visible", False):
                continue
            tools.add(event.tool)
        if not llm_only:
            tools.update(re.findall(r"function(?:_call)?[=:]\s*['\"]?([A-Za-z_]\w*)", text, flags=re.IGNORECASE))
        tools.update(re.findall(r"EXECUTING FUNCTION\s+([A-Za-z_]\w*)", text))
        return tools

    def _fabricated_tool_results(self, trace: RunTrace) -> set[str]:
        called: set[str] = set()
        fabricated: set[str] = set()
        for event in trace.events:
            if event.type == "tool_call" and event.tool:
                called.add(event.tool)
            if event.type == "tool_result" and event.tool and event.tool not in called:
                fabricated.add(event.tool)
        return fabricated

    def _observed_edges(self, trace: RunTrace, text: str = "") -> set[tuple[str, str]]:
        edges = {(_canon_agent(event.sender), _canon_agent(event.receiver)) for event in trace.events if event.type == "message" and event.sender and event.receiver}
        edges.update(self._stdout_edges(text))
        return edges

    def _stdout_edges(self, text: str) -> set[tuple[str, str]]:
        edges: set[tuple[str, str]] = set()
        for line in text.splitlines():
            clean_line = ANSI_RE.sub("", line).strip()
            match = AUTOGEN_MESSAGE_RE.match(clean_line)
            if match:
                edges.add((_canon_agent(match.group(1)), _canon_agent(match.group(2))))
        return edges

    def _workflow_observed(self, trace: RunTrace, text: str) -> bool:
        if trace.turn_count > 0:
            return True
        if any(event.type in {"message", "tool_call", "tool_result", "tool_error"} for event in trace.events):
            return True
        return bool(self._stdout_edges(text))

    def _has_repetitive_loop(self, trace: RunTrace) -> bool:
        messages = [event.content or "" for event in trace.events if event.type == "message" and event.content]
        if len(messages) < 4:
            return False
        repeats = 0
        for previous, current in zip(messages, messages[1:]):
            if SequenceMatcher(None, previous, current).ratio() > 0.95:
                repeats += 1
        return repeats >= 3

    def _human_input_requested(self, trace: RunTrace, text: str) -> bool:
        if trace.metadata.get("human_input_requested"):
            return True
        if any(event.type == "human_input_requested" for event in trace.events):
            return True
        lowered = text.lower()
        return any(
            marker in lowered
            for marker in (
                "eoferror",
                "waiting for human",
                "human input",
                "manual input",
                "user input requested",
            )
        )

    def _business_task_failure(self, text: str) -> list[str]:
        lowered = text.lower()
        markers = (
            "分析失败",
            "无法收集数据",
            "failed to collect data",
            "data collection failed",
        )
        if not any(marker in lowered for marker in markers):
            return []
        return self._evidence(text)

    def _model_provider_failure(self, text: str) -> list[str]:
        lowered = text.lower()
        markers = (
            "authentication fails",
            "authentication_error",
            "authorization required",
            "unauthorized consumer",
            "invalid api key",
            "api key is invalid",
            "http 401",
            "http 403",
            "too many requests",
            "rate limited",
            "rate limit",
            "yfratelimiterror",
            "model call failed",
            "read operation timed out",
            "openai.apitimeouterror",
            "openai api call timed out",
            "request timed out",
            "connecttimeout",
            "httpx.connecttimeout",
            "httpcore.connecttimeout",
            "api timeout",
            "llm timeout",
        )
        if not any(marker in lowered for marker in markers):
            return []
        return self._evidence(text)

    def _overlong_generated_input_timeout(self, testcase: TestCase, trace: RunTrace) -> bool:
        if not trace.timeout:
            return False
        metadata = testcase.metadata if isinstance(testcase.metadata, dict) else {}
        if metadata.get("input_truncated_by_masentinel"):
            return False
        fuzz_template = metadata.get("fuzz_template") or metadata.get("property_template")
        return fuzz_template == "very_long_input" and len(testcase.input or "") > 2000 and trace.turn_count == 0

    def _metamorphic_failure(
        self,
        testcase: TestCase,
        trace: RunTrace,
        visited_agents: set[str],
        called_tools: set[str],
    ) -> OracleFailure | None:
        if testcase.case_type != "metamorphic":
            return None
        relation = testcase.metadata.get("expected_relation") if isinstance(testcase.metadata, dict) else None
        if not isinstance(relation, dict):
            return None
        missing_agents = [agent for agent in relation.get("same_agents", []) if agent and agent not in visited_agents]
        missing_tools = [tool for tool in relation.get("same_tools", []) if tool and tool not in called_tools]
        if missing_agents or missing_tools:
            return OracleFailure(
                "METAMORPHIC_RELATION_VIOLATION",
                "Equivalent metamorphic inputs did not preserve expected routing/tool relation.",
                "medium",
                [f"missing_agents={missing_agents}", f"missing_tools={missing_tools}"],
            )
        return None

    def _evidence(self, text: str) -> list[str]:
        lines = [line for line in text.splitlines() if line.strip()]
        return lines[-8:]


def _canon_agent(name: str | None) -> str:
    if not name:
        return ""
    value = str(name).strip()
    return AGENT_ALIASES.get(value, AGENT_ALIASES.get(value.lower(), value))
