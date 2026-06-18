export type AdapterType = 'autogen' | 'generic_cli' | 'generic_http'
export type ProjectStatus = 'analyzed' | 'draft' | 'running' | 'error'
export type CaseType = 'baseline' | 'contract' | 'negative' | 'metamorphic' | 'tool_error'
export type RunCaseStatus = 'pending' | 'running' | 'passed' | 'failed'
export type TraceStatus = 'pending' | 'running' | 'passed' | 'failed'
export type BugStatus = 'Open' | 'Processing' | 'Fixed' | 'Closed' | 'Reopen'
export type Severity = 'critical' | 'high' | 'medium' | 'low'

export interface ProjectConfig {
  adapter_type: AdapterType
  project_path: string
  command_template: string
  http_url: string
  timeout: number
  model_config: string
  oracle_config: string
}

export interface Project {
  id: string
  name: string
  adapter_type: AdapterType
  status: ProjectStatus
  created_at: string
  config: ProjectConfig
  profile?: SystemProfile
}

export interface SystemProfile {
  agents: string[]
  tools: string[]
  requirements: string[]
  message_edges: Array<[string, string]>
}

export interface TestCase {
  id: string
  project_id: string
  case_id: string
  case_type: CaseType
  objective: string
  oracle_type: 'rule_oracle' | 'contract_oracle' | 'llm_judge' | 'metamorphic_oracle'
  enabled: boolean
}

export interface RunCase {
  case_id: string
  objective: string
  status: RunCaseStatus
  stdout?: string
  stderr?: string
  error_summary?: string
  oracle?: OracleResult
}

export interface RunRecord {
  id: string
  project_id: string
  name: string
  status: 'idle' | 'running' | 'completed'
  started_at: string
  pass_rate: number
  cases: RunCase[]
}

export interface OracleResult {
  rule_oracle: 'passed' | 'failed'
  contract_oracle: 'passed' | 'failed'
  summary: string
}

export interface TraceEventDTO {
  id: string
  timestamp: string
  event_type: 'agent_message' | 'tool_call' | 'tool_result' | 'oracle_check' | 'system'
  event_name: string
  sender: string
  receiver: string
  input_data: string
  output_data: string
  status: TraceStatus
}

export interface CoverageMetrics {
  AgentCov: number
  ToolCov: number
  EdgeCov: number
  ReqVerifiedCov: number
  ContractCov: number
  TraceCompleteness: number
  MASCov: number
}

export interface BugRecord {
  id: string
  title: string
  bug_type: string
  severity: Severity
  status: BugStatus
  test_case: string
  evidence: string
}

export interface DashboardSummary {
  projects: number
  totalCases: number
  latestPassRate: number
  openBugs: number
  coverage: CoverageMetrics
  severity: Record<Severity, number>
  trend: Array<{ date: string; passRate: number }>
}
