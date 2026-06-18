<template>
  <div class="settings-page">
    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>设置 / 接口状态</h2>
          <p>当前前端默认连接 MASentinel FastAPI，可读取 outputs 真实数据，也可启动 MASentinel 后端实时运行任务。</p>
        </div>
        <el-tag :type="useMock ? 'warning' : 'success'" effect="dark">
          {{ useMock ? 'Mock Mode' : 'Real API Mode' }}
        </el-tag>
      </div>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="API Base">{{ apiBase }}</el-descriptions-item>
        <el-descriptions-item label="默认 system_id">system1_iterative_coding</el-descriptions-item>
        <el-descriptions-item label="Mock 开关">VITE_USE_MOCK=true 时才启用</el-descriptions-item>
        <el-descriptions-item label="后端启动">uvicorn backend.main:app --reload --port 8000</el-descriptions-item>
      </el-descriptions>
    </section>

    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>已接入真实接口</h2>
          <p>这些操作会直接请求 backend/main.py 中已经存在的接口。</p>
        </div>
      </div>
      <el-table :data="realEndpoints">
        <el-table-column prop="method" label="method" width="90" />
        <el-table-column prop="path" label="path" min-width="320" />
        <el-table-column prop="usage" label="前端用途" min-width="260" />
      </el-table>
    </section>

    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>占位操作</h2>
          <p>这些按钮在 UI 中保留，但当前后端没有对应实时执行接口，点击只会给出明确提示。</p>
        </div>
      </div>
      <div class="placeholder-grid">
        <el-tag v-for="item in placeholders" :key="item" type="info" effect="plain">{{ item }}</el-tag>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useMock } from '@/api/client'

const apiBase = import.meta.env.VITE_API_BASE || '/api'

const realEndpoints = [
  { method: 'GET', path: '/api/projects', usage: '项目列表、Dashboard 项目数' },
  { method: 'GET', path: '/api/projects/{system_id}', usage: 'SystemProfile 摘要' },
  { method: 'GET', path: '/api/projects/{system_id}/testcases', usage: '测试用例列表、Dashboard 用例数' },
  { method: 'POST', path: '/api/runs', usage: '启动 MASentinel 实时运行任务' },
  { method: 'GET', path: '/api/jobs/{job_id}', usage: '轮询后端任务进度和日志' },
  { method: 'GET', path: '/api/runs/{run_id}', usage: '运行总览和通过率' },
  { method: 'GET', path: '/api/runs/{run_id}/results', usage: '用例结果队列' },
  { method: 'GET', path: '/api/runs/{run_id}/trace?case_id=xxx', usage: '单用例 Trace 时间线' },
  { method: 'GET', path: '/api/runs/{run_id}/coverage', usage: '覆盖率雷达图' },
  { method: 'GET', path: '/api/bugs?project_id=xxx', usage: '缺陷看板' },
  { method: 'PUT', path: '/api/bugs/{bug_id}', usage: '缺陷状态 / 严重程度内存更新' },
  { method: 'GET', path: '/api/reports/{system_id}', usage: '报告索引和 Markdown 预览' },
  { method: 'GET', path: '/api/reports/{system_id}/file/{filename}', usage: 'HTML 报告 iframe 预览' }
]

const placeholders = ['新建项目', '保存项目', '分析项目', '自动生成用例', '保存测试用例', '导出报告']
</script>

<style scoped>
.settings-page {
  display: grid;
  gap: 16px;
}

.panel {
  padding: 18px;
}

.placeholder-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
</style>
