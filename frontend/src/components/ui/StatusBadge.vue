<script setup>
import { computed } from 'vue'
import AppBadge from './AppBadge.vue'
import { ASSET_STATUS, HANDOVER_STATUS, MAINTENANCE_STATUS } from '@/utils/constants'

const props = defineProps({ status: String, kind: { type: String, default: 'asset' } })
const meta = computed(() => ({ asset: ASSET_STATUS, handover: HANDOVER_STATUS, maintenance: MAINTENANCE_STATUS })[props.kind]?.[props.status])
</script>

<template>
  <AppBadge :tone="meta?.tone" dot>{{ meta?.label || status }}</AppBadge>
</template>
