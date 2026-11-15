<script setup>
import { useId } from 'vue'

const model = defineModel({ type: [String, Number, null], default: '' })
defineProps({
  label: String,
  error: [String, Array, Object],
  hint: String,
  type: { type: String, default: 'text' },
  textarea: Boolean,
  rows: { type: Number, default: 3 },
  icon: { type: [Object, Function], default: null },
  required: Boolean,
})
defineOptions({ inheritAttrs: false })
const id = useId()
</script>

<template>
  <div>
    <label v-if="label" :for="id" class="label">{{ label }}<span v-if="required" class="text-danger"> *</span></label>
    <div class="relative">
      <component :is="icon" v-if="icon" class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted" />
      <textarea v-if="textarea" :id="id" v-model="model" :rows="rows" class="field resize-y" :class="error && 'border-danger'" v-bind="$attrs" />
      <input
        v-else
        :id="id"
        v-model="model"
        :type="type"
        class="field"
        :class="[icon && 'pl-9', error && 'border-danger']"
        :aria-invalid="!!error"
        v-bind="$attrs"
      />
    </div>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ Array.isArray(error) ? error.join(' ') : typeof error === 'object' ? Object.values(error).join(' ') : error }}</p>
    <p v-else-if="hint" class="mt-1 text-xs text-muted">{{ hint }}</p>
  </div>
</template>
