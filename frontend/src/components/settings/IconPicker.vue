<script setup>
import { computed, ref } from 'vue'
import { X } from 'lucide-vue-next'
import { ICONS, ICON_NAMES } from '@/utils/icons'

const model = defineModel({ type: String, default: '' })
defineProps({ label: { type: String, default: 'Icon' } })
const q = ref('')
const shown = computed(() => ICON_NAMES.filter((n) => n.includes(q.value.trim().toLowerCase())))
</script>

<template>
  <div>
    <div class="mb-1.5 flex items-center justify-between gap-2">
      <span class="label mb-0">{{ label }}</span>
      <input v-model="q" class="field !w-36 !py-1 text-xs" placeholder="Filter icons…" aria-label="Filter icons" />
    </div>
    <div class="grid max-h-44 grid-cols-7 gap-1.5 overflow-y-auto rounded-2xl border border-line p-2 sm:grid-cols-9" role="radiogroup" :aria-label="label">
      <button type="button" class="grid aspect-square place-items-center rounded-xl text-muted transition hover:bg-surface-hover" :class="!model && 'bg-accent/15 text-accent ring-2 ring-accent'" title="No icon" role="radio" :aria-checked="!model" @click="model = ''">
        <X class="h-4 w-4" />
      </button>
      <button
        v-for="name in shown"
        :key="name"
        type="button"
        role="radio"
        :aria-checked="model === name"
        :title="name"
        class="grid aspect-square place-items-center rounded-xl transition hover:bg-surface-hover"
        :class="model === name ? 'bg-accent/15 text-accent ring-2 ring-accent' : 'text-muted'"
        @click="model = name"
      >
        <component :is="ICONS[name]" class="h-4 w-4" />
      </button>
    </div>
  </div>
</template>
