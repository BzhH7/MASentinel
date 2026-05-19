# Patch Suggestions

## SYSTEM2_RESEARCH_AGENTS_FAULT_001: Human Input Mode Error
- Layer: autogen_framework
- Affected cases: system2_research_agents_COV_001
- Suggested fix: In the test harness or agent configuration, explicitly set human_input_mode='NEVER' for all agents involved in automated execution. Ensure no blocking input() calls are present in the execution path. For example, in the GroupChat or agent initialization, set the parameter human_input_mode='NEVER'.

Suggested patch direction:
- Remove blocking `input()` calls in automated paths or gate them behind a non-interactive configuration.

## SYSTEM2_RESEARCH_AGENTS_FAULT_002:  böjnings Termination
- Layer: autogen_framework
- Affected cases: system2_research_agents_COV_001, system2_research_agents_COV_003, system2_research_agents_META_001, system2_research_agents_REG_001, system2_research_agents_REQ_004, system2_research_agents_TOOLFUZZ_001, system2_research_agents_TOOLFUZZ_002
- Suggested fix: 1. Add a max retry limit in the speaker selection logic (e.g., after 3 empty responses, default to 'user_proxy' or 'director'). 2. Implement a fallback speaker selection rule when the model response is empty or invalid. 3. Ensure the speaker selection agent's prompt or configuration forces a valid output (e.g., using function calling or structured output). 4. Add a global max_turns/max_round parameter in the GroupChat configuration to force termination even if speaker selection loops.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM2_RESEARCH_AGENTS_FAULT_003: Message Routing Error
- Layer: autogen_framework
- Affected cases: system2_research_agents_COV_002
- Suggested fix: This is a likely false positive for a software fault. To improve coverage, consider adding a more specific prompt that forces director to delegate to research_manager, or adjust the test oracle to accept indirect communication via chat_manager. If a direct edge is required, review the agent configuration and  model instructions to ensure the director is prompted to send a message to research_manager.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM2_RESEARCH_AGENTS_FAULT_004: Encoding/Decoding Error
- Layer: application
- Affected cases: system2_research_agents_TOOLFUZZ_001
- Suggested fix: In the checking_agent's speaker validation logic (or the speaker_selection_agent's response processing), add string normalization: strip whitespaceantu and remove known prefixes like 'response' before performing the exact match. Alternatively, update the speaker_selection_agent's system prompt to strictly output only the speaker name with no extra characters.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

