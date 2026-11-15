<script setup>
import ReminderButton from '@/components/reminders/ReminderButton.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Columns3, FileUp, Filter, MapPin, Plus, Printer, X } from 'lucide-vue-next'
import { assetsApi, categoriesApi, departmentsApi, locationsApi } from '@/api'
import { downloadFile, parseError } from '@/api/http'
import { pick } from '@/api/pickers'
import { useList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import ColumnsPanel from '@/components/table/ColumnsPanel.vue'
import { useTableConfig } from '@/composables/useTableConfig'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import CategoryIcon from '@/components/ui/CategoryIcon.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import ImportModal from '@/components/assets/ImportModal.vue'
import { ASSET_STATUS, CONDITIONS } from '@/utils/constants'
import { daysUntil, inSentence } from '@/utils/format'

const auth = useAuthStore()
const ui = useUiStore()
const notes = useNotificationsStore()
const router = useRouter()

const cfg = useTableConfig('assets', { resource: '/assets', names: { plural: 'Assets', singular: 'Asset' } })
const names = cfg.names
const list = useList(assetsApi.list, {
  filters: { search: '', status: [], category: '', department: '', location: '', condition: '', warranty_expiring_in: '', ordering: '-updated_at' },
  extraParams: () => cfg.params.value,
  onData: cfg.setFromList,
})
const columnsOpen = ref(false)
watch(cfg.pageItemId, () => list.load())
const { filters } = list
const selected = ref([])
const showFilters = ref(false)
const importOpen = ref(false)
const bulkOpen = ref(false)
const bulk = ref({ location: null, condition: '' })
const busy = ref(false)

const categories = ref([])
const departments = ref([])
const locations = ref([])
onMounted(async () => {
  list.load()
  const [c, d, l] = await Promise.allSettled([categoriesApi.list(), departmentsApi.list({ page_size: 200 }), locationsApi.list({ page_size: 200 })])
  categories.value = c.value || []
  departments.value = d.value?.results || []
  locations.value = l.value?.results || []
})
// Live: refresh the visible page when assets change elsewhere.
watch(() => notes.dashboardTick, () => !list.loading.value && list.load())


const activeFilterCount = computed(
  () => ['category', 'department', 'location', 'condition', 'warranty_expiring_in'].filter((k) => filters[k]).length + (filters.status.length ? 1 : 0),
)

function toggleStatus(s) {
  filters.status = filters.status.includes(s) ? filters.status.filter((x) => x !== s) : [...filters.status, s]
}

function sortBy(key) {
  list.filters.ordering = list.filters.ordering === key ? `-${key}` : key
}

async function printLabels() {
  try {
    await downloadFile('/assets/labels/', { method: 'post', data: { ids: selected.value }, open: true })
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

async function applyBulk() {
  const data = { ids: selected.value }
  if (bulk.value.location) data.location = bulk.value.location
  if (bulk.value.condition) data.condition = bulk.value.condition
  if (Object.keys(data).length < 2) return ui.warning('Choose at least one field to update.')
  busy.value = true
  try {
    const res = await assetsApi.bulkUpdate(data)
    ui.success(`${res.updated} ${inSentence(names.value.plural)} updated`)
    bulkOpen.value = false
    selected.value = []
    list.load()
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    busy.value = false
  }
}

const bulkConfig = computed(() => ({
  resource: '/assets',
  params: () => ({ ...list.params(), ...cfg.params.value }),
  count: list.count.value,
  singular: names.value.singular,
  plural: names.value.plural,
  canDelete: auth.isManager,
  canExport: auth.isManager,
  statusOptions: auth.isManager ? Object.entries(ASSET_STATUS).filter(([k]) => k !== 'assigned').map(([value, m]) => ({ value, label: m.label })) : [],
}))

function issueSelected() {
  router.push({ name: 'handover-new', query: { type: 'issue', assets: selected.value.join(',') } })
}

const catOptions = computed(() => categories.value.map((c) => ({ value: String(c.id), label: c.parent_name ? `${c.parent_name} › ${c.name}` : c.name })))
</script>

<template>
  <div>
    <PageHeader
      :title="auth.isManager ? names.plural : `My ${inSentence(names.plural)}`"
      :subtitle="names.description || `${list.count.value} ${inSentence(list.count.value === 1 ? names.singular : names.plural)}`"
    >
      <template #actions>
        <ReminderButton :section="cfg.pageItemId.value" />
        <AppButton variant="secondary" :icon="Columns3" @click="columnsOpen = true">Columns</AppButton>
        <template v-if="auth.isManager">
          <AppButton variant="secondary" :icon="FileUp" @click="importOpen = true">Import</AppButton>
          <AppButton :icon="Plus" to="/assets/new">Add {{ names.singular }}</AppButton>
        </template>
      </template>
    </PageHeader>

    <div class="card p-3 sm:p-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchInput v-model="filters.search" class="flex-1" placeholder="Search tag, name, serial, holder…" />
        <div class="flex gap-2">
          <AppSelect
            v-model="filters.ordering"
            class="min-w-40"
            aria-label="Sort"
            :options="[
              { value: '-updated_at', label: 'Recently updated' },
              { value: '-created_at', label: 'Newest' },
              { value: 'name', label: 'Name A–Z' },
              { value: 'asset_tag', label: 'Asset tag' },
              { value: 'warranty_expiry', label: 'Warranty ending' },
              { value: '-purchase_cost', label: 'Highest value' },
            ]"
          />
          <AppButton variant="secondary" :icon="Filter" @click="showFilters = !showFilters">
            Filters<span v-if="activeFilterCount" class="rounded-full bg-accent px-1.5 text-[10px] text-accent-ink">{{ activeFilterCount }}</span>
          </AppButton>
        </div>
      </div>

      <div class="mt-3 flex flex-wrap gap-1.5">
        <button
          v-for="(meta, s) in ASSET_STATUS"
          :key="s"
          class="chip transition"
          :class="filters.status.includes(s) ? 'border-transparent bg-accent/15 text-accent' : 'text-muted hover:text-ink'"
          @click="toggleStatus(s)"
        >
          <span class="h-1.5 w-1.5 rounded-full" :style="{ background: meta.color }" />{{ meta.label }}
        </button>
        <button v-if="activeFilterCount || filters.search" class="chip text-muted hover:text-danger" @click="list.reset()"><X class="h-3 w-3" /> Clear</button>
      </div>

      <Transition name="fade">
        <div v-if="showFilters" class="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-5">
          <AppSelect v-model="filters.category" label="Category" placeholder="All" :options="catOptions" />
          <AppSelect v-if="auth.isManager" v-model="filters.department" label="Department" placeholder="All" :options="departments.map((d) => ({ value: String(d.id), label: d.name }))" />
          <AppSelect v-model="filters.location" label="Location" placeholder="All" :options="locations.map((l) => ({ value: String(l.id), label: l.name }))" />
          <AppSelect v-model="filters.condition" label="Condition" placeholder="Any" :options="CONDITIONS" />
          <AppSelect
            v-model="filters.warranty_expiring_in"
            label="Warranty"
            placeholder="Any"
            :options="[{ value: '30', label: 'Ends ≤ 30 days' }, { value: '90', label: 'Ends ≤ 90 days' }, { value: '365', label: 'Ends ≤ 1 year' }]"
          />
        </div>
      </Transition>
    </div>

    <div class="card mt-3 p-1 sm:p-2">
      <p v-if="list.error.value" class="p-4 text-sm text-danger">{{ list.error.value }}</p>
      <ConfigurableTable
        v-model:selected="selected"
        :columns="cfg.visibleColumns.value"
        :rows="list.items.value"
        :loading="list.loading.value"
        :offset="(list.page.value - 1) * 25"
        :ordering="filters.ordering"
        :bulk="auth.isManager ? bulkConfig : null"
        :editable-values="cfg.canEditValues.value"
        :save-value="cfg.setCustomValue"
        clickable
        @row-click="(r) => router.push(`/assets/${r.id}`)"
        @sort="sortBy"
        @changed="list.load()"
      >
        <template #bulk-actions>
          <AppButton size="sm" variant="subtle" @click="issueSelected">Issue</AppButton>
          <AppButton size="sm" variant="secondary" :icon="MapPin" @click="bulkOpen = true">Bulk edit</AppButton>
          <AppButton size="sm" variant="secondary" :icon="Printer" @click="printLabels">Labels</AppButton>
        </template>
        <template #cell-name="{ row }">
          <div class="flex min-w-0 items-center gap-3">
            <img v-if="row.thumbnail" :src="row.thumbnail" alt="" class="h-10 w-10 shrink-0 rounded-xl object-cover ring-1 ring-line" loading="lazy" />
            <CategoryIcon v-else :name="row.category?.icon" :color="row.category?.color" />
            <div class="min-w-0">
              <p class="truncate font-medium">{{ row.name }}</p>
              <p class="truncate text-xs text-muted"><span class="font-mono">{{ row.asset_tag }}</span> · {{ row.category?.name }}<template v-if="row.serial_number"> · {{ row.serial_number }}</template></p>
            </div>
          </div>
        </template>
        <template #mobile="{ row }">
          <div class="flex items-center gap-3 pr-6">
            <img v-if="row.thumbnail" :src="row.thumbnail" alt="" class="h-12 w-12 shrink-0 rounded-xl object-cover" loading="lazy" />
            <CategoryIcon v-else :name="row.category?.icon" :color="row.category?.color" />
            <div class="min-w-0 flex-1">
              <p class="truncate font-medium">{{ row.name }}</p>
              <p class="truncate text-xs text-muted"><span class="font-mono">{{ row.asset_tag }}</span> · {{ row.assigned_to?.full_name || row.department_name || row.location_name || 'Unassigned' }}</p>
              <div class="mt-1.5 flex items-center gap-2">
                <StatusBadge :status="row.status" />
                <span v-if="row.warranty_expiry && daysUntil(row.warranty_expiry) <= 30" class="text-[11px] text-warning">Warranty {{ daysUntil(row.warranty_expiry) < 0 ? 'expired' : `${daysUntil(row.warranty_expiry)}d` }}</span>
              </div>
            </div>
          </div>
        </template>
        <template #empty>
          <EmptyState
            :title="`No ${inSentence(names.plural)} found`"
            :message="activeFilterCount || filters.search ? 'Try adjusting the filters.' : auth.isManager ? `Add your first ${inSentence(names.singular)} or import a spreadsheet.` : `No ${inSentence(names.plural)} are assigned to you yet.`"
          >
            <AppButton v-if="auth.isManager && !activeFilterCount" :icon="Plus" to="/assets/new">Add {{ names.singular }}</AppButton>
          </EmptyState>
        </template>
      </ConfigurableTable>
      <div class="px-3 pb-2"><AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" /></div>
    </div>

    <ImportModal v-model:open="importOpen" @imported="list.load()" />
    <ColumnsPanel v-model:open="columnsOpen" :cfg="cfg" :title="`${names.plural} columns`" />

    <AppModal v-model:open="bulkOpen" :title="`Bulk edit ${selected.length} ${inSentence(selected.length === 1 ? names.singular : names.plural)}`" size="sm">
      <div class="space-y-4">
        <EntityPicker v-model="bulk.location" label="Move to location" :fetcher="pick.locations" placeholder="Keep current" />
        <AppSelect v-model="bulk.condition" label="Set condition" placeholder="Keep current" :options="CONDITIONS" />
      </div>
      <template #footer>
        <AppButton variant="secondary" @click="bulkOpen = false">Cancel</AppButton>
        <AppButton :loading="busy" @click="applyBulk">Apply</AppButton>
      </template>
    </AppModal>
  </div>
</template>
