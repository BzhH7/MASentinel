<template>
  <div class="glass-card trace-page">
    <div class="section-heading">
      <div>
        <h2>完整 Trace 证据链</h2>
        <p>展示一次运行中全部 Agent 消息、工具调用、工具返回和 Oracle 判定。</p>
      </div>
      <el-tag effect="dark">{{ store.trace.length }} events</el-tag>
    </div>
    <TraceTimeline :events="store.trace" />
  </div>
</template>

<script setup lang="ts">
import TraceTimeline from '@/components/trace/TraceTimeline.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
</script>

<style scoped>
.trace-page {
  padding: 18px;
}
</style>
