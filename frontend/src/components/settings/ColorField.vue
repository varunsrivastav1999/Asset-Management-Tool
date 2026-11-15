<script setup>
import { computed, useId } from 'vue'
import { X } from 'lucide-vue-next'
import { COLOR_PRESETS, normalizeHex } from '@/utils/color'

const model = defineModel({ type: String, default: '' })
defineProps({ label: String, hint: String, error: [String, Array] })
const id = useId()
const valid = computed(() => normalizeHex(model.value))
// <input type=color> only understands #rrggbb.
const pickerValue = computed(() => {
  const v = valid.value
  if (!v) return '#10b981'
  if (v.length === 4) return `#${[...v.slice(1)].map((c) => c + c).join('')}`
  return v.slice(0, 7)
})
</script>

<template>
  <div>
    <label :for="id" class="label">{{ label }}</label>
    <div class="flex items-center gap-2">
      <label class="relative h-10 w-10 shrink-0 cursor-pointer overflow-hidden rounded-xl border border-line" :style="{ background: valid || 'transparent' }" :title="`Pick ${label}`">
        <span v-if="!valid" class="absolute inset-0 grid place-items-center text-[10px] text-muted">auto</span>
        <input type="color" class="absolute inset-0 h-full w-full cursor-pointer opacity-0" :value="pickerValue" :aria-label="`${label} picker`" @input="model = $event.target.value" />
      </label>
      <input :id="id" v-model="model" class="field !w-28 font-mono text-xs uppercase" placeholder="#22D3EE" maxlength="9" :aria-invalid="!!model && !valid" />
      <button v-if="model" type="button" class="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-ink" :aria-label="`Clear ${label}`" @click="model = ''"><X class="h-4 w-4" /></button>
    </div>
    <div class="mt-2 flex flex-wrap gap-1.5">
      <button
        v-for="c in COLOR_PRESETS"
        :key="c"
        type="button"
        class="h-6 w-6 rounded-full ring-offset-2 ring-offset-bg transition hover:scale-110"
        :class="model?.toLowerCase() === c && 'ring-2 ring-accent'"
        :style="{ background: c }"
        :aria-label="`Use ${c}`"
        @click="model = c"
      />
    </div>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ Array.isArray(error) ? error.join(' ') : error }}</p>
    <p v-else-if="model && !valid" class="mt-1 text-xs text-danger">Use a hex color like #10b981.</p>
    <p v-else-if="hint" class="mt-1 text-xs text-muted">{{ hint }}</p>
  </div>
</template>
