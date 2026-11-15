<script setup>
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { baseOptions, PALETTE, useChartTheme } from './theme'

const props = defineProps({ labels: Array, values: Array, colors: Array, centerLabel: String, centerValue: [String, Number] })
const theme = useChartTheme()

const data = computed(() => ({
  labels: props.labels,
  datasets: [
    {
      data: props.values,
      backgroundColor: props.colors?.length ? props.colors : PALETTE,
      borderColor: theme.value.border,
      borderWidth: 3,
      hoverOffset: 8,
      borderRadius: 6,
      spacing: 2,
    },
  ],
}))
const options = computed(() => {
  const o = baseOptions(theme.value)
  return { ...o, cutout: '72%', plugins: { ...o.plugins, legend: { ...o.plugins.legend, position: 'bottom' } } }
})
</script>

<template>
  <div class="relative h-full w-full">
    <Doughnut :data="data" :options="options" />
    <div v-if="centerValue !== undefined" class="pointer-events-none absolute inset-x-0 top-[38%] -translate-y-1/2 text-center">
      <p class="font-display text-2xl font-semibold">{{ centerValue }}</p>
      <p class="text-xs text-muted">{{ centerLabel }}</p>
    </div>
  </div>
</template>
