from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from masentinel.schema import SystemProfile, TestCase
from masentinel.utils import read_text


class TestPattern(Protocol):
    name: str
    case_type: str
    fault_modes: list[str]

    def applicable(self, profile: SystemProfile) -> bool:
        ...

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        ...


@dataclass
class PatternContext:
    max_cases_per_pattern: int = 4
    max_tools_per_system: int = 5
    max_requirements_per_pattern: int = 8


def profile_text(profile: SystemProfile, include_code: bool = True, max_code_chars: int = 250_000) -> str:
    chunks: list[str] = []
    if profile.doc_path:
        chunks.append(read_text(profile.doc_path))
    chunks.extend(req.description for req in profile.requirements)
    for agent in profile.agents:
        chunks.extend(str(item or "") for item in (agent.name, agent.class_name, agent.system_message, agent.description))
    for tool in profile.tools:
        chunks.extend(str(item or "") for item in (tool.name, tool.function_name, tool.signature, tool.docstring, tool.source_file))
    chunks.append(str(profile.raw_notes or {}))
    if include_code and profile.root_path:
        chunks.append(_read_code_corpus(Path(profile.root_path), max_chars=max_code_chars))
    return "\n".join(chunks)


def has_any(text: str, markers: tuple[str, ...] | list[str]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def limited(cases: list[TestCase], budget: int | None) -> list[TestCase]:
    if budget is None or budget <= 0:
        return cases
    return cases[:budget]


def base_metadata(pattern: str, reason: str, fault_mode: str, strength: str = "hard") -> dict:
    return {
        "generic_pattern": pattern,
        "applicability_reason": reason,
        "target_fault_mode": fault_mode,
        "oracle_strength": strength,
    }


def _read_code_corpus(root: Path, max_chars: int) -> str:
    if not root.exists():
        return ""
    excluded = {".git", ".venv", "venv", "__pycache__", "outputs", "output", "node_modules", "site-packages"}
    chunks: list[str] = []
    total = 0
    for path in sorted(root.rglob("*.py")):
        if any(part in excluded or part.startswith(".ipynb_checkpoints") for part in path.parts):
            continue
        text = read_text(path)
        if not text:
            continue
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        chunk = f"\n# FILE: {rel}\n{text}\n"
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_chars:
            break
    return "".join(chunks)
