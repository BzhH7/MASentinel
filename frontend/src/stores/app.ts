import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { BugRecord, CoverageMetrics, DashboardSummary, Project, RunCase, RunJob, RunRecord, TestCase, TraceEventDTO } from '@/types/domain'

const DEFAULT_SYSTEM_ID = 'system1_iterative_coding'

interface AppState {
  loading: boolean
  dashboard: DashboardSummary | null
  projects: Project[]
  currentProjectId: string
  selectedCaseId: string
  testCases: TestCase[]
  run: RunRecord | null
  visibleRunCases: RunCase[]
  trace: TraceEventDTO[]
  visibleTrace: TraceEventDTO[]
  bugs: BugRecord[]
  coverage: CoverageMetrics | null
  currentJob: RunJob | null
  runtimeValidation: { system_id: string; runnable: boolean; errors: string[] } | null
}

export const useAppStore = defineStore('app', {
  state: (): AppState => ({
    loading: false,
    dashboard: null,
    projects: [],
    currentProjectId: DEFAULT_SYSTEM_ID,
    selectedCaseId: '',
    testCases: [],
    run: null,
    visibleRunCases: [],
    trace: [],
    visibleTrace: [],
    bugs: [],
    coverage: null,
    currentJob: null,
    runtimeValidation: null
  }),
  getters: {
    currentProject(state) {
      return state.projects.find((item) => item.id === state.currentProjectId) ?? state.projects[0]
    }
  },
  actions: {
    async bootstrap() {
      this.loading = true
      try {
        this.projects = await api.listProjects()
        if (!this.projects.some((item) => item.id === this.currentProjectId) && this.projects[0]) {
          this.currentProjectId = this.projects[0].id
        }
        await this.loadProjectData(this.currentProjectId)
      } finally {
        this.loading = false
      }
    },
    async loadProjectData(projectId: string) {
      this.currentProjectId = projectId
      const [project, cases, run, results, coverage, bugs] = await Promise.all([
        api.getProject(projectId),
        api.listTestCases(projectId),
        api.getRun(projectId),
        api.getRunResults(projectId),
        api.getCoverage(projectId),
        api.listBugs(projectId)
      ])
      const index = this.projects.findIndex((item) => item.id === projectId)
      if (index >= 0) this.projects[index] = project
      else this.projects.push(project)
      this.testCases = cases
      this.run = { ...run, cases: results }
      this.visibleRunCases = results
      this.coverage = coverage
      this.bugs = bugs
      this.selectedCaseId = this.selectedCaseId && results.some((item) => item.case_id === this.selectedCaseId)
        ? this.selectedCaseId
        : results[0]?.case_id || cases[0]?.case_id || ''
      this.dashboard = buildDashboard(this.projects, cases, run, coverage, bugs)
      this.trace = []
      this.visibleTrace = []
    },
    async loadTrace(caseId?: string) {
      const targetCaseId = caseId || this.selectedCaseId
      if (!this.currentProjectId || !targetCaseId) {
        this.trace = []
        this.visibleTrace = []
        return
      }
      this.selectedCaseId = targetCaseId
      this.trace = await api.getTrace(this.currentProjectId, targetCaseId)
      this.visibleTrace = this.trace
    },
    async loadBugs(projectId?: string) {
      const targetProjectId = projectId || this.currentProjectId
      this.bugs = await api.listBugs(targetProjectId)
      if (this.dashboard && this.coverage && this.run) {
        this.dashboard = buildDashboard(this.projects, this.testCases, this.run, this.coverage, this.bugs)
      }
    },
    async validateRuntime(projectId?: string) {
      const targetProjectId = projectId || this.currentProjectId
      this.runtimeValidation = await api.validateRuntime(targetProjectId)
      return this.runtimeValidation
    },
    async moveBug(id: string, status: BugRecord['status']) {
      const updated = await api.updateBug(id, { status })
      const item = this.bugs.find((bug) => bug.id === id)
      if (item) Object.assign(item, updated || { status })
      if (this.dashboard && this.coverage && this.run) {
        this.dashboard = buildDashboard(this.projects, this.testCases, this.run, this.coverage, this.bugs)
      }
    },
    async startRealtimeRun(projectId?: string) {
      const targetProjectId = projectId || this.currentProjectId
      const job = await api.createRun(targetProjectId)
      this.currentJob = job
      this.run = this.run ? { ...this.run, status: 'running' } : null
      while (this.currentJob && ['pending', 'running'].includes(this.currentJob.status)) {
        await wait(1600)
        this.currentJob = await api.getJob(this.currentJob.id)
      }
      if (this.currentJob?.status === 'succeeded') {
        await this.loadProjectData(targetProjectId)
      } else if (this.run) {
        this.run.status = 'completed'
      }
      return this.currentJob
    },
    async showCompletedRun() {
      if (!this.run) return
      this.run = { ...this.run, status: 'running', pass_rate: 0 }
      this.visibleRunCases = this.visibleRunCases.map((item) => ({ ...item, status: 'pending' }))
      this.visibleTrace = []
      for (let i = 0; i < this.visibleRunCases.length; i += 1) {
        this.visibleRunCases[i].status = 'running'
        await wait(260)
        this.visibleRunCases[i].status = this.run.cases[i]?.status ?? 'passed'
      }
      this.run.status = 'completed'
      this.run.pass_rate = this.run.cases.length
        ? this.run.cases.filter((item) => item.status === 'passed').length / this.run.cases.length
        : 0
    }
  }
})

const buildDashboard = (
  projects: Project[],
  cases: TestCase[],
  run: RunRecord,
  coverage: CoverageMetrics,
  bugs: BugRecord[]
): DashboardSummary => {
  const severity = { critical: 0, high: 0, medium: 0, low: 0 }
  bugs.forEach((bug) => {
    severity[bug.severity] += 1
  })
  const openBugs = bugs.filter((item) => !['Closed', 'Fixed'].includes(item.status)).length
  const passRate = Number(run.pass_rate || 0)
  return {
    projects: projects.length,
    totalCases: cases.length || run.cases.length,
    latestPassRate: passRate,
    openBugs,
    coverage,
    severity,
    trend: [
      { date: '本次-4', passRate: Math.max(0, passRate - 0.16) },
      { date: '本次-3', passRate: Math.max(0, passRate - 0.1) },
      { date: '本次-2', passRate: Math.max(0, passRate - 0.05) },
      { date: '本次-1', passRate: Math.max(0, passRate - 0.02) },
      { date: '本次', passRate }
    ]
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
