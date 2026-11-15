<script setup>
const model = defineModel({ type: Array, default: () => [] })
const props = defineProps({
  label: { type: String, default: 'Visible to' },
  allowed: { type: Array, default: () => ['admin', 'manager', 'employee'] },
  error: [String, Array],
})
const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'manager', label: 'Manager' },
  { value: 'employee', label: 'Employee' },
]
function toggle(role) {
  model.value = model.value.includes(role) ? model.value.filter((r) => r !== role) : [...model.value, role]
}
const disabled = (role) => !props.allowed.includes(role)
</script>

<template>
  <fieldset>
    <legend class="label">{{ label }}</legend>
    <div class="flex flex-wrap gap-2">
      <button
        v-for="r in ROLES"
        :key="r.value"
        type="button"
        role="checkbox"
        :aria-checked="model.includes(r.value)"
        :disabled="disabled(r.value)"
        :title="disabled(r.value) ? 'This data source is not available to this role' : undefined"
        class="chip px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40"
        :class="model.includes(r.value) ? 'border-transparent bg-accent/15 text-accent' : 'text-muted hover:text-ink'"
        @click="toggle(r.value)"
      >
        {{ r.label }}
      </button>
    </div>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ Array.isArray(error) ? error.join(' ') : error }}</p>
  </fieldset>
</template>
