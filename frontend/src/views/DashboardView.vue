<template>
  <div class="dashboard" v-if="summary">
    <section class="hero glass-card">
      <div>
        <p class="eyebrow">MASentinel-X Command Center</p>
        <h1>智能体应用测试态势一屏掌控</h1>
        <p>基于 MASentinel 后端读取 outputs 中已完成的真实测试数据，在前端聚合项目、用例、运行结果、覆盖率与缺陷态势。</p>
      </div>
      <div class="hero-glow">
        <strong>{{ percent(summary.coverage.MASCov) }}</strong>
        <span>MASCov 综合覆盖</span>
      </div>
    </section>

    <section class="metric-grid">
      <article v-for="card in cards" :key="card.label" class="metric-card glass-card">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small :class="card.tone">▲ {{ card.trend }}</small>
      </article>
    </section>

    <section class="chart-grid">
      <ChartPanel title="语义覆盖雷达" subtitle="Agent / Tool / Edge / Contract 等覆盖维度" :option="radarOption" />
      <ChartPanel title="通过率 / 失败率" subtitle="最近一次运行结果" :option="passPieOption" />
      <ChartPanel title="缺陷严重程度分布" subtitle="按 critical / high / medium / low 聚合" :option="severityOption" />
      <ChartPanel title="最近运行趋势" subtitle="通过率随时间变化" :option="trendOption" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ChartPanel from '@/components/charts/ChartPanel.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const summary = computed(() => store.dashboard)

const percent = (value: number) => `${Math.round(value * 100)}%`

const cards = computed(() => {
  if (!summary.value) return []
  return [
    { label: '项目数', value: summary.value.projects, trend: 'outputs/profile.json', tone: 'up' },
    { label: '用例总数', value: summary.value.totalCases, trend: 'testcases.json', tone: 'up' },
    { label: '最近通过率', value: percent(summary.value.latestPassRate), trend: 'oracle_results.json', tone: 'up' },
    { label: '未关闭缺陷', value: summary.value.openBugs, trend: 'faults.json', tone: 'warn' }
  ]
})

const baseChartText = {
  color: '#c8d3e1'
}

const radarOption = computed(() => {
  const cov = summary.value!.coverage
  const keys = Object.keys(cov)
  return {
    tooltip: {},
    radar: {
      indicator: keys.map((name) => ({ name, max: 1 })),
      radius: '62%',
      axisName: { color: '#9fb4cc' },
      splitLine: { lineStyle: { color: 'rgba(148,163,184,.22)' } },
      splitArea: { areaStyle: { color: ['rgba(34,211,238,.04)', 'rgba(167,139,250,.04)'] } },
      axisLine: { lineStyle: { color: 'rgba(148,163,184,.22)' } }
    },
    series: [
      {
        type: 'radar',
        data: [{ value: Object.values(cov), name: 'Coverage' }],
        lineStyle: { color: '#22d3ee', width: 3 },
        areaStyle: { color: 'rgba(34,211,238,.22)' },
        symbol: 'circle',
        symbolSize: 6
      }
    ]
  }
})

const passPieOption = computed(() => ({
  tooltip: {},
  legend: { bottom: 0, textStyle: baseChartText },
  series: [
    {
      type: 'pie',
      radius: ['58%', '78%'],
      center: ['50%', '46%'],
      label: { color: '#dbeafe', formatter: '{b}\n{d}%' },
      data: [
        { name: '通过', value: Math.round(summary.value!.latestPassRate * 100), itemStyle: { color: '#22c55e' } },
        { name: '失败', value: Math.round((1 - summary.value!.latestPassRate) * 100), itemStyle: { color: '#f43f5e' } }
      ]
    }
  ]
}))

const severityOption = computed(() => ({
  tooltip: {},
  grid: { left: 35, right: 16, top: 28, bottom: 34 },
  xAxis: { type: 'category', data: Object.keys(summary.value!.severity), axisLabel: baseChartText },
  yAxis: { type: 'value', axisLabel: baseChartText, splitLine: { lineStyle: { color: 'rgba(148,163,184,.16)' } } },
  series: [
    {
      type: 'bar',
      data: Object.values(summary.value!.severity),
      barWidth: 34,
      itemStyle: {
        borderRadius: [8, 8, 0, 0],
        color: (params: { dataIndex: number }) => ['#ef4444', '#f43f5e', '#f59e0b', '#22c55e'][params.dataIndex]
      }
    }
  ]
}))

const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 42, right: 16, top: 26, bottom: 34 },
  xAxis: { type: 'category', data: summary.value!.trend.map((item) => item.date), axisLabel: baseChartText },
  yAxis: {
    type: 'value',
    min: 0.5,
    max: 1,
    axisLabel: { color: '#c8d3e1', formatter: (value: number) => `${Math.round(value * 100)}%` },
    splitLine: { lineStyle: { color: 'rgba(148,163,184,.16)' } }
  },
  series: [
    {
      type: 'line',
      smooth: true,
      data: summary.value!.trend.map((item) => item.passRate),
      lineStyle: { width: 4, color: '#38bdf8' },
      areaStyle: { color: 'rgba(56,189,248,.18)' },
      symbolSize: 8
    }
  ]
}))
</script>

<style scoped>
.dashboard {
  display: grid;
  gap: 18px;
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 24px;
  min-height: 240px;
  padding: 30px;
  overflow: hidden;
  position: relative;
}

.hero::after {
  content: "";
  position: absolute;
  inset: -120px -80px auto auto;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(37, 99, 235, 0.18), transparent 70%);
  animation: float-orbit 5s ease-in-out infinite;
}

.eyebrow {
  margin: 0 0 10px;
  color: var(--cyan);
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  max-width: 12em;
  font-size: 48px;
  line-height: 1.05;
}

.hero p:last-child {
  max-width: 62ch;
  color: var(--muted);
  line-height: 1.75;
}

.hero-glow {
  display: grid;
  place-items: center;
  align-self: center;
  aspect-ratio: 1;
  border-radius: 50%;
  border: 1px solid rgba(37, 99, 235, 0.28);
  background: radial-gradient(circle, rgba(37, 99, 235, 0.18), rgba(255, 255, 255, 0.8) 62%);
  box-shadow: 0 20px 60px rgba(37, 99, 235, 0.18);
  animation: soft-pulse 2.6s ease-in-out infinite;
}

.hero-glow strong {
  font-size: 54px;
}

.hero-glow span {
  color: var(--muted);
}

@keyframes soft-pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.035);
  }
}

@keyframes float-orbit {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(16px);
  }
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric-card {
  padding: 18px;
}

.metric-card span,
.metric-card small {
  color: var(--muted);
}

.metric-card strong {
  display: block;
  margin: 10px 0;
  font-size: 38px;
}

.metric-card small.up {
  color: var(--green);
}

.metric-card small.warn {
  color: var(--yellow);
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

@media (max-width: 1100px) {
  .hero,
  .metric-grid,
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
