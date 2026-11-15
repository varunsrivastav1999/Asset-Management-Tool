<script setup>
import { COLUMN_TYPES, COLUMN_TYPE_LABEL, hasOptions, optionsPlaceholder, parseOptions } from '@/utils/columnTypes'
import { computed, reactive, ref, watch } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { ChevronDown, GripVertical, Lock, Plus, RotateCcw, Trash2 } from 'lucide-vue-next'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import RoleChecklist from '@/components/settings/RoleChecklist.vue'
import { tablesApi } from '@/api'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'

/**
 * Everyone: show/hide columns for their own view (saved per user).
 * Admins additionally: drag to reorder, rename, edit, add and delete columns for everyone.
 */
const open = defineModel('open', { type: Boolean })
const props = defineProps({ cfg: { type: Object, required: true }, title: { type: String, default: 'Customize columns' } })
const ui = useUiStore()

const TYPES = COLUMN_TYPES
const TYPE_LABEL = COLUMN_TYPE_LABEL

const list = ref([])
watch(
  () => [open.value, props.cfg.columns.value],
  () => {
    if (open.value) list.value = props.cfg.columns.value.map((c) => ({ ...c }))
  },
  { immediate: true, deep: true },
)
const admin = computed(() => props.cfg.canEdit.value)
const expanded = ref(null)
const busy = ref(false)
const newCol = reactive({ name: '', type: 'text', options: '' })
const addErrors = ref({})

async function run(fn, success) {
  busy.value = true
  try {
    await fn()
    if (success) ui.success(success)
    await props.cfg.reload()
  } catch (e) {
    ui.error(parseError(e).message)
    await props.cfg.reload()
  } finally {
    busy.value = false
  }
}

function toggle(col) {
  const real = props.cfg.columns.value.find((c) => c.key === col.key)
  if (real) props.cfg.toggle(real).then(() => (col.visible = real.visible))
}

const onSort = () => run(() => tablesApi.reorderColumns(props.cfg.item.value, list.value.map((c) => c.id)))
const rename = (col) => col.name.trim() && run(() => tablesApi.updateColumn(col.id, { name: col.name.trim() }))
const saveCol = (col) =>
  run(
    () =>
      tablesApi.updateColumn(col.id, {
        name: col.name,
        is_visible: col.is_visible,
        is_required: col.is_required,
        is_searchable: col.is_searchable,
        is_sortable: col.is_sortable,
        width: col.width ? Number(col.width) : null,
        visible_roles: col.visible_roles,
        ...(!col.is_builtin ? { options: parseOptions(col.type, col.optionsText ?? (Array.isArray(col.options) ? col.options : []).join(', ')) } : {}),
      }),
    'Column saved',
  )

async function remove(col) {
  if (!(await ui.confirm({ title: `Delete “${col.name}”?`, message: 'The column is removed for everyone. Values already stored stay in the records and reappear if you re-add a column with the same key.', confirmText: 'Delete', danger: true })))
    return
  run(() => tablesApi.deleteColumn(col.id), 'Column deleted')
}

async function add() {
  addErrors.value = {}
  busy.value = true
  try {
    await tablesApi.createColumn({
      sidebar_item: props.cfg.item.value,
      name: newCol.name,
      type: newCol.type,
      options: parseOptions(newCol.type, newCol.options),
      is_searchable: ['text', 'select', 'status', 'user'].includes(newCol.type),
      is_sortable: newCol.type !== 'file',
    })
    ui.success('Column added')
    Object.assign(newCol, { name: '', type: 'text', options: '' })
    await props.cfg.reload()
  } catch (e) {
    const { message, fields } = parseError(e)
    addErrors.value = fields
    ui.error(message)
  } finally {
    busy.value = false
  }
}

async function resetAll() {
  if (!(await ui.confirm({ title: 'Reset columns for everyone?', message: 'Built-in columns return to their defaults and custom columns are removed (their stored values are kept).', confirmText: 'Reset', danger: true }))) return
  run(() => tablesApi.resetColumns(props.cfg.item.value), 'Columns reset')
}
</script>

<template>
  <AppModal v-model:open="open" :title="title" :subtitle="admin ? 'Drag to reorder for everyone. Checkboxes only change your own view.' : 'Choose which columns you see. Saved to your account.'" size="lg">
    <VueDraggable v-model="list" :disabled="!admin || busy" :animation="160" :force-fallback="true" :fallback-tolerance="3" handle=".col-handle" ghost-class="opacity-40" class="space-y-1.5" @end="onSort">
      <div v-for="col in list" :key="col.key" class="rounded-2xl border border-line bg-surface-strong/40">
        <div class="flex items-center gap-2 px-2 py-2">
          <button v-if="admin" type="button" class="col-handle cursor-grab touch-none rounded-lg p-1 text-muted hover:bg-surface-hover" :aria-label="`Drag ${col.name}`"><GripVertical class="h-4 w-4" /></button>
          <label class="flex items-center p-1" :title="col.is_required ? 'Always shown' : 'Show in my view'">
            <input type="checkbox" class="h-4 w-4 accent-[var(--accent)]" :checked="col.visible" :disabled="col.is_required || busy" :aria-label="`Show ${col.name}`" @change="toggle(col)" />
          </label>
          <input
            v-if="admin"
            v-model="col.name"
            class="min-w-0 flex-1 rounded-lg border border-transparent bg-transparent px-2 py-1 text-sm font-medium outline-none hover:border-line focus:border-accent"
            :aria-label="`Rename ${col.name}`"
            @keydown.enter.prevent="$event.target.blur()"
            @blur="rename(col)"
          />
          <span v-else class="min-w-0 flex-1 truncate px-2 text-sm font-medium">{{ col.name }}</span>
          <Lock v-if="col.is_required" class="h-3.5 w-3.5 text-muted" />
          <AppBadge :tone="col.is_builtin ? 'slate' : 'violet'" class="hidden sm:inline-flex">{{ col.is_builtin ? 'built-in' : TYPE_LABEL[col.type] }}</AppBadge>
          <button v-if="admin" type="button" class="rounded-lg p-1.5 text-muted hover:bg-surface-hover" :aria-label="`Edit ${col.name}`" @click="expanded = expanded === col.key ? null : col.key">
            <ChevronDown class="h-4 w-4 transition" :class="expanded === col.key && 'rotate-180'" />
          </button>
          <button v-if="admin && !col.is_builtin" type="button" class="rounded-lg p-1.5 text-muted hover:bg-danger/10 hover:text-danger" :aria-label="`Delete ${col.name}`" @click="remove(col)"><Trash2 class="h-4 w-4" /></button>
        </div>
        <Transition name="fade">
          <div v-if="admin && expanded === col.key" class="grid gap-3 border-t border-line px-4 py-3 sm:grid-cols-2">
            <p class="text-xs text-muted sm:col-span-2">Key <code class="text-accent">{{ col.key }}</code> · {{ TYPE_LABEL[col.type] }}</p>
            <label class="flex items-center gap-2 text-sm"><input v-model="col.is_visible" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Shown by default</label>
            <label class="flex items-center gap-2 text-sm"><input v-model="col.is_required" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Required (can't be hidden)</label>
            <label class="flex items-center gap-2 text-sm"><input v-model="col.is_searchable" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Searchable</label>
            <label class="flex items-center gap-2 text-sm"><input v-model="col.is_sortable" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Sortable</label>
            <AppInput v-model="col.width" label="Width (px)" type="number" min="40" max="800" placeholder="auto" />
            <AppInput v-if="!col.is_builtin && hasOptions(col.type)" :model-value="col.optionsText ?? (col.options || []).join(', ')" label="Options (comma separated)" @update:model-value="col.optionsText = $event" />
            <RoleChecklist v-model="col.visible_roles" class="sm:col-span-2" label="Visible to roles" />
            <div class="flex justify-end sm:col-span-2"><AppButton size="sm" :loading="busy" @click="saveCol(col)">Save column</AppButton></div>
          </div>
        </Transition>
      </div>
    </VueDraggable>

    <form v-if="admin && cfg.supportsCustom.value" class="mt-5 rounded-2xl border border-dashed border-line p-4" @submit.prevent="add">
      <p class="mb-3 text-sm font-semibold">Add a column</p>
      <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px_auto] sm:items-end">
        <AppInput v-model="newCol.name" label="Name" placeholder="e.g. Cost centre" required :error="addErrors.name || addErrors.key" />
        <AppSelect v-model="newCol.type" label="Type" :options="TYPES" :error="addErrors.type" />
        <AppButton type="submit" :icon="Plus" :loading="busy" :disabled="!newCol.name.trim()">Add</AppButton>
        <AppInput v-if="hasOptions(newCol.type)" v-model="newCol.options" class="sm:col-span-3" :label="newCol.type === 'status' ? 'Statuses (comma separated, leave empty for the defaults)' : 'Options (comma separated)'" :placeholder="optionsPlaceholder(newCol.type)" :error="addErrors.options" />
      </div>
      <p class="mt-2 text-xs text-muted">Values are edited inline in the table and stored on each record — no database change needed.</p>
    </form>
    <p v-else-if="admin" class="mt-4 text-xs text-muted">This table shows built-in fields only, so custom columns aren't available here.</p>

    <template #footer>
      <AppButton v-if="admin" variant="ghost" class="sm:mr-auto" :icon="RotateCcw" @click="resetAll">Reset for everyone</AppButton>
      <AppButton variant="secondary" @click="cfg.resetMine()">Reset my view</AppButton>
      <AppButton @click="open = false">Done</AppButton>
    </template>
  </AppModal>
</template>
