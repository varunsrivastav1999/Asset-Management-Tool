<script setup>
import { inSentence } from '@/utils/format'
import ReminderButton from '@/components/reminders/ReminderButton.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Archive, ArchiveRestore, Columns3, MoveRight, Pencil, Plus, Table2, Trash2 } from 'lucide-vue-next'
import { definitionsApi, recordsApi } from '@/api'
import { parseError } from '@/api/http'
import { useList } from '@/composables/useList'
import { useTableConfig } from '@/composables/useTableConfig'
import { useAuthStore } from '@/stores/auth'
import { useSidebarStore } from '@/stores/sidebar'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppTabs from '@/components/ui/AppTabs.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import ColumnsPanel from '@/components/table/ColumnsPanel.vue'
import RecordForm from '@/components/table/RecordForm.vue'

/** Generic page for admin-created tables (/t/<slug>). */
const route = useRoute()
const auth = useAuthStore()
const sidebar = useSidebarStore()
const ui = useUiStore()

const cfg = useTableConfig('custom', { resource: '/records', names: { plural: 'Records', singular: 'Record' } })
const names = cfg.names
const notFound = ref(false)
const view = ref('active')
const list = useList((p) => recordsApi.list(p), {
  filters: { search: '', ordering: '' },
  extraParams: () => ({ ...cfg.params.value, ...(view.value === 'archived' ? { archived: 1 } : {}) }),
  onData: cfg.setFromList,
})
const itemId = computed(() => cfg.pageItemId.value)
const dataColumns = computed(() => cfg.columns.value.filter((c) => !c.is_builtin))

async function load() {
  if (!sidebar.loaded) await sidebar.load()
  if (!itemId.value) {
    notFound.value = true
    return
  }
  notFound.value = false
  list.load().catch(() => {})
}
onMounted(load)
watch(() => route.params.slug, () => load())
watch(view, () => list.load())
watch(() => list.error.value, (e) => e && /not found/i.test(e) && (notFound.value = true))

const columnsOpen = ref(false)
const sortBy = (key) => (list.filters.ordering = list.filters.ordering === key ? `-${key}` : key)

// --- create / edit ---
const formOpen = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
function openForm(row = null) {
  if (!auth.isManager || view.value === 'archived') return
  editing.value = row
  errors.value = {}
  formOpen.value = true
}
async function save(customData) {
  saving.value = true
  errors.value = {}
  try {
    editing.value
      ? await recordsApi.update(itemId.value, editing.value.id, { custom_data: customData })
      : await recordsApi.create(itemId.value, { custom_data: customData })
    ui.success(`${names.value.singular} ${editing.value ? 'updated' : 'added'}`)
    formOpen.value = false
    list.load()
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = typeof fields.custom_data === 'object' ? fields.custom_data : fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}
const saveValue = async (row, key, value) => {
  const res = await recordsApi.update(itemId.value, row.id, { custom_data: { [key]: value } })
  row.custom_data = res.custom_data
}

async function removeOne(row) {
  const ok = await ui.confirm({
    title: `Delete this ${inSentence(names.value.singular)}?`,
    message: 'This cannot be undone. Archive it instead if you may need it later.',
    confirmText: 'Delete',
    danger: true,
    action: () => recordsApi.remove(itemId.value, row.id),
  })
  if (ok) {
    ui.success(`${names.value.singular} deleted`)
    list.load()
  }
}

// --- archive / restore / move ---
async function archive({ ids, all, clear }, restore = false) {
  const n = all ? list.count.value : ids.length
  const word = restore ? 'Restore' : 'Archive'
  const ok = await ui.confirm({
    title: `${word} ${n} ${inSentence(n === 1 ? names.value.singular : names.value.plural)}?`,
    message: restore ? 'They will show up in the table again.' : 'Archived rows are hidden from the table and exports, but kept.',
    confirmText: word,
    action: () => recordsApi.archive(itemId.value, all && !restore ? { all: true } : { ids, restore }),
  })
  if (ok) {
    ui.success(`${word}d ${ok.updated}`)
    clear()
    list.load()
  }
}
const moveOpen = ref(false)
const moveTarget = ref('')
const moveCtx = ref(null)
const targets = ref([])
async function openMove(ctx) {
  moveCtx.value = ctx
  moveTarget.value = ''
  targets.value = (await definitionsApi.list({ source: 'custom' })).filter((d) => d.sidebar_item !== itemId.value)
  moveOpen.value = true
}
async function doMove() {
  const { ids, all, clear } = moveCtx.value
  try {
    const res = await recordsApi.move(itemId.value, all ? { all: true, target: moveTarget.value } : { ids, target: moveTarget.value })
    ui.success(`Moved ${res.moved} to ${res.target}`)
    moveOpen.value = false
    clear()
    list.load()
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

const bulkConfig = computed(() => ({
  resource: '/records',
  params: () => ({ ...list.params(), ...cfg.params.value, ...(view.value === 'archived' ? { archived: 1 } : {}) }),
  count: list.count.value,
  singular: names.value.singular,
  plural: names.value.plural,
  canDelete: auth.isManager,
  canExport: auth.isManager && view.value === 'active',
}))
</script>

<template>
  <div>
    <div v-if="notFound" class="card mx-auto mt-10 max-w-md">
      <EmptyState :icon="Table2" title="Table not found" message="It may have been deleted, or it isn't shared with your role." />
    </div>
    <template v-else>
      <PageHeader :title="names.plural" :subtitle="names.description || `${list.count.value} ${inSentence(list.count.value === 1 ? names.singular : names.plural)}`">
        <template #actions>
          <ReminderButton :section="cfg.pageItemId.value" />
          <AppButton variant="secondary" :icon="Columns3" @click="columnsOpen = true">Columns</AppButton>
          <AppButton v-if="auth.isManager" :icon="Plus" @click="openForm()">Add {{ names.singular }}</AppButton>
        </template>
      </PageHeader>

      <div class="card p-3 sm:p-4">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchInput v-model="list.filters.search" class="flex-1" :placeholder="`Search ${inSentence(names.plural)}…`" />
          <AppTabs v-if="auth.isManager" v-model="view" :tabs="[{ value: 'active', label: 'Active' }, { value: 'archived', label: 'Archived' }]" />
        </div>
        <div class="mt-3">
          <p v-if="list.error.value && !notFound" class="p-3 text-sm text-danger">{{ list.error.value }}</p>
          <ConfigurableTable
            :bulk="bulkConfig"
            :columns="cfg.visibleColumns.value"
            :extra-columns="auth.isManager ? [{ key: '_actions', label: '', align: 'right', mobile: false }] : []"
            :rows="list.items.value"
            :loading="list.loading.value"
            :offset="(list.page.value - 1) * 25"
            :ordering="list.filters.ordering"
            :editable-values="auth.isManager && view === 'active'"
            :save-value="saveValue"
            :clickable="auth.isManager && view === 'active'"
            @row-click="openForm"
            @sort="sortBy"
            @changed="list.load()"
          >
            <template #bulk-actions="ctx">
              <template v-if="view === 'active'">
                <AppButton size="sm" variant="secondary" :icon="Archive" @click="archive(ctx)">Archive</AppButton>
                <AppButton size="sm" variant="secondary" :icon="MoveRight" @click="openMove(ctx)">Move</AppButton>
              </template>
              <AppButton v-else size="sm" variant="secondary" :icon="ArchiveRestore" :disabled="ctx.all" @click="archive(ctx, true)">Restore</AppButton>
            </template>
            <template #cell-_actions="{ row }">
              <div class="flex justify-end gap-1">
                <AppButton v-if="view === 'active'" size="sm" variant="ghost" :icon="Pencil" aria-label="Edit" @click.stop="openForm(row)" />
                <AppButton size="sm" variant="ghost" :icon="Trash2" aria-label="Delete" @click.stop="removeOne(row)" />
              </div>
            </template>
            <template #empty>
              <EmptyState :icon="Table2" :title="view === 'archived' ? 'Nothing archived' : `No ${inSentence(names.plural)} yet`">
                <AppButton v-if="auth.isManager && view === 'active'" :icon="Plus" @click="openForm()">Add {{ names.singular }}</AppButton>
              </EmptyState>
            </template>
          </ConfigurableTable>
          <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
        </div>
      </div>

      <RecordForm v-model:open="formOpen" :columns="dataColumns" :record="editing" :title="`${editing ? 'Edit' : 'Add'} ${inSentence(names.singular)}`" :saving="saving" :errors="errors" @save="save" />
      <ColumnsPanel v-model:open="columnsOpen" :cfg="cfg" :title="`${names.plural} columns`" />
      <AppModal v-model:open="moveOpen" title="Move to another table" size="sm">
        <AppSelect v-model="moveTarget" label="Target table" placeholder="Choose a table" :options="targets.map((t) => ({ value: t.id, label: t.name }))" />
        <p class="mt-2 text-xs text-muted">Values are matched by column key; columns the target doesn't have are kept but hidden.</p>
        <template #footer>
          <AppButton variant="secondary" @click="moveOpen = false">Cancel</AppButton>
          <AppButton :disabled="!moveTarget" @click="doMove">Move</AppButton>
        </template>
      </AppModal>
    </template>
  </div>
</template>
