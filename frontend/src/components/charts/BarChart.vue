<script setup>
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { baseOptions, PALETTE, useChartTheme } from './theme'

const props = defineProps({
  labels: Array,
  datasets: Array, // [{ label, data, color? }]
  horizontal: Boolean,
  stacked: Boolean,
})
const theme = useChartTheme()

const data = computed(() => ({
  labels: props.labels,
  datasets: props.datasets.map((d, i) => ({
    label: d.label,
    data: d.data,
    backgroundColor: d.colors || d.color || PALETTE[i % PALETTE.length],
    borderRadius: 8,
    borderSkipped: false,
    maxBarThickness: 28,
  })),
}))
const options = computed(() => {
  const t = theme.value
  const axis = { grid: { color: t.grid, drawBorder: false }, ticks: { color: t.text, precision: 0 }, border: { display: false }, stacked: props.stacked }
  const o = baseOptions(t)
  return {
    ...o,
    indexAxis: props.horizontal ? 'y' : 'x',
    plugins: { ...o.plugins, legend: { ...o.plugins.legend, display: props.datasets.length > 1 } },
    scales: { x: { ...axis, grid: { display: !props.horizontal ? false : true, color: t.grid } }, y: { ...axis, grid: { display: props.horizontal ? false : true, color: t.grid }, beginAtZero: true } },
  }
})
</script>

<template>
  <Bar :data="data" :options="options" />
</template>
