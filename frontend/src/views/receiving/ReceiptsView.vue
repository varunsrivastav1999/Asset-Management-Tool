<script setup>
import ReminderButton from '@/components/reminders/ReminderButton.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Columns3, FileText, PackagePlus, Plus } from 'lucide-vue-next'
import { receiptsApi } from '@/api'
import { downloadFile } from '@/api/http'
import { useList } from '@/composables/useList'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import ColumnsPanel from '@/components/table/ColumnsPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { useTableConfig } from '@/composables/useTableConfig'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

const router = useRouter()
const auth = useAuthStore()
const cfg = useTableConfig('receipts', { resource: '/receipts', names: { plural: 'Goods receipts', singular: 'Goods receipt' } })
const names = cfg.names
const list = useList(receiptsApi.list, { filters: { search: '', ordering: '' }, extraParams: () => cfg.params.value, onData: cfg.setFromList })
onMounted(list.load)
watch(cfg.pageItemId, () => list.load())
const columnsOpen = ref(false)
const sortBy = (key) => (list.filters.ordering = list.filters.ordering === key ? `-${key}` : key)

const bulkConfig = computed(() => ({
  resource: '/receipts',
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
    <PageHeader :title="names.plural" :subtitle="names.description || 'Inward goods received notes (GRN)'">
      <template #actions>
        <ReminderButton :section="cfg.pageItemId.value" />
        <AppButton variant="secondary" :icon="Columns3" @click="columnsOpen = true">Columns</AppButton>
        <AppButton :icon="Plus" to="/receiving/new">Add {{ names.singular }}</AppButton>
      </template>
    </PageHeader>
    <div class="card p-3 sm:p-4">
      <SearchInput v-model="list.filters.search" placeholder="Search reference, invoice, PO, vendor…" />
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
          @row-click="(r) => router.push(`/receiving/${r.id}`)"
          @sort="sortBy"
          @changed="list.load()"
        >
          <template #cell-reference="{ row }">
            <p class="font-mono font-medium">{{ row.reference }}</p>
            <p class="text-xs text-muted">{{ row.invoice_number ? `Inv ${row.invoice_number}` : '' }} {{ row.po_number ? `· PO ${row.po_number}` : '' }}</p>
          </template>
          <template #cell-actions="{ row }">
            <AppButton size="sm" variant="ghost" :icon="FileText" @click.stop="downloadFile(`/receipts/${row.id}/pdf/`, { open: true })">PDF</AppButton>
          </template>
          <template #empty>
            <EmptyState :icon="PackagePlus" :title="`No ${names.plural.toLowerCase()} yet`" message="Record deliveries from suppliers to add assets in bulk.">
              <AppButton :icon="Plus" to="/receiving/new">Add {{ names.singular }}</AppButton>
            </EmptyState>
          </template>
        </ConfigurableTable>
        <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
      </div>
    </div>
    <ColumnsPanel v-model:open="columnsOpen" :cfg="cfg" title="Receiving table columns" />
  </div>
</template>
