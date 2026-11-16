<script setup>
import { hasOptions } from '@/utils/columnTypes'
import { reactive, ref, watch } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import MediaInput from '@/components/table/MediaInput.vue'
import { pick, userLabel, userSub } from '@/api/pickers'

/** Create/edit form generated from a table's custom columns. Emits `save` with a custom_data object. */
const open = defineModel('open', { type: Boolean })
const props = defineProps({ columns: { type: Array, default: () => [] }, record: Object, title: String, saving: Boolean, errors: { type: Object, default: () => ({}) } })
const emit = defineEmits(['save'])
const form = reactive({})
const users = ref({})

watch(open, (v) => {
  if (!v) return
  Object.keys(form).forEach((k) => delete form[k])
  for (const c of props.columns) {
    const val = props.record?.custom_data?.[c.key]
    if (c.type === 'media') form[c.key] = val && typeof val === 'object' ? val : null
    else form[c.key] = c.type === 'user' ? (val?.id ?? null) : c.type === 'boolean' ? (val === true ? 'true' : val === false ? 'false' : '') : (val ?? '')
    if (c.type === 'user' && val) users.value[c.key] = { id: val.id, full_name: val.name }
  }
})

function submit() {
  const out = {}
  for (const c of props.columns) {
    let v = form[c.key]
    if (c.type === 'boolean') v = v === '' ? null : v === 'true'
    else if (c.type === 'user') v = v ? { id: v, name: users.value[c.key] ? userLabel(users.value[c.key]) : '' } : null
    else if (v === '') v = null
    out[c.key] = v
  }
  emit('save', out)
}
</script>

<template>
  <AppModal v-model:open="open" :title="title" size="lg">
    <form id="record-form" class="grid gap-4 sm:grid-cols-2" novalidate @submit.prevent="submit">
      <template v-for="c in columns" :key="c.key">
        <MediaInput v-if="c.type === 'media'" v-model="form[c.key]" class="sm:col-span-2" :item="c.item" :column="c.key" :label="c.name" :error="errors[c.key]" />
        <AppSelect v-else-if="hasOptions(c.type)" v-model="form[c.key]" :label="c.name" :required="c.is_required" placeholder="—" :options="c.options.map((o) => ({ value: o, label: o }))" :error="errors[c.key]" />
        <AppSelect v-else-if="c.type === 'boolean'" v-model="form[c.key]" :label="c.name" :required="c.is_required" placeholder="—" :options="[{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]" :error="errors[c.key]" />
        <EntityPicker v-else-if="c.type === 'user'" v-model="form[c.key]" :label="c.name" :required="c.is_required" :fetcher="pick.users" :label-of="userLabel" :sublabel-of="userSub" :initial="users[c.key] ? [users[c.key]] : []" :error="errors[c.key]" @select="(u) => (users[c.key] = u)" />
        <AppInput
          v-else
          v-model="form[c.key]"
          :label="c.name"
          :required="c.is_required"
          :type="c.type === 'number' ? 'number' : c.type === 'date' ? 'date' : c.type === 'file' ? 'url' : 'text'"
          :placeholder="c.type === 'file' ? 'https://…' : ''"
          step="any"
          :error="errors[c.key]"
        />
      </template>
    </form>
    <template #footer>
      <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
      <AppButton type="submit" form="record-form" :loading="saving">Save</AppButton>
    </template>
  </AppModal>
</template>
