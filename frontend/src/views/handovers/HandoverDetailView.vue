<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Ban, CheckCircle2, FileText, PenLine } from 'lucide-vue-next'
import { handoversApi } from '@/api'
import { downloadFile, parseError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useTableNames } from '@/composables/useTableNames'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import SignaturePad from '@/components/ui/SignaturePad.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UserAvatar from '@/components/ui/UserAvatar.vue'
import { HANDOVER_TYPES } from '@/utils/constants'
import { formatDate, formatDateTime } from '@/utils/format'

const route = useRoute()
const auth = useAuthStore()
const ui = useUiStore()
const notes = useNotificationsStore()
const h = ref(null)
const error = ref('')
const signature = ref('')
const signedName = ref('')
const signing = ref(false)
const agreed = ref(false)

async function load() {
  try {
    h.value = await handoversApi.get(route.params.id)
    signedName.value ||= h.value.signer_detail?.full_name || auth.user?.full_name || ''
  } catch (e) {
    error.value = e.response?.status === 404 ? 'This handover does not exist or is not addressed to you.' : parseError(e).message
  }
}
onMounted(load)
watch(() => notes.dashboardTick, () => h.value?.status === 'pending' && load())

const from = computed(() => h.value?.from_user_detail?.full_name || h.value?.from_department_name || 'Store')
const to = computed(() => h.value?.to_user_detail?.full_name || h.value?.to_department_name || (h.value?.type === 'return' ? 'Store' : '—'))
const iAmSigner = computed(() => h.value?.signer === auth.user?.id)

async function sign() {
  if (!signature.value) return ui.warning('Please draw your signature.')
  signing.value = true
  try {
    h.value = await handoversApi.sign(h.value.id, { signature: signature.value, signed_name: signedName.value })
    ui.success('Handover signed — thank you!')
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    signing.value = false
  }
}
async function cancel() {
  const res = await ui.confirm({ title: `Cancel ${h.value.reference}?`, confirmText: 'Cancel handover', danger: true, input: { label: 'Reason', placeholder: 'Optional' } })
  if (!res) return
  try {
    h.value = await handoversApi.cancel(h.value.id, res.value)
    ui.success('Handover cancelled')
  } catch (e) {
    ui.error(parseError(e).message)
  }
}
const pdf = () => downloadFile(`/handovers/${h.value.id}/pdf/`, { open: true }).catch((e) => ui.error(parseError(e).message))
const hoNames = useTableNames('handovers', { plural: 'Handovers', singular: 'Handover', route: '/handovers' })
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <div v-if="error" class="card"><EmptyState title="Handover unavailable" :message="error"><AppButton to="/handovers">All handovers</AppButton></EmptyState></div>
    <div v-else-if="!h" class="space-y-4"><div class="skeleton h-10 w-64" /><div class="skeleton h-72" /></div>
    <template v-else>
      <PageHeader :crumbs="[{ label: hoNames.plural, to: hoNames.route }, { label: h.reference }]">
        <template #title><span class="font-mono">{{ h.reference }}</span></template>
        <template #subtitle>
          <span class="flex flex-wrap items-center gap-2">
            <AppBadge :tone="HANDOVER_TYPES[h.type]?.tone">{{ h.type_display }}</AppBadge>
            <StatusBadge kind="handover" :status="h.status" />
            <span>Created {{ formatDateTime(h.created_at) }} by {{ h.created_by_name || 'system' }}</span>
          </span>
        </template>
        <template #actions>
          <AppButton variant="secondary" :icon="FileText" @click="pdf">Receipt PDF</AppButton>
          <AppButton v-if="auth.isManager && h.status === 'pending'" variant="ghost" :icon="Ban" @click="cancel">Cancel</AppButton>
        </template>
      </PageHeader>

      <div class="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:items-center">
        <div class="card flex items-center gap-3 p-4">
          <UserAvatar :name="from" />
          <div class="min-w-0"><p class="text-xs text-muted">From</p><p class="truncate font-medium">{{ from }}</p></div>
        </div>
        <div class="hidden h-px w-12 bg-gradient-accent md:block" />
        <div class="card flex items-center gap-3 p-4">
          <UserAvatar :name="to" />
          <div class="min-w-0">
            <p class="text-xs text-muted">To</p>
            <p class="truncate font-medium">{{ to }}</p>
            <p v-if="h.to_location_name" class="truncate text-xs text-muted">📍 {{ h.to_location_name }}</p>
          </div>
        </div>
      </div>

      <section class="card mt-4 p-5">
        <h2 class="mb-3 font-semibold">{{ h.items.length }} asset{{ h.items.length === 1 ? '' : 's' }}</h2>
        <ul class="divide-y divide-line">
          <li v-for="i in h.items" :key="i.id" class="flex items-center gap-3 py-2.5">
            <RouterLink :to="`/assets/${i.asset}`" class="min-w-0 flex-1 hover:text-accent">
              <p class="truncate text-sm font-medium">{{ i.asset_name }}</p>
              <p class="truncate text-xs text-muted"><span class="font-mono">{{ i.asset_tag }}</span> · {{ i.category_name }} · {{ i.serial_number || 'no serial' }}</p>
            </RouterLink>
            <AppBadge>{{ i.condition }}</AppBadge>
          </li>
        </ul>
        <div v-if="h.notes || h.expected_return_date" class="mt-4 space-y-1 border-t border-line pt-4 text-sm">
          <p v-if="h.expected_return_date"><span class="text-muted">Expected return:</span> {{ formatDate(h.expected_return_date) }}</p>
          <p v-if="h.notes" class="text-muted">{{ h.notes }}</p>
        </div>
      </section>

      <section v-if="h.status === 'completed'" class="card mt-4 flex items-center gap-4 border-success/30 p-5">
        <CheckCircle2 class="h-8 w-8 shrink-0 text-success" />
        <div>
          <p class="font-semibold">Signed by {{ h.signed_name }}</p>
          <p class="text-sm text-muted">{{ formatDateTime(h.signed_at) }} · the PDF receipt includes the signatures.</p>
        </div>
      </section>
      <section v-else-if="h.status === 'cancelled'" class="card mt-4 p-5 text-sm text-muted">Cancelled {{ formatDateTime(h.cancelled_at) }}{{ h.cancel_reason ? ` — ${h.cancel_reason}` : '' }}</section>

      <section v-else-if="h.can_sign" class="card mt-4 p-5 sm:p-6">
        <h2 class="mb-1 flex items-center gap-2 font-semibold"><PenLine class="h-5 w-5 text-accent" /> {{ iAmSigner ? 'Your signature is required' : `Sign on behalf of ${h.signer_detail?.full_name || 'the recipient'} (in person)` }}</h2>
        <p class="mb-4 text-sm text-muted">
          I confirm that the assets listed above were {{ h.type === 'return' ? 'returned by me' : 'received by me' }} in the stated condition{{ h.type !== 'return' ? ' and I accept responsibility for their care under company policy' : '' }}.
        </p>
        <div class="grid gap-4 md:grid-cols-2">
          <div class="space-y-3">
            <AppInput v-model="signedName" label="Full name" />
            <label class="flex items-start gap-2 text-sm"><input v-model="agreed" type="checkbox" class="mt-0.5 h-4 w-4 accent-[var(--accent)]" /> I have checked the assets and agree.</label>
          </div>
          <SignaturePad v-model="signature" />
        </div>
        <div class="mt-5 flex justify-end">
          <AppButton :icon="PenLine" :loading="signing" :disabled="!agreed || !signature" @click="sign">Sign & complete</AppButton>
        </div>
      </section>
      <section v-else class="card mt-4 p-5 text-sm text-muted">Waiting for {{ h.signer_detail?.full_name || 'a manager' }} to sign.</section>
    </template>
  </div>
</template>
