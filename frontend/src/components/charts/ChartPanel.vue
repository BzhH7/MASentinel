<template>
  <div class="chart-panel glass-card">
    <div class="chart-head">
      <div>
        <h3>{{ title }}</h3>
        <p>{{ subtitle }}</p>
      </div>
      <slot name="extra" />
    </div>
    <VChart class="chart" :option="option" autoresize />
  </div>
</template>

<script setup lang="ts">
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart, RadarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, RadarComponent, TooltipComponent } from 'echarts/components'

use([CanvasRenderer, BarChart, LineChart, PieChart, RadarChart, GridComponent, LegendComponent, RadarComponent, TooltipComponent])

defineProps<{
  title: string
  subtitle?: string
  option: Record<string, unknown>
}>()
</script>

<style scoped>
.chart-panel {
  min-height: 340px;
  padding: 18px;
}

.chart-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}

h3 {
  margin: 0;
  font-size: 18px;
}

p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
}

.chart {
  height: 270px;
}
</style>
