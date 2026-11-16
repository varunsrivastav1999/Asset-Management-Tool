<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Lock, Plus, Trash2 } from 'lucide-vue-next'
import { tablesApi } from '@/api'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import { COLUMN_TYPES, COLUMN_TYPE_LABEL, hasOptions, optionsPlaceholder, parseOptions } from '@/utils/columnTypes'

/**
 * Add, rename and delete the columns of an existing table (custom or built-in). Changes save immediately.
 * Built-in columns can be renamed but not deleted; hide them per page from the table's Columns panel.
 */
const props = defineProps({ item: { type: [Number, String], required: true } })
const emit = defineEmits(['changed'])
const ui = useUiStore()
const columns = ref([])
const loading = ref(true)
const busy = ref(false)
const newCol = reactive({ name: '', type: 'text', options: '' })
const errors = ref({})

async function load() {
  loading.value = true
  try {
    columns.value = (await tablesApi.listColumns(props.item)).filter((c) => c.type !== 'auto_number')
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function rename(col, name) {
  name = name.trim()
  if (!name || name === col.name) return
  try {
    Object.assign(col, await tablesApi.updateColumn(col.id, { name }))
    ui.success(`Column renamed to “${col.name}”`)
    emit('changed')
  } catch (e) {
    ui.error(parseError(e).message)
    load()
  }
}

async function remove(col) {
  const ok = await ui.confirm({
    title: `Delete the column “${col.name}”?`,
    message: 'It disappears from the table for everyone. Values already entered stay stored and come back if you add a column with the same name again.',
    confirmText: 'Delete column',
    danger: true,
    action: () => tablesApi.deleteColumn(col.id),
  })
  if (!ok) return
  ui.success(`Column “${col.name}” deleted`)
  columns.value = columns.value.filter((c) => c.id !== col.id)
  emit('changed')
}

async function add() {
  errors.value = {}
  busy.value = true
  try {
    const col = await tablesApi.createColumn({
      sidebar_item: Number(props.item),
      name: newCol.name.trim(),
      type: newCol.type,
      options: parseOptions(newCol.type, newCol.options),
      is_searchable: ['text', 'select', 'status', 'user'].includes(newCol.type),
      is_sortable: !['file', 'media'].includes(newCol.type),
    })
    columns.value.push(col)
    Object.assign(newCol, { name: '', type: 'text', options: '' })
    ui.success(`Column “${col.name}” added`)
    emit('changed')
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    busy.value = false
  }
}
defineExpose({ reload: load })
</script>

<template>
  <div data-testid="columns-editor">
    <div v-if="loading" class="space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-11" /></div>
    <ul v-else class="space-y-2">
      <li v-for="c in columns" :key="c.id" class="flex items-center gap-2 rounded-2xl border border-line px-3 py-2">
        <input
          class="field min-w-0 flex-1 !py-1.5 text-sm"
          :value="c.name"
          :aria-label="`Name of column ${c.name}`"
          @keydown.enter.prevent="$event.target.blur()"
          @blur="rename(c, $event.target.value)"
        />
        <span class="hidden w-36 shrink-0 truncate text-xs text-muted sm:block">{{ COLUMN_TYPE_LABEL[c.type] || c.type }}</span>
        <span v-if="c.is_builtin" class="grid h-8 w-8 shrink-0 place-items-center text-muted" title="Built-in column: rename or hide it, but it can't be deleted"><Lock class="h-3.5 w-3.5" /></span>
        <button v-else type="button" class="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted hover:bg-danger/10 hover:text-danger" :aria-label="`Delete column ${c.name}`" @click="remove(c)"><Trash2 class="h-4 w-4" /></button>
      </li>
    </ul>

    <!-- Not a <form>: this editor sits inside the table dialog's form, and forms can't be nested. -->
    <div class="mt-3 grid gap-2 rounded-2xl border border-dashed border-line p-3 sm:grid-cols-[minmax(0,1fr)_170px_auto]" @keydown.enter.prevent="newCol.name.trim() && !busy && add()">
      <AppInput v-model="newCol.name" aria-label="New column name" placeholder="New column name" :error="errors.name || errors.key" />
      <AppSelect v-model="newCol.type" aria-label="New column type" :options="COLUMN_TYPES" />
      <AppButton type="button" :icon="Plus" :loading="busy" :disabled="!newCol.name.trim()" @click="add">Add column</AppButton>
      <AppInput v-if="hasOptions(newCol.type)" v-model="newCol.options" class="sm:col-span-3" :aria-label="newCol.type === 'status' ? 'Statuses' : 'Options'" :placeholder="optionsPlaceholder(newCol.type)" :error="errors.options" />
    </div>
    <p class="mt-2 text-xs text-muted">Reorder columns, or hide them for one page, from the table's own Columns panel.</p>
  </div>
</template>
