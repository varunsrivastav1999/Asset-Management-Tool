<script setup>
import { computed } from 'vue'
import { APP_NAME } from '@/brand'

// Highlight the last word with the accent gradient.
const parts = computed(() => {
  const words = APP_NAME.trim().split(/\s+/)
  return { head: words.slice(0, -1).join(' '), tail: words.at(-1) }
})
</script>

<template>
  <span class="font-display font-semibold">{{ parts.head }}<span class="text-gradient">{{ parts.head ? ' ' : '' }}{{ parts.tail }}</span></span>
</template>
