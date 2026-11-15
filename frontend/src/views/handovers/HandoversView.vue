<script setup>
import ReminderButton from '@/components/reminders/ReminderButton.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeftRight, Columns3, FileText, Plus } from 'lucide-vue-next'
import { handoversApi } from '@/api'
import { downloadFile } from '@/api/http'
import { useList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppTabs from '@/components/ui/AppTabs.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import ColumnsPanel from '@/components/table/ColumnsPanel.vue'
import { useTableConfig } from '@/composables/useTableConfig'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { HANDOVER_TYPES } from '@/utils/constants'

const auth = useAuthStore()
const notes = useNotificationsStore()
const router = useRouter()
const cfg = useTableConfig('handovers', { resource: '/handovers', names: { plural: 'Handovers', singular: 'Handover' } })
const names = cfg.names
const list = useList(handoversApi.list, {
  filters: { search: '', status: '', type: '', awaiting_me: '', ordering: '-created_at' },
  extraParams: () => cfg.params.value,
  onData: cfg.setFromList,
})
watch(cfg.pageItemId, () => list.load())
const columnsOpen = ref(false)
const sortBy = (key) => (list.filters.ordering = list.filters.ordering === key ? `-${key}` : key)
onMounted(list.load)
watch(() => notes.dashboardTick, () => list.load())

const tab = computed({
  get: () => (list.filters.awaiting_me ? 'mine' : list.filters.status || 'all'),
  set: (v) => {
    list.filters.awaiting_me = v === 'mine' ? '1' : ''
    list.filters.status = ['pending', 'completed', 'cancelled'].includes(v) ? v : ''
  },
})
const tabs = [
  { value: 'all', label: 'All' },
  { value: 'mine', label: 'Awaiting me' },
  { value: 'pending', label: 'Pending' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
]

const bulkConfig = computed(() => ({
  resource: '/handovers',
  params: () => ({ ...list.params(), ...cfg.params.value }),
  count: list.count.value,
  singular: names.value.singular,
  plural: names.value.plural,
  canDelete: auth.isManager,
  canExport: auth.isManager,
}))
</script>

<template>
  <div>
    <PageHeader :title="names.plural" :subtitle="names.description || 'Issue, return and transfer records with digital sign-off'">
      <template #actions>
        <ReminderButton :section="cfg.pageItemId.value" />
        <AppButton variant="secondary" :icon="Columns3" @click="columnsOpen = true">Columns</AppButton>
        <template v-if="auth.isManager">
          <AppButton :icon="Plus" to="/handovers/new">Add {{ names.singular }}</AppButton>
        </template>
      </template>
    </PageHeader>

    <div class="card p-3 sm:p-4">
      <AppTabs v-model="tab" :tabs="tabs" />
      <div class="mt-3 flex flex-col gap-3 sm:flex-row">
        <SearchInput v-model="list.filters.search" class="flex-1" placeholder="Search reference, person, asset tag…" />
        <AppSelect v-model="list.filters.type" class="sm:w-44" placeholder="All types" :options="Object.entries(HANDOVER_TYPES).map(([value, m]) => ({ value, label: m.label }))" aria-label="Type" />
      </div>
      <div class="mt-3">
        <ConfigurableTable
          :bulk="bulkConfig"
          :columns="cfg.visibleColumns.value"
          :extra-columns="[{ key: 'actions', label: '', align: 'right', mobile: false }]"
          :rows="list.items.value"
          :loading="list.loading.value"
          :offset="(list.page.value - 1) * 25"
          :ordering="list.filters.ordering"
          :editable-values="cfg.canEditValues.value"
          :save-value="cfg.setCustomValue"
          clickable
          @row-click="(r) => router.push(`/handovers/${r.id}`)"
          @sort="sortBy"
          @changed="list.load()"
        >
          <template #cell-reference="{ row }">
            <div class="flex items-center gap-2">
              <span class="font-mono font-medium">{{ row.reference }}</span>
              <AppBadge :tone="HANDOVER_TYPES[row.type]?.tone">{{ row.type_display }}</AppBadge>
            </div>
          </template>
          <template #cell-actions="{ row }"><AppButton size="sm" variant="ghost" :icon="FileText" aria-label="PDF receipt" @click.stop="downloadFile(`/handovers/${row.id}/pdf/`, { open: true })" /></template>
          <template #empty>
            <EmptyState :icon="ArrowLeftRight" :title="tab === 'mine' ? 'Nothing awaiting your signature' : `No ${names.plural.toLowerCase()}`" :message="tab === 'mine' ? 'You are all caught up.' : undefined">
              <AppButton v-if="auth.isManager && tab !== 'mine'" :icon="Plus" to="/handovers/new">New handover</AppButton>
            </EmptyState>
          </template>
        </ConfigurableTable>
        <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
      </div>
    </div>
    <ColumnsPanel v-model:open="columnsOpen" :cfg="cfg" title="Handover table columns" />
  </div>
</template>
