import axios from 'axios'
import type { BugRecord, CoverageMetrics, Project, RunCase, RunJob, RunRecord, TestCase, TraceEventDTO } from '@/types/domain'
import { bugs, coverage, projects, runRecord, testCases, traceEvents } from '@/mock/data'

export const useMock = import.meta.env.VITE_USE_MOCK === 'true'
const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE || '/api', timeout: 12000 })

const delay = <T>(value: T, ms = 360) =>
  new Promise<T>((resolve) => window.setTimeout(() => resolve(structuredClone(value)), ms))

const textOf = (value: unknown): string => {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

const firstString = (...values: unknown[]) => values.find((value) => typeof value === 'string' && value) as string | undefined

const normalizeSeverity = (value: unknown): BugRecord['severity'] => {
  const severity = String(value || 'medium').toLowerCase()
  if (severity === 'critical' || severity === 'high' || severity === 'medium' || severity === 'low') return severity
  return 'medium'
}

const normalizeProject = (row: any): Project => {
  const id = String(row.id || row.system_id || '')
  return {
    id,
    name: String(row.name || row.system_id || row.id || id),
    adapter_type: String(row.adapter_type || 'autogen'),
    status: String(row.status || 'analyzed'),
    created_at: String(row.created_at || row.generated_at || '已生成'),
    config: {
      adapter_type: String(row.adapter_type || 'autogen'),
      project_path: String(row.root_path || ''),
      command_template: String(row.entrypoint || ''),
      http_url: '',
      timeout: Number(row.timeout || 120),
      model_config: '',
      oracle_config: ''
    }
  }
}

const normalizeProfile = (profile: any) => ({
  agents: (profile?.agents || []).map((item: any) => firstString(item?.name, item?.var_name, item) || 'unknown_agent'),
  tools: (profile?.tools || []).map((item: any) => firstString(item?.name, item?.function_name, item) || 'unknown_tool'),
  requirements: (profile?.requirements || []).map((item: any) => {
    if (typeof item === 'string') return item
    const prefix = item?.id ? `${item.id}: ` : ''
    return `${prefix}${item?.description || item?.name || JSON.stringify(item)}`
  }),
  message_edges: Array.isArray(profile?.message_edges) ? profile.message_edges : []
})

const normalizeTestCase = (row: any): TestCase => ({
  id: String(row.id || row.case_id),
  project_id: String(row.project_id || row.system_id || ''),
  case_id: String(row.case_id || ''),
  case_type: String(row.case_type || 'unknown'),
  objective: String(row.objective || ''),
  oracle_type: row.oracle?.output_contract ? 'contract_oracle' : 'rule_oracle',
  enabled: row.enabled !== false
})

const normalizeRun = (row: any): RunRecord => ({
  id: String(row.run_id || row.system_id || ''),
  project_id: String(row.system_id || row.run_id || ''),
  name: String(row.name || `${row.run_id || row.system_id || 'MASentinel'} completed run`),
  status: 'completed',
  started_at: String(row.started_at || '已完成'),
  pass_rate: Number(row.pass_rate || 0),
  cases: []
})

const normalizeRunCase = (row: any): RunCase => {
  const failures = Array.isArray(row.failures) ? row.failures : []
  const passed = row.passed === true
  return {
    case_id: String(row.case_id || ''),
    objective: String(row.objective || ''),
    status: passed ? 'passed' : 'failed',
    stdout: '',
    stderr: '',
    error_summary: failures.map((item: any) => item?.message || item?.code || textOf(item)).filter(Boolean).join('\n'),
    oracle: {
      rule_oracle: passed ? 'passed' : 'failed',
      contract_oracle: passed ? 'passed' : 'failed',
      summary: passed ? 'Oracle 判定通过' : failures.length ? failures.map((item: any) => item?.code || item?.message || textOf(item)).join('；') : 'Oracle 判定失败'
    }
  }
}

const normalizeTraceStatus = (row: any): TraceEventDTO['status'] => {
  if (row?.error_type || row?.error_message) return 'failed'
  const type = String(row?.type || '').toLowerCase()
  if (type.includes('error') || type.includes('fail')) return 'failed'
  return 'passed'
}

const normalizeTraceType = (row: any): TraceEventDTO['event_type'] => {
  const type = String(row?.type || '').toLowerCase()
  if (type.includes('tool_call')) return 'tool_call'
  if (type.includes('tool_result')) return 'tool_result'
  if (type.includes('oracle')) return 'oracle_check'
  if (type === 'message') return 'agent_message'
  return 'system'
}

const normalizeTimestamp = (value: unknown) => {
  if (typeof value === 'number') return new Date(value * 1000).toISOString()
  if (typeof value === 'string') return value
  return new Date().toISOString()
}

const normalizeTraceEvent = (row: any, index: number): TraceEventDTO => ({
  id: String(row.id || `${row.type || 'event'}-${index + 1}`),
  timestamp: normalizeTimestamp(row.timestamp),
  event_type: normalizeTraceType(row),
  event_name: String(row.tool || row.type || `event-${index + 1}`),
  sender: String(row.sender || row.tool || 'MASentinel'),
  receiver: String(row.receiver || 'MASentinel'),
  input_data: textOf(row.content || row.arguments || row.metadata),
  output_data: textOf(row.result_preview || row.error_message || ''),
  status: normalizeTraceStatus(row)
})

const normalizeCoverage = (row: any): CoverageMetrics => ({
  AgentCov: Number(row.agent_coverage ?? row.AgentCov ?? 0),
  ToolCov: Number(row.tool_coverage ?? row.ToolCov ?? 0),
  EdgeCov: Number(row.message_edge_coverage ?? row.EdgeCov ?? 0),
  ReqVerifiedCov: Number(row.req_verified_coverage ?? row.requirement_coverage ?? row.ReqVerifiedCov ?? 0),
  ContractCov: Number(row.contract_coverage ?? row.ContractCov ?? 0),
  TraceCompleteness: Number(row.trace_completeness ?? row.TraceCompleteness ?? 0),
  MASCov: Number(row.mascov ?? row.MASCov ?? averageCoverage(row))
})

const averageCoverage = (row: any) => {
  const values = [
    row.agent_coverage,
    row.tool_coverage,
    row.message_edge_coverage,
    row.req_verified_coverage ?? row.requirement_coverage,
    row.contract_coverage,
    row.trace_completeness
  ].map(Number).filter((value) => Number.isFinite(value))
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
}

const normalizeBug = (row: any): BugRecord => ({
  id: String(row.id || row.fault_id),
  title: String(row.title || row.summary || '未命名缺陷'),
  bug_type: String(row.bug_type || row.fault_type || ''),
  severity: normalizeSeverity(row.severity),
  status: row.status || 'Open',
  test_case: String(row.test_case || row.case_id || ''),
  evidence: Array.isArray(row.evidence) ? row.evidence.join('\n') : textOf(row.evidence)
})

export interface ReportIndex {
  system_id: string
  reports: Array<{ name: string; type: string; size: number; url: string }>
  previews: Record<string, string>
}

export const api = {
  async listProjects(): Promise<Project[]> {
    if (useMock) return delay(projects)
    const data = (await http.get('/projects')).data
    return data.map(normalizeProject)
  },
  async getProject(systemId: string): Promise<Project> {
    if (useMock) return delay(projects.find((item) => item.id === systemId) ?? projects[0])
    const profile = (await http.get(`/projects/${systemId}`)).data
    return { ...normalizeProject(profile), id: systemId, name: profile.system_id || systemId, profile: normalizeProfile(profile) }
  },
  async listTestCases(projectId: string): Promise<TestCase[]> {
    if (useMock) return delay(testCases.filter((item) => item.project_id === projectId))
    const data = (await http.get(`/projects/${projectId}/testcases`)).data
    return data.map(normalizeTestCase)
  },
  async getRun(runId: string): Promise<RunRecord> {
    if (useMock) return delay(runRecord)
    return normalizeRun((await http.get(`/runs/${runId}`)).data)
  },
  async createRun(systemId: string): Promise<RunJob> {
    if (useMock) {
      return delay({
        id: `job-${Date.now()}`,
        system_id: systemId,
        config_path: 'mock',
        status: 'succeeded',
        progress: 100,
        logs: ['mock run completed'],
        created_at: Date.now() / 1000
      } as RunJob)
    }
    return (await http.post('/runs', { system_id: systemId, clean_output: false, no_human: true })).data
  },
  async getJob(jobId: string): Promise<RunJob> {
    return (await http.get(`/jobs/${jobId}`)).data
  },
  async getRunResults(runId: string): Promise<RunCase[]> {
    if (useMock) return delay(runRecord.cases)
    const data = (await http.get(`/runs/${runId}/results`)).data
    return data.map(normalizeRunCase)
  },
  async getTrace(runId: string, caseId: string): Promise<TraceEventDTO[]> {
    if (useMock) return delay(traceEvents)
    const data = (await http.get(`/runs/${runId}/trace`, { params: { case_id: caseId } })).data
    return data.map(normalizeTraceEvent)
  },
  async getCoverage(runId: string): Promise<CoverageMetrics> {
    if (useMock) return delay(coverage)
    return normalizeCoverage((await http.get(`/runs/${runId}/coverage`)).data)
  },
  async listBugs(projectId: string): Promise<BugRecord[]> {
    if (useMock) return delay(bugs)
    const data = (await http.get('/bugs', { params: { project_id: projectId } })).data
    return data.map(normalizeBug)
  },
  async updateBug(id: string, patch: Partial<BugRecord>) {
    if (useMock) {
      const item = bugs.find((bug) => bug.id === id)
      if (item) Object.assign(item, patch)
      return delay(item, 240)
    }
    return (await http.put(`/bugs/${id}`, patch)).data
  },
  async listReports(systemId: string): Promise<ReportIndex> {
    return (await http.get(`/reports/${systemId}`)).data
  },
  reportFileUrl(systemId: string, filename: string) {
    const base = import.meta.env.VITE_API_BASE || '/api'
    return `${base}/reports/${systemId}/file/${encodeURIComponent(filename)}`
  }
}

export type ApiRun = RunRecord
