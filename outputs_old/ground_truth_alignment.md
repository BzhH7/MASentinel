# Ground Truth Alignment

- Ground truth: `../analysis/ground_truth_defects.json`
- Outputs: `outputs`
- Strict matches: 6
- Partial matches: 0
- Missed: 9

| Defect | System | Type | Severity | Status | Matched Faults |
|--------|--------|------|----------|--------|----------------|
| `GT-S1-001` | system_1 | wrong_output_schema | medium | missed | - |
| `GT-S1-002` | system_1 | missing_state | medium | strict_match | `SYSTEM1_ITERATIVE_CODING_FAULT_006`/RESUME_STATE_INCOMPLETE |
| `GT-S1-003` | system_1 | wrong_output_schema | low | missed | - |
| `GT-S1-004` | system_1 | input_validation_error | high | strict_match | `SYSTEM1_ITERATIVE_CODING_FAULT_002`/FILESYSTEM_ESCAPE |
| `GT-S2-001` | system_2 | human_input_blocking | high | missed | - |
| `GT-S2-002` | system_2 | tool_semantics_error | high | strict_match | `SYSTEM2_RESEARCH_AGENTS_FAULT_004`/VIEW_PARAMETER_IGNORED, `SYSTEM2_RESEARCH_AGENTS_FAULT_005`/PAGINATION_NOT_FOLLOWED |
| `GT-S2-003` | system_2 | tool_error_handling_missing | medium | missed | - |
| `GT-S2-004` | system_2 | wrong_routing | high | strict_match | `SYSTEM2_RESEARCH_AGENTS_FAULT_001`/SPEAKER_SELECTION_LOOP, `SYSTEM2_RESEARCH_AGENTS_FAULT_003`/MISSING_TOOL_CALL |
| `GT-S2-005` | system_2 | termination_error | medium | missed | - |
| `GT-S3-001` | system_3 | message_passing_error | high | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_001`/MESSAGE_HANDOFF_TERMINATE_ONLY |
| `GT-S3-002` | system_3 | data_processing_error | medium | missed | - |
| `GT-S3-003` | system_3 | data_processing_error | medium | missed | - |
| `GT-S3-004` | system_3 | documented_entrypoint_broken | high | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_002`/DOCUMENTED_ENTRYPOINT_BROKEN |
| `GT-S3-005` | system_3 | missing_feature | medium | missed | - |
| `GT-S3-006` | system_3 | agent_orchestration_missing | high | missed | - |
