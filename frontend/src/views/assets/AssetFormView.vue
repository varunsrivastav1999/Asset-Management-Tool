<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Save } from 'lucide-vue-next'
import { assetsApi, categoriesApi } from '@/api'
import { parseError } from '@/api/http'
import { pick } from '@/api/pickers'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useTableNames } from '@/composables/useTableNames'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import CustomFieldInputs from '@/components/assets/CustomFieldInputs.vue'
import { CONDITIONS } from '@/utils/constants'
import { todayISO } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const id = computed(() => route.params.id)
const editing = computed(() => !!id.value)

const blank = () => ({
  name: '',
  category: '',
  status: 'in_stock',
  condition: 'new',
  serial_number: '',
  model: '',
  manufacturer: '',
  vendor: null,
  location: null,
  purchase_date: '',
  purchase_cost: '',
  currency: 'USD',
  invoice_number: '',
  po_number: '',
  warranty_expiry: '',
  maintenance_interval_days: '',
  next_maintenance_date: '',
  description: '',
  notes: '',
  custom_data: {},
})
const form = reactive(blank())
const errors = ref({})
const saving = ref(false)
const loading = ref(false)
const categories = ref([])
const initial = reactive({ vendor: [], location: [] })
const dirty = ref(false)

const category = computed(() => categories.value.find((c) => String(c.id) === String(form.category)))
const customFields = computed(() => (category.value ? [...(category.value.inherited_fields || []), ...(category.value.custom_fields || [])].sort((a, b) => a.order - b.order) : []))

onMounted(async () => {
  loading.value = true
  try {
    categories.value = await categoriesApi.list({ is_active: true })
    if (editing.value) {
      const a = await assetsApi.get(id.value)
      Object.assign(form, {
        ...blank(),
        ...Object.fromEntries(Object.keys(blank()).map((k) => [k, a[k] ?? blank()[k]])),
        category: String(a.category.id),
        custom_data: { ...(a.custom_data || {}) },
      })
      if (a.vendor) initial.vendor = [{ id: a.vendor, name: a.vendor_name }]
      if (a.location) initial.location = [{ id: a.location, name: a.location_name }]
      if (!categories.value.some((c) => c.id === a.category.id)) categories.value.push({ ...a.category, custom_fields: a.custom_fields, inherited_fields: [] })
    }
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    loading.value = false
    setTimeout(() => (dirty.value = false))
  }
})
watch(form, () => (dirty.value = true), { deep: true })

function payload() {
  const out = {}
  for (const [k, v] of Object.entries(form)) {
    if (editing.value && k === 'status') continue
    out[k] = v === '' && !['name', 'serial_number', 'model', 'manufacturer', 'invoice_number', 'po_number', 'description', 'notes', 'currency'].includes(k) ? null : v
  }
  out.custom_data = Object.fromEntries(Object.entries(form.custom_data).filter(([key, v]) => v !== '' && v !== null && customFields.value.some((f) => f.key === key)))
  return out
}

async function save() {
  errors.value = {}
  saving.value = true
  try {
    const asset = editing.value ? await assetsApi.update(id.value, payload()) : await assetsApi.create(payload())
    dirty.value = false
    ui.success(editing.value ? 'Asset updated' : `Asset ${asset.asset_tag} created`)
    router.replace(`/assets/${asset.id}`)
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

const catOptions = computed(() => categories.value.map((c) => ({ value: String(c.id), label: c.parent_name ? `${c.parent_name} › ${c.name}` : c.name })))
const assetNames = useTableNames('assets', { plural: 'Assets', singular: 'Asset', route: '/assets' })
</script>

<template>
  <form class="mx-auto max-w-4xl" novalidate @submit.prevent="save">
    <PageHeader
      :title="editing ? `Edit ${assetNames.singular.toLowerCase()}` : `Add ${assetNames.singular}`"
      :subtitle="editing ? undefined : `Register a single ${assetNames.singular.toLowerCase()}. Use Receiving for batches from a supplier.`"
      :crumbs="[{ label: assetNames.plural, to: assetNames.route }, ...(editing ? [{ label: 'Details', to: `/assets/${id}` }] : []), { label: editing ? 'Edit' : 'New' }]"
    >
      <template #actions>
        <AppButton variant="secondary" :to="editing ? `/assets/${id}` : '/assets'">Cancel</AppButton>
        <AppButton type="submit" :icon="Save" :loading="saving">Save</AppButton>
      </template>
    </PageHeader>

    <div v-if="loading" class="card space-y-4 p-6"><div v-for="i in 6" :key="i" class="skeleton h-10" /></div>
    <div v-else class="space-y-4">
      <section class="card animate-fade-up p-5 sm:p-6">
        <h2 class="mb-4 font-semibold">Identity</h2>
        <div class="grid gap-4 sm:grid-cols-2">
          <AppInput v-model="form.name" label="Name" required class="sm:col-span-2" placeholder="e.g. MacBook Pro 14” M4" :error="errors.name" />
          <AppSelect v-model="form.category" label="Category" required placeholder="Select a category" :options="catOptions" :error="errors.category" />
          <AppSelect v-if="!editing" v-model="form.status" label="Initial status" :options="[{ value: 'in_stock', label: 'In stock' }, { value: 'in_repair', label: 'In repair' }, { value: 'lost', label: 'Lost' }, { value: 'retired', label: 'Retired' }]" />
          <AppSelect v-model="form.condition" label="Condition" :options="CONDITIONS" />
          <AppInput v-model="form.serial_number" label="Serial number" placeholder="Unique if provided" :error="errors.serial_number" />
          <AppInput v-model="form.manufacturer" label="Manufacturer" />
          <AppInput v-model="form.model" label="Model" />
          <AppInput v-model="form.description" label="Description" textarea class="sm:col-span-2" :rows="2" />
        </div>
      </section>

      <section v-if="customFields.length" class="card animate-fade-up p-5 sm:p-6">
        <h2 class="mb-1 font-semibold">{{ category?.name }} details</h2>
        <p class="mb-4 text-xs text-muted">Custom fields defined for this category.</p>
        <CustomFieldInputs v-model="form.custom_data" :fields="customFields" :errors="typeof errors.custom_data === 'object' ? errors.custom_data : {}" />
      </section>

      <section class="card animate-fade-up p-5 sm:p-6">
        <h2 class="mb-4 font-semibold">Purchase & warranty</h2>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <EntityPicker v-model="form.vendor" label="Vendor" :fetcher="pick.vendors" :initial="initial.vendor" />
          <AppInput v-model="form.purchase_date" label="Purchase date" type="date" :max="todayISO()" :error="errors.purchase_date" />
          <div class="grid grid-cols-[minmax(0,1fr)_88px] gap-2">
            <AppInput v-model="form.purchase_cost" label="Cost" type="number" min="0" step="0.01" :error="errors.purchase_cost" />
            <AppInput v-model="form.currency" label="Currency" maxlength="3" :error="errors.currency" />
          </div>
          <AppInput v-model="form.invoice_number" label="Invoice #" />
          <AppInput v-model="form.po_number" label="PO #" />
          <AppInput v-model="form.warranty_expiry" label="Warranty expires" type="date" :error="errors.warranty_expiry" />
        </div>
      </section>

      <section class="card animate-fade-up p-5 sm:p-6">
        <h2 class="mb-4 font-semibold">Location & maintenance</h2>
        <div class="grid gap-4 sm:grid-cols-3">
          <EntityPicker v-model="form.location" label="Location" :fetcher="pick.locations" :initial="initial.location" />
          <AppInput v-model="form.maintenance_interval_days" label="Service every (days)" type="number" min="1" hint="Leave empty if not serviced" />
          <AppInput v-model="form.next_maintenance_date" label="Next service" type="date" />
          <AppInput v-model="form.notes" label="Internal notes" textarea :rows="2" class="sm:col-span-3" />
        </div>
      </section>

      <div class="safe-bottom sticky bottom-20 z-10 flex justify-end gap-2 lg:bottom-4">
        <div class="glass-strong flex gap-2 rounded-2xl p-2">
          <AppButton variant="secondary" :to="editing ? `/assets/${id}` : '/assets'">Cancel</AppButton>
          <AppButton type="submit" :icon="Save" :loading="saving">{{ editing ? 'Save changes' : `Create ${assetNames.singular.toLowerCase()}` }}</AppButton>
        </div>
      </div>
    </div>
  </form>
</template>
