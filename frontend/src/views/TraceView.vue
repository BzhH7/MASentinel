<template>
  <div class="glass-card trace-page">
    <div class="section-heading">
      <div>
        <h2>完整 Trace 证据链</h2>
        <p>后端接口要求指定 case_id。请先选择一条真实测试用例，再加载该用例的 Trace。</p>
      </div>
      <div class="trace-actions">
        <el-select v-model="selectedCase" filterable placeholder="选择 case_id">
          <el-option v-for="item in store.visibleRunCases" :key="item.case_id" :label="item.case_id" :value="item.case_id" />
        </el-select>
        <el-button type="primary" :disabled="!selectedCase" :loading="loading" @click="loadTrace">加载 Trace</el-button>
        <el-tag effect="dark">{{ store.trace.length }} events</el-tag>
      </div>
    </div>
    <TraceTimeline :events="store.trace" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import TraceTimeline from '@/components/trace/TraceTimeline.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const selectedCase = ref(store.selectedCaseId)
const loading = ref(false)

watch(
  () => store.selectedCaseId,
  (value) => {
    selectedCase.value = value
  }
)

const loadTrace = async () => {
  if (!selectedCase.value) return
  loading.value = true
  try {
    await store.loadTrace(selectedCase.value)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.trace-page {
  padding: 18px;
}

.trace-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.trace-actions .el-select {
  width: 360px;
}
</style>
