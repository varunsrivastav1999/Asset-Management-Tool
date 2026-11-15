<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, Send, Signature, X } from 'lucide-vue-next'
import { assetsApi, handoversApi } from '@/api'
import { parseError } from '@/api/http'
import { assetLabel, assetSub, pick, userLabel, userSub } from '@/api/pickers'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useTableNames } from '@/composables/useTableNames'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import SignaturePad from '@/components/ui/SignaturePad.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { CONDITIONS, HANDOVER_TYPES } from '@/utils/constants'
import { todayISO } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

const icons = { issue: ArrowUpRight, transfer: ArrowLeftRight, return: ArrowDownLeft }
const type = ref(['issue', 'transfer', 'return'].includes(route.query.type) ? route.query.type : 'issue')
const assetIds = ref([])
const assetMap = ref(new Map())
const conditions = reactive({})
const form = reactive({ to_user: null, to_department: null, to_location: null, expected_return_date: '', notes: '' })
const mode = ref('remote') // remote | in_person
const signature = ref('')
const signedName = ref('')
const issuerSignature = ref('')
const saving = ref(false)
const errors = ref({})
const initialAssets = ref([])
const recipient = ref(null)

const assetFilter = computed(() => (type.value === 'issue' ? { status: 'in_stock' } : type.value === 'transfer' ? { status: 'assigned' } : { status: 'assigned,in_repair', unassigned: false }))
const assetFetcher = computed(() => pick.assets(assetFilter.value))
const selectedAssets = computed(() => assetIds.value.map((id) => assetMap.value.get(id)).filter(Boolean))
const holder = computed(() => {
  const a = selectedAssets.value[0]
  return a ? a.assigned_to?.full_name || a.department_name : null
})
const mixedHolders = computed(() => new Set(selectedAssets.value.map((a) => `${a.assigned_to?.id || ''}|${a.department || ''}`)).size > 1)
const needsRecipient = computed(() => type.value !== 'return')
const signerLabel = computed(() => (type.value === 'return' ? holder.value : recipient.value ? userLabel(recipient.value) : null))

onMounted(async () => {
  const ids = String(route.query.assets || '').split(',').map(Number).filter(Boolean)
  if (!ids.length) return
  const results = await Promise.allSettled(ids.map((id) => assetsApi.get(id)))
  const found = results.filter((r) => r.status === 'fulfilled').map((r) => r.value)
  found.forEach((a) => assetMap.value.set(a.id, a))
  initialAssets.value = found
  assetIds.value = found.map((a) => a.id)
})

watch(type, (t, old) => {
  if (old && t !== old) {
    assetIds.value = []
    errors.value = {}
  }
  router.replace({ query: { ...route.query, type: t, assets: undefined } })
})
watch(assetIds, (ids) => ids.forEach((id) => (conditions[id] ||= assetMap.value.get(id)?.condition || 'good')))
watch(recipient, (u) => {
  if (u && !signedName.value) signedName.value = userLabel(u)
})

function onAssetSelect(a) {
  assetMap.value.set(a.id, a)
}
function removeAsset(id) {
  assetIds.value = assetIds.value.filter((x) => x !== id)
}

async function submit() {
  errors.value = {}
  if (!assetIds.value.length) return (errors.value = { items: 'Select at least one asset.' })
  if (needsRecipient.value && !form.to_user && !form.to_department) return (errors.value = { to_user: 'Choose an employee or department.' })
  if (mode.value === 'in_person' && !signature.value) return (errors.value = { signature: 'Ask the employee to sign.' })
  saving.value = true
  const payload = {
    type: type.value,
    items: assetIds.value.map((id) => ({ asset: id, condition: conditions[id] })),
    notes: form.notes,
    to_location: form.to_location || null,
    ...(needsRecipient.value ? { to_user: form.to_user || null, to_department: form.to_department || null } : {}),
    ...(type.value === 'issue' && form.expected_return_date ? { expected_return_date: form.expected_return_date } : {}),
    ...(issuerSignature.value ? { issuer_signature: issuerSignature.value } : {}),
    ...(mode.value === 'in_person' ? { signature: signature.value, signed_name: signedName.value } : {}),
  }
  try {
    const h = await handoversApi.create(payload)
    ui.success(h.status === 'completed' ? `${h.reference} completed and signed` : `${h.reference} sent for signature`)
    router.replace(`/handovers/${h.id}`)
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}
const hoNames = useTableNames('handovers', { plural: 'Handovers', singular: 'Handover', route: '/handovers' })
</script>

<template>
  <form class="mx-auto max-w-4xl space-y-4" novalidate @submit.prevent="submit">
    <PageHeader :title="`Add ${hoNames.singular}`" subtitle="Issue, transfer or return assets with a signed receipt." :crumbs="[{ label: hoNames.plural, to: hoNames.route }, { label: 'New' }]" />

    <section class="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Handover type">
      <button
        v-for="(meta, key) in HANDOVER_TYPES"
        :key="key"
        type="button"
        role="radio"
        :aria-checked="type === key"
        class="card flex items-start gap-3 p-4 text-left transition"
        :class="type === key ? 'border-accent/60 ring-4 ring-[var(--glow)]' : 'hover:border-line-strong'"
        @click="type = key"
      >
        <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl" :class="type === key ? 'bg-gradient-accent text-accent-ink' : 'bg-surface-hover text-muted'">
          <component :is="icons[key]" class="h-5 w-5" />
        </span>
        <span>
          <span class="block font-semibold">{{ meta.label }}</span>
          <span class="block text-xs text-muted">{{ meta.hint }}</span>
        </span>
      </button>
    </section>

    <section class="card p-5 sm:p-6">
      <h2 class="mb-4 font-semibold">Assets</h2>
      <EntityPicker
        :key="type"
        v-model="assetIds"
        multiple
        :fetcher="assetFetcher"
        :label-of="assetLabel"
        :sublabel-of="assetSub"
        :initial="initialAssets"
        :placeholder="type === 'issue' ? 'Search in-stock assets…' : 'Search assigned assets…'"
        :error="errors.items"
        @select="onAssetSelect"
      />
      <p v-if="holder && type !== 'issue'" class="mt-3 text-sm" :class="mixedHolders ? 'text-danger' : 'text-muted'">
        {{ mixedHolders ? 'Selected assets have different holders — a handover must involve a single holder.' : `Currently held by ${holder}` }}
      </p>
      <TransitionGroup v-if="selectedAssets.length" tag="ul" name="list" class="mt-4 divide-y divide-line rounded-2xl border border-line">
        <li v-for="a in selectedAssets" :key="a.id" class="flex flex-wrap items-center gap-3 px-4 py-3">
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-medium">{{ a.name }}</p>
            <p class="truncate text-xs text-muted"><span class="font-mono">{{ a.asset_tag }}</span> · {{ a.serial_number || 'no serial' }}</p>
          </div>
          <StatusBadge :status="a.status" class="hidden sm:inline-flex" />
          <AppSelect v-model="conditions[a.id]" class="w-32" aria-label="Condition" :options="CONDITIONS" />
          <button type="button" class="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-danger" :aria-label="`Remove ${a.asset_tag}`" @click="removeAsset(a.id)"><X class="h-4 w-4" /></button>
        </li>
      </TransitionGroup>
    </section>

    <section class="card p-5 sm:p-6">
      <h2 class="mb-4 font-semibold">{{ type === 'return' ? 'Return to' : 'Recipient' }}</h2>
      <div class="grid gap-4 sm:grid-cols-2">
        <template v-if="needsRecipient">
          <EntityPicker v-model="form.to_user" label="Employee" :fetcher="pick.users" :label-of="userLabel" :sublabel-of="userSub" :error="errors.to_user" @select="(u) => (recipient = u)" />
          <EntityPicker v-model="form.to_department" label="Department" :fetcher="pick.departments" placeholder="Defaults to the employee's department" />
        </template>
        <EntityPicker v-model="form.to_location" label="Location" :fetcher="pick.locations" :placeholder="type === 'return' ? 'Store room / shelf' : 'Optional'" />
        <AppInput v-if="type === 'issue'" v-model="form.expected_return_date" label="Expected return" type="date" :min="todayISO()" hint="Optional — we'll alert if overdue" :error="errors.expected_return_date" />
        <AppInput v-model="form.notes" class="sm:col-span-2" label="Notes" textarea :rows="2" placeholder="Accessories included, purpose, etc." />
      </div>
    </section>

    <section class="card p-5 sm:p-6">
      <h2 class="mb-1 font-semibold">Sign-off</h2>
      <p class="mb-4 text-sm text-muted">Assets only change hands once the {{ type === 'return' ? 'returning employee' : 'recipient' }} signs.</p>
      <div class="mb-5 grid gap-2 sm:grid-cols-2">
        <button type="button" class="flex items-center gap-3 rounded-2xl border p-4 text-left transition" :class="mode === 'remote' ? 'border-accent bg-accent/10' : 'border-line'" @click="mode = 'remote'">
          <Send class="h-5 w-5 text-accent" />
          <span><b class="block text-sm">Send for signature</b><span class="text-xs text-muted">{{ signerLabel ? `${signerLabel} signs from their device` : 'The employee signs from their own device' }}</span></span>
        </button>
        <button type="button" class="flex items-center gap-3 rounded-2xl border p-4 text-left transition" :class="mode === 'in_person' ? 'border-accent bg-accent/10' : 'border-line'" @click="mode = 'in_person'">
          <Signature class="h-5 w-5 text-accent" />
          <span><b class="block text-sm">Sign now, in person</b><span class="text-xs text-muted">Hand this device over and complete immediately</span></span>
        </button>
      </div>
      <div class="grid gap-5 md:grid-cols-2">
        <div v-if="mode === 'in_person'" class="space-y-3">
          <AppInput v-model="signedName" label="Signer name" placeholder="Full name" />
          <SignaturePad v-model="signature" :label="type === 'return' ? 'Returned by' : 'Received by'" :error="errors.signature" />
        </div>
        <SignaturePad v-model="issuerSignature" :label="`Issued by ${auth.user?.full_name || 'you'} (optional)`" />
      </div>
    </section>

    <div class="safe-bottom sticky bottom-20 z-10 flex justify-end lg:bottom-4">
      <div class="glass-strong flex gap-2 rounded-2xl p-2">
        <AppButton variant="secondary" to="/handovers">Cancel</AppButton>
        <AppButton type="submit" :loading="saving" :disabled="mixedHolders">
          {{ mode === 'in_person' ? 'Complete handover' : 'Send for signature' }} · {{ assetIds.length }}
        </AppButton>
      </div>
    </div>
  </form>
</template>
