<script setup>
import { computed, useId } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const model = defineModel({ type: [String, Number, Boolean, null], default: '' })
const props = defineProps({
  label: String,
  options: { type: Array, default: () => [] }, // [{ value, label, group? }] — options with a group render in <optgroup>s
  placeholder: String,
  error: [String, Array],
  required: Boolean,
})
defineOptions({ inheritAttrs: false })
const id = useId()
const ungrouped = computed(() => props.options.filter((o) => !o.group))
const groups = computed(() => {
  const out = new Map()
  props.options.filter((o) => o.group).forEach((o) => out.set(o.group, [...(out.get(o.group) || []), o]))
  return [...out.entries()]
})
</script>

<template>
  <div>
    <label v-if="label" :for="id" class="label">{{ label }}<span v-if="required" class="text-danger"> *</span></label>
    <div class="relative">
      <select :id="id" v-model="model" class="field appearance-none pr-9" :class="error && 'border-danger'" v-bind="$attrs">
        <option v-if="placeholder !== undefined" :value="''">{{ placeholder }}</option>
        <option v-for="o in ungrouped" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
        <optgroup v-for="[name, items] in groups" :key="name" :label="name">
          <option v-for="o in items" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
        </optgroup>
      </select>
      <ChevronDown class="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-muted" />
    </div>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ Array.isArray(error) ? error.join(' ') : error }}</p>
  </div>
</template>
