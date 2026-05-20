from masentinel.diagnosis.fault_grouper import annotate_fault_groups, build_fault_groups


def test_fault_grouper_marks_missing_agent_as_crash_cascade() -> None:
    faults = [
        {
            "fault_id": "SYS_FAULT_001",
            "case_id": "C1",
            "failure_code": "RUNTIME_EXCEPTION",
            "layer": "application",
            "fault_type": "Missing Error Handling",
            "severity": "high",
            "confidence": 0.9,
            "summary": "crashed",
            "evidence": ['File "IterativeTools.py", line 251', "ValueError: invalid literal for int()"],
            "root_cause": "input parse crash",
            "suggested_fix": "validate input",
            "affected_cases": ["C1", "C2"],
        },
        {
            "fault_id": "SYS_FAULT_002",
            "case_id": "C1",
            "failure_code": "MISSING_AGENT",
            "layer": "autogen_framework",
            "fault_type": "Wrong Agent Routing",
            "severity": "medium",
            "confidence": 0.7,
            "summary": "manager missing",
            "evidence": ["manager"],
            "root_cause": "agent missing",
            "suggested_fix": "inspect routing",
            "affected_cases": ["C1"],
        },
    ]

    annotated = annotate_fault_groups(faults)
    groups = build_fault_groups(annotated)

    assert annotated[0]["is_primary_fault"] is True
    assert annotated[1]["is_primary_fault"] is False
    assert annotated[1]["cascades_from"] == "SYS_FAULT_001"
    assert len(groups) == 1
    assert groups[0]["primary_fault_id"] == "SYS_FAULT_001"
    assert groups[0]["symptom_fault_ids"] == ["SYS_FAULT_002"]


def test_fault_grouper_merges_unattended_human_input_and_nontermination() -> None:
    faults = [
        {
            "fault_id": "SYS_FAULT_001",
            "case_id": "C1",
            "failure_code": "HUMAN_INPUT_REQUESTED",
            "layer": "autogen_framework",
            "fault_type": "Human Input Mode Error",
            "severity": "high",
            "confidence": 0.9,
            "summary": "waiting for human",
            "evidence": ["Is there anything else you'd like me to review?"],
            "root_cause": "manual prompt",
            "suggested_fix": "set human_input_mode",
        },
        {
            "fault_id": "SYS_FAULT_002",
            "case_id": "C1",
            "failure_code": "NON_TERMINATION",
            "layer": "autogen_framework",
            "fault_type": "Termination Condition Error",
            "severity": "high",
            "confidence": 0.8,
            "summary": "did not terminate",
            "evidence": ["turn_count=20"],
            "root_cause": "missing termination",
            "suggested_fix": "add is_termination_msg",
        },
    ]

    annotated = annotate_fault_groups(faults)

    assert {fault["root_cause_group_id"] for fault in annotated} == {"interaction:unattended-termination-guard-missing"}
    assert len([fault for fault in annotated if fault["is_primary_fault"]]) == 1
