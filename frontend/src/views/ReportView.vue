<template>
  <div class="report-page">
    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>真实报告预览</h2>
          <p>直接读取 MASentinel 已生成的 report.html、dashboard.html 和 Markdown 报告。</p>
        </div>
        <div class="toolbar">
          <el-select v-model="selectedSystem" placeholder="选择 system_id" @change="loadReports">
            <el-option v-for="item in projects" :key="item.id" :label="item.id" :value="item.id" />
          </el-select>
          <el-button type="primary" :loading="loading" @click="loadReports">刷新报告</el-button>
        </div>
      </div>

      <div v-if="reports.length" class="report-links">
        <a v-for="item in reports" :key="item.name" :href="item.url" target="_blank" rel="noopener">
          {{ item.name }} <small>{{ item.type }} · {{ formatSize(item.size) }}</small>
        </a>
      </div>

      <el-tabs v-model="active">
        <el-tab-pane label="report.html" name="report_html">
          <iframe v-if="hasReport('report.html')" class="html-frame" :src="fileUrl('report.html')" />
          <el-empty v-else description="当前 system_id 没有 report.html" />
        </el-tab-pane>
        <el-tab-pane label="dashboard.html" name="dashboard_html">
          <iframe v-if="hasReport('dashboard.html')" class="html-frame" :src="fileUrl('dashboard.html')" />
          <el-empty v-else description="当前 system_id 没有 dashboard.html" />
        </el-tab-pane>
        <el-tab-pane label="report.md" name="report_md">
          <pre>{{ previews['report.md'] || '当前 system_id 没有 report.md' }}</pre>
        </el-tab-pane>
        <el-tab-pane label="故障报告" name="fault_md">
          <pre>{{ previews['故障报告.md'] || previews['fault_report.md'] || '当前 system_id 没有故障报告' }}</pre>
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

interface ProjectRow {
  id: string
}

interface ReportRow {
  name: string
  type: string
  size: number
  url: string
}

const loading = ref(false)
const projects = ref<ProjectRow[]>([])
const selectedSystem = ref('system1_iterative_coding')
const reports = ref<ReportRow[]>([])
const previews = ref<Record<string, string>>({})
const active = ref('report_html')

const loadProjects = async () => {
  projects.value = await fetch('/api/projects').then((res) => res.json())
  if (!projects.value.some((item) => item.id === selectedSystem.value) && projects.value[0]) {
    selectedSystem.value = projects.value[0].id
  }
}

const loadReports = async () => {
  if (!selectedSystem.value) return
  loading.value = true
  try {
    const data = await fetch(`/api/reports/${selectedSystem.value}`).then((res) => res.json())
    reports.value = data.reports || []
    previews.value = data.previews || {}
    ElMessage.success('已加载 MASentinel 真实报告')
  } finally {
    loading.value = false
  }
}

const hasReport = (name: string) => reports.value.some((item) => item.name === name)
const fileUrl = (name: string) => `/api/reports/${selectedSystem.value}/file/${encodeURIComponent(name)}`
const formatSize = (size: number) => `${(size / 1024).toFixed(1)} KB`

onMounted(async () => {
  await loadProjects()
  await loadReports()
})
</script>

<style scoped>
.panel {
  padding: 18px;
}

.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
}

.toolbar .el-select {
  width: 280px;
}

.report-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.report-links a {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  padding: 10px 12px;
  color: var(--blue);
  font-weight: 800;
}

.report-links small {
  color: var(--muted);
  font-weight: 500;
}

pre,
.html-frame {
  width: 100%;
  min-height: 620px;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: #ffffff;
  color: var(--text);
}

pre {
  padding: 18px;
  white-space: pre-wrap;
  overflow: auto;
}
</style>
