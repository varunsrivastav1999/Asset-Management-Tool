<script setup>
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'

const model = defineModel({ type: Object, default: () => ({}) })
defineProps({ fields: { type: Array, default: () => [] }, errors: { type: Object, default: () => ({}) } })

function set(key, value) {
  model.value = { ...model.value, [key]: value }
}
</script>

<template>
  <div v-if="fields.length" class="grid gap-4 sm:grid-cols-2">
    <template v-for="f in fields" :key="f.key">
      <AppSelect
        v-if="f.field_type === 'select'"
        :model-value="model[f.key] ?? ''"
        :label="f.label"
        :required="f.required"
        :options="f.options.map((o) => ({ value: o, label: o }))"
        placeholder="Select…"
        :error="errors[f.key]"
        @update:model-value="set(f.key, $event)"
      />
      <AppSelect
        v-else-if="f.field_type === 'boolean'"
        :model-value="model[f.key] === undefined || model[f.key] === null ? '' : String(model[f.key])"
        :label="f.label"
        :required="f.required"
        :options="[{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]"
        placeholder="—"
        :error="errors[f.key]"
        @update:model-value="set(f.key, $event === '' ? null : $event === 'true')"
      />
      <AppInput
        v-else
        :model-value="model[f.key] ?? ''"
        :label="f.label"
        :required="f.required"
        :type="f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : 'text'"
        :step="f.field_type === 'number' ? 'any' : undefined"
        :hint="f.help_text"
        :error="errors[f.key]"
        @update:model-value="set(f.key, $event)"
      />
    </template>
  </div>
</template>
