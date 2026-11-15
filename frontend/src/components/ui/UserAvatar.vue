<script setup>
import { computed } from 'vue'
import { initials } from '@/utils/format'

const props = defineProps({ name: String, src: String, size: { type: String, default: 'md' } })
const hue = computed(() => [...(props.name || '?')].reduce((a, c) => a + c.charCodeAt(0), 0) % 360)
</script>

<template>
  <span
    class="inline-grid shrink-0 place-items-center overflow-hidden rounded-full font-semibold text-white ring-2 ring-line"
    :class="{ xs: 'h-6 w-6 text-[10px]', sm: 'h-8 w-8 text-xs', md: 'h-10 w-10 text-sm', lg: 'h-16 w-16 text-xl' }[size]"
    :style="!src ? { background: `linear-gradient(135deg, hsl(${hue} 80% 55%), hsl(${(hue + 60) % 360} 80% 45%))` } : undefined"
  >
    <img v-if="src" :src="src" :alt="name" class="h-full w-full object-cover" />
    <template v-else>{{ initials(name) }}</template>
  </span>
</template>
