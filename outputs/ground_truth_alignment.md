# Ground Truth Alignment

- Ground truth: `../analysis/ground_truth_defects.json`
- Outputs: `outputs`
- Strict matches: 13
- Partial matches: 2
- Missed: 0

| Defect | System | Type | Severity | Status | Matched Faults |
|--------|--------|------|----------|--------|----------------|
| `GT-S1-001` | system_1 | wrong_output_schema | medium | strict_match | `SYSTEM1_ITERATIVE_CODING_FAULT_009`/MARKDOWN_ARTIFACT_CORRUPTION |
| `GT-S1-002` | system_1 | missing_state | medium | strict_match | `SYSTEM1_ITERATIVE_CODING_FAULT_011`/RESUME_STATE_INCOMPLETE |
| `GT-S1-003` | system_1 | wrong_output_schema | low | strict_match | `SYSTEM1_ITERATIVE_CODING_FAULT_010`/ARTIFACT_SCHEMA_MISMATCH |
| `GT-S1-004` | system_1 | input_validation_error | high | partial_match | `SYSTEM1_ITERATIVE_CODING_FAULT_001`/RUNTIME_EXCEPTION |
| `GT-S2-001` | system_2 | human_input_blocking | high | strict_match | `SYSTEM2_RESEARCH_AGENTS_FAULT_004`/HUMAN_INPUT_REQUESTED |
| `GT-S2-002` | system_2 | tool_semantics_error | high | strict_match | `SYSTEM2_RESEARCH_AGENTS_FAULT_005`/VIEW_PARAMETER_IGNORED, `SYSTEM2_RESEARCH_AGENTS_FAULT_006`/PAGINATION_NOT_FOLLOWED |
| `GT-S2-003` | system_2 | tool_error_handling_missing | medium | partial_match | `SYSTEM2_RESEARCH_AGENTS_FAULT_007`/TOOL_UNSTRUCTURED_ERROR |
| `GT-S2-004` | system_2 | wrong_routing | high | strict_match | `SYSTEM2_RESEARCH_AGENTS_FAULT_001`/SPEAKER_SELECTION_LOOP |
| `GT-S2-005` | system_2 | termination_error | medium | strict_match | `SYSTEM2_RESEARCH_AGENTS_FAULT_008`/SCALABLE_BUDGET_EXCEEDED |
| `GT-S3-001` | system_3 | message_passing_error | high | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_002`/MESSAGE_HANDOFF_TERMINATE_ONLY, `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_004`/MESSAGE_HANDOFF_TERMINATE_ONLY |
| `GT-S3-002` | system_3 | data_processing_error | medium | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_008`/PARTIAL_METRIC_ZEROED |
| `GT-S3-003` | system_3 | data_processing_error | medium | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_007`/NUMERIC_SIGN_CONVENTION_ERROR |
| `GT-S3-004` | system_3 | documented_entrypoint_broken | high | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_001`/DOCUMENTED_ENTRYPOINT_BROKEN |
| `GT-S3-005` | system_3 | missing_feature | medium | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_009`/DOCUMENTED_CLI_COMMAND_MISSING |
| `GT-S3-006` | system_3 | agent_orchestration_missing | high | strict_match | `SYSTEM3_FINANCIAL_ANALYSIS_FAULT_010`/AUTOGEN_WIRING_MISSING |
