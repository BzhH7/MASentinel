<template>
  <div class="trace-wrap">
    <div v-for="(event, index) in events" :key="event.id" class="trace-row" :class="{ right: index % 2 === 1 }">
      <div class="node" :class="event.event_type">
        <el-icon><component :is="iconFor(event.event_type)" /></el-icon>
      </div>
      <article class="bubble glass-card" :class="[event.event_type, `state-${event.status}`]">
        <header>
          <div>
            <strong>{{ event.event_name }}</strong>
            <span>{{ formatTime(event.timestamp) }}</span>
          </div>
          <el-tag :type="tagType(event.status)" effect="dark">{{ event.status }}</el-tag>
        </header>
        <div class="flow">
          <b>{{ event.sender }}</b>
          <span>→</span>
          <b>{{ event.receiver }}</b>
        </div>
        <p class="payload"><em>input</em>{{ event.input_data }}</p>
        <p class="payload"><em>output</em>{{ event.output_data }}</p>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChatLineRound, Cpu, MagicStick, Operation, Tools } from '@element-plus/icons-vue'
import type { TraceEventDTO } from '@/types/domain'

defineProps<{ events: TraceEventDTO[] }>()

const iconFor = (type: TraceEventDTO['event_type']) => {
  const map = {
    agent_message: ChatLineRound,
    tool_call: Tools,
    tool_result: Cpu,
    oracle_check: MagicStick,
    system: Operation
  }
  return map[type]
}

const tagType = (status: TraceEventDTO['status']) => {
  if (status === 'passed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'primary'
  return 'warning'
}

const formatTime = (value: string) => new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
</script>

<style scoped>
.trace-wrap {
  position: relative;
  display: grid;
  gap: 16px;
  padding: 18px 0;
}

.trace-wrap::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  background: linear-gradient(180deg, transparent, rgba(37, 99, 235, 0.32), rgba(8, 145, 178, 0.28), transparent);
}

.trace-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 52px minmax(0, 1fr);
  align-items: center;
}

.trace-row.right .bubble {
  grid-column: 3;
}

.trace-row:not(.right) .bubble {
  grid-column: 1;
}

.node {
  grid-column: 2;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  margin: 0 auto;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: #ffffff;
  color: var(--cyan);
  box-shadow: 0 0 28px rgba(34, 211, 238, 0.22);
}

.node.tool_call,
.node.tool_result {
  color: var(--yellow);
  box-shadow: 0 0 28px rgba(245, 158, 11, 0.2);
}

.node.oracle_check {
  color: var(--violet);
}

.bubble {
  padding: 14px;
  border-radius: 16px;
}

.bubble header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.bubble header strong,
.bubble header span {
  display: block;
}

.bubble header span {
  margin-top: 4px;
  color: var(--muted);
  font-size: 12px;
}

.bubble.agent_message {
  border-color: rgba(34, 211, 238, 0.24);
}

.bubble.tool_call,
.bubble.tool_result {
  border-color: rgba(245, 158, 11, 0.28);
}

.bubble.oracle_check {
  border-color: rgba(167, 139, 250, 0.32);
}

.bubble.state-failed {
  border-color: rgba(244, 63, 94, 0.5);
  box-shadow: 0 0 34px rgba(244, 63, 94, 0.12);
}

.flow {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
  color: #1e3a8a;
}

.flow span {
  color: var(--cyan);
}

.payload {
  margin: 8px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.5;
}

.payload em {
  display: inline-flex;
  min-width: 54px;
  margin-right: 8px;
  color: var(--muted);
  font-style: normal;
  font-weight: 800;
}

@media (max-width: 900px) {
  .trace-wrap::before {
    left: 19px;
  }

  .trace-row,
  .trace-row.right {
    grid-template-columns: 38px minmax(0, 1fr);
    gap: 12px;
  }

  .node {
    grid-column: 1;
  }

  .trace-row .bubble,
  .trace-row.right .bubble,
  .trace-row:not(.right) .bubble {
    grid-column: 2;
  }
}
</style>
