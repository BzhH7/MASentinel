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
