# Patch Suggestions

## SYSTEM1_ITERATIVE_CODING_FAULT_001: Unsafe Project Path
- Layer: application
- Affected cases: system1_iterative_coding_FSSAFE_001
- Suggested fix: In all affected functions (write_latest_iteration_manual, write_latest_iteration_comments, write_latest_iteration, write_settled_plan, list_subdirectories), resolve the candidate path relative to the configured safe root using pathlib.Path.resolve() and enforce that the resolved path starts with the safe root. Reject and raise an error or return a controlled validation error for any path containing '..' components or absolute references outside the root.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM1_ITERATIVE_CODING_FAULT_002: Human Input Mode Error
- Layer: autogen_framework
- Affected cases: system1_iterative_coding_OUTCONTRACT_003, system1_iterative_coding_RESUME_001
- Suggested fix: Ensure AutoGen is instantiated with human_input_mode='NEVER' and remove all blocking input() or CLI prompt loops from the automated execution path. Replace them with programmatic decisions or pre-defined test inputs that satisfy the requirement without human intervention.

Suggested patch direction:
- Remove blocking `input()` calls in automated paths or gate them behind a non-interactive configuration.

## SYSTEM1_ITERATIVE_CODING_FAULT_003: Termination Condition Error
- Layer: autogen_framework
- Affected cases: system1_iterative_coding_OUTCONTRACT_003, system1_iterative_coding_RESUME_001
- Suggested fix: 1) Add a termination message check (e.g., return True for messages containing 'TERMINATE' or a specific keyword). 2) Set the group chat's max_round or run's max_turns to a hard limit (e.g., 30). 3) Implement a speaker selection policy that prevents the same agent from sending repeated messages without progress.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM1_ITERATIVE_CODING_FAULT_004: Speaker Selection Error
- Layer: autogen_framework
- Affected cases: system1_iterative_coding_OUTCONTRACT_003, system1_iterative_coding_RESUME_001
- Suggested fix: Inspect the AutoGen configuration (e.g., GroupChat, speaker selection method, max_consecutive_auto_reply) and add a guard to break loops when the same agent sends consecutive messages with identical content. Implement a max-turn limit or a termination condition based on task progress (e.g., after a manager directive to provide code, the coder must act). Additionally, register a tool to check message uniqueness and force a handoff if repetition is detected.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM1_ITERATIVE_CODING_FAULT_005: Non-Termination
- Layer: autogen_framework
- Affected cases: system1_iterative_coding_REQ_002
- Suggested fix: 1. Set human_input_mode='NEVER' in the AssistantAgent configuration and group chat manager to allow full automation. 2. Define an is_termination_msg function that returns True on messages containing 'TERMINATE' or final workflow completion signals (e.g., after Reviewer approves with write_latest_iteration). 3. Enforce max_turns/max_round in the group chat configuration to a safe upper bound (e.g., 30) to guard against infinite loops. 4. Ensure the workflow states in IterativeTools.py properly transition to an exit condition.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM1_ITERATIVE_CODING_FAULT_006: Resume State Inconsistency
- Layer: application
- Affected cases: system1_iterative_coding_RESUME_001
- Suggested fix: Modify the iterative coding workflow to call 'retrieve_latest_iteration' or 'does_version_one_exist' at the start of a resume session to detect the existing plan and script files. If an existing iteration is found, populate the agent's context with the retrieved state instead of treating the project as a first iteration.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

## SYSTEM1_ITERATIVE_CODING_FAULT_007: Termination Signal Ignored
- Layer: autogen_framework
- Affected cases: system1_iterative_coding_TERM_001
- Suggested fix: Add or fix is_termination_msg handling so TERMINATE stops the conversation within a small grace window.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

