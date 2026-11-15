<script setup>
import { reactive, ref, watch } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import { maintenanceApi } from '@/api'
import { parseError } from '@/api/http'
import { assetLabel, assetSub, pick } from '@/api/pickers'
import { useUiStore } from '@/stores/ui'
import { MAINTENANCE_KINDS } from '@/utils/constants'
import { todayISO } from '@/utils/format'

const open = defineModel('open', { type: Boolean })
const props = defineProps({ asset: Object, record: Object })
const emit = defineEmits(['saved'])
const ui = useUiStore()
const form = reactive({})
const errors = ref({})
const saving = ref(false)

watch(open, (v) => {
  if (!v) return
  errors.value = {}
  const r = props.record
  Object.assign(form, {
    asset: r?.asset ?? props.asset?.id ?? null,
    title: r?.title ?? '',
    kind: r?.kind ?? 'preventive',
    scheduled_date: r?.scheduled_date ?? todayISO(),
    technician: r?.technician ?? '',
    vendor: r?.vendor ?? null,
    cost: r?.cost ?? '',
    description: r?.description ?? '',
  })
})

async function save() {
  saving.value = true
  errors.value = {}
  const data = { ...form, cost: form.cost === '' ? null : form.cost }
  try {
    props.record ? await maintenanceApi.update(props.record.id, data) : await maintenanceApi.create(data)
    ui.success(props.record ? 'Maintenance updated' : 'Maintenance scheduled')
    emit('saved')
    open.value = false
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal v-model:open="open" :title="record ? 'Edit maintenance' : 'Schedule maintenance'" :subtitle="asset ? `${asset.asset_tag} · ${asset.name}` : undefined">
    <form id="maint-form" class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
      <EntityPicker
        v-if="!asset && !record"
        v-model="form.asset"
        class="sm:col-span-2"
        label="Asset"
        required
        :fetcher="pick.assets({ status: 'in_stock,assigned,in_repair' })"
        :label-of="assetLabel"
        :sublabel-of="assetSub"
        :error="errors.asset"
      />
      <AppInput v-model="form.title" class="sm:col-span-2" label="Title" required placeholder="e.g. Annual service, screen replacement" :error="errors.title" />
      <AppSelect v-model="form.kind" label="Type" :options="MAINTENANCE_KINDS" />
      <AppInput v-model="form.scheduled_date" label="Scheduled for" type="date" required :error="errors.scheduled_date" />
      <AppInput v-model="form.technician" label="Technician" />
      <EntityPicker v-model="form.vendor" label="Service vendor" :fetcher="pick.vendors" :initial="record?.vendor ? [{ id: record.vendor, name: record.vendor_name }] : []" />
      <AppInput v-model="form.cost" label="Estimated cost" type="number" min="0" step="0.01" :error="errors.cost" />
      <AppInput v-model="form.description" class="sm:col-span-2" label="Description" textarea :rows="3" />
    </form>
    <template #footer>
      <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
      <AppButton type="submit" form="maint-form" :loading="saving">{{ record ? 'Save' : 'Schedule' }}</AppButton>
    </template>
  </AppModal>
</template>
