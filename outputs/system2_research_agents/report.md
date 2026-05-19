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
- `R1` The multi-agent workflow must route a user task through the declared agents (user_proxy, researcher, research_manager, director) and terminate within the configured max_turns or upon receiving a TERMINATE signal.
- `R2` Registered tools (web_scraping, google_search, get_airtable_records, update_single_airtable_record) must be callable with valid arguments and return usable results or handled errors.
- `R3` The researcher agent must be able to invoke web_scraping and google_search tools to gather16 information, and16 the director agent must be able to invoke get_airtable_records and update_single_airtable_record to manage Airtable data.
- `R4` The group chat manager must coordinate the conversation among agents, allowing any agent to send messages to any other agent as per the group chat configuration.
- `R5` The system must handle termination conditions correctly, including explicit TERMINATE messages and max_turns limit, without hanging or crashing.

## Test Summary
- Cases: 16
- Passed process runs: 9
- Failed/timeout process runs: 7
- Fault findings: 4
- Root-cause groups: 4
- Primary fault findings: 4
- Suspected false positives: 2

## Coverage
| Metric | Value |
|--------|-------|
| AgentCov | 1.0000 |
| ToolCov | 1.0000 |
| EdgeCov | 1.0000 |
| ReqCov | 1.0000 |
| StateCov | 0.6250 |
| FaultCov | 0.3333 |
| MASCov | 0.8333 |

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
- Testcase frozen SHA256: `41184ba93b9c2a8e34ea7365d0efc06d6a930a1adf59b1e11df5d6ef168e18c6`
- Second-round extra cases: 0
- Non-target issues excluded from target faults: 4
- Test harness issues excluded from target faults: 4
- Artifacts: `run_manifest.json`, `testcases.generated.json`, `testcases.validated.json`, `oracle_results.json`, `non_target_issues.json`, `test_harness_issues.json`, `faults.json`, `false_positive_audit.json`

## Testing-Agent Model Usage
- Total agent calls: 16
- Successful model calls: 16
- Fallback calls: 0
- Estimated input tokens: 46969
- Estimated output tokens: 7088

| Agent | Calls |
|-------|-------|
| CoverageStrategistAgent | 1 |
| ExecutionMonitorAgent | 1 |
| FalsePositiveAuditorAgent | 4 |
| FaultDiagnoserAgent | 4 |
| InteractionAdapterAgent | 1 |
| ReportWriterAgent | 1 |
| RequirementAnalystAgent | 1 |
| SystemModelingAgent | 1 |
| TestDesignerAgent | 2 |

## Target-System Model Usage
- Scope: `target_system_subprocess`
- Traced cases: 16
- AutoGen model-warning mentions: 91
- API key envs: `INF_API_KEY_FLASH`

| Target Model | Cases |
|--------------|-------|
| ds-v4-flash | 16 |

| Target Base URL | Cases |
|-----------------|-------|
| `https://ds-v4-flash-w8a8-vllm-ascend.openapi-sj.sii.edu.cn/v1` | 16 |

## Agentic Analysis
本次自动化测试运行基于 deterministic AST + 文档启发式分析构建的 profile，对 research-agents-3.0 系统进行了覆盖测试。测试覆盖了全部 5 个 agent、4 个工具、13 条消息边和 5 项需求，状态覆盖率为 62.5%，故障模式覆盖率为 33.3%。共发现 4 个故障，其中 一枝 2 个被确认为真实故障（SYSTEM2_RESEARCH_AGENTS_FAULT_002 和 SYSTEM2_RESEARCH_AGENTS_FAULT_004），2 个被判定为疑似误报（SYSTEM2_RESEARCH_AGENTS_FAULT_001 和 SYSTEM2_RESEARCH_AGENTS_FAULT_003）。模型使用方面，共调用 15 次 ds-v4-pro 模型，全部成功，无 fallback 或失败，估计消耗输入 token 39834、输出 token 6182。

本次测试在 agent/tool/消息边/需求覆盖率上均达到 100%，但状态覆盖率仅 62.5%，故障模式覆盖率仅 33.3%，说明测试用例在覆盖正常路径和部分异常路径方面有效，但在覆盖更多运行时状态（如 conflicting_instruction、metamorphic_relation、property_boundary）和故障模式（如 tool_schema_error、agent_configuration_error）方面存在不足。已确认的两个真实故障（FAULT_002 和 FAULT_004）均与 speaker_selection_agent 的响应解析和循环控制缺陷相关，属于框架层和应用层逻辑错误，诊断准确且修复建议具体。两个疑似误报（FAULT_001 和 FAULT_003）经审计后认为更可能是模型服务行为或测试覆盖缺口导致，而非软件缺陷，降低了误报对后续修复的干扰。整体上，测试流程有效识别了关键的非终止和解析错误，但需扩展测试用例以提升状态和故障模式覆盖率。

False positive analysis: 共 2 个故障被标记为疑似误报。FAULT_001（Human Input Mode Error）的 trace 中未发现实际 human input 提示或阻塞调用，超时更可能由模型服务返回空内容导致，属于基础设施/模型服务问题，非应用或框架配置故障，误报风险高。FAULT_003（Message Routing Error）的测试已正常通过，缺失的 director->research_manager 边是模型决策行为导致的覆盖缺口，无证据表明框架路由失败，误报风险高。两个误报均经 FalsePositiveAuditorAgent 审计并给出详细理由，置信度分别为 0.85 和 0.9，有效避免了将非软件缺陷误判为目标故障。

Agent-proposed next steps:
- 修复 FAULT_002：在 speaker_selection_agent 的调用逻辑中增加最大重试次数和 fallback 机制，例如连续 3 次空响应后默认选择 'user_proxy' 或 'director'，并在 GroupChat 配置中设置合理的 max_turns 作为兜底。
- 修复 FAULT_004：在 checking_agent 的 speaker 验证逻辑中增加字符串归一化处理（去除空白字符和已知前缀如 'response'），或修改 speaker_selection_agent 的 prompt 强制输出纯 speaker 名称。
- 扩展测试用例以覆盖更多状态和故障模式：针对 tool_schema_risk 和 agent_configuration_risk 设计异常参数测试（如无效 JSON、缺失必填字段），覆盖 conflicting_instruction、metamorphic_relation、property_boundary 等状态。
- 优化测试 oracle 和覆盖率目标：对 FAULT_003 类缺失边问题，调整 oracle 为接受间接通信或增加强制路由的 prompt；对 FAULT_001 类超时问题，增加模型服务健康检查或重试机制，避免误判。
- 在 CI/CD 中集成自动化测试，并设置 max_turns 和 timeout 阈值，确保回归测试能及时发现 speaker selection 循环和解析错误。

## Fault Summary

### Root-Cause Groups
- `generic:autogen_framework-message-routing-error-the-collected-trace-does-not-contain-a-direct-director--research_manager-message` Message Routing Error primary=`SYSTEM2_RESEARCH_AGENTS_FAULT_003` cases=1 symptoms=0
- `interaction:human-input-or-approval` Unattended run blocked by human input or approval primary=`SYSTEM2_RESEARCH_AGENTS_FAULT_001` cases=1 symptoms=0
- `interaction:timeout-or-non-termination` Conversation timeout or missing termination guard primary=`SYSTEM2_RESEARCH_AGENTS_FAULT_002` cases=7 symptoms=0
- `runtime:the-speaker_selection_agent-s-response-is-not-properly-parsed.-the-agent-returns-response-director-instead-of-director-.` Unhandled startup/runtime exception primary=`SYSTEM2_RESEARCH_AGENTS_FAULT_004` cases=1 symptoms=0
- `SYSTEM2_RESEARCH_AGENTS_FAULT_001` `system2_research_agents_COV_001` autogen_framework / Human Input Mode Error / high / primary: The target system requested human input during an automated no-human run.
- `SYSTEM2_RESEARCH_AGENTS_FAULT_002` `system2_research_agents_COV_001` autogen_framework /  böjnings Termination / high / primary: The process exceeded the configured timeout.
- `SYSTEM2_RESEARCH_AGENTS_FAULT_003` `system2_research_agents_COV_002` autogen_framework / Message Routing Error / medium / primary: Expected message edge was not observed: director->research_manager
- `SYSTEM2_RESEARCH_AGENTS_FAULT_004` `system2_research_agents_TOOLFUZZ_001` application / Encoding/Decoding Error / high / primary: The process ended with an unhandled runtime error.

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
