<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import { baseOptions, PALETTE, useChartTheme } from './theme'

const props = defineProps({ labels: Array, datasets: Array })
const theme = useChartTheme()

function gradient(ctx, color) {
  const { chart } = ctx
  const area = chart.chartArea
  if (!area) return `${color}33`
  const g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom)
  g.addColorStop(0, `${color}55`)
  g.addColorStop(1, `${color}00`)
  return g
}

const data = computed(() => ({
  labels: props.labels,
  datasets: props.datasets.map((d, i) => {
    const color = d.color || PALETTE[i % PALETTE.length]
    return {
      label: d.label,
      data: d.data,
      borderColor: color,
      backgroundColor: (ctx) => gradient(ctx, color),
      fill: true,
      tension: 0.4,
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 5,
      pointBackgroundColor: color,
    }
  }),
}))
const options = computed(() => {
  const t = theme.value
  const o = baseOptions(t)
  return {
    ...o,
    interaction: { mode: 'index', intersect: false },
    plugins: { ...o.plugins, legend: { ...o.plugins.legend, position: 'top', align: 'end' } },
    scales: {
      x: { grid: { display: false }, ticks: { color: t.text }, border: { display: false } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, precision: 0 }, border: { display: false }, beginAtZero: true },
    },
  }
})
</script>

<template>
  <Line :data="data" :options="options" />
</template>
