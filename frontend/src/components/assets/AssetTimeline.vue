<script setup>
import { onMounted, ref } from 'vue'
import { assetsApi } from '@/api'
import AppBadge from '@/components/ui/AppBadge.vue'
import AppButton from '@/components/ui/AppButton.vue'
import { ASSET_STATUS, EVENT_META } from '@/utils/constants'
import { formatDateTime, timeAgo } from '@/utils/format'

const props = defineProps({ assetId: { type: [Number, String], required: true } })
const events = ref([])
const page = ref(1)
const hasMore = ref(false)
const loading = ref(true)

async function load(more = false) {
  loading.value = true
  try {
    const data = await assetsApi.history(props.assetId, { page: page.value, page_size: 20 })
    events.value = more ? [...events.value, ...data.results] : data.results
    hasMore.value = !!data.next
  } finally {
    loading.value = false
  }
}
function next() {
  page.value++
  load(true)
}
defineExpose({ reload: () => { page.value = 1; load() } })
onMounted(load)

function lines(e) {
  const out = []
  if (e.from_status || e.to_status) {
    if (e.from_status && e.to_status && e.from_status !== e.to_status) out.push(`${ASSET_STATUS[e.from_status]?.label || e.from_status} → ${ASSET_STATUS[e.to_status]?.label || e.to_status}`)
  }
  if (e.from_user_name || e.to_user_name) out.push([e.from_user_name || e.from_department_name, e.to_user_name || e.to_department_name].filter(Boolean).join(' → '))
  if (e.to_location_name && e.to_location_name !== e.from_location_name) out.push(`📍 ${e.to_location_name}`)
  if (e.metadata?.fields?.length) out.push(`Changed: ${e.metadata.fields.join(', ')}`)
  return out
}
</script>

<template>
  <div>
    <div v-if="loading && !events.length" class="space-y-4">
      <div v-for="i in 4" :key="i" class="flex gap-3"><div class="skeleton h-3 w-3 rounded-full" /><div class="flex-1"><div class="skeleton mb-2 h-4 w-1/3" /><div class="skeleton h-3 w-2/3" /></div></div>
    </div>
    <ol v-else class="relative ml-1.5 border-l border-line">
      <li v-for="e in events" :key="e.id" class="relative mb-5 pl-6 last:mb-0">
        <span class="absolute top-1.5 -left-[5px] h-2.5 w-2.5 rounded-full ring-4 ring-bg" :class="{ primary: 'bg-primary', violet: 'bg-violet-400', emerald: 'bg-emerald-400', amber: 'bg-amber-400', slate: 'bg-slate-400' }[EVENT_META[e.event_type]?.tone] || 'bg-slate-400'" />
        <div class="flex flex-wrap items-center gap-2">
          <AppBadge :tone="EVENT_META[e.event_type]?.tone">{{ e.label }}</AppBadge>
          <RouterLink v-if="e.handover" :to="`/handovers/${e.handover}`" class="font-mono text-xs text-accent hover:underline">{{ e.handover_reference }}</RouterLink>
          <RouterLink v-if="e.receipt" :to="`/receiving/${e.receipt}`" class="font-mono text-xs text-accent hover:underline">{{ e.receipt_reference }}</RouterLink>
          <span class="text-xs text-muted" :title="formatDateTime(e.created_at)">{{ timeAgo(e.created_at) }} · {{ e.actor_name }}</span>
        </div>
        <p v-for="(l, i) in lines(e)" :key="i" class="mt-1 text-sm">{{ l }}</p>
        <p v-if="e.notes" class="mt-1 text-sm text-muted">{{ e.notes }}</p>
      </li>
    </ol>
    <AppButton v-if="hasMore" variant="ghost" size="sm" class="mt-3" :loading="loading" @click="next">Load more</AppButton>
  </div>
</template>
