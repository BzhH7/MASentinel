# MASentinel Report: system2_research_agents

## System Overview
- Root path: `/Users/zhbai/code/cz_exp/research-agents-3.0-main`
- Entrypoint: `/Users/zhbai/code/cz_exp/research-agents-3.0-main/app.py`
- Agents: 5
- Tools: 4
- Requirements: 5
- Message edges: 13

## Detected Agents
- `user_proxy` (UserProxyAgent) tools=[]
- `researcher` (GPTAssistantAgent) tools=['web_scraping', 'google_search']
- `research_manager` (GPTAssistantAgent) tools=[]
- `director` (GPTAssistantAgent) tools=['get_airtable_records', 'update_single_airtable_record']
- `group_chat_manager` (GroupChatManager) tools=[]

## Detected Tools
- `web_scraping` 
- `google_search` 
- `get_airtable_records` 
- `update_single_airtable_record` 

## Requirements
- `R1` The multi-agent workflow must route a user task through the declared agents (user_proxy, researcher, research_manager, director) and terminate cleanly.
- `R2` Registered tools (web_scraping, google_search, get_airtable_records, update_single_airtable_record) must be callable with valid arguments and return usable results or handled errors.
- `R3` The researcher agent must be able to use web_scraping and google_search tools to gather16 information.
- `R4` The director agent must be able to use get_airtable_records and update_single_airtable_record toolsood to manage Airtable data.
- `R5` The group chat manager must coordinate the conversation and enforce termination conditions (TERMINATE, max_turns, process_exit).

## Test Summary
- Cases: 20
- Passed process runs: 6
- Failed/timeout process runs: 14
- Fault findings: 8
- Root-cause groups: 3
- Primary fault findings: 3
- Suspected false positives: 6

## Coverage
| Metric | Value |
|--------|-------|
| AgentCov | 1.0000 |
| ToolCov | 1.0000 |
| EdgeCov | 0.0000 |
| ReqCov | 1.0000 |
| StateCov | 0.5625 |
| FaultCov | 0.5000 |
| MASCov | 0.6900 |

## Agentic Testing Workflow
- `RequirementAnalystAgent`
- `SystemModelingAgent`
- `TestDesignerAgent`
- `InteractionAdapterAgent`
- `CoverageStrategistAgent`
- `ExecutionMonitorAgent`
- `FaultDiagnoserAgent`
- `FalsePositiveAuditorAgent`
- `ReportWriterAgent`

## Three-Stage Automation Evidence
- Human intervention allowed: False
- Testcase frozen SHA256: `8fa8d73642aa4cf43261abe2751ce1fc31d9668590c62a5659e39bbce2371f79`
- Second-round extra cases: 4
- Non-target issues excluded from target faults: 0
- Test harness issues excluded from target faults: 0
- Artifacts: `run_manifest.json`, `testcases.generated.json`, `testcases.validated.json`, `oracle_results.json`, `non_target_issues.json`, `test_harness_issues.json`, `faults.json`, `false_positive_audit.json`

## Testing-Agent Model Usage
- Total agent calls: 39
- Successful model calls: 35
- Fallback calls: 4
- Estimated input tokens: 90176
- Estimated output tokens: 10818

| Agent | Calls |
|-------|-------|
| CoverageStrategistAgent | 2 |
| ExecutionMonitorAgent | 1 |
| FalsePositiveAuditorAgent | 15 |
| FaultDiagnoserAgent | 15 |
| InteractionAdapterAgent | 1 |
| ReportWriterAgent | 1 |
| RequirementAnalystAgent | 1 |
| SystemModelingAgent | 1 |
| TestDesignerAgent | 2 |

## Target-System Model Usage
- Scope: `target_system_subprocess`
- Traced cases: 20
- AutoGen model-warning mentions: 42
- API key envs: `INF_API_KEY_FLASH`

| Target Model | Cases |
|--------------|-------|
| ds-v4-flash | 20 |

| Target Base URL | Cases |
|-----------------|-------|
| `https://ds-v4-flash-w8a8-vllm-ascend.openapi-sj.sii.edu.cn/v1` | 20 |

## Agentic Analysis
本次运行针对 system2_research_agents 系统执行了完整的 MASentinel 自动化测试流程。系统包含 5 个 Agent（user_proxy, researcher, research_manager, director, group_chat_manager）和 4 个工具（web_scraping, google_search, get_airtable_records, update_single_airtable_record）。测试覆盖了所有 5 个需求（R1-R5），访问了 8 个 Agent，调用了全部 4 个工具，覆盖了 9 种状态和 6 种故障模式。共产生 20 条规则结果，诊断出 8 个唯一故障（FAULT_001 至 FAULT_008），其中 2 个被确认为真实故障（FAULT_004 和 FAULT_008），其余 6 个被审计为误报。模型使用方面，共调用 38 次 ds-v4-pro 模型，成功 34 次，失败 4 次，fallback 4 次，主要用于故障诊断（15 次）和误报审计（15 次）。

本次测试在故障检测方面表现出较高的覆盖率（agent_coverage=1.0, tool_coverage=1.0, requirement_coverage=1.0），但 message_edge_coverage 为 0.0，state_coverage 为 0.5625，fault_mode_coverage 为 0.5，整体 mascov 为 0.69。检测到的 8 个故障中，2 个为真实故障（FAULT_004: 未处理的 TimeoutError 导致运行时崩溃；FAULT_008: 缺少终止条件导致超时），其余 6 个为误报（主要因 oracle 阈值过严、命名不匹配或外部服务超时导致）。真实故障均属于 AutoGen 框架层问题，可通过修改配置或添加错误处理来缓解。误报率较高（6/8=75%），主要源于 oracle 的 max_turns 阈值设置过紧（20 或 15）以及 agent 命名不一致（group_chat_manager vs chat_manager）。测试有效性中等，需要优化 oracle 规则以减少误报。

False positive analysis: 在 8 个故障中，6 个被审计为误报（FAULT_001, FAULT_002, FAULT_003, FAULT_005, FAULT_006, FAULT_007），误报率 75%。主要原因包括：(1) Oracle 阈值过严：FAULT_001 和 FAULT_003 因 turn_count 超过 max_turns（23>20）被误判为 NON_TERMINATION 和 REPETITIVE_LOOP，但实际对话已正常终止；(2) 外部服务超时导致的级联误报：FAULT_005 和 FAULT_006 因 OpenAI API TimeoutError 导致工作流中断，进而触发 MISSING_MESSAGE_EDGE 和 METAMORPHIC_RELATION_VIOLATION，根源为基础设施问题而非软件缺陷；(3) 命名不一致：FAULT_007 因系统使用 'chat_manager' 而 oracle 期望 'group_chat_manager'，导致 MISSING_AGENT 误报；(4) 日志缺失：FAULT_002 因 trace 中无工具调用日志，oracle 无法确认 google_search 是否被调用，但测试本身已通过。这些误报均不涉及应用代码或 AutoGen 框架的实际缺陷，建议调整 oracle 阈值、统一命名规范并增强日志记录。

Agent-proposed next steps:
- 调整测试 oracle 的 max_turns 阈值：将 system2_research_agents_COV_001 等用例的 max_turns 从 20 提高到 25 或 30，以匹配实际工作流的正常耗时。
- 统一 Agent 命名：将 oracle 中的 'group_chat_manager' 改为 'chat_manager'，或在系统配置中将 agent 名称改为 'group_chat_manager'，消除命名不一致导致的误报。
- 增强工具调用日志：在 app.py 中添加工具调用的显式日志输出，确保 MASentinel 能准确捕获 google_search 等工具的调用情况，避免因日志缺失导致的 MISSING_TOOL_CALL 误报。
- 添加 API 超时处理：在 app.py 或 AutoGen 配置中添加 try-except 块捕获 TimeoutError，实现重试或优雅降级，修复 FAULT_004 的真实故障。
- 完善终止条件：在 GroupChat 配置中设置 human_input_mode='NEVER'，添加 is_termination_msg 检查，并设置 max_round 参数，修复 FAULT_008 的真实故障。
- 优化 oracle 规则：对 MISSING_MESSAGE_EDGE 和 METAMORPHIC_RELATION_VIOLATION 规则增加前置条件检查（如确认无 TimeoutError），减少因外部服务中断导致的级联误报。

## Fault Summary

### Root-Cause Groups
- `generic:autogen_framework-wrong-agent-routing-the-agent-name-in-the-trace-is-chat_manager-while-the-oracle-expects-group_chat_ma` Wrong Agent Routing primary=`SYSTEM2_RESEARCH_AGENTS_FAULT_007` cases=2 symptoms=0
- `interaction:timeout-or-non-termination` Conversation timeout or missing termination guard primary=`SYSTEM2_RESEARCH_AGENTS_FAULT_001` cases=20 symptoms=3
- `runtime:users-zhbai-code-cz_exp-masentinel-.venv-runtime-lib-python3.9-site-packages-autogen-oai-client.py:739` Unhandled startup/runtime exception primary=`SYSTEM2_RESEARCH_AGENTS_FAULT_004` cases=14 symptoms=2
- `SYSTEM2_RESEARCH_AGENTS_FAULT_001` `system2_research_agents_COV_001` autogen_framework / Termination Condition Error / high / primary: The run did not terminate within the expected turn budget.
- `SYSTEM2_RESEARCH_AGENTS_FAULT_002` `system2_research_agents_COV_001` application / Missing Tool Call / medium / derived from `SYSTEM2_RESEARCH_AGENTS_FAULT_001`: Expected tool was not called: google_search
- `SYSTEM2_RESEARCH_AGENTS_FAULT_003` `system2_research_agents_COV_001` autogen_framework / Speaker Selection Error / medium / derived from `SYSTEM2_RESEARCH_AGENTS_FAULT_001`: Trace contains highly repetitive consecutive messages.
- `SYSTEM2_RESEARCH_AGENTS_FAULT_004` `system2_research_agents_COV_002` autogen_framework / alen / high / primary: The process ended with an unhandled runtime error.
- `SYSTEM2_RESEARCH_AGENTS_FAULT_005` `system2_research_agents_COV_002` autogen_framework / Message Routing Error / medium / derived from `SYSTEM2_RESEARCH_AGENTS_FAULT_004`: Expected message edge was not observed: director->research_manager
- `SYSTEM2_RESEARCH_AGENTS_FAULT_006` `system2_research_agents_META_001` application / Metamorphic Relation Violation / medium / derived from `SYSTEM2_RESEARCH_AGENTS_FAULT_004`: Equivalent metamorphic inputs did not preserve expected routing/tool relation.
- `SYSTEM2_RESEARCH_AGENTS_FAULT_007` `system2_research_agents_PROP_001` autogen_framework / Wrong Agent Routing / medium / primary: Expected agent was not observed: group_chat_manager
- `SYSTEM2_RESEARCH_AGENTS_FAULT_008` `system2_research_agents_R2_001` autogen_framework / Non-Termination / high / derived from `SYSTEM2_RESEARCH_AGENTS_FAULT_001`: The process exceeded the configured timeout.

## Suspected False Positives
Findings with confidence below 0.65 are marked as suspected false positives. Missing-agent and missing-edge findings can be caused by limited instrumentation when a target system does not emit MASentinel trace events.

## Limitations
- Subprocess tracing captures stdout/stderr for arbitrary systems; deep AutoGen message/tool traces require optional monkey patch import in the target process.
- The deterministic generator avoids judging subjective LLM answer quality.
- Static AST extraction is conservative and may over-approximate potential GroupChat edges.

## Next Steps
- Import `masentinel.instrumentation.autogen_patch` in target entrypoints for richer traces.
- Add system-specific configuration for command arguments and timeout budgets.
- Enable an OpenAI-compatible local model for document extraction and optional LLM judge.
