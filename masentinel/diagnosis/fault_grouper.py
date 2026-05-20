from __future__ import annotations

import re
from typing import Any


CASCADE_FAILURE_CODES = {
    "MISSING_AGENT",
    "MISSING_TOOL_CALL",
    "MISSING_MESSAGE_EDGE",
    "METAMORPHIC_RELATION_VIOLATION",
    "OUTPUT_EMPTY",
    "BUSINESS_TASK_FAILED",
    "TIMEOUT",
    "RUNTIME_EXCEPTION",
}

INTERACTION_FAILURE_CODES = {
    "TIMEOUT",
    "NON_TERMINATION",
    "HUMAN_INPUT_REQUESTED",
    "REPETITIVE_LOOP",
    "TERMINATION_SIGNAL_IGNORED",
}

ROOT_PRIORITY_CODES = {
    "MESSAGE_HANDOFF_TERMINATE_ONLY",
    "MESSAGE_HANDOFF_EMPTY",
    "SPEAKER_SELECTION_LOOP",
    "HUMAN_INPUT_REQUESTED",
    "TOOL_UNSTRUCTURED_ERROR",
    "TOOL_RAW_HTTP_ERROR",
    "TOOL_RETURNED_NONE",
    "FILESYSTEM_ESCAPE",
}

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def annotate_fault_groups(faults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = [dict(fault) for fault in faults]
    blocking_groups = _blocking_failure_groups(annotated)
    primary_group_by_case: dict[str, tuple[str, str]] = {}
    for group_id, primary_fault in blocking_groups.items():
        for case_id in _affected_cases(primary_fault):
            primary_group_by_case[case_id] = (group_id, str(primary_fault.get("fault_id", "")))

    first_seen: set[str] = set()
    unattended_cases = _unattended_termination_cases(annotated)
    for fault in annotated:
        code = str(fault.get("failure_code", ""))
        cases = _affected_cases(fault)
        cascade_group = _matching_primary_group(cases, primary_group_by_case)
        if code in CASCADE_FAILURE_CODES and cascade_group and code not in ROOT_PRIORITY_CODES:
            group_id, primary_id = cascade_group
            if primary_id == str(fault.get("fault_id", "")):
                cascade_group = None
            else:
                fault.update(
                    {
                        "root_cause_group_id": group_id,
                        "root_cause_group_title": _group_title_for_id(group_id),
                        "is_primary_fault": False,
                        "cascades_from": primary_id,
                        "classification_note": "Derived symptom: the target failed before MASentinel could judge downstream agent/tool/message behavior.",
                    }
                )
                continue
        if code in INTERACTION_FAILURE_CODES and cases & unattended_cases:
            group_id = "interaction:unattended-termination-guard-missing"
        elif code in ROOT_PRIORITY_CODES:
            group_id = _priority_group_id(fault)
        elif code in INTERACTION_FAILURE_CODES:
            group_id = _interaction_group_id(fault)
        elif code == "RUNTIME_EXCEPTION":
            group_id = _runtime_group_id(fault)
        else:
            group_id = _generic_group_id(fault)

        is_primary = group_id not in first_seen
        first_seen.add(group_id)
        fault.update(
            {
                "root_cause_group_id": group_id,
                "root_cause_group_title": _group_title_for_id(group_id, fault),
                "is_primary_fault": is_primary,
                "cascades_from": None if is_primary else _first_fault_id_for_group(annotated, group_id),
            }
        )
    return annotated


def build_fault_groups(faults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = annotate_fault_groups(faults)
    groups: dict[str, dict[str, Any]] = {}
    for fault in annotated:
        group_id = str(fault.get("root_cause_group_id") or _generic_group_id(fault))
        group = groups.setdefault(
            group_id,
            {
                "group_id": group_id,
                "title": fault.get("root_cause_group_title") or _group_title_for_id(group_id, fault),
                "primary_fault_id": fault.get("fault_id"),
                "fault_ids": [],
                "symptom_fault_ids": [],
                "affected_cases": [],
                "failure_codes": [],
                "severity": fault.get("severity", "medium"),
                "confidence": float(fault.get("confidence", 0) or 0),
                "root_cause": fault.get("root_cause", ""),
                "suggested_fix": fault.get("suggested_fix", ""),
                "summary": fault.get("summary", ""),
            },
        )
        group["fault_ids"].append(fault.get("fault_id"))
        if not fault.get("is_primary_fault", True):
            group["symptom_fault_ids"].append(fault.get("fault_id"))
        group["affected_cases"] = sorted({*group.get("affected_cases", []), *_affected_cases(fault)})
        group["failure_codes"] = sorted({*group.get("failure_codes", []), str(fault.get("failure_code", ""))})
        if SEVERITY_RANK.get(str(fault.get("severity", "medium")), 0) > SEVERITY_RANK.get(str(group.get("severity", "medium")), 0):
            group["severity"] = fault.get("severity", "medium")
        group["confidence"] = max(float(group.get("confidence", 0) or 0), float(fault.get("confidence", 0) or 0))
        if fault.get("is_primary_fault", True):
            group["primary_fault_id"] = fault.get("fault_id")
            group["root_cause"] = fault.get("root_cause", group.get("root_cause", ""))
            group["suggested_fix"] = fault.get("suggested_fix", group.get("suggested_fix", ""))
            group["summary"] = fault.get("summary", group.get("summary", ""))
    return sorted(groups.values(), key=lambda item: str(item.get("group_id", "")))


def _blocking_failure_groups(faults: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for fault in faults:
        code = str(fault.get("failure_code", ""))
        if code in ROOT_PRIORITY_CODES:
            group_id = _priority_group_id(fault)
        elif code == "RUNTIME_EXCEPTION":
            group_id = _runtime_group_id(fault)
        elif code in INTERACTION_FAILURE_CODES:
            group_id = _interaction_group_id(fault)
        else:
            continue
        groups.setdefault(group_id, fault)
    return groups


def _affected_cases(fault: dict[str, Any]) -> set[str]:
    cases = fault.get("affected_cases")
    if isinstance(cases, list) and cases:
        return {str(case) for case in cases if case}
    case_id = fault.get("case_id")
    return {str(case_id)} if case_id else set()


def _matching_primary_group(cases: set[str], primary_group_by_case: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    for case_id in sorted(cases):
        if case_id in primary_group_by_case:
            return primary_group_by_case[case_id]
    return None


def _runtime_group_id(fault: dict[str, Any]) -> str:
    evidence = "\n".join(str(item) for item in fault.get("evidence", []) or [])
    file_line = _first_match(evidence, r"File \"([^\"]+)\", line (\d+)")
    exception = _first_match(evidence, r"([A-Za-z_]*Error|RuntimeError|Exception):\s*([^\n]+)")
    if file_line or exception:
        signature = ":".join(part for part in (file_line, exception) if part)
        return "runtime:" + _slug(signature)
    return "runtime:" + _slug(str(fault.get("root_cause") or fault.get("summary") or "unknown"))


def _interaction_group_id(fault: dict[str, Any]) -> str:
    evidence = "\n".join(str(item) for item in fault.get("evidence", []) or []).lower()
    text = " ".join(
        [
            str(fault.get("root_cause", "")),
            str(fault.get("summary", "")),
            str(fault.get("fault_type", "")),
            evidence,
        ]
    ).lower()
    if any(marker in text for marker in ("human", "manual input", "input requested", "do you agree", "selection:")):
        return "interaction:human-input-or-approval"
    return "interaction:timeout-or-non-termination"


def _generic_group_id(fault: dict[str, Any]) -> str:
    return "generic:" + _slug(
        "|".join(
            [
                str(fault.get("layer", "")),
                str(fault.get("fault_type", "")),
                str(fault.get("root_cause", ""))[:120],
            ]
        )
    )


def _priority_group_id(fault: dict[str, Any]) -> str:
    code = str(fault.get("failure_code", ""))
    if code.startswith("MESSAGE_HANDOFF"):
        return "handoff:terminate-empty-or-wrong-source"
    if code == "SPEAKER_SELECTION_LOOP":
        return "interaction:speaker-selection-loop"
    if code == "HUMAN_INPUT_REQUESTED":
        return "interaction:human-input-or-approval"
    if code.startswith("TOOL_"):
        return "tool:error-envelope-missing"
    if code == "FILESYSTEM_ESCAPE":
        return "filesystem:path-escape"
    return _generic_group_id(fault)


def _group_title_for_id(group_id: str, fault: dict[str, Any] | None = None) -> str:
    if group_id.startswith("runtime:"):
        return "Unhandled startup/runtime exception"
    if group_id == "interaction:human-input-or-approval":
        return "Unattended run blocked by human input or approval"
    if group_id == "interaction:unattended-termination-guard-missing":
        return "Unattended termination / approval guard missing"
    if group_id == "interaction:timeout-or-non-termination":
        return "Conversation timeout or missing termination guard"
    if group_id == "interaction:speaker-selection-loop":
        return "GroupChat speaker selection loop"
    if group_id == "handoff:terminate-empty-or-wrong-source":
        return "Message handoff forwarded empty or TERMINATE content"
    if group_id == "tool:error-envelope-missing":
        return "External tool error envelope missing"
    if group_id == "filesystem:path-escape":
        return "User-controlled path escaped configured root"
    if fault:
        return str(fault.get("fault_type") or fault.get("failure_code") or "Fault group")
    return "Fault group"


def _first_fault_id_for_group(faults: list[dict[str, Any]], group_id: str) -> str | None:
    for fault in faults:
        if fault.get("root_cause_group_id") == group_id and fault.get("is_primary_fault", True):
            return str(fault.get("fault_id", ""))
    return None


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    if not match:
        return ""
    return ":".join(match.groups())


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
    normalized = normalized.strip("-").lower()
    return normalized[:120] or "unknown"


def _unattended_termination_cases(faults: list[dict[str, Any]]) -> set[str]:
    cases: set[str] = set()
    for fault in faults:
        code = str(fault.get("failure_code", ""))
        text = " ".join(
            [
                str(fault.get("summary", "")),
                str(fault.get("root_cause", "")),
                str(fault.get("fault_type", "")),
                "\n".join(str(item) for item in fault.get("evidence", []) or []),
            ]
        ).lower()
        if code == "HUMAN_INPUT_REQUESTED" or any(
            marker in text
            for marker in (
                "anything else",
                "waiting for human",
                "manual input",
                "human input",
                "input requested",
                "approval",
                "selection:",
            )
        ):
            cases.update(_affected_cases(fault))
    return cases
