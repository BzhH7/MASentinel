<template>
  <div class="bug-page">
    <div class="section-heading">
      <div>
        <h2>缺陷管理 Kanban</h2>
        <p>拖拽卡片切换状态，模拟 PUT /api/bugs/{id}。</p>
      </div>
    </div>
    <section class="kanban">
      <div
        v-for="status in statuses"
        :key="status"
        class="column glass-card"
        @dragover.prevent
        @drop="dropBug(status)"
      >
        <h3>{{ status }} <span>{{ grouped[status]?.length ?? 0 }}</span></h3>
        <article
          v-for="bug in grouped[status]"
          :key="bug.id"
          draggable="true"
          class="bug-card"
          @dragstart="dragging = bug.id"
        >
          <div>
            <strong>{{ bug.title }}</strong>
            <el-tag :type="severityType(bug.severity)" effect="dark">{{ bug.severity }}</el-tag>
          </div>
          <p>{{ bug.evidence }}</p>
          <small>{{ bug.bug_type }} · {{ bug.test_case }}</small>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import type { BugStatus, Severity } from '@/types/domain'

const store = useAppStore()
const dragging = ref('')
const statuses: BugStatus[] = ['Open', 'Processing', 'Fixed', 'Closed', 'Reopen']
const grouped = computed(() => {
  const result: Record<BugStatus, typeof store.bugs> = {
    Open: [],
    Processing: [],
    Fixed: [],
    Closed: [],
    Reopen: []
  }
  store.bugs.forEach((item) => result[item.status].push(item))
  return result
})

const dropBug = async (status: BugStatus) => {
  if (!dragging.value) return
  await store.moveBug(dragging.value, status)
  dragging.value = ''
}

const severityType = (severity: Severity) => {
  if (severity === 'critical' || severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  return 'success'
}
</script>

<style scoped>
.kanban {
  display: grid;
  grid-template-columns: repeat(5, minmax(220px, 1fr));
  gap: 12px;
  overflow-x: auto;
}

.column {
  min-height: 560px;
  padding: 14px;
}

.column h3 {
  display: flex;
  justify-content: space-between;
  margin: 0 0 12px;
}

.column h3 span {
  color: var(--muted);
}

.bug-card {
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
  padding: 12px;
  cursor: grab;
}

.bug-card div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.bug-card p {
  margin: 0;
  color: #475569;
  font-size: 13px;
}

.bug-card small {
  color: var(--muted);
}
</style>
