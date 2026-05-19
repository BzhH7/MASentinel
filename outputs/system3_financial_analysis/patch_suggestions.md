# Patch Suggestions

## SYSTEM3_FINANCIAL_ANALYSIS_FAULT_001: Non-Termination
- Layer: autogen_framework
- Affected cases: system3_financial_analysis_COV_001, system3_financial_analysis_META_001, system3_financial_analysis_REQ_003, system3_financial_analysis_REQ_004
- Suggested fix: 1. Ensure the termination checking function is registered and checks for the 'TERMINATE' keyword in messages. 2. Set human_input_mode='NEVER' for automated runs. 3. Enforce max_turns/max_round in the runtime configuration to prevent infinite loops. 4. Verify speaker selection constraints to avoid unnecessary agent handoffs.

Suggested patch direction:
- Add or tighten `is_termination_msg`, `max_turns`/`max_round`, and set automated `human_input_mode='NEVER'`.

## SYSTEM3_FINANCIAL_ANALYSIS_FAULT_002: Wrong Agent Routing
- Layer: autogen_framework
- Affected cases: system3_financial_analysis_COV_002, system3_financial_analysis_COV_003, system3_financial_analysis_REQ_001, system3_financial_analysis_REQ_002, system3_financial_analysis_REQ_005, system3_financial_analysis_REQ_006, system3_financial_analysis_REQ_007, system3_financial_analysis_TOOLFUZZ_001, system3_financial_analysis_R2_001, system3_financial_analysis_R2_002, system3_financial_analysis_R2_003, system3_financial_analysis_R2_004
- Suggested fix: Register yfinance tool for data_collector or provide a mock tool; if 0 tool is intentional, update oracle to check for 0 data output instead of agent presence.

Suggested patch direction:
- Inspect the recorded trace evidence, then add a focused regression test before changing behavior.

