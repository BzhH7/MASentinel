<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-logo">MX</div>
        <div>
          <strong>MASentinel-X</strong>
          <span>Agent App QA Platform</span>
        </div>
      </div>
      <nav>
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="mode-card">
        <span class="status-dot status-running"></span>
        {{ modeTitle }}
        <small>{{ modeDescription }}</small>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div>
          <span class="kicker">面向智能体应用的自动化测试与缺陷管理平台</span>
          <h1>{{ routeTitle }}</h1>
        </div>
        <div class="top-actions">
          <el-tag type="success" effect="dark">MASCov 84%</el-tag>
          <el-button type="primary" @click="$router.push('/runs')">启动演示运行</el-button>
        </div>
      </header>
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { DataAnalysis, FolderOpened, Histogram, Management, Tickets, Timer, Warning } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const route = useRoute()

onMounted(() => {
  if (!store.dashboard) store.bootstrap()
})

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: DataAnalysis },
  { path: '/projects', label: '项目管理', icon: FolderOpened },
  { path: '/testcases', label: '测试用例', icon: Tickets },
  { path: '/runs', label: '测试运行', icon: Timer },
  { path: '/trace', label: 'Trace', icon: Histogram },
  { path: '/bugs', label: '缺陷管理', icon: Warning },
  { path: '/reports', label: '报告', icon: Management },
  { path: '/settings', label: '设置', icon: Management }
]

const titleMap: Record<string, string> = {
  Dashboard: 'Dashboard',
  Projects: '项目管理',
  TestCases: '测试用例',
  Runs: '测试运行',
  Trace: 'Trace 证据链',
  Bugs: '缺陷管理',
  Reports: '报告预览',
  Settings: '设置'
}

const routeTitle = computed(() => titleMap[String(route.name)] ?? 'MASentinel-X')
const useMock = import.meta.env.VITE_USE_MOCK !== 'false'
const modeTitle = computed(() => (useMock ? 'Mock 演示模式' : 'MASentinel 后端模式'))
const modeDescription = computed(() =>
  useMock ? '无需后端，可完整跑通流程' : '已连接 MASentinel Python API'
)
</script>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  min-height: 100vh;
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 22px 18px;
  border-right: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(20px);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 30px;
}

.brand-logo {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, #2563eb, #06b6d4);
  color: #ffffff;
  font-weight: 950;
  box-shadow: 0 14px 32px rgba(37, 99, 235, 0.28);
}

.brand strong,
.brand span {
  display: block;
}

.brand strong {
  font-size: 18px;
}

.brand span,
.mode-card small,
.kicker {
  color: var(--muted);
}

nav {
  display: grid;
  gap: 8px;
}

nav a {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 0 12px;
  border-radius: 12px;
  color: #475569;
  font-weight: 750;
}

nav a.router-link-active,
nav a:hover {
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.12), rgba(8, 145, 178, 0.08));
  color: var(--blue);
  transform: translateX(4px);
}

.mode-card {
  position: absolute;
  left: 18px;
  right: 18px;
  bottom: 22px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: rgba(241, 247, 255, 0.86);
  color: var(--text);
  font-weight: 800;
}

.mode-card small {
  display: block;
  margin-top: 6px;
  font-weight: 500;
}

.main {
  min-width: 0;
  padding: 24px;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
  margin: -24px -24px 24px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border);
  background: rgba(248, 251, 255, 0.82);
  backdrop-filter: blur(18px);
}

.topbar h1 {
  margin: 4px 0 0;
  font-size: 28px;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

@media (max-width: 980px) {
  .shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
    height: auto;
  }

  .mode-card {
    position: static;
    margin-top: 16px;
  }
}
</style>
