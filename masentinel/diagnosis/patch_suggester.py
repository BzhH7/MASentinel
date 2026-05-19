from __future__ import annotations

from pathlib import Path
from typing import Any

from masentinel.utils import write_text


def write_patch_suggestions(faults: list[dict[str, Any]], out_dir: str | Path) -> None:
    lines = ["# Patch Suggestions", ""]
    if not faults:
        lines.append("No patch suggestions because no faults were detected.")
    for fault in faults:
        lines.extend(
            [
                f"## {fault.get('fault_id')}: {fault.get('fault_type')}",
                f"- Layer: {fault.get('layer')}",
                f"- Affected cases: {', '.join(str(x) for x in fault.get('affected_cases', [fault.get('case_id')]))}",
                f"- Suggested fix: {fault.get('suggested_fix')}",
                "",
                "Suggested patch direction:",
                _direction(fault),
                "",
            ]
        )
    write_text(Path(out_dir) / "patch_suggestions.md", "\n".join(lines) + "\n")


def _direction(fault: dict[str, Any]) -> str:
    code = fault.get("failure_code")
    if code == "TOOL_SCHEMA_MISMATCH":
        return "- Align the Python function signature, AutoGen function schema, and registration name. Add a regression case using the failing input."
    if code in {"TIMEOUT", "NON_TERMINATION"}:
        return "- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`."
    if code == "HUMAN_INPUT_REQUESTED":
        return "- Remove blocking `input()` calls in automated paths or gate them behind a non-interactive configuration."
    if code == "MISSING_TOOL_CALL":
        return "- Verify the target agent has the tool registered and that prompts/schema expose the tool name and required arguments."
    return "- Inspect the recorded trace evidence, then add a focused regression test before changing behavior."
