import type {
  BugRecord,
  CoverageMetrics,
  DashboardSummary,
  Project,
  RunRecord,
  TestCase,
  TraceEventDTO
} from '@/types/domain'

export const coverage: CoverageMetrics = {
  AgentCov: 0.92,
  ToolCov: 0.86,
  EdgeCov: 0.78,
  ReqVerifiedCov: 0.74,
  ContractCov: 0.81,
  TraceCompleteness: 0.96,
  MASCov: 0.84
}

export const projects: Project[] = [
  {
    id: 'p-autogen-001',
    name: 'AutoGen Research Crew',
    adapter_type: 'autogen',
    status: 'analyzed',
    created_at: '2026-06-12 10:24',
    config: {
      adapter_type: 'autogen',
      project_path: 'examples/research-agents',
      command_template: 'python main.py --topic "{input}"',
      http_url: '',
      timeout: 120,
      model_config: 'deepseek-v4-pro / ds-v4-flash',
      oracle_config: 'rule_oracle + contract_oracle + trace oracle'
    },
    profile: {
      agents: ['Director', 'ResearchManager', 'Researcher', 'CheckingAgent', 'UserProxy'],
      tools: ['google_search', 'web_scraping', 'get_airtable_records', 'update_airtable_record'],
      requirements: ['无人值守执行', '研究任务分解', '工具错误结构化返回', '终止信号可识别', '报告产物可追溯'],
      message_edges: [
        ['Director', 'ResearchManager'],
        ['ResearchManager', 'Researcher'],
        ['Researcher', 'CheckingAgent'],
        ['CheckingAgent', 'Director']
      ]
    }
  }
]

export const testCases: TestCase[] = [
  { id: 'tc-001', project_id: 'p-autogen-001', case_id: 'BASELINE_001', case_type: 'baseline', objective: '正常研究主题应能完成分解、搜索和总结', oracle_type: 'rule_oracle', enabled: true },
  { id: 'tc-002', project_id: 'p-autogen-001', case_id: 'CONTRACT_001', case_type: 'contract', objective: '工具调用失败时必须返回结构化错误对象', oracle_type: 'contract_oracle', enabled: true },
  { id: 'tc-003', project_id: 'p-autogen-001', case_id: 'NEGATIVE_001', case_type: 'negative', objective: '空主题不能触发无限自动回复', oracle_type: 'rule_oracle', enabled: true },
  { id: 'tc-004', project_id: 'p-autogen-001', case_id: 'META_001', case_type: 'metamorphic', objective: '同义任务应产生等价研究结论', oracle_type: 'metamorphic_oracle', enabled: true },
  { id: 'tc-005', project_id: 'p-autogen-001', case_id: 'TOOLERR_001', case_type: 'tool_error', objective: '搜索 API 超时应被上层 Agent 感知并降级', oracle_type: 'contract_oracle', enabled: true },
  { id: 'tc-006', project_id: 'p-autogen-001', case_id: 'CONTRACT_002', case_type: 'contract', objective: '最终报告必须包含引用和数据来源', oracle_type: 'llm_judge', enabled: true },
  { id: 'tc-007', project_id: 'p-autogen-001', case_id: 'NEGATIVE_002', case_type: 'negative', objective: '恶意路径输入不能写出项目目录', oracle_type: 'rule_oracle', enabled: true },
  { id: 'tc-008', project_id: 'p-autogen-001', case_id: 'BASELINE_002', case_type: 'baseline', objective: '多轮消息交接应覆盖 Director 与 Researcher', oracle_type: 'rule_oracle', enabled: true },
  { id: 'tc-009', project_id: 'p-autogen-001', case_id: 'CONTRACT_003', case_type: 'contract', objective: '终止消息出现后 GroupChat 必须停止', oracle_type: 'contract_oracle', enabled: true }
]

export const runRecord: RunRecord = {
  id: 'run-20260618-001',
  project_id: 'p-autogen-001',
  name: 'AutoGen Research Crew nightly semantic run',
  status: 'completed',
  started_at: '2026-06-18 15:20',
  pass_rate: 0.78,
  cases: testCases.map((item, index) => ({
    case_id: item.case_id,
    objective: item.objective,
    status: index === 1 || index === 4 ? 'failed' : 'passed',
    stdout: `执行 ${item.case_id}: agent conversation captured, artifacts collected.`,
    stderr: index === 1 ? 'ToolErrorEnvelopeMismatch: missing retryable field' : index === 4 ? 'TimeoutError: google_search exceeded budget' : '',
    error_summary: index === 1 ? '工具错误没有返回统一错误契约' : index === 4 ? '外部搜索超时后未触发降级路径' : '',
    oracle: {
      rule_oracle: index === 4 ? 'failed' : 'passed',
      contract_oracle: index === 1 ? 'failed' : 'passed',
      summary: index === 1 || index === 4 ? 'Oracle 捕获到可复现缺陷' : '行为符合预期'
    }
  }))
}

const baseTime = new Date('2026-06-18T15:20:00+08:00').getTime()
const names = [
  ['system', 'RunCreated', 'MASentinel-X', 'BatchRunner', '加载 9 条测试用例', 'run_id=run-20260618-001', 'passed'],
  ['agent_message', 'TaskDispatch', 'Director', 'ResearchManager', '研究主题: AI agents in finance', '拆分为搜索、验证、总结三个子任务', 'passed'],
  ['agent_message', 'PlanRequest', 'ResearchManager', 'Researcher', '请收集最近资料并标注来源', '开始调用检索工具', 'passed'],
  ['tool_call', 'google_search', 'Researcher', 'google_search', 'query=AI agent finance risk', 'HTTP 200, 8 results', 'passed'],
  ['tool_result', 'SearchResult', 'google_search', 'Researcher', '8 条候选链接', '筛选 3 条高可信来源', 'passed'],
  ['agent_message', 'EvidenceReview', 'Researcher', 'CheckingAgent', '提交证据片段和引用', '发现引用格式缺失风险', 'passed'],
  ['oracle_check', 'ContractOracle', 'MASentinel', 'CheckingAgent', '检查 report artifact schema', 'passed=true', 'passed'],
  ['agent_message', 'Feedback', 'CheckingAgent', 'ResearchManager', '补齐引用字段', '已更新产物要求', 'passed'],
  ['agent_message', 'TaskDispatch', 'Director', 'ResearchManager', '测试工具错误契约', '构造 google_search timeout', 'passed'],
  ['tool_call', 'google_search', 'Researcher', 'google_search', 'query=timeout://semantic-budget', 'Timeout after 2s', 'failed'],
  ['tool_result', 'ErrorEnvelope', 'google_search', 'Researcher', 'TimeoutError', '缺失 retryable 和 error_code 字段', 'failed'],
  ['oracle_check', 'ContractOracle', 'MASentinel', 'Researcher', '校验工具错误结构', 'failed: schema mismatch', 'failed'],
  ['agent_message', 'RecoveryAttempt', 'Researcher', 'ResearchManager', '尝试无工具降级总结', '缺少外部证据，返回不完整报告', 'failed'],
  ['agent_message', 'NegativeCase', 'Director', 'UserProxy', '空任务输入', 'UserProxy 未请求人工输入', 'passed'],
  ['agent_message', 'TerminationCheck', 'CheckingAgent', 'Director', 'TERMINATE', 'GroupChat stopped', 'passed'],
  ['tool_call', 'web_scraping', 'Researcher', 'web_scraping', 'url=https://example.org/report', '抽取正文 1420 chars', 'passed'],
  ['agent_message', 'ArtifactWrite', 'ResearchManager', 'ReportWriter', '写入 research_report.md', 'artifact_id=ART-042', 'passed'],
  ['oracle_check', 'RuleOracle', 'MASentinel', 'ReportWriter', '检查报告是否包含来源', 'passed=true', 'passed'],
  ['agent_message', 'MetamorphicA', 'Director', 'ResearchManager', 'topic=A autonomous agents', 'summary fingerprint=0.83', 'passed'],
  ['agent_message', 'MetamorphicB', 'Director', 'ResearchManager', 'topic=B agentic automation', 'summary fingerprint=0.79', 'passed'],
  ['oracle_check', 'MetamorphicOracle', 'MASentinel', 'Director', '比较语义相似度', 'passed=true similarity=0.91', 'passed'],
  ['system', 'RunComplete', 'BatchRunner', 'MASentinel-X', '9 cases executed', '7 passed / 2 failed', 'passed']
] as const

export const traceEvents: TraceEventDTO[] = names.map((row, index) => ({
  id: `ev-${String(index + 1).padStart(3, '0')}`,
  timestamp: new Date(baseTime + index * 9000).toISOString(),
  event_type: row[0] as TraceEventDTO['event_type'],
  event_name: row[1],
  sender: row[2],
  receiver: row[3],
  input_data: row[4],
  output_data: row[5],
  status: row[6] as TraceEventDTO['status']
}))

export const bugs: BugRecord[] = [
  { id: 'bug-001', title: '工具错误未返回统一 ErrorEnvelope', bug_type: 'tool_error_contract', severity: 'critical', status: 'Open', test_case: 'CONTRACT_001', evidence: 'google_search timeout 后缺少 retryable/error_code 字段' },
  { id: 'bug-002', title: '外部搜索超时后没有降级策略', bug_type: 'resilience', severity: 'high', status: 'Processing', test_case: 'TOOLERR_001', evidence: 'Researcher 直接输出不完整报告，未通知 ResearchManager' },
  { id: 'bug-003', title: '报告引用字段偶发缺失', bug_type: 'artifact_contract', severity: 'medium', status: 'Fixed', test_case: 'CONTRACT_002', evidence: '早期 artifact schema 校验发现 citations 为空' },
  { id: 'bug-004', title: '空输入路径缺少业务提示', bug_type: 'input_validation', severity: 'low', status: 'Closed', test_case: 'NEGATIVE_001', evidence: '没有进入人工输入，但提示信息不够明确' },
  { id: 'bug-005', title: '消息交接边 Director -> CheckingAgent 未覆盖', bug_type: 'coverage_gap', severity: 'medium', status: 'Reopen', test_case: 'BASELINE_002', evidence: 'Trace 中缺少直接复核边，需要补充测试模式' }
]

export const dashboard: DashboardSummary = {
  projects: 3,
  totalCases: testCases.length,
  latestPassRate: runRecord.pass_rate,
  openBugs: bugs.filter((item) => !['Closed', 'Fixed'].includes(item.status)).length,
  coverage,
  severity: {
    critical: 1,
    high: 1,
    medium: 2,
    low: 1
  },
  trend: [
    { date: '06-12', passRate: 0.61 },
    { date: '06-13', passRate: 0.66 },
    { date: '06-14', passRate: 0.69 },
    { date: '06-15', passRate: 0.73 },
    { date: '06-16', passRate: 0.71 },
    { date: '06-17', passRate: 0.76 },
    { date: '06-18', passRate: 0.78 }
  ]
}
