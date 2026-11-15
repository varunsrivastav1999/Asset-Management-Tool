<script setup>
import { computed } from 'vue'
import { TriangleAlert } from 'lucide-vue-next'
import StatCard from '@/components/ui/StatCard.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import DoughnutChart from '@/components/charts/DoughnutChart.vue'
import BarChart from '@/components/charts/BarChart.vue'
import LineChart from '@/components/charts/LineChart.vue'
import { EVENT_META } from '@/utils/constants'
import { iconFor } from '@/utils/icons'
import { formatDate, formatMoney, formatNumber, timeAgo } from '@/utils/format'

const props = defineProps({ widget: { type: Object, required: true }, loading: Boolean })

const d = computed(() => props.widget.data)
const cfg = computed(() => props.widget.config || {})

const statValue = computed(() => {
  const v = d.value?.value
  if (v === undefined || v === null) return '—'
  if (d.value.format === 'currency') return formatMoney(v, undefined, { compact: true })
  if (d.value.format === 'percent') return `${v}%`
  return formatNumber(v)
})

// Month keys ("2026-03") read better as short month names.
const labels = computed(() =>
  (d.value?.labels || []).map((l) => (/^\d{4}-\d{2}$/.test(l) ? new Date(`${l}-01T00:00:00`).toLocaleDateString(undefined, { month: 'short' }) : l)),
)
const doughnut = computed(() => {
  const ds = d.value?.datasets?.[0] || { data: [] }
  return { labels: labels.value, values: ds.data, colors: ds.colors, total: ds.data.reduce((a, b) => a + b, 0) }
})
const hasChartData = computed(() => (d.value?.datasets || []).some((ds) => ds.data.some((v) => v > 0)))

function cell(row, col) {
  const v = row[col.key]
  if (col.type === 'date') return formatDate(v)
  if (col.type === 'ago') return timeAgo(v)
  return v ?? '—'
}
</script>

<template>
  <StatCard
    v-if="widget.type === 'stat'"
    class="h-full"
    :label="widget.title"
    :value="statValue"
    :hint="d?.hint"
    :icon="cfg.icon ? iconFor(cfg.icon) : null"
    :tone="cfg.tone || 'accent'"
    :to="d?.link || undefined"
    :loading="loading && !d"
  />

  <section v-else class="card flex h-full flex-col p-5">
    <h2 class="mb-3 font-semibold">{{ widget.title }}</h2>
    <div v-if="widget.error" class="flex flex-1 items-center gap-2 text-sm text-muted"><TriangleAlert class="h-4 w-4 text-warning" /> Data unavailable</div>

    <template v-else-if="widget.type === 'chart'">
      <div class="h-64 sm:h-72">
        <div v-if="loading && !d" class="skeleton h-full w-full" />
        <p v-else-if="!hasChartData" class="grid h-full place-items-center text-sm text-muted">No data yet</p>
        <DoughnutChart v-else-if="widget.chart_type === 'doughnut'" :labels="doughnut.labels" :values="doughnut.values" :colors="doughnut.colors" center-label="total" :center-value="formatNumber(doughnut.total)" />
        <LineChart v-else-if="widget.chart_type === 'line'" :labels="labels" :datasets="d.datasets" />
        <BarChart v-else :labels="labels" :datasets="d.datasets" :horizontal="widget.chart_type === 'hbar'" />
      </div>
    </template>

    <template v-else-if="widget.type === 'table'">
      <p v-if="!d?.rows?.length" class="py-6 text-center text-sm text-muted">Nothing to show</p>
      <TransitionGroup v-else tag="ul" name="list" class="-mx-2 divide-y divide-line">
        <li v-for="(row, i) in d.rows" :key="row.link || i">
          <component :is="row.link ? 'RouterLink' : 'div'" :to="row.link" class="flex items-center gap-3 rounded-lg px-2 py-2 text-sm transition hover:bg-surface-hover">
            <template v-for="(col, ci) in d.columns" :key="col.key">
              <AppBadge v-if="col.type === 'badge'" :tone="EVENT_META[row.event_type]?.tone" class="shrink-0">{{ row[col.key] }}</AppBadge>
              <StatusBadge v-else-if="col.type === 'status'" :status="row[col.key]" class="shrink-0" />
              <span v-else :class="ci === 0 || (ci === 1 && d.columns[0].type === 'badge') ? 'min-w-0 flex-1 truncate' : 'hidden shrink-0 text-xs text-muted sm:inline'">{{ cell(row, col) }}</span>
            </template>
          </component>
        </li>
      </TransitionGroup>
    </template>
  </section>
</template>
