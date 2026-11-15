<script setup>
import { onMounted, ref } from 'vue'
import { ScrollText } from 'lucide-vue-next'
import { auditApi } from '@/api'
import { useList } from '@/composables/useList'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import DataTable from '@/components/ui/DataTable.vue'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { formatDateTime } from '@/utils/format'

const list = useList(auditApi.list, { filters: { search: '', action: '', model: '', date_from: '' }, pageSize: 50 })
onMounted(list.load)
const detail = ref(null)

const ACTIONS = ['create', 'update', 'delete', 'login', 'login_failed', 'logout', 'password_change', 'status_change', 'sign', 'cancel', 'import', 'export', 'bulk_update']
const MODELS = ['assets.asset', 'workflows.handover', 'workflows.goodsreceipt', 'maintenance.maintenancerecord', 'assets.category', 'assets.location', 'assets.vendor', 'accounts.user', 'accounts.department']
const tone = (a) => ({ create: 'emerald', update: 'primary', delete: 'rose', login_failed: 'rose', sign: 'violet', status_change: 'amber', import: 'lime', export: 'lime' })[a] || 'slate'
const columns = [
  { key: 'created_at', label: 'When' },
  { key: 'actor_name', label: 'Who' },
  { key: 'action', label: 'Action' },
  { key: 'object_repr', label: 'Object' },
  { key: 'ip_address', label: 'IP', class: 'hidden lg:table-cell' },
]
</script>

<template>
  <div>
    <PageHeader title="Audit log" subtitle="Immutable record of every change, sign-in and export" />
    <div class="card p-3 sm:p-4">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_170px_220px_170px]">
        <SearchInput v-model="list.filters.search" placeholder="Search object, user, IP, request id…" />
        <AppSelect v-model="list.filters.action" placeholder="All actions" :options="ACTIONS.map((a) => ({ value: a, label: a.replace('_', ' ') }))" aria-label="Action" />
        <AppSelect v-model="list.filters.model" placeholder="All records" :options="MODELS.map((m) => ({ value: m, label: m.split('.')[1] }))" aria-label="Record type" />
        <AppInput v-model="list.filters.date_from" type="date" aria-label="From date" />
      </div>
      <div class="mt-3">
        <DataTable :columns="columns" :rows="list.items.value" :loading="list.loading.value" clickable @row-click="(r) => (detail = r)">
          <template #cell-created_at="{ value }"><span class="text-sm whitespace-nowrap text-muted">{{ formatDateTime(value) }}</span></template>
          <template #cell-actor_name="{ row }"><span class="text-sm">{{ row.actor_name }}</span></template>
          <template #cell-action="{ value }"><AppBadge :tone="tone(value)">{{ value.replace('_', ' ') }}</AppBadge></template>
          <template #cell-object_repr="{ row }"><span class="text-sm"><span class="text-xs text-muted">{{ row.model }}</span> {{ row.object_repr }}</span></template>
          <template #cell-ip_address="{ value }"><span class="font-mono text-xs text-muted">{{ value || '—' }}</span></template>
          <template #empty><EmptyState :icon="ScrollText" title="No entries match" /></template>
        </DataTable>
        <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
      </div>
    </div>
    <AppModal :open="!!detail" :title="detail ? `${detail.action} · ${detail.object_repr || detail.model}` : ''" size="lg" @update:open="(v) => !v && (detail = null)">
      <dl v-if="detail" class="mb-4 grid gap-2 text-sm sm:grid-cols-2">
        <div><dt class="text-xs text-muted">Actor</dt><dd>{{ detail.actor_name }} {{ detail.actor_email ? `(${detail.actor_email})` : '' }}</dd></div>
        <div><dt class="text-xs text-muted">When</dt><dd>{{ formatDateTime(detail.created_at) }}</dd></div>
        <div><dt class="text-xs text-muted">IP</dt><dd class="font-mono text-xs">{{ detail.ip_address || '—' }}</dd></div>
        <div><dt class="text-xs text-muted">Request ID</dt><dd class="truncate font-mono text-xs">{{ detail.request_id || '—' }}</dd></div>
        <div class="sm:col-span-2"><dt class="text-xs text-muted">User agent</dt><dd class="truncate text-xs">{{ detail.user_agent || '—' }}</dd></div>
      </dl>
      <pre v-if="detail" class="max-h-96 overflow-auto rounded-2xl bg-surface-hover p-4 text-xs">{{ JSON.stringify(detail.changes, null, 2) }}</pre>
    </AppModal>
  </div>
</template>
