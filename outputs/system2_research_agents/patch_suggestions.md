# Patch Suggestions

## SYSTEM2_RESEARCH_AGENTS_FAULT_001: Speaker Selection Error
- Layer: autogen_framework
- Affected cases: system2_research_agents_ARTIFACT_001, system2_research_agents_BUDGET_001, system2_research_agents_COV_001, system2_research_agents_COV_002, system2_research_agents_COV_003, system2_research_agents_COV_004, system2_research_agents_COV_005, system2_research_agents_COV_006, system2_research_agents_COV_007, system2_research_agents_DATAINV_001, system2_research_agents_FUZZ_001, system2_research_agents_HANDOFF_001, system2_research_agents_META_001, system2_research_agents_NOHUMAN_001, system2_research_agents_OUTCONTRACT_001, system2_research_agents_PROP_001, system2_research_agents_REG_001, system2_research_agents_REQ_001, system2_research_agents_REQ_002, system2_research_agents_REQ_004, system2_research_agents_SMOKE_001, system2_research_agents_SPEAKER_001, system2_research_agents_TOOLAPI_001, system2_research_agents_TOOLCONTRACT_001, system2_research_agents_TOOLCONTRACT_002, system2_research_agents_TOOLCONTRACT_003, system2_research_agents_TOOLCONTRACT_004, system2_research_agents_TOOLERR_001, system2_research_agents_TOOLFUZZ_001, system2_research_agents_WIRING_001
- Suggested fix: Harden GroupChat speaker selection logic: 1) Implement explicit termination detection when the conversation indicates task completion (e.g., check for 'Task complete' or final answer). 2) Normalize speaker names and filter invalid selections. 3) Cap the number of consecutive speaker selection retries without progress. 4) Ensure that the GroupChat manager correctly handles a 'TERMINATE' response from the speaker selection agent. 5) Review and update the speaker selection agent's prompt to recognize end-of-task signals.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_002: Non-Termination
- Layer: autogen_framework
- Affected cases: system2_research_agents_ARTIFACT_001, system2_research_agents_BUDGET_001, system2_research_agents_COV_002, system2_research_agents_COV_004, system2_research_agents_COV_007, system2_research_agents_FUZZ_001, system2_research_agents_HANDOFF_001, system2_research_agents_OUTCONTRACT_001, system2_research_agents_REQ_001, system2_research_agents_SPEAKER_001, system2_research_agents_TOOLAPI_001
- Suggested fix: Add a termination message check (e.g., if 'Task complete' appears, set is_termination_msg=true), enforce a strict max_turns limit, and/or configure human_input_mode='NEVER' with a terminating condition to prevent infinite loops.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM2_RESEARCH_AGENTS_FAULT_003: Missing Tool Call
- Layer: application
- Affected cases: system2_research_agents_REQ_002, system2_research_agents_REQ_002
- Suggested fix: 1) Enable detailed tool-call logging (e.g. log each AutoGen tool invoke/return). 2) Re-run with verbose LLM call traces to confirm whether the director agent attempted to call get_airtable_records. 3) If the tool is truly uncallable, register get_airtable_records in the director's tool map and ensure prompts instruct its use.

Suggested patch direction:
- Verify the target agent has the tool registered and that prompts/schema expose the tool name and required arguments.

## SYSTEM2_RESEARCH_AGENTS_FAULT_004: Tool Schema Mismatch
- Layer: application
- Affected cases: system2_research_agents_TOOLAPI_001
- Suggested fix: Modify get_airtable_records and update_single_airtable_record in app.py to: 1) parse and pass semantic fields such as view/base/table into the API request; 2) follow offset-based pagination by iterating until all records are fetched (e.g., checking for 'offset' in responses and issuing subsequent requests); 3) ensure structured error handling for non-200 responses or missing parameters.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_005: Tool API Pagination Missing
- Layer: application
- Affected cases: system2_research_agents_TOOLAPI_001
- Suggested fix: Modify the get_airtable_records function in app.py to: (1) Parse and preserve semantic URL parameters such as view/base/table from the request. (2) Implement a loop that follows offset-based pagination, checking for continuation tokens or next page URLs until all pages are retrieved. (3) Aggregate all records from all pages into a single response. (4) Handle rate limits and error responses gracefully.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_006: Tool Error Contract Missing
- Layer: application
- Affected cases: system2_research_agents_TOOLERR_001, system2_research_agents_TOOLERR_001
- Suggested fix: Modify the web_scraping tool wrapper to check HTTP response status codes. On non-2xx responses, construct and return a structured error dictionary (e.g., {"error": True, "status_code": 401, "detail": "invalid key"}) and ensure this error is propagated through the tool result and logged in the MAS_TRACE envelope. This should be implemented in the application-layer tool definition code (e.g., in the function registered for web_scraping).

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

