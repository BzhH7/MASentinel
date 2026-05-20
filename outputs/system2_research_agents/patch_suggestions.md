# Patch Suggestions

## SYSTEM2_RESEARCH_AGENTS_FAULT_001: Speaker Selection Error
- Layer: autogen_framework
- Affected cases: system2_research_agents_BUDGET_001, system2_research_agents_COV_002, system2_research_agents_COV_003, system2_research_agents_COV_004, system2_research_agents_COV_005, system2_research_agents_COV_006, system2_research_agents_FUZZ_001, system2_research_agents_FUZZ_002, system2_research_agents_FUZZ_003, system2_research_agents_HANDOFF_001, system2_research_agents_META_001, system2_research_agents_NOHUMAN_001, system2_research_agents_OUTCONTRACT_001, system2_research_agents_PROP_001, system2_research_agents_REG_001, system2_research_agents_REQ_001, system2_research_agents_REQ_003, system2_research_agents_REQ_004, system2_research_agents_REQ_005, system2_research_agents_REQ_006, system2_research_agents_SMOKE_001, system2_research_agents_TOOLAPI_001, system2_research_agents_TOOLCONTRACT_001, system2_research_agents_TOOLCONTRACT_002, system2_research_agents_TOOLCONTRACT_003, system2_research_agents_TOOLCONTRACT_004, system2_research_agents_TOOLERR_001, system2_research_agents_TOOLFUZZ_001, system2_research_agents_WIRING_001
- Suggested fix: Enforce max_turns limit strictly in speaker selection by checking turn count before selecting the next speaker and terminating immediately when the limit is reached, rather than after generating another message. Additionally, harden speaker name normalization and add a retry cap for empty/ invalid responses to prevent loops.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_002: Non-Termination
- Layer: autogen_framework
- Affected cases: system2_research_agents_COV_003, system2_research_agents_COV_006, system2_research_agents_HANDOFF_001, system2_research_agents_OUTCONTRACT_001, system2_research_agents_REQ_003, system2_research_agents_REQ_004, system2_research_agents_REQ_006
- Suggested fix: 1) Define an explicit termination message e.g., a custom function `is_termination_msg` that checks for 'APPROVED' or 'TASK_COMPLETE' in chat content. 2) In the group chat configuration, set `max_round` (or `max_turns`) to a reasonable value (e.g., 15) so the conversation terminates even if the LLM fails to send a termination keyword. 3) Set `human_input_mode='NEVER'` to prevent the system from waiting for human input that never arrives. 4) Modify the system prompt for director to output 'TERMINATE' after the review is complete.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM2_RESEARCH_AGENTS_FAULT_003: Missing Tool Call
- Layer: application
- Affected cases: system2_research_agents_REQ_001, system2_research_agents_REQ_001, system2_research_agents_REQ_001, system2_research_agents_REQ_001
- Suggested fix: Review tool registration and agent configuration to ensure 'google_search' is available to the researcher agent. Check if the tool was called within the 23-turn conversation but not captured by the trace, or if the model chose not to invoke it. If no code defect is found, classify as non-target issue (model decision/behavior) and reduce severity.

Suggested patch direction:
- Verify the target agent has the tool registered and that prompts/schema expose the tool name and required arguments.

## SYSTEM2_RESEARCH_AGENTS_FAULT_004: Human Input Mode Error
- Layer: autogen_framework
- Affected cases: system2_research_agents_STATIC_human_input_requested
- Suggested fix: Set human_input_mode='NEVER' or provide a deterministic non-blocking input adapter for automated runs.

Suggested patch direction:
- Remove blocking `input()` calls in automated paths or gate them behind a non-interactive configuration.

## SYSTEM2_RESEARCH_AGENTS_FAULT_005: Tool API Semantics Error
- Layer: application
- Affected cases: system2_research_agents_STATIC_view_parameter_ignored
- Suggested fix: Parse the semantic fields (base, table, view, query, filterByFormula, etc.) from the tool input and explicitly include them as query parameters in the API request URL. Ensure that the request builder proxies all relevant semantic parameters to the downstream API call.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_006: Tool API Pagination Missing
- Layer: application
- Affected cases: system2_research_agents_STATIC_pagination_not_followed
- Suggested fix: Refactor the Airtable tool functions to loop while an 'offset' is present in the response, accumulate all records from successive pages, and return the complete merged list. Ensure that the loop terminates when no further offset is returned to avoid infinite requests.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_007: Tool Error Contract Missing
- Layer: application
- Affected cases: system2_research_agents_STATIC_tool_unstructured_error
- Suggested fix: Check status codes and return typed success/error payloads with status, message, and retryability.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_008: Scalable Turn Budget Error
- Layer: autogen_framework
- Affected cases: system2_research_agents_STATIC_scalable_budget_exceeded
- Suggested fix: Scale max_round with record count or move repeated per-record work into deterministic batched tools. For example: calculate max_round as BASE_ROUNDS + (num_records * ROUNDS_PER_RECORD) or refactor the workflow to batch all record processing into a single deterministic tool call before entering the group chat, so the conversation itself doesn't scale with data volume.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

