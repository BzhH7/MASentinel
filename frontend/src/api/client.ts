import axios from 'axios'
import type { BugRecord, Project, RunRecord, TestCase } from '@/types/domain'
import { bugs, dashboard, projects, runRecord, testCases, traceEvents, coverage } from '@/mock/data'

const useMock = import.meta.env.VITE_USE_MOCK !== 'false'
const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE || '/api', timeout: 12000 })

const delay = <T>(value: T, ms = 520) => new Promise<T>((resolve) => window.setTimeout(() => resolve(structuredClone(value)), ms))

export const api = {
  async dashboard() {
    if (useMock) return delay(dashboard)
    return (await http.get('/dashboard')).data
  },
  async listProjects() {
    if (useMock) return delay(projects)
    return (await http.get('/projects')).data
  },
  async saveProject(project: Project) {
    if (useMock) {
      const index = projects.findIndex((item) => item.id === project.id)
      if (index >= 0) projects[index] = project
      else projects.push(project)
      return delay(project, 360)
    }
    return (await http.post('/projects', project)).data
  },
  async analyzeProject(id: string) {
    if (useMock) {
      const project = projects.find((item) => item.id === id) ?? projects[0]
      project.status = 'analyzed'
      return delay(project.profile, 900)
    }
    return (await http.post(`/projects/${id}/analyze`)).data
  },
  async listTestCases(projectId: string) {
    if (useMock) return delay(testCases.filter((item) => item.project_id === projectId))
    return (await http.get(`/projects/${projectId}/testcases`)).data
  },
  async generateTestCases(projectId: string) {
    if (useMock) return delay(testCases.filter((item) => item.project_id === projectId), 1800)
    return (await http.post(`/projects/${projectId}/testcases/generate`)).data
  },
  async saveTestCase(item: TestCase) {
    if (useMock) {
      const index = testCases.findIndex((caseItem) => caseItem.id === item.id)
      if (index >= 0) testCases[index] = item
      else testCases.push(item)
      return delay(item, 300)
    }
    return item.id ? (await http.put(`/testcases/${item.id}`, item)).data : (await http.post('/testcases', item)).data
  },
  async createRun(projectId: string) {
    if (useMock) {
      runRecord.project_id = projectId
      return delay(runRecord, 500)
    }
    return (await http.post('/runs', { project_id: projectId })).data
  },
  async getRun(id: string) {
    if (useMock) return delay(runRecord)
    return (await http.get(`/runs/${id}`)).data
  },
  async getRunResults(id: string) {
    if (useMock) return delay(runRecord.cases)
    return (await http.get(`/runs/${id}/results`)).data
  },
  async getTrace(id: string) {
    if (useMock) return delay(traceEvents)
    return (await http.get(`/runs/${id}/trace`)).data
  },
  async getCoverage(id: string) {
    if (useMock) return delay(coverage)
    return (await http.get(`/runs/${id}/coverage`)).data
  },
  async listBugs() {
    if (useMock) return delay(bugs)
    return (await http.get('/bugs')).data
  },
  async updateBug(id: string, patch: Partial<BugRecord>) {
    if (useMock) {
      const item = bugs.find((bug) => bug.id === id)
      if (item) Object.assign(item, patch)
      return delay(item, 240)
    }
    return (await http.put(`/bugs/${id}`, patch)).data
  },
  async exportReport(runId: string) {
    if (useMock) {
      return delay({
        run_id: runId,
        markdown: '# MASentinel-X 测试报告\n\n本次运行通过率 78%，发现 2 个关键缺陷，MASCov 达到 84%。',
        html: '<h1>MASentinel-X 测试报告</h1><p>本次运行通过率 <strong>78%</strong>，发现 2 个关键缺陷。</p>',
        dashboard: '覆盖率雷达、Trace 证据链和缺陷看板已生成。'
      })
    }
    return (await http.post(`/reports/${runId}/export`)).data
  }
}

export type ApiRun = RunRecord
