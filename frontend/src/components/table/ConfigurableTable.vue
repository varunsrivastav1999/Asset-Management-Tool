<script setup>
import { computed, ref, useSlots, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { ChevronDown, Download, RefreshCcw, Trash2, X } from 'lucide-vue-next'
import DataTable from '@/components/ui/DataTable.vue'
import AppButton from '@/components/ui/AppButton.vue'
import { downloadFile, http, parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import TableCell from './TableCell.vue'

/**
 * The one table every list page uses: renders columns from the server-side config, and (with `bulk`)
 * adds row selection, "select all N results", a bulk action bar (delete / export / change status)
 * and an export menu. Views can still override a built-in column's cell with a `cell-<key>` slot.
 *
 * bulk = {
 *   resource: '/assets',                 // API base of the resource
 *   params: () => ({...}),               // current filters + table_item (no paging)
 *   count: Number,                       // total rows matching the filters
 *   singular, plural,                    // names used in messages ("Delete 5 assets?")
 *   canDelete, canExport, statusOptions, // feature switches
 *   deleteVerb: 'Delete' | 'Deactivate',
 * }
 */
const selected = defineModel('selected', { type: Array, default: () => [] })
const props = defineProps({
  columns: { type: Array, required: true }, // visible column configs
  rows: { type: Array, default: () => [] },
  loading: Boolean,
  offset: { type: Number, default: 0 },
  ordering: { type: String, default: '' },
  selectable: Boolean,
  clickable: Boolean,
  editableValues: Boolean,
  saveValue: { type: Function, default: null },
  extraColumns: { type: Array, default: () => [] }, // non-config columns (e.g. row actions)
  bulk: { type: Object, default: null },
})
const emit = defineEmits(['row-click', 'sort', 'changed'])
const slots = useSlots()
const ui = useUiStore()

const tableColumns = computed(() => [
  ...props.columns.map((c) => ({
    key: c.key,
    label: c.name,
    sortable: c.is_sortable,
    width: c.width || (c.type === 'auto_number' ? 56 : undefined),
    align: c.type === 'number' ? 'right' : undefined,
    mobile: c.type !== 'auto_number',
  })),
  ...props.extraColumns,
])
const byKey = computed(() => Object.fromEntries(props.columns.map((c) => [c.key, c])))
const passthrough = computed(() => Object.keys(slots).filter((n) => n !== 'bulk-actions' && (!n.startsWith('cell-') || !byKey.value[n.slice(5)])))

// --- selection ---------------------------------------------------------------
const canSelect = computed(() => props.selectable || !!(props.bulk && (props.bulk.canDelete || props.bulk.canExport || props.bulk.statusOptions?.length)))
const allMatching = ref(false)
const pageIds = computed(() => props.rows.map((r) => r.id))
const pageFullySelected = computed(() => pageIds.value.length > 0 && pageIds.value.every((id) => selected.value.includes(id)))
const total = computed(() => props.bulk?.count ?? props.rows.length)
const selectionCount = computed(() => (allMatching.value ? total.value : selected.value.length))
watch(selected, (v) => {
  if (!v.length || !pageFullySelected.value) allMatching.value = false
})
// Filters changed → the "all matching" set changed too; start over.
watch(
  () => JSON.stringify(props.bulk?.params?.() || {}),
  () => {
    allMatching.value = false
    selected.value = []
  },
)
function clearSelection() {
  allMatching.value = false
  selected.value = []
}

const noun = (n) => (n === 1 ? props.bulk?.singular || 'row' : props.bulk?.plural || 'rows').toLowerCase()
const params = () => {
  const { page: _p, page_size: _ps, with_columns: _w, ...rest } = props.bulk?.params?.() || {}
  return rest
}
const target = () => (allMatching.value ? { all: true } : { ids: [...selected.value] })

function reportSkipped(res, verb) {
  const skipped = res.skipped || []
  if (!skipped.length) return
  const lines = skipped.slice(0, 3).map((s) => `• ${s.label}: ${s.reason}`)
  if (skipped.length > 3) lines.push(`…and ${skipped.length - 3} more`)
  ui.warning(lines.join('\n'), { title: `${skipped.length} ${noun(skipped.length)} not ${verb}`, timeout: 10000 })
}

async function bulkDelete() {
  const n = selectionCount.value
  const verbWord = props.bulk.deleteVerb || 'Delete'
  const res = await ui.confirm({
    title: `${verbWord} ${n} ${noun(n)}?`,
    message:
      verbWord === 'Delete'
        ? 'This cannot be undone. Rows that are still in use are skipped and listed afterwards.'
        : `They will lose access. Rows that can't be changed are skipped and listed afterwards.`,
    confirmText: `${verbWord} ${n}`,
    danger: true,
    action: () => http.post(`${props.bulk.resource}/bulk-delete/`, target(), { params: params() }).then((r) => r.data),
  })
  if (!res) return
  const verb = res.verb || 'deleted'
  if (res.deleted) ui.success(`${res.deleted} ${noun(res.deleted)} ${verb}.`)
  reportSkipped(res, verb)
  clearSelection()
  emit('changed')
}

const statusOpen = ref(false)
const statusMenu = ref(null)
onClickOutside(statusMenu, () => (statusOpen.value = false))
async function bulkStatus(opt) {
  statusOpen.value = false
  const n = selectionCount.value
  const res = await ui.confirm({
    title: `Change ${n} ${noun(n)} to “${opt.label}”?`,
    message: 'Rows where this change isn’t allowed are skipped and listed afterwards.',
    confirmText: 'Change status',
    action: () => http.post(`${props.bulk.resource}/bulk-status/`, { ...target(), status: opt.value }, { params: params() }).then((r) => r.data),
  })
  if (!res) return
  if (res.updated) ui.success(`${res.updated} ${noun(res.updated)} updated.`)
  reportSkipped(res, 'changed')
  clearSelection()
  emit('changed')
}

const exporting = ref(false)
async function exportRows(scope, fmt = 'csv') {
  exporting.value = true
  try {
    const p = { ...params(), file_format: fmt }
    if (scope === 'selected') {
      if (allMatching.value) p.scope = 'filtered'
      else Object.assign(p, { scope: 'selected', ids: selected.value.join(',') })
    } else p.scope = scope
    await downloadFile(`${props.bulk.resource}/export-table/`, { params: p })
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    exporting.value = false
  }
}
const exportOpen = ref(false)
const exportMenu = ref(null)
onClickOutside(exportMenu, () => (exportOpen.value = false))
</script>

<template>
  <div class="min-w-0">
    <!-- Toolbar: export menu -->
    <div v-if="bulk?.canExport" class="mb-2 flex justify-end">
      <div ref="exportMenu" class="relative">
        <AppButton size="sm" variant="ghost" :icon="Download" :loading="exporting" aria-haspopup="menu" :aria-expanded="exportOpen" @click="exportOpen = !exportOpen">
          Export <ChevronDown class="h-3.5 w-3.5" />
        </AppButton>
        <Transition name="fade">
          <div v-if="exportOpen" role="menu" class="glass-strong absolute right-0 z-30 mt-1 w-60 rounded-2xl p-1.5 text-sm">
            <button v-for="opt in [
              { scope: 'filtered', fmt: 'csv', label: 'Current view (CSV)' },
              { scope: 'filtered', fmt: 'xlsx', label: 'Current view (Excel)' },
              { scope: 'all', fmt: 'csv', label: `All ${bulk.plural?.toLowerCase() || 'rows'} (CSV)` },
              { scope: 'all', fmt: 'xlsx', label: `All ${bulk.plural?.toLowerCase() || 'rows'} (Excel)` },
            ]" :key="opt.label" role="menuitem" class="block w-full rounded-xl px-3 py-2 text-left hover:bg-surface-hover" @click="exportOpen = false; exportRows(opt.scope, opt.fmt)">{{ opt.label }}</button>
            <p class="px-3 pt-1 pb-1.5 text-[11px] text-muted">Uses your visible columns and their names.</p>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Bulk action bar -->
    <Transition name="fade">
      <div v-if="bulk && selectionCount" class="glass-strong sticky top-[4.5rem] z-10 mb-2 flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2 sm:px-4" role="region" aria-label="Bulk actions">
        <span class="text-sm font-medium">{{ selectionCount }} {{ noun(selectionCount) }} selected</span>
        <button class="rounded-lg p-1 text-muted hover:bg-surface-hover hover:text-ink" aria-label="Clear selection" @click="clearSelection"><X class="h-4 w-4" /></button>
        <div class="ml-auto flex flex-wrap items-center gap-2">
          <slot name="bulk-actions" :ids="selected" :all="allMatching" :clear="clearSelection" />
          <div v-if="bulk.statusOptions?.length" ref="statusMenu" class="relative">
            <AppButton size="sm" variant="secondary" :icon="RefreshCcw" @click="statusOpen = !statusOpen">Change status</AppButton>
            <div v-if="statusOpen" role="menu" class="glass-strong absolute right-0 z-30 mt-1 w-44 rounded-2xl p-1.5 text-sm">
              <button v-for="opt in bulk.statusOptions" :key="opt.value" role="menuitem" class="block w-full rounded-xl px-3 py-2 text-left hover:bg-surface-hover" @click="bulkStatus(opt)">{{ opt.label }}</button>
            </div>
          </div>
          <AppButton v-if="bulk.canExport" size="sm" variant="secondary" :icon="Download" @click="exportRows('selected')">Export CSV</AppButton>
          <AppButton v-if="bulk.canDelete" size="sm" variant="danger" :icon="Trash2" @click="bulkDelete">{{ bulk.deleteVerb || 'Delete' }}</AppButton>
        </div>
      </div>
    </Transition>

    <!-- "Select all N results" -->
    <div v-if="bulk && pageFullySelected && total > rows.length" class="mb-2 rounded-xl bg-primary-soft px-3 py-2 text-center text-sm">
      <template v-if="!allMatching">
        All {{ rows.length }} on this page are selected.
        <button class="font-semibold text-primary underline-offset-2 hover:underline" @click="allMatching = true">Select all {{ total }} {{ noun(total) }}</button>
      </template>
      <template v-else>
        All {{ total }} {{ noun(total) }} matching the current filters are selected.
        <button class="font-semibold text-primary underline-offset-2 hover:underline" @click="clearSelection">Clear selection</button>
      </template>
    </div>

    <DataTable
      v-model:selected="selected"
      :columns="tableColumns"
      :rows="rows"
      :loading="loading"
      :ordering="ordering"
      :selectable="canSelect"
      :clickable="clickable"
      @row-click="(r) => emit('row-click', r)"
      @sort="(k) => emit('sort', k)"
    >
      <template v-for="c in columns" :key="c.key" #[`cell-${c.key}`]="{ row, index }">
        <slot v-if="c.is_builtin && $slots[`cell-${c.key}`]" :name="`cell-${c.key}`" :row="row" :col="c" :index="index" />
        <TableCell v-else :col="c" :row="row" :index="index" :offset="offset" :editable="editableValues" :save="saveValue" />
      </template>
      <template v-for="name in passthrough" :key="name" #[name]="scope">
        <slot :name="name" v-bind="scope" />
      </template>
    </DataTable>
  </div>
</template>
