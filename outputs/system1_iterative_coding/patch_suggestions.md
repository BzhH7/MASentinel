# Patch Suggestions

## SYSTEM1_ITERATIVE_CODING_FAULT_001: Potential False Positive (Missing Tool Call)
- Layer: application
- Affected cases: system1_iterative_coding_COV_001, system1_iterative_coding_PROP_001, system1_iterative_coding_REQ_002
- Suggested fix: Re-evaluate the oracle's must_call_tools requirement for write_settled_plan. Check if the test case input sequence and agent interactions logically lead to a state where write_settled_plan should be called. If not, update the oracle to reflect the correct expected tool calls. Also verify tool registration and agent's tool access to ensure write_settled_plan is available when needed.

Suggested patch direction:
- Verify the target agent has the tool registered and that prompts/schema expose the tool name and required arguments.

## SYSTEM1_ITERATIVE_CODING_FAULT_002: Human Input Mode Error
- Layer: autogen_framework
- Affected cases: system1_iterative_coding_R2_006
- Suggested fix: Set `human_input_mode='NEVER'` in the AutoGen runtime configuration (e.g., `ConversableAgent` constructor or `GroupChatManager`/`aio_run` parameters) and ensure that the termination condition is strictly enforced: either by using a `max_round` limit on `GroupChat`, a termination message like '__TERMINATE__' sent by agents after completing the required workflow, or by implementing an `is_termination_msg` predicate that recognizes workflow completion phrases. Additionally, remove any blocking `input()` calls from the agents' tool or response handling paths.

Suggested patch direction:
- Remove blocking `input()` calls in automated paths or gate them behind a non-interactive configuration.

## SYSTEM1_ITERATIVE_CODING_FAULT_003: Termination Condition Error
- Layer: application
- Affected cases: system1_iterative_coding_R2_006
- Suggested fix: 1. In the application's agent logic (e.g., in the planner or manager), after calling write_settled_plan, ensure the agent returns a specific termination message (e.g., a structured message with a 'terminate' flag or a predefined delimiter) that is recognized by the is_termination_msg function in the AutoGen configuration. 2. Configure the GroupChatManager with an is_termination_msg handler that checks for this specific message. 3. Set human_input_mode to 'NEVER' for automated orchestration to prevent the system from waiting for non-existent human input. 4. As a safety net, enforce a max_round or max_turns in the GroupChat settings that triggers graceful termination before the test oracle's limit is reached.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM1_ITERATIVE_CODING_FAULT_004: Termination/Guardrail Missing
- Layer: autogen_framework
- Affected cases: system1_iterative_coding_R2_006
- Suggested fix: In the AutoGen configuration (group chat or SelectorGroupChat), set a strict max_turns ≤ 15. Add a custom termination message/method that triggers when write_settled_plan is successfully executed after manager's confirmation, immediately ending the conversation. Optionally implement a state guard in planner's agent definition to prevent any planning actions once settled plan is written.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

