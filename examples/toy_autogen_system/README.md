# Toy AutoGen-like System

This small system simulates a multi-agent workflow without requiring AutoGen.

Runnable requirements:

- The user proxy should send a task to the planner agent.
- The planner should route actionable work to the executor agent.
- The executor should call `search_tool` for normal research tasks.
- The system should emit a final non-empty summary and terminate.
- Tool argument errors should be reported as software faults rather than treated as model quality issues.
