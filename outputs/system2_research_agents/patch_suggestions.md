# Patch Suggestions

## SYSTEM2_RESEARCH_AGENTS_FAULT_001: Speaker Selection Error
- Layer: autogen_framework
- Affected cases: system2_research_agents_COV_001, system2_research_agents_COV_002, system2_research_agents_COV_003, system2_research_agents_COV_004, system2_research_agents_COV_005, system2_research_agents_COV_006, system2_research_agents_COV_007, system2_research_agents_COV_008, system2_research_agents_COV_009, system2_research_agents_FUZZ_001, system2_research_agents_HANDOFF_001, system2_research_agents_META_001, system2_research_agents_NOHUMAN_001, system2_research_agents_OUTCONTRACT_001, system2_research_agents_PROP_001, system2_research_agents_REG_001, system2_research_agents_REQ_001, system2_research_agents_REQ_003, system2_research_agents_REQ_004, system2_research_agents_SMOKE_001, system2_research_agents_TOOLAPI_001, system2_research_agents_TOOLCONTRACT_001, system2_research_agents_TOOLCONTRACT_002, system2_research_agents_TOOLCONTRACT_003, system2_research_agents_TOOLCONTRACT_004, system2_research_agents_TOOLERR_001, system2_research_agents_TOOLFUZZ_001, system2_research_agents_TOOLFUZZ_002, system2_research_agents_WIRING_001
- Suggested fix: Harden GroupChat speaker selection: normalize speaker names, handle empty responses, and cap repeated retries.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_002: Missing Tool Call
- Layer: application
- Affected cases: system2_research_agents_COV_001, system2_research_agents_TOOLFUZZ_001
- Suggested fix: Verify tool registration and prompting; ensure the target agent has access to the tool.

Suggested patch direction:
- Verify the target agent has the tool registered and that prompts/schema expose the tool name and required arguments.

## SYSTEM2_RESEARCH_AGENTS_FAULT_003: Non-Termination
- Layer: autogen_framework
- Affected cases: system2_research_agents_COV_002, system2_research_agents_COV_003, system2_research_agents_COV_006, system2_research_agents_COV_007, system2_research_agents_HANDOFF_001, system2_research_agents_REQ_001, system2_research_agents_REQ_003
- Suggested fix: Add a termination message function that checks for keywords like 'TERMINATE' or 'exit'. Configure max_turns=12 in groupchat/agent settings and set human_input_mode='NEVER' for automated runs. Implement a fallback speaker selection logic that picks 'checking_agent' when a cycle is detected.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM2_RESEARCH_AGENTS_FAULT_004: Missing Error Handling
- Layer: application
- Affected cases: system2_research_agents_REQ_003
- Suggested fix: Modify the code generation logic or the Python execution environment to ensure all required tools (web_scraping, google_search, get_airtable_records, update_single_airtable_record) are properly imported and defined before executing user code. Add a try/except block around the execution to catch NameError and other exceptions, allowing the agent to handle missing tools gracefully rather than crashing. Alternatively, explicitly list tool names injected into the code namespace.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

