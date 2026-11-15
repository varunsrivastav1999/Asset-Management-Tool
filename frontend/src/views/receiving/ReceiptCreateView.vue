<script setup>
import { appConfig } from '@/config'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Copy, PackageCheck, Plus, Trash2 } from 'lucide-vue-next'
import { categoriesApi, receiptsApi } from '@/api'
import { parseError } from '@/api/http'
import { pick } from '@/api/pickers'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useTableNames } from '@/composables/useTableNames'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import SignaturePad from '@/components/ui/SignaturePad.vue'
import CustomFieldInputs from '@/components/assets/CustomFieldInputs.vue'
import { CONDITIONS } from '@/utils/constants'
import { formatMoney, todayISO } from '@/utils/format'

const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()
const categories = ref([])
const saving = ref(false)
const errors = ref({})
let uid = 0

const newItem = () => ({ _id: ++uid, name: '', category: '', quantity: 1, serials: '', model: '', manufacturer: '', condition: 'new', unit_cost: '', currency: appConfig.currency, warranty_expiry: '', maintenance_interval_days: '', custom_data: {} })
const form = reactive({ vendor: null, received_date: todayISO(), invoice_number: '', po_number: '', location: null, notes: '', signed_name: auth.user?.full_name || '', signature: '' })
const items = ref([newItem()])

onMounted(async () => (categories.value = await categoriesApi.list({ is_active: true })))
const catOptions = computed(() => categories.value.map((c) => ({ value: String(c.id), label: c.parent_name ? `${c.parent_name} › ${c.name}` : c.name })))
const fieldsFor = (item) => {
  const c = categories.value.find((x) => String(x.id) === String(item.category))
  return c ? [...(c.inherited_fields || []), ...(c.custom_fields || [])] : []
}
const serialList = (item) => item.serials.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean)
const totalUnits = computed(() => items.value.reduce((n, i) => n + (Number(i.quantity) || 0), 0))
const totalValue = computed(() => items.value.reduce((n, i) => n + (Number(i.quantity) || 0) * (Number(i.unit_cost) || 0), 0))
const itemErrors = (idx) => (Array.isArray(errors.value.items) ? errors.value.items[idx] || {} : {})

function duplicate(item) {
  items.value.push({ ...item, _id: ++uid, serials: '', custom_data: { ...item.custom_data } })
}

async function save() {
  errors.value = {}
  saving.value = true
  const payload = {
    ...form,
    signature: form.signature || undefined,
    vendor: form.vendor || null,
    location: form.location || null,
    items: items.value.map((i) => ({
      name: i.name,
      category: i.category,
      quantity: Number(i.quantity) || 1,
      serial_numbers: serialList(i),
      model: i.model,
      manufacturer: i.manufacturer,
      condition: i.condition,
      unit_cost: i.unit_cost === '' ? null : i.unit_cost,
      currency: i.currency || appConfig.currency,
      warranty_expiry: i.warranty_expiry || null,
      maintenance_interval_days: i.maintenance_interval_days || null,
      custom_data: i.custom_data,
    })),
  }
  try {
    const receipt = await receiptsApi.create(payload)
    ui.success(`${receipt.reference}: ${receipt.asset_count} assets received`)
    router.replace(`/receiving/${receipt.id}`)
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = e.response?.data || fields
    ui.error(Array.isArray(e.response?.data?.items) ? 'Some items need attention.' : message)
  } finally {
    saving.value = false
  }
}
const grnNames = useTableNames('receipts', { plural: 'Goods receipts', singular: 'Goods receipt', route: '/receiving' })
</script>

<template>
  <form class="mx-auto max-w-5xl space-y-4" novalidate @submit.prevent="save">
    <PageHeader :title="`Add ${grnNames.singular}`" subtitle="Each unit becomes an in-stock asset with its own tag." :crumbs="[{ label: grnNames.plural, to: grnNames.route }, { label: 'New' }]" />

    <section class="card p-5 sm:p-6">
      <h2 class="mb-4 font-semibold">Delivery</h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <EntityPicker v-model="form.vendor" label="Vendor" :fetcher="pick.vendors" />
        <AppInput v-model="form.received_date" label="Received on" type="date" :max="todayISO()" required :error="errors.received_date" />
        <EntityPicker v-model="form.location" label="Store at" :fetcher="pick.locations" />
        <AppInput v-model="form.invoice_number" label="Invoice #" />
        <AppInput v-model="form.po_number" label="PO #" />
        <AppInput v-model="form.notes" label="Notes" />
      </div>
    </section>

    <TransitionGroup name="list" tag="div" class="space-y-4">
      <section v-for="(item, idx) in items" :key="item._id" class="card p-5 sm:p-6">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="font-semibold">Item {{ idx + 1 }}</h2>
          <div class="flex gap-1">
            <AppButton size="sm" variant="ghost" :icon="Copy" @click="duplicate(item)">Duplicate</AppButton>
            <AppButton v-if="items.length > 1" size="sm" variant="ghost" :icon="Trash2" aria-label="Remove item" @click="items.splice(idx, 1)" />
          </div>
        </div>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <AppInput v-model="item.name" class="sm:col-span-2" label="Name" required :error="itemErrors(idx).name" />
          <AppSelect v-model="item.category" label="Category" required placeholder="Select…" :options="catOptions" :error="itemErrors(idx).category" />
          <AppInput v-model="item.quantity" label="Quantity" type="number" min="1" max="500" :error="itemErrors(idx).quantity" />
          <AppInput v-model="item.manufacturer" label="Manufacturer" />
          <AppInput v-model="item.model" label="Model" />
          <AppSelect v-model="item.condition" label="Condition" :options="CONDITIONS" />
          <div class="grid grid-cols-[minmax(0,1fr)_76px] gap-2">
            <AppInput v-model="item.unit_cost" label="Unit cost" type="number" min="0" step="0.01" />
            <AppInput v-model="item.currency" label="Cur." maxlength="3" />
          </div>
          <AppInput v-model="item.warranty_expiry" label="Warranty until" type="date" />
          <AppInput v-model="item.maintenance_interval_days" label="Service every (days)" type="number" min="1" />
          <AppInput
            v-model="item.serials"
            class="sm:col-span-2"
            label="Serial numbers"
            textarea
            :rows="2"
            :hint="`${serialList(item).length} of ${item.quantity || 0} — one per line or comma-separated (optional)`"
            :error="itemErrors(idx).serial_numbers"
          />
        </div>
        <div v-if="fieldsFor(item).length" class="mt-4 border-t border-line pt-4">
          <CustomFieldInputs v-model="item.custom_data" :fields="fieldsFor(item)" :errors="itemErrors(idx).custom_data || {}" />
        </div>
      </section>
    </TransitionGroup>
    <AppButton variant="secondary" :icon="Plus" block @click="items.push(newItem())">Add another item</AppButton>

    <section class="card p-5 sm:p-6">
      <h2 class="mb-4 font-semibold">Sign-off</h2>
      <div class="grid gap-4 md:grid-cols-2">
        <div class="space-y-4">
          <AppInput v-model="form.signed_name" label="Received & verified by" />
          <div class="rounded-2xl border border-line p-4 text-sm">
            <p class="flex justify-between"><span class="text-muted">Units</span><b>{{ totalUnits }}</b></p>
            <p class="mt-1 flex justify-between"><span class="text-muted">Total value</span><b>{{ formatMoney(totalValue) }}</b></p>
          </div>
        </div>
        <SignaturePad v-model="form.signature" label="Signature (optional)" :error="errors.signature" />
      </div>
    </section>

    <div class="safe-bottom sticky bottom-20 z-10 flex justify-end lg:bottom-4">
      <div class="glass-strong flex gap-2 rounded-2xl p-2">
        <AppButton variant="secondary" to="/receiving">Cancel</AppButton>
        <AppButton type="submit" :icon="PackageCheck" :loading="saving">Receive {{ totalUnits }} asset{{ totalUnits === 1 ? '' : 's' }}</AppButton>
      </div>
    </div>
  </form>
</template>
