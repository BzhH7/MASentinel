from __future__ import annotations

import re
from pathlib import Path

from masentinel.generator.patterns.base import base_metadata, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec
from masentinel.utils import read_text


class CliDocConformancePattern:
    name = "cli_doc_conformance"
    case_type = "cli_doc_conformance"
    fault_modes = ["documented_entrypoint_broken", "documented_cli_command_missing"]

    def applicable(self, profile: SystemProfile) -> bool:
        return bool(extract_documented_commands(_doc_text(profile)))

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        cases: list[TestCase] = []
        for idx, command in enumerate(extract_documented_commands(_doc_text(profile))[:4], start=1):
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_CLIDOC_{idx:03d}",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective=f"README/documented command should be accepted or fail only with controlled dependency/config diagnostics: {command}",
                    input=command,
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=5),
                    metadata={
                        **base_metadata("documented_cli_conformance", "README/doc contains executable CLI commands", "documented_cli_conformance", "diagnostic"),
                        "command_override": command,
                        "documented_command": command,
                        "timeout_seconds": 20,
                        "assertions": [
                            "no_import_error",
                            "constructor_signatures_match",
                            "called_methods_exist",
                            "controlled_config_error_only",
                        ],
                    },
                )
            )
        if not cases and "argparse" in profile_text(profile).lower():
            entry = Path(profile.entrypoint).name if profile.entrypoint else "main.py"
            cases.append(
                TestCase(
                    case_id=f"{profile.system_id}_CLIDOC_001",
                    system_id=profile.system_id,
                    case_type=self.case_type,
                    objective="CLI help should expose documented parser commands.",
                    input=f"python {entry} --help",
                    oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=5),
                    metadata={
                        **base_metadata("documented_cli_conformance", "code uses argparse-like CLI", "documented_cli_conformance", "diagnostic"),
                        "command_override": f"python {entry} --help",
                        "assertions": ["cli_help_lists_documented_commands"],
                    },
                )
            )
        return limited(cases, budget)


def extract_documented_commands(doc_text: str) -> list[str]:
    commands: list[str] = []
    for line in doc_text.splitlines():
        raw = line.strip().strip("`")
        if not raw or raw.startswith("#"):
            continue
        raw = re.sub(r"^[-*]\s+", "", raw)
        raw = re.sub(r"^\$+\s*", "", raw)
        if not re.match(r"^python(?:3)?\s+", raw):
            continue
        command = raw.split("#", 1)[0].strip()
        if _skip_setup_or_meta_command(command):
            continue
        if "..." in command or len(command.split()) < 2:
            continue
        commands.append(command)
    unique: list[str] = []
    for command in commands:
        if command not in unique:
            unique.append(command)
    return unique[:8]


def _skip_setup_or_meta_command(command: str) -> bool:
    lowered = command.lower()
    setup_markers = (
        "python -m venv",
        "python3 -m venv",
        "python -m pip",
        "python3 -m pip",
        "python -m pytest",
        "python3 -m pytest",
        "python -m compileall",
        "python3 -m compileall",
    )
    if any(lowered.startswith(marker) for marker in setup_markers):
        return True
    if "setup.py" in lowered or "requirements" in lowered:
        return True
    return False


def _doc_text(profile: SystemProfile) -> str:
    if profile.doc_path:
        return read_text(profile.doc_path)
    return ""
