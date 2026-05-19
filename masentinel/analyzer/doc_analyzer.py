from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable

from masentinel.model.model_client import ModelClient
from masentinel.model.prompt_templates import REQUIREMENT_EXTRACTION_PROMPT
from masentinel.schema import RequirementInfo
from masentinel.utils import read_text, shorten


KEYWORDS = (
    "must",
    "should",
    "support",
    "generate",
    "analyze",
    "collect",
    "report",
    "agent",
    "tool",
    "output",
    "error",
    "exception",
    "termination",
    "需要",
    "必须",
    "支持",
    "生成",
    "分析",
    "收集",
    "报告",
    "智能体",
    "工具",
    "输出",
    "异常",
    "错误",
    "终止",
    "协作",
)

ProgressFn = Callable[[str], None]


class DocAnalyzer:
    def __init__(
        self,
        doc_path: str | Path | None,
        model_client: ModelClient | None = None,
        known_agents: Iterable[str] | None = None,
        known_tools: Iterable[str] | None = None,
        progress: ProgressFn | None = None,
        use_model: bool = True,
    ) -> None:
        self.doc_path = Path(doc_path) if doc_path else None
        self.model_client = model_client or ModelClient()
        self.known_agents = list(known_agents or [])
        self.known_tools = list(known_tools or [])
        self.progress = progress
        self.use_model = use_model
        self.warnings: list[str] = []

    def analyze(self) -> list[RequirementInfo]:
        self._progress(f"doc analyzer: reading {self.doc_path or 'no documentation'}")
        text = read_text(self.doc_path) if self.doc_path else ""
        if not text.strip():
            self.warnings.append("No readable documentation; using synthesized requirements.")
            self._progress("doc analyzer: no readable documentation, using synthesized requirements")
            return self._synthesized_requirements()
        self._progress(f"doc analyzer: loaded {len(text)} characters")
        model_requirements = self._from_model(text)
        if model_requirements:
            self._progress(f"doc analyzer: model extracted {len(model_requirements)} requirements")
            return model_requirements
        requirements = self._heuristic_requirements(text)
        self._progress(f"doc analyzer: heuristic extracted {len(requirements)} requirements")
        return requirements or self._synthesized_requirements()

    def _from_model(self, text: str) -> list[RequirementInfo]:
        if not self.use_model:
            self._progress("doc analyzer: model extraction disabled, using heuristic requirements")
            return []
        if not self.model_client.available:
            self._progress("doc analyzer: model client not configured, skipping model extraction")
            return []
        self._progress(f"doc analyzer: calling model for requirement extraction timeout={self.model_client.timeout}s retries={self.model_client.retries}")
        data = self.model_client.json_chat(
            [
                {"role": "system", "content": REQUIREMENT_EXTRACTION_PROMPT},
                {"role": "user", "content": text[:24000]},
            ]
        )
        out: list[RequirementInfo] = []
        for index, item in enumerate(data.get("requirements", []) if isinstance(data, dict) else []):
            if not isinstance(item, dict) or not item.get("description"):
                continue
            out.append(
                RequirementInfo(
                    id=str(item.get("id") or f"R{index + 1}"),
                    description=str(item["description"]),
                    expected_agents=list(item.get("expected_agents", [])),
                    expected_tools=list(item.get("expected_tools", [])),
                    expected_behavior=list(item.get("expected_behavior", [])),
                    negative_cases=list(item.get("negative_cases", [])),
                )
            )
        return out

    def _progress(self, message: str) -> None:
        if self.progress:
            self.progress(message)

    def _heuristic_requirements(self, text: str) -> list[RequirementInfo]:
        candidates: list[str] = []
        for raw in text.splitlines():
            line = re.sub(r"^[#>*\-\d\.\s]+", "", raw).strip()
            if len(line) < 12 or len(line) > 260:
                continue
            lowered = line.lower()
            if any(keyword in lowered or keyword in line for keyword in KEYWORDS):
                candidates.append(line)
        deduped: list[str] = []
        seen = set()
        for line in candidates:
            key = line.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(line)
            if len(deduped) >= 20:
                break
        requirements: list[RequirementInfo] = []
        for idx, line in enumerate(deduped, start=1):
            requirements.append(
                RequirementInfo(
                    id=f"R{idx}",
                    description=shorten(line, 240),
                    expected_agents=[a for a in self.known_agents if a.lower() in line.lower()],
                    expected_tools=[t for t in self.known_tools if t.lower() in line.lower()],
                    expected_behavior=[line],
                    negative_cases=[],
                )
            )
        return requirements

    def _synthesized_requirements(self) -> list[RequirementInfo]:
        requirements: list[RequirementInfo] = []
        if self.known_agents:
            requirements.append(
                RequirementInfo(
                    id="R1",
                    description="The configured multi-agent workflow should route the task through the declared agents and terminate.",
                    expected_agents=self.known_agents[:4],
                    expected_tools=[],
                    expected_behavior=["multi-agent routing", "termination"],
                    negative_cases=["empty_input", "termination_stress"],
                )
            )
        if self.known_tools:
            requirements.append(
                RequirementInfo(
                    id=f"R{len(requirements) + 1}",
                    description="Registered tools should be callable with valid arguments and return usable results or handled errors.",
                    expected_agents=[],
                    expected_tools=self.known_tools[:4],
                    expected_behavior=["tool invocation", "error handling"],
                    negative_cases=["tool_failure", "tool_invalid_json"],
                )
            )
        if not requirements:
            requirements.append(
                RequirementInfo(
                    id="R1",
                    description="The system should accept a user task, produce a non-empty response, and exit without an unhandled exception.",
                    expected_behavior=["non-empty output", "termination"],
                    negative_cases=["empty_input", "malformed_input"],
                )
            )
        return requirements
