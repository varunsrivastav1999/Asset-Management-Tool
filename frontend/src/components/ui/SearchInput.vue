<script setup>
import { Search, X } from 'lucide-vue-next'
const model = defineModel({ type: String, default: '' })
defineProps({ placeholder: { type: String, default: 'Search…' } })
</script>

<template>
  <div class="relative">
    <Search class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted" />
    <input v-model="model" type="search" class="field pr-9 pl-9" :placeholder="placeholder" :aria-label="placeholder" />
    <button v-if="model" class="absolute top-1/2 right-2.5 -translate-y-1/2 rounded-md p-0.5 text-muted hover:text-ink" aria-label="Clear search" @click="model = ''">
      <X class="h-4 w-4" />
    </button>
  </div>
</template>
