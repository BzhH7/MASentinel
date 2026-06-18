import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { BugRecord, DashboardSummary, Project, RunRecord, RunCase, TestCase, TraceEventDTO } from '@/types/domain'

interface AppState {
  loading: boolean
  dashboard: DashboardSummary | null
  projects: Project[]
  currentProjectId: string
  testCases: TestCase[]
  run: RunRecord | null
  visibleRunCases: RunCase[]
  trace: TraceEventDTO[]
  visibleTrace: TraceEventDTO[]
  bugs: BugRecord[]
}

export const useAppStore = defineStore('app', {
  state: (): AppState => ({
    loading: false,
    dashboard: null,
    projects: [],
    currentProjectId: 'p-autogen-001',
    testCases: [],
    run: null,
    visibleRunCases: [],
    trace: [],
    visibleTrace: [],
    bugs: []
  }),
  getters: {
    currentProject(state) {
      return state.projects.find((item) => item.id === state.currentProjectId) ?? state.projects[0]
    }
  },
  actions: {
    async bootstrap() {
      this.loading = true
      const [dashboard, projects, cases, run, trace, bugs] = await Promise.all([
        api.dashboard(),
        api.listProjects(),
        api.listTestCases(this.currentProjectId),
        api.getRun('run-20260618-001'),
        api.getTrace('run-20260618-001'),
        api.listBugs()
      ])
      this.dashboard = dashboard
      this.projects = projects
      this.testCases = cases
      this.run = run
      this.visibleRunCases = run.cases
      this.trace = trace
      this.visibleTrace = trace
      this.bugs = bugs
      this.loading = false
    },
    async analyzeProject(id: string) {
      return api.analyzeProject(id)
    },
    async saveProject(project: Project) {
      const saved = await api.saveProject(project)
      const index = this.projects.findIndex((item) => item.id === saved.id)
      if (index >= 0) this.projects[index] = saved
      else this.projects.push(saved)
      return saved
    },
    async generateTestCases(projectId: string) {
      this.testCases = await api.generateTestCases(projectId)
    },
    async saveTestCase(item: TestCase) {
      const saved = await api.saveTestCase(item)
      const index = this.testCases.findIndex((caseItem) => caseItem.id === saved.id)
      if (index >= 0) this.testCases[index] = saved
      else this.testCases.push(saved)
      return saved
    },
    async startRun(projectId: string) {
      const run = await api.createRun(projectId)
      this.run = { ...run, status: 'running', pass_rate: 0 }
      this.visibleRunCases = run.cases.map((item: RunCase) => ({ ...item, status: 'pending' }))
      this.visibleTrace = []
      for (let i = 0; i < this.visibleRunCases.length; i += 1) {
        this.visibleRunCases[i].status = 'running'
        await wait(520)
        this.visibleRunCases[i].status = run.cases[i].status
        const end = Math.min(this.trace.length, Math.ceil(((i + 1) / this.visibleRunCases.length) * this.trace.length))
        this.visibleTrace = this.trace.slice(0, end)
      }
      if (this.run) {
        this.run.status = 'completed'
        this.run.pass_rate = run.pass_rate
      }
    },
    async loadBugs() {
      this.bugs = await api.listBugs()
    },
    async moveBug(id: string, status: BugRecord['status']) {
      const updated = await api.updateBug(id, { status })
      const item = this.bugs.find((bug) => bug.id === id)
      if (item && updated) item.status = status
    },
    async exportReport() {
      return api.exportReport(this.run?.id ?? 'run-20260618-001')
    }
  }
})

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
