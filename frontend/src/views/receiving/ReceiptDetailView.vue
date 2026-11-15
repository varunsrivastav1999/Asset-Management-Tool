<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FileText, Printer } from 'lucide-vue-next'
import { assetsApi, receiptsApi } from '@/api'
import { downloadFile, parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useTableNames } from '@/composables/useTableNames'
import AppButton from '@/components/ui/AppButton.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import DataTable from '@/components/ui/DataTable.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { formatDate, formatDateTime, formatMoney } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const receipt = ref(null)
const assets = ref([])
const error = ref('')

onMounted(async () => {
  try {
    receipt.value = await receiptsApi.get(route.params.id)
    assets.value = (await assetsApi.list({ receipt: route.params.id, page_size: 200, ordering: 'asset_tag' })).results
  } catch (e) {
    error.value = parseError(e).message
  }
})
const labels = () => downloadFile('/assets/labels/', { method: 'post', data: { ids: assets.value.map((a) => a.id) }, open: true }).catch((e) => ui.error(parseError(e).message))
const grnNames = useTableNames('receipts', { plural: 'Goods receipts', singular: 'Goods receipt', route: '/receiving' })
</script>

<template>
  <div>
    <div v-if="error" class="card"><EmptyState title="Could not load receipt" :message="error" /></div>
    <div v-else-if="!receipt" class="skeleton h-64" />
    <template v-else>
      <PageHeader :title="receipt.reference" :subtitle="`Received ${formatDate(receipt.received_date)}${receipt.vendor_name ? ` from ${receipt.vendor_name}` : ''}`" :crumbs="[{ label: grnNames.plural, to: grnNames.route }, { label: receipt.reference }]">
        <template #actions>
          <AppButton variant="secondary" :icon="Printer" :disabled="!assets.length" @click="labels">Print labels</AppButton>
          <AppButton :icon="FileText" @click="downloadFile(`/receipts/${receipt.id}/pdf/`, { open: true })">GRN PDF</AppButton>
        </template>
      </PageHeader>
      <div class="grid gap-4 lg:grid-cols-3">
        <section class="card p-5">
          <dl class="space-y-3 text-sm">
            <div v-for="[k, v] in [['Vendor', receipt.vendor_name], ['Invoice #', receipt.invoice_number], ['PO #', receipt.po_number], ['Location', receipt.location_name], ['Received by', receipt.received_by_name], ['Assets', receipt.asset_count], ['Total value', formatMoney(receipt.total_value)]]" :key="k" class="flex justify-between gap-3">
              <dt class="text-muted">{{ k }}</dt><dd class="text-right font-medium">{{ v || '—' }}</dd>
            </div>
          </dl>
          <div class="mt-4 border-t border-line pt-4">
            <AppBadge v-if="receipt.is_signed" tone="emerald" dot>Signed by {{ receipt.signed_name }} · {{ formatDateTime(receipt.signed_at) }}</AppBadge>
            <AppBadge v-else tone="slate">Not signed</AppBadge>
          </div>
          <p v-if="receipt.notes" class="mt-4 text-sm text-muted">{{ receipt.notes }}</p>
        </section>
        <section class="card p-2 lg:col-span-2">
          <DataTable
            :columns="[{ key: 'asset_tag', label: 'Tag' }, { key: 'name', label: 'Asset' }, { key: 'serial_number', label: 'Serial' }, { key: 'status', label: 'Status' }]"
            :rows="assets"
            clickable
            @row-click="(r) => router.push(`/assets/${r.id}`)"
          >
            <template #cell-asset_tag="{ value }"><span class="font-mono">{{ value }}</span></template>
            <template #cell-status="{ row }"><StatusBadge :status="row.status" /></template>
          </DataTable>
        </section>
      </div>
    </template>
  </div>
</template>
