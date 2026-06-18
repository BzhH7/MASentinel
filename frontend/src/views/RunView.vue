<template>
  <div class="run-page">
    <section class="run-hero glass-card">
      <div>
        <p class="eyebrow">Live Semantic Test Run</p>
        <h1>实时执行智能体测试用例</h1>
        <p>点击启动后，用例会从 pending 逐条进入 running，并产生 Agent 消息、工具调用和 Oracle 判定 Trace。</p>
      </div>
      <div class="run-actions">
        <el-button type="primary" size="large" :loading="isRunning" @click="startRun">
          {{ isRunning ? '运行中...' : '创建运行任务' }}
        </el-button>
        <div class="pass-ring">
          <strong>{{ passRate }}</strong>
          <span>当前通过率</span>
        </div>
      </div>
    </section>

    <section class="run-grid">
      <div class="glass-card case-panel">
        <div class="section-heading">
          <div>
            <h2>用例执行队列</h2>
            <p>状态会按运行进度逐条变化；后端返回运行结果后，前端用动画展示实时执行感。</p>
          </div>
        </div>
        <div class="case-list">
          <button
            v-for="item in store.visibleRunCases"
            :key="item.case_id"
            class="case-item"
            :class="item.status"
            @click="selected = item.case_id"
          >
            <span><i class="status-dot" :class="`status-${item.status}`"></i>{{ item.case_id }}</span>
            <strong>{{ item.status }}</strong>
            <small>{{ item.objective }}</small>
          </button>
        </div>
      </div>

      <div class="glass-card detail-panel">
        <div class="section-heading">
          <div>
            <h2>失败详情 / Oracle</h2>
            <p>点击失败用例查看 stdout、stderr 和规则/契约 Oracle 判定。</p>
          </div>
        </div>
        <template v-if="selectedCase">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="Case">{{ selectedCase.case_id }}</el-descriptions-item>
            <el-descriptions-item label="stdout">{{ selectedCase.stdout || 'N/A' }}</el-descriptions-item>
            <el-descriptions-item label="stderr">{{ selectedCase.stderr || 'N/A' }}</el-descriptions-item>
            <el-descriptions-item label="错误摘要">{{ selectedCase.error_summary || '无' }}</el-descriptions-item>
            <el-descriptions-item label="Oracle">{{ selectedCase.oracle?.summary }}</el-descriptions-item>
          </el-descriptions>
        </template>
        <el-empty v-else description="选择一个用例查看详情" />
      </div>
    </section>

    <section class="glass-card trace-panel">
      <div class="section-heading">
        <div>
          <h2>Trace 时间线</h2>
          <p>消息流向、工具调用、工具返回和 Oracle 检查被统一组织成可审计证据链。</p>
        </div>
        <el-tag effect="dark" type="primary">{{ store.visibleTrace.length }} events</el-tag>
      </div>
      <TraceTimeline :events="store.visibleTrace" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import TraceTimeline from '@/components/trace/TraceTimeline.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const selected = ref('')
const isRunning = computed(() => store.run?.status === 'running')
const passRate = computed(() => `${Math.round((store.run?.pass_rate ?? 0) * 100)}%`)
const selectedCase = computed(() => store.visibleRunCases.find((item) => item.case_id === selected.value))

const startRun = async () => {
  selected.value = ''
  await store.startRun(store.currentProject?.id ?? 'p-autogen-001')
  selected.value = store.visibleRunCases.find((item) => item.status === 'failed')?.case_id ?? store.visibleRunCases[0]?.case_id ?? ''
}
</script>

<style scoped>
.run-page {
  display: grid;
  gap: 16px;
}

.run-hero {
  display: flex;
  justify-content: space-between;
  gap: 22px;
  padding: 26px;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--cyan);
  font-weight: 900;
}

.run-hero h1 {
  margin: 0;
  font-size: 38px;
}

.run-hero p {
  max-width: 68ch;
  color: var(--muted);
}

.run-actions {
  display: grid;
  justify-items: center;
  gap: 16px;
  min-width: 220px;
}

.pass-ring {
  display: grid;
  place-items: center;
  width: 150px;
  height: 150px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(34, 197, 94, 0.18), rgba(255, 255, 255, 0.86) 62%);
  border: 1px solid rgba(34, 197, 94, 0.32);
}

.pass-ring strong {
  font-size: 38px;
}

.pass-ring span {
  color: var(--muted);
}

.run-grid {
  display: grid;
  grid-template-columns: minmax(360px, 0.9fr) minmax(0, 1.1fr);
  gap: 16px;
}

.case-panel,
.detail-panel,
.trace-panel {
  padding: 18px;
}

.case-list {
  display: grid;
  gap: 10px;
}

.case-item {
  display: grid;
  gap: 6px;
  width: 100%;
  min-height: 78px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--text);
  padding: 12px;
  text-align: left;
  cursor: pointer;
}

.case-item span,
.case-item strong {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.case-item small {
  color: var(--muted);
}

.case-item.running {
  border-color: rgba(56, 189, 248, 0.55);
  box-shadow: 0 0 30px rgba(56, 189, 248, 0.12);
  animation: running-card 1.1s ease-in-out infinite;
}

.case-item.passed {
  border-color: rgba(34, 197, 94, 0.35);
}

@keyframes running-card {
  0%,
  100% {
    transform: translateX(0);
  }
  50% {
    transform: translateX(4px);
  }
}

.case-item.failed {
  border-color: rgba(244, 63, 94, 0.5);
}

@media (max-width: 1100px) {
  .run-hero,
  .run-grid {
    grid-template-columns: 1fr;
    display: grid;
  }
}
</style>
