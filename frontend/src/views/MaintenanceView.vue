<script setup>
import ReminderButton from '@/components/reminders/ReminderButton.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { CheckCircle2, Columns3, Pencil, Play, Plus, Wrench, XCircle } from 'lucide-vue-next'
import { maintenanceApi } from '@/api'
import { parseError } from '@/api/http'
import { useList } from '@/composables/useList'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppTabs from '@/components/ui/AppTabs.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import ColumnsPanel from '@/components/table/ColumnsPanel.vue'
import { useTableConfig } from '@/composables/useTableConfig'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import MaintenanceFormModal from '@/components/workflows/MaintenanceFormModal.vue'
import { formatDate, inSentence } from '@/utils/format'

const ui = useUiStore()
const notes = useNotificationsStore()
const cfg = useTableConfig('maintenance', { resource: '/maintenance', names: { plural: 'Maintenance', singular: 'Maintenance job' } })
const names = cfg.names
const list = useList(maintenanceApi.list, {
  filters: { search: '', status: 'scheduled,in_progress', ordering: 'scheduled_date' },
  extraParams: () => cfg.params.value,
  onData: cfg.setFromList,
})
watch(cfg.pageItemId, () => list.load())
const columnsOpen = ref(false)
const sortBy = (key) => (list.filters.ordering = list.filters.ordering === key ? `-${key}` : key)
onMounted(list.load)
watch(() => notes.dashboardTick, () => list.load())

const formOpen = ref(false)
const editing = ref(null)
const tab = computed({
  get: () => list.filters.status || 'all',
  set: (v) => {
    list.filters.status = v === 'all' ? '' : v
    list.filters.ordering = v === 'completed' ? '-completed_date' : 'scheduled_date'
  },
})
const tabs = [
  { value: 'scheduled,in_progress', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'all', label: 'All' },
]

async function act(rec, action) {
  try {
    if (action === 'complete') {
      const res = await ui.confirm({ title: `Complete “${rec.title}”`, confirmText: 'Mark complete', input: { label: 'Final cost (optional)', placeholder: rec.cost || '0.00' } })
      if (!res) return
      const cost = res.value?.trim()
      await maintenanceApi.action(rec.id, 'complete', cost ? { cost } : {})
    } else if (action === 'cancel') {
      if (!(await ui.confirm({ title: 'Cancel this maintenance?', confirmText: 'Cancel it', danger: true }))) return
      await maintenanceApi.action(rec.id, 'cancel')
    } else {
      await maintenanceApi.action(rec.id, action)
    }
    ui.success('Maintenance updated')
    list.load()
  } catch (e) {
    ui.error(parseError(e).message)
  }
}
function edit(rec) {
  editing.value = rec
  formOpen.value = true
}
function create() {
  editing.value = null
  formOpen.value = true
}

const bulkConfig = computed(() => ({
  resource: '/maintenance',
  params: () => ({ ...list.params(), ...cfg.params.value }),
  count: list.count.value,
  singular: names.value.singular,
  plural: names.value.plural,
  canDelete: true,
  canExport: true,
}))
</script>

<template>
  <div>
    <PageHeader :title="names.plural" :subtitle="names.description || 'Preventive service, repairs and inspections'">
      <template #actions>
        <ReminderButton :section="cfg.pageItemId.value" />
        <AppButton variant="secondary" :icon="Columns3" @click="columnsOpen = true">Columns</AppButton>
        <AppButton :icon="Plus" @click="create">Add {{ names.singular }}</AppButton>
      </template>
    </PageHeader>
    <div class="card p-3 sm:p-4">
      <AppTabs v-model="tab" :tabs="tabs" />
      <SearchInput v-model="list.filters.search" class="mt-3" placeholder="Search work, asset, technician…" />
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
          @sort="sortBy"
          @changed="list.load()"
        >
          <template #cell-title="{ row }">
            <p class="font-medium">{{ row.title }}</p>
            <p class="text-xs text-muted">{{ row.kind_display }}<template v-if="row.technician"> · {{ row.technician }}</template><template v-if="row.vendor_name"> · {{ row.vendor_name }}</template></p>
          </template>
          <template #cell-asset_tag="{ row }">
            <RouterLink :to="`/assets/${row.asset}`" class="hover:text-accent"><span class="font-mono text-xs">{{ row.asset_tag }}</span> <span class="text-sm">{{ row.asset_name }}</span></RouterLink>
          </template>
          <template #cell-actions="{ row }">
            <div class="flex justify-end gap-1">
              <AppButton v-if="row.status === 'scheduled'" size="sm" variant="subtle" :icon="Play" @click="act(row, 'start')">Start</AppButton>
              <AppButton v-if="['scheduled', 'in_progress'].includes(row.status)" size="sm" variant="secondary" :icon="CheckCircle2" @click="act(row, 'complete')">Done</AppButton>
              <AppButton v-if="['scheduled', 'in_progress'].includes(row.status)" size="sm" variant="ghost" :icon="Pencil" aria-label="Edit" @click="edit(row)" />
              <AppButton v-if="['scheduled', 'in_progress'].includes(row.status)" size="sm" variant="ghost" :icon="XCircle" aria-label="Cancel" @click="act(row, 'cancel')" />
            </div>
          </template>
          <template #mobile="{ row }">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate font-medium">{{ row.title }}</p>
                <p class="truncate text-xs text-muted"><span class="font-mono">{{ row.asset_tag }}</span> · {{ formatDate(row.scheduled_date) }}</p>
              </div>
              <StatusBadge kind="maintenance" :status="row.status" />
            </div>
            <div v-if="['scheduled', 'in_progress'].includes(row.status)" class="mt-3 flex gap-2">
              <AppButton v-if="row.status === 'scheduled'" size="sm" variant="subtle" :icon="Play" @click="act(row, 'start')">Start</AppButton>
              <AppButton size="sm" variant="secondary" :icon="CheckCircle2" @click="act(row, 'complete')">Done</AppButton>
              <AppButton size="sm" variant="ghost" :icon="Pencil" @click="edit(row)">Edit</AppButton>
            </div>
          </template>
          <template #empty>
            <EmptyState :icon="Wrench" :title="`No ${inSentence(names.plural)} here`" message="Schedule preventive service or log a repair."><AppButton :icon="Plus" @click="create">Schedule</AppButton></EmptyState>
          </template>
        </ConfigurableTable>
        <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
      </div>
    </div>
    <MaintenanceFormModal v-model:open="formOpen" :record="editing" @saved="list.load()" />
    <ColumnsPanel v-model:open="columnsOpen" :cfg="cfg" title="Maintenance table columns" />
  </div>
</template>
