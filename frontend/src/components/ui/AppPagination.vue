<script setup>
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

const page = defineModel({ type: Number, default: 1 })
const props = defineProps({ pages: { type: Number, default: 1 }, count: { type: Number, default: 0 } })

const window_ = computed(() => {
  const p = page.value
  const out = new Set([1, props.pages, p - 1, p, p + 1])
  return [...out].filter((n) => n >= 1 && n <= props.pages).sort((a, b) => a - b)
})
</script>

<template>
  <nav v-if="pages > 1" class="flex items-center justify-between gap-3 pt-4 text-sm" aria-label="Pagination">
    <span class="text-xs text-muted">{{ count }} results</span>
    <div class="flex items-center gap-1">
      <button class="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-hover disabled:opacity-40" :disabled="page <= 1" aria-label="Previous page" @click="page--">
        <ChevronLeft class="h-4 w-4" />
      </button>
      <template v-for="(n, i) in window_" :key="n">
        <span v-if="i && n - window_[i - 1] > 1" class="px-1 text-muted">…</span>
        <button
          class="h-8 min-w-8 rounded-lg px-2 text-xs font-medium transition"
          :class="n === page ? 'bg-gradient-accent text-accent-ink' : 'text-muted hover:bg-surface-hover'"
          :aria-current="n === page ? 'page' : undefined"
          @click="page = n"
        >
          {{ n }}
        </button>
      </template>
      <button class="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-hover disabled:opacity-40" :disabled="page >= pages" aria-label="Next page" @click="page++">
        <ChevronRight class="h-4 w-4" />
      </button>
    </div>
  </nav>
</template>
