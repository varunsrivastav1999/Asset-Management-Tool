<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ExternalLink, Pencil, Plus, Table2, Trash2, X } from 'lucide-vue-next'
import { definitionsApi, sidebarApi } from '@/api'
import { parseError } from '@/api/http'
import { useSidebarStore } from '@/stores/sidebar'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import DataTable from '@/components/ui/DataTable.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import IconPicker from '@/components/settings/IconPicker.vue'
import RoleChecklist from '@/components/settings/RoleChecklist.vue'
import { iconFor } from '@/utils/icons'
import { COLUMN_TYPES, hasOptions, optionsPlaceholder, parseOptions } from '@/utils/columnTypes'

const ui = useUiStore()
const sidebar = useSidebarStore()
const router = useRouter()
const tables = ref([])
const groups = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    tables.value = await definitionsApi.list()
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  load()
  const tree = (await sidebarApi.tree()).items
  const out = []
  const walk = (nodes, depth) => nodes.forEach((n) => n.type === 'group' && (out.push({ value: n.id, label: `${'— '.repeat(depth)}${n.name}` }), walk(n.children || [], depth + 1)))
  walk(tree, 0)
  groups.value = out
})

const TYPES = COLUMN_TYPES

const open = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
const form = reactive({})
function openForm(t = null) {
  editing.value = t
  errors.value = {}
  Object.assign(form, {
    name: t?.name || '',
    singular: t?.singular || '',
    icon: t?.icon || 'list',
    description: t?.description || '',
    parent: '',
    visible_roles: t ? [...t.roles] : ['admin', 'manager', 'employee'],
    columns: t ? [] : [{ name: 'Name', type: 'text', options: '' }],
  })
  open.value = true
}

async function save() {
  saving.value = true
  errors.value = {}
  const payload = {
    name: form.name,
    singular: form.singular || form.name,
    icon: form.icon,
    description: form.description,
    visible_roles: form.visible_roles,
    ...(form.parent !== '' ? { parent: form.parent } : editing.value ? {} : { parent: null }),
    ...(editing.value
      ? {}
      : { columns: form.columns.filter((c) => c.name.trim()).map((c) => ({ name: c.name.trim(), type: c.type, options: parseOptions(c.type, c.options) })) }),
  }
  try {
    const t = editing.value ? await definitionsApi.update(editing.value.id, payload) : await definitionsApi.create(payload)
    ui.success(editing.value ? `“${t.name}” updated` : `Table “${t.name}” created`)
    open.value = false
    await Promise.all([load(), sidebar.load()])
    if (!editing.value) router.push(t.route)
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

async function remove(t) {
  let check
  try {
    check = await definitionsApi.deleteCheck(t.id)
  } catch (e) {
    return ui.error(parseError(e).message)
  }
  if (!check.can_delete) {
    await ui.confirm({ title: `“${t.name}” can't be deleted yet`, message: `${check.reason}\n\nOpen the table to archive or move its rows, then try again.`, confirmText: 'Open table' }).then((go) => go && router.push(t.route))
    return
  }
  const ok = await ui.confirm({
    title: `Delete the table “${t.name}”?`,
    message: 'Its menu entry and column settings are removed. This cannot be undone.',
    confirmText: 'Delete table',
    danger: true,
    action: () => definitionsApi.remove(t.id),
  })
  if (ok) {
    ui.success(`Table “${t.name}” deleted`)
    load()
    sidebar.load()
  }
}

const columns = [
  { key: 'name', label: 'Table' },
  { key: 'source', label: 'Type' },
  { key: 'row_count', label: 'Rows', align: 'right' },
  { key: 'route', label: 'Page', class: 'hidden md:table-cell' },
  { key: 'actions', label: '', align: 'right', mobile: false },
]
const singularHint = computed(() => (form.name ? `Used in buttons: “Add ${form.singular || form.name}”` : 'e.g. Equipment item'))
</script>

<template>
  <div>
    <PageHeader title="Tables" subtitle="Rename any table, or create your own. Names update in the menu, page titles, buttons and empty states.">
      <template #actions><AppButton :icon="Plus" @click="openForm()">New table</AppButton></template>
    </PageHeader>
    <div class="card p-2 sm:p-3">
      <DataTable :columns="columns" :rows="tables" :loading="loading" clickable @row-click="openForm">
        <template #cell-name="{ row }">
          <div class="flex items-center gap-3">
            <span class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary-soft text-primary"><component :is="iconFor(row.icon)" class="h-4 w-4" /></span>
            <div class="min-w-0">
              <p class="truncate font-medium">{{ row.name }}</p>
              <p class="truncate text-xs text-muted">{{ row.description || `One row: ${row.singular}` }}</p>
            </div>
          </div>
        </template>
        <template #cell-source="{ row }"><AppBadge :tone="row.source === 'custom' ? 'lime' : 'slate'">{{ row.source === 'custom' ? 'Custom' : 'Built-in' }}</AppBadge></template>
        <template #cell-route="{ row }"><span class="font-mono text-xs text-muted">{{ row.route }}</span></template>
        <template #cell-actions="{ row }">
          <div class="flex justify-end gap-1">
            <AppButton size="sm" variant="ghost" :icon="ExternalLink" :aria-label="`Open ${row.name}`" @click.stop="router.push(row.route)" />
            <AppButton size="sm" variant="ghost" :icon="Pencil" :aria-label="`Edit ${row.name}`" @click.stop="openForm(row)" />
            <AppButton size="sm" variant="ghost" :icon="Trash2" :aria-label="`Delete ${row.name}`" @click.stop="remove(row)" />
          </div>
        </template>
        <template #empty><EmptyState :icon="Table2" title="No tables" /></template>
      </DataTable>
    </div>

    <AppModal v-model:open="open" :title="editing ? `Edit “${editing.name}”` : 'New table'" size="lg">
      <form id="table-form" class="grid gap-4 sm:grid-cols-2" novalidate @submit.prevent="save">
        <AppInput v-model="form.name" label="Table name (plural)" placeholder="e.g. Equipment" required :error="errors.name" />
        <AppInput v-model="form.singular" label="One row is called" :hint="singularHint" :error="errors.singular" />
        <AppInput v-model="form.description" class="sm:col-span-2" label="Description" placeholder="Shown under the page title" :error="errors.description" />
        <AppSelect v-model="form.parent" :label="editing ? 'Move to menu group' : 'Menu group'" :placeholder="editing ? 'Keep current' : 'Top level'" :options="groups" />
        <RoleChecklist v-model="form.visible_roles" :error="errors.visible_roles" />
        <IconPicker v-model="form.icon" class="sm:col-span-2" />
        <div v-if="!editing" class="sm:col-span-2">
          <div class="mb-2 flex items-center justify-between">
            <span class="label mb-0">Columns</span>
            <AppButton size="sm" variant="subtle" :icon="Plus" @click="form.columns.push({ name: '', type: 'text', options: '' })">Add column</AppButton>
          </div>
          <div class="space-y-2">
            <div v-for="(c, i) in form.columns" :key="i" class="grid gap-2 rounded-2xl border border-line p-3 sm:grid-cols-[minmax(0,1fr)_150px_auto]">
              <AppInput v-model="c.name" :aria-label="`Column ${i + 1} name`" :placeholder="i === 0 ? 'Name (required column)' : 'Column name'" />
              <AppSelect v-model="c.type" :aria-label="`Column ${i + 1} type`" :options="TYPES" />
              <button v-if="form.columns.length > 1" type="button" class="self-center rounded-lg p-1.5 text-muted hover:bg-danger/10 hover:text-danger" :aria-label="`Remove column ${i + 1}`" @click="form.columns.splice(i, 1)"><X class="h-4 w-4" /></button>
              <AppInput v-if="hasOptions(c.type)" v-model="c.options" class="sm:col-span-3" :aria-label="`Column ${i + 1} options`" :placeholder="c.type === 'status' ? `Statuses, comma separated (default: ${optionsPlaceholder('status')})` : 'Options, comma separated'" />
            </div>
          </div>
          <p v-if="errors.columns" class="mt-1 text-xs text-danger">{{ errors.columns }}</p>
          <p class="mt-2 text-xs text-muted">An S.No column is added automatically. You can add, rename and reorder columns later from the table's Columns panel.</p>
        </div>
      </form>
      <template #footer>
        <AppButton v-if="editing" variant="ghost" class="sm:mr-auto" :icon="Trash2" @click="open = false; remove(editing)">Delete</AppButton>
        <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
        <AppButton type="submit" form="table-form" :loading="saving">{{ editing ? 'Save' : 'Create table' }}</AppButton>
      </template>
    </AppModal>
  </div>
</template>
