import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import DashboardView from '@/views/DashboardView.vue'
import ProjectView from '@/views/ProjectView.vue'
import TestCaseView from '@/views/TestCaseView.vue'
import RunView from '@/views/RunView.vue'
import TraceView from '@/views/TraceView.vue'
import BugView from '@/views/BugView.vue'
import ReportView from '@/views/ReportView.vue'
import SettingsView from '@/views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'Dashboard', component: DashboardView },
        { path: 'projects', name: 'Projects', component: ProjectView },
        { path: 'testcases', name: 'TestCases', component: TestCaseView },
        { path: 'runs', name: 'Runs', component: RunView },
        { path: 'trace', name: 'Trace', component: TraceView },
        { path: 'bugs', name: 'Bugs', component: BugView },
        { path: 'reports', name: 'Reports', component: ReportView },
        { path: 'settings', name: 'Settings', component: SettingsView }
      ]
    }
  ]
})

export default router
