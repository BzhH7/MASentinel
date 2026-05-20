# MASentinel Alignment Against Independent Ground Truth

## Scope

I first reviewed the three target AutoGen systems from docs, entrypoints, agents, tools, group-chat configuration, prompts, config, and tests/examples. Only after that pass did I read `MASentinel/outputs/**`. The ground-truth IDs below refer to `analysis/ground_truth_defects.json`.

## Alignment Table

| Ground Truth defect ID | System | Layer | Defect type | MASentinel found | Matched report ID | Evidence sufficient | Judgment |
|---|---|---|---|---|---|---|---|
| GT-S1-001 | system_1 | application | wrong_output_schema | No | N/A | N/A | FN |
| GT-S1-002 | system_1 | application | missing_state | No | N/A | N/A | FN |
| GT-S1-003 | system_1 | application | wrong_output_schema | No | N/A | N/A | FN |
| GT-S1-004 | system_1 | application | input_validation_error | No | N/A | N/A | FN |
| GT-S2-001 | system_2 | framework | human_input_blocking | Yes | SYSTEM2_RESEARCH_AGENTS_FAULT_001 | Yes. Trace records `human_input_requested`; code has `human_input_mode="ALWAYS"`. | TP |
| GT-S2-002 | system_2 | application | tool_semantics_error | No | N/A | N/A | FN |
| GT-S2-003 | system_2 | application | tool_error_handling_missing | Partly | SYSTEM2_RESEARCH_AGENTS_FAULT_019 | Partial. MASentinel observed an unhandled runtime error, but did not localize the raw HTTP and `None` tool-result contracts. | Partial |
| GT-S2-004 | system_2 | framework | wrong_routing | Yes | SYSTEM2_RESEARCH_AGENTS_FAULT_002 and duplicate speaker-loop faults | Yes. Traces show repeated or invalid speaker-selection output and no completed required tool chain. | TP |
| GT-S2-005 | system_2 | framework | termination_error | No | N/A | N/A | FN |
| GT-S3-001 | system_3 | framework | message_passing_error | Partly | SYSTEM3_FINANCIAL_ANALYSIS_FAULT_002 and duplicate data-collection faults | Partial. MASentinel saw downstream missing-data symptoms, but diagnosed missing data-provider/tool registration. Code and traces show the stronger root cause is `last_message()` passing `TERMINATE`. | Partial |
| GT-S3-002 | system_3 | application | data_processing_error | No | N/A | N/A | FN |
| GT-S3-003 | system_3 | application | data_processing_error | No | N/A | N/A | FN |
| GT-S3-004 | system_3 | application | documented_entrypoint_broken | No | N/A | N/A | FN |
| GT-S3-005 | system_3 | application | missing_feature | No | N/A | N/A | FN |
| GT-S3-006 | system_3 | framework | agent_orchestration_missing | Partly | Coverage/report notes only, no specific failure ID | Partial. MASentinel noticed weak/isolated agent coverage, but did not connect it to `AgentOrchestrator({})` and the non-agent enterprise path. | Partial |

## MASentinel Failure Audit

The table keeps every MASentinel report ID visible. Repeated report IDs with the same root cause are concise but were checked against trace evidence, code locations, and oracle assumptions.

| MASentinel report ID | System | Reported issue | Why it may be false positive or partial | Missing evidence | How to improve oracle |
|---|---|---|---|---|---|
| SYSTEM1_ITERATIVE_CODING_FAULT_001 | system_1 | Missing `write_settled_plan` | Partial/likely FP. The triggering conversation did not clearly reach the planner's contract point: manager approval of a settled valid plan. | Need proof that a complete plan was approved and the planner still failed to call the tool. | Require a precondition: valid task details plus manager approval before asserting `write_settled_plan` must occur. |
| SYSTEM1_ITERATIVE_CODING_FAULT_002 | system_1 | Missing `write_settled_plan` | Same as FAULT_001. Missing tool call alone is weak for an interactive planning workflow. | Need prompt state and approval state, not only absence of tool call. | Track plan-state milestones before firing the missing-tool oracle. |
| SYSTEM1_ITERATIVE_CODING_FAULT_003 | system_1 | Missing `write_settled_plan` | Same as FAULT_001. Could be an under-specified user task rather than a code defect. | Need a validated complete planning request and final planner answer. | Pair the tool-call oracle with a task-completeness oracle. |
| SYSTEM1_ITERATIVE_CODING_FAULT_004 | system_1 | Human input requested | Partial. Real for unattended evaluation, but the README describes an interactive workflow. It is an automation compatibility issue, not necessarily a product defect. | Need explicit target-mode metadata: interactive expected vs no-human batch expected. | Make human-input assertions conditional on system profile mode. |
| SYSTEM1_ITERATIVE_CODING_FAULT_005 | system_1 | Run did not terminate | Partial. It is probably caused by the same interactive/no-human mismatch as FAULT_004. | Need termination reason and whether stdin was intentionally unavailable. | Cluster with human-input mode when the blocked point is an input prompt. |
| SYSTEM1_ITERATIVE_CODING_FAULT_006 | system_1 | Repetitive consecutive messages | Partial. Repetition is a symptom, but MASentinel did not identify a code/config defect. | Need speaker-transition trace and exact AutoGen termination state. | Diagnose repetition through speaker selection, max rounds, and human input together. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_001 | system_2 | Human input requested | Not FP. This matches GT-S2-001. | Evidence is sufficient. | Keep rule, but include code pointer to `human_input_mode="ALWAYS"`. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_002 | system_2 | Speaker selection loop | Not FP. This matches GT-S2-004. | Evidence is sufficient. | Keep rule, add suggested fix for explicit transitions. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_003 | system_2 | Timeout | Partial. Timeout is a symptom of human-input blocking or speaker-selection loop. | Need root-cause attribution to FAULT_001 or FAULT_002. | Deduplicate timeout symptoms under the blocking speaker/human-input cause. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_004 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_005 | system_2 | Missing edge director->research_manager | Likely FP. A fully connected group chat does not require every possible pair to speak in every successful trace. | Need a workflow invariant proving this edge is mandatory. | Do not assert arbitrary graph edges unless derived from code, prompt, or profile workflow. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_006 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_007 | system_2 | Timeout | Partial. Symptom of speaker loop or human input. | Need root-cause link. | Fold into dominant speaker-selection or human-input group. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_008 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_009 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_010 | system_2 | Timeout | Partial. Symptom, not root cause. | Need causality chain. | Attribute timeouts to preceding trace anomalies. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_011 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_012 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_013 | system_2 | Timeout | Partial. Symptom, not root cause. | Need causality chain. | Attribute timeouts to preceding trace anomalies. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_014 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_015 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_016 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_017 | system_2 | Timeout | Partial. Symptom, not root cause. | Need causality chain. | Attribute timeouts to preceding trace anomalies. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_018 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_019 | system_2 | Missing error handling | Partial. It aligns with GT-S2-003 at symptom level, but the report lacks the exact raw HTTP/`None` tool-contract diagnosis. | Need tool name, HTTP status, exception text, args, and returned value. | Record tool result envelopes and map failures to wrapper code. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_020 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_021 | system_2 | Timeout | Partial. Symptom, not root cause. | Need causality chain. | Attribute timeouts to preceding trace anomalies. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_022 | system_2 | Speaker selection loop | Not FP. Duplicate of GT-S2-004. | Evidence is sufficient. | Cluster duplicate speaker-loop failures. |
| SYSTEM2_RESEARCH_AGENTS_FAULT_023 | system_2 | Timeout | Partial. Symptom, not root cause. | Need causality chain. | Attribute timeouts to preceding trace anomalies. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_001 | system_3 | Timeout | Partial/possible FP. Some generated inputs are not valid stock-analysis tasks for the configured command template, so timeout alone is weak. | Need exact command, parsed ticker, last agent message, and termination state. | Validate generated test inputs against CLI schema before using timeout as failure evidence. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_002 | system_3 | Data collection tool registration missing | Partial. The symptom is real, but trace/code point to wrong message handoff via `last_message()`, not missing data collection. | Need downstream prompt content showing `TERMINATE` and code pointer to `conduct_analysis`. | Add a message-handoff oracle before diagnosing provider/tool registration. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_003 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_004 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_005 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_006 | system_3 | Timeout | Partial/possible FP. Timeout is not connected to a specific framework defect. | Need termination reason and prior message sequence. | Use timeout only as symptom unless linked to routing or termination config. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_007 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_008 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_009 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_010 | system_3 | Timeout | Partial/possible FP. Likely caused by bad generated command/input or unclustered runtime stall. | Need command, ticker, subprocess logs, and termination state. | Validate CLI inputs and cluster with exact preceding cause. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_011 | system_3 | Timeout | Partial/possible FP. Same concern as FAULT_010. | Need command, ticker, subprocess logs, and termination state. | Validate CLI inputs and cluster with exact preceding cause. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_012 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_013 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_014 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_015 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_016 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_017 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_018 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_019 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_020 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_021 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_022 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_023 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |
| SYSTEM3_FINANCIAL_ANALYSIS_FAULT_024 | system_3 | Data collection tool registration missing | Partial, same root cause as FAULT_002. | Need message-handoff evidence. | Same as FAULT_002. |

## Missed Or Partial Root Causes

| Defect ID | Why MASentinel missed or only partially found it |
|---|---|
| GT-S1-001 | No generated test forced valid non-`python` code fences, and the oracle did not inspect persisted script contents against the coder response. |
| GT-S1-002 | Tests did not construct partial on-disk project state, so resume-state branches were not exercised. |
| GT-S1-003 | The oracle did not compare documented artifact names against generated files. |
| GT-S1-004 | Test generator did not include malicious or invalid project-name inputs, and runner did not track writes outside the intended root. |
| GT-S2-002 | Tests did not model Airtable view URLs, pagination, or filtered views; oracle only looked for tool invocation symptoms. |
| GT-S2-003 | Runner did not capture HTTP status, structured tool args/results, or raw exceptions enough to map failure to wrapper code. |
| GT-S2-005 | Test cases did not scale the number of Airtable records and oracle did not estimate required turns from task cardinality. |
| GT-S3-001 | Diagnoser stopped at downstream missing-data language and did not compare collected data availability with downstream prompt content. |
| GT-S3-002 | No tests injected partial financial statement data with one missing row. |
| GT-S3-003 | Oracle did not validate numeric sign conventions for risk metrics. |
| GT-S3-004 | MASentinel targeted `simple_autogen/main.py`, so it never exercised the README-documented `src.main` entrypoint. |
| GT-S3-005 | CLI documentation conformance tests were not generated. |
| GT-S3-006 | Coverage noted weak agent use, but diagnoser did not connect static orchestration code to missing AutoGen collaboration. |

