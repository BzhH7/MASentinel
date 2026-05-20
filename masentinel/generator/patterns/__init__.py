from __future__ import annotations

from masentinel.generator.patterns.artifact_contract import ArtifactContractPattern
from masentinel.generator.patterns.autogen_wiring import AutoGenWiringPattern
from masentinel.generator.patterns.base import PatternContext, TestPattern
from masentinel.generator.patterns.cli_doc_conformance import CliDocConformancePattern, extract_documented_commands
from masentinel.generator.patterns.data_invariant import DataInvariantPattern
from masentinel.generator.patterns.filesystem_safety import FilesystemSafetyPattern
from masentinel.generator.patterns.message_handoff import MessageHandoffPattern
from masentinel.generator.patterns.scalable_budget import ScalableBudgetPattern
from masentinel.generator.patterns.state_resume import StateResumePattern
from masentinel.generator.patterns.tool_api_contract import ToolAPIContractPattern
from masentinel.generator.patterns.tool_error_contract import ToolErrorContractPattern


PATTERN_REGISTRY: list[TestPattern] = [
    ArtifactContractPattern(),
    FilesystemSafetyPattern(),
    StateResumePattern(),
    ToolAPIContractPattern(),
    ToolErrorContractPattern(),
    ScalableBudgetPattern(),
    MessageHandoffPattern(),
    DataInvariantPattern(),
    CliDocConformancePattern(),
    AutoGenWiringPattern(),
]


__all__ = ["PATTERN_REGISTRY", "PatternContext", "TestPattern", "extract_documented_commands"]
