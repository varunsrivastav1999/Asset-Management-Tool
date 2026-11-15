<script setup>
import ReminderButton from '@/components/reminders/ReminderButton.vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Columns3, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { parseError } from '@/api/http'
import { useList } from '@/composables/useList'
import { useUiStore } from '@/stores/ui'
import PageHeader from './PageHeader.vue'
import AppButton from './AppButton.vue'
import AppInput from './AppInput.vue'
import AppSelect from './AppSelect.vue'
import AppModal from './AppModal.vue'
import SearchInput from './SearchInput.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import ColumnsPanel from '@/components/table/ColumnsPanel.vue'
import { useTableConfig } from '@/composables/useTableConfig'
import { useAuthStore } from '@/stores/auth'
import AppPagination from './AppPagination.vue'
import EmptyState from './EmptyState.vue'
import EntityPicker from './EntityPicker.vue'

/**
 * Config-driven list + create/edit modal.
 * fields: [{ key, label, type?: 'text'|'textarea'|'email'|'url'|'select'|'picker'|'checkbox', options?, fetcher?, required?, span? , initial?(row) }]
 */
const props = defineProps({
  title: String,
  subtitle: String,
  singular: String,
  api: { type: Object, required: true },
  /** Table definition key; columns come from the server-side column config. */
  table: { type: String, required: true },
  /** API base for bulk actions, e.g. '/locations'. */
  resource: { type: String, required: true },
  fields: { type: Array, required: true },
  canWrite: Boolean,
  canDelete: Boolean,
  icon: { type: [Object, Function], default: null },
})

const ui = useUiStore()
const auth = useAuthStore()
const cfg = useTableConfig(props.table, { resource: props.resource, names: { plural: props.title, singular: props.singular } })
const names = cfg.names
const list = useList(props.api.list, { filters: { search: '', ordering: '' }, extraParams: () => cfg.params.value, onData: cfg.setFromList })
onMounted(list.load)
watch(cfg.pageItemId, () => list.load())
const columnsOpen = ref(false)
const sortBy = (key) => (list.filters.ordering = list.filters.ordering === key ? `-${key}` : key)

const open = ref(false)
const editing = ref(null)
const form = reactive({})
const errors = ref({})
const saving = ref(false)
const initials = reactive({})

function openForm(row = null) {
  editing.value = row
  errors.value = {}
  for (const f of props.fields) {
    form[f.key] = row ? row[f.key] ?? (f.type === 'checkbox' ? false : f.type === 'picker' ? null : '') : f.default ?? (f.type === 'checkbox' ? true : f.type === 'picker' ? null : '')
    if (f.type === 'picker') initials[f.key] = row && f.initial ? f.initial(row) : []
  }
  open.value = true
}

async function save() {
  saving.value = true
  errors.value = {}
  try {
    const data = { ...form }
    editing.value ? await props.api.update(editing.value.id, data) : await props.api.create(data)
    ui.success(`${names.value.singular} ${editing.value ? 'updated' : 'created'}`)
    open.value = false
    list.load()
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  const ok = await ui.confirm({
    title: `Delete ${names.value.singular.toLowerCase()} “${row.name}”?`,
    message: 'This cannot be undone. Records still referenced elsewhere cannot be deleted — deactivate them instead.',
    confirmText: 'Delete',
    danger: true,
    action: () => props.api.remove(row.id),
  })
  if (!ok) return
  ui.success(`${names.value.singular} deleted`)
  list.load()
}

const bulkConfig = computed(() => ({
  resource: props.resource,
  params: () => ({ ...list.params(), ...cfg.params.value }),
  count: list.count.value,
  singular: names.value.singular,
  plural: names.value.plural,
  canDelete: props.canDelete,
  canExport: auth.isManager,
}))

const extra = props.canWrite ? [{ key: '_actions', label: '', align: 'right', mobile: false }] : []
</script>

<template>
  <div>
    <PageHeader :title="names.plural" :subtitle="names.description || subtitle">
      <template #actions>
        <ReminderButton :section="cfg.pageItemId.value" />
        <AppButton variant="secondary" :icon="Columns3" @click="columnsOpen = true">Columns</AppButton>
        <AppButton v-if="canWrite" :icon="Plus" @click="openForm()">Add {{ names.singular }}</AppButton>
      </template>
    </PageHeader>
    <div class="card p-3 sm:p-4">
      <SearchInput v-model="list.filters.search" :placeholder="`Search ${title.toLowerCase()}…`" />
      <div class="mt-3">
        <ConfigurableTable
          :bulk="bulkConfig"
          :columns="cfg.visibleColumns.value"
          :extra-columns="extra"
          :rows="list.items.value"
          :loading="list.loading.value"
          :offset="(list.page.value - 1) * 25"
          :ordering="list.filters.ordering"
          :clickable="canWrite"
          @row-click="openForm"
          @sort="sortBy"
          @changed="list.load()"
        >
          <template v-for="(_, name) in $slots" :key="name" #[name]="scope"><slot :name="name" v-bind="scope" /></template>
          <template #cell-_actions="{ row }">
            <div class="flex justify-end gap-1">
              <AppButton size="sm" variant="ghost" :icon="Pencil" :aria-label="`Edit ${row.name}`" @click.stop="openForm(row)" />
              <AppButton v-if="canDelete" size="sm" variant="ghost" :icon="Trash2" :aria-label="`Delete ${row.name}`" @click.stop="remove(row)" />
            </div>
          </template>
          <template #empty>
            <EmptyState :icon="icon || undefined" :title="`No ${names.plural.toLowerCase()} yet`">
              <AppButton v-if="canWrite" :icon="Plus" @click="openForm()">Add {{ names.singular }}</AppButton>
            </EmptyState>
          </template>
        </ConfigurableTable>
        <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
      </div>
    </div>

    <ColumnsPanel v-model:open="columnsOpen" :cfg="cfg" :title="`${names.plural} columns`" />
    <AppModal v-model:open="open" :title="`${editing ? 'Edit' : 'Add'} ${names.singular.toLowerCase()}`">
      <form id="crud-form" class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <template v-for="f in fields" :key="f.key">
          <AppSelect v-if="f.type === 'select'" v-model="form[f.key]" :class="f.span && 'sm:col-span-2'" :label="f.label" :options="f.options" :required="f.required" :error="errors[f.key]" />
          <EntityPicker v-else-if="f.type === 'picker'" v-model="form[f.key]" :class="f.span && 'sm:col-span-2'" :label="f.label" :fetcher="f.fetcher" :label-of="f.labelOf" :initial="initials[f.key]" :error="errors[f.key]" />
          <label v-else-if="f.type === 'checkbox'" class="flex items-center gap-2 self-end pb-2 text-sm"><input v-model="form[f.key]" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> {{ f.label }}</label>
          <AppInput
            v-else
            v-model="form[f.key]"
            :class="f.span && 'sm:col-span-2'"
            :label="f.label"
            :type="f.type || 'text'"
            :textarea="f.type === 'textarea'"
            :required="f.required"
            :error="errors[f.key]"
          />
        </template>
      </form>
      <template #footer>
        <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
        <AppButton type="submit" form="crud-form" :loading="saving">Save</AppButton>
      </template>
    </AppModal>
  </div>
</template>
