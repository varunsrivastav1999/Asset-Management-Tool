<script setup>
import { useId } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const model = defineModel({ type: [String, Number, Boolean, null], default: '' })
defineProps({
  label: String,
  options: { type: Array, default: () => [] }, // [{ value, label }]
  placeholder: String,
  error: [String, Array],
  required: Boolean,
})
defineOptions({ inheritAttrs: false })
const id = useId()
</script>

<template>
  <div>
    <label v-if="label" :for="id" class="label">{{ label }}<span v-if="required" class="text-danger"> *</span></label>
    <div class="relative">
      <select :id="id" v-model="model" class="field appearance-none pr-9" :class="error && 'border-danger'" v-bind="$attrs">
        <option v-if="placeholder !== undefined" :value="''">{{ placeholder }}</option>
        <option v-for="o in options" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
      </select>
      <ChevronDown class="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-muted" />
    </div>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ Array.isArray(error) ? error.join(' ') : error }}</p>
  </div>
</template>
