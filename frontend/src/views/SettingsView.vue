<template>
  <div class="settings-page">
    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>设置 / 真实项目</h2>
          <p>管理后端、真实项目克隆位置、配置生成和分析入口。</p>
        </div>
      </div>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="Backend Root">{{ settings?.backend_root }}</el-descriptions-item>
        <el-descriptions-item label="Real Targets">{{ settings?.real_targets_root }}</el-descriptions-item>
        <el-descriptions-item label="Configs">{{ settings?.configs_root }}</el-descriptions-item>
        <el-descriptions-item label="Outputs">{{ settings?.outputs_root }}</el-descriptions-item>
        <el-descriptions-item label="Python">{{ settings?.python }}</el-descriptions-item>
        <el-descriptions-item label="Mock Mode">{{ settings?.mock_mode }}</el-descriptions-item>
      </el-descriptions>
    </section>

    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>真实项目池</h2>
          <p>已下载 / 待下载项目可以在这里一键克隆并生成 MASentinel 配置。</p>
        </div>
        <el-button type="primary" :loading="loading" @click="refresh">刷新</el-button>
      </div>
      <el-table :data="projects">
        <el-table-column prop="name" label="name" min-width="220" />
        <el-table-column prop="framework" label="framework" width="180" />
        <el-table-column label="local_path" min-width="260">
          <template #default="{ row }">
            <span :class="{ ready: row.exists }">{{ row.local_path }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="240">
          <template #default="{ row }">
            <el-tag :type="row.exists ? 'success' : 'warning'" effect="dark">{{ row.exists ? '已下载' : '未下载' }}</el-tag>
            <el-tag :type="row.configured ? 'success' : 'info'" effect="dark" class="tag-gap">{{ row.configured ? '已配置' : '未配置' }}</el-tag>
            <el-tag :type="row.analyzed ? 'success' : 'danger'" effect="dark" class="tag-gap">{{ row.analyzed ? '已分析' : '未分析' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300">
          <template #default="{ row }">
            <el-button size="small" @click="cloneProject(row)" :loading="jobId === row.id && jobAction === 'clone'">克隆</el-button>
            <el-button size="small" @click="configureProject(row)">生成配置</el-button>
            <el-button size="small" type="primary" @click="analyzeProject(row)" :loading="jobId === row.id && jobAction === 'analyze'">分析</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const settings = ref<any>(null)
const projects = ref<any[]>([])
const loading = ref(false)
const jobId = ref('')
const jobAction = ref('')

const refresh = async () => {
  loading.value = true
  settings.value = await fetch('/api/settings').then((res) => res.json()).catch(() => null)
  projects.value = await fetch('/api/real-projects').then((res) => res.json()).catch(() => [])
  loading.value = false
}

const cloneProject = async (row: any) => {
  jobId.value = row.id
  jobAction.value = 'clone'
  await fetch('/api/real-projects/clone', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: row.id })
  })
  ElMessage.success('已提交克隆任务')
  await refresh()
}

const configureProject = async (row: any) => {
  const payload = row.id === 'real_crewai_examples'
    ? { id: row.id, subpath: 'crews/markdown_validator' }
    : { id: row.id }
  await fetch('/api/real-projects/configure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  ElMessage.success('已生成配置')
  await refresh()
}

const analyzeProject = async (row: any) => {
  jobId.value = row.id
  jobAction.value = 'analyze'
  await fetch(`/api/real-projects/${row.id}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_path: row.config_path })
  })
  ElMessage.success('已提交分析任务')
  await refresh()
}

refresh()
</script>

<style scoped>
.settings-page {
  display: grid;
  gap: 16px;
}

.panel {
  padding: 18px;
}

.ready {
  color: var(--green);
}

.tag-gap {
  margin-left: 6px;
}
</style>
