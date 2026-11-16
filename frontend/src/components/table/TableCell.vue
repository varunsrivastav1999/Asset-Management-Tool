<script setup>
import { computed, nextTick, ref } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { Check, FileText, Pencil, X } from 'lucide-vue-next'
import AppBadge from '@/components/ui/AppBadge.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import UserAvatar from '@/components/ui/UserAvatar.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import MediaValue from '@/components/table/MediaValue.vue'
import MediaInput from '@/components/table/MediaInput.vue'
import { pick, userLabel, userSub } from '@/api/pickers'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import { formatDate, formatMoney, formatNumber } from '@/utils/format'
import { hasOptions, isCustomStatus, statusTone } from '@/utils/columnTypes'

const props = defineProps({
  col: { type: Object, required: true },
  row: { type: Object, required: true },
  index: { type: Number, default: 0 },
  offset: { type: Number, default: 0 },
  editable: Boolean,
  save: { type: Function, default: null },
})
const ui = useUiStore()

const isCustom = computed(() => !props.col.is_builtin)
const raw = computed(() => {
  if (isCustom.value) return props.row.custom_data?.[props.col.key]
  return props.col.key.split('.').reduce((o, k) => o?.[k], props.row)
})
const options = computed(() => (Array.isArray(props.col.options) ? props.col.options : []))
const fmt = computed(() => (!Array.isArray(props.col.options) && props.col.options?.format) || '')

const userName = computed(() => {
  const v = raw.value
  if (!v) return ''
  if (typeof v === 'string') return v
  return v.full_name || v.name || v.email || ''
})
const display = computed(() => {
  const v = raw.value
  if (v === null || v === undefined || v === '') return '—'
  switch (props.col.type) {
    case 'number':
      return fmt.value === 'currency' ? formatMoney(v, props.row.currency || undefined) : formatNumber(v)
    case 'date':
      return formatDate(v)
    default:
      return String(v)
  }
})

// --- inline editing (custom columns only) ---
const editing = ref(false)
const draft = ref(null)
const saving = ref(false)
const box = ref(null)
onClickOutside(box, () => editing.value && !saving.value && (editing.value = false))

async function start() {
  if (!props.editable || !isCustom.value) return
  const v = raw.value
  if (props.col.type === 'media') draft.value = v && typeof v === 'object' ? v : null
  else draft.value = props.col.type === 'user' ? (v && typeof v === 'object' ? v.id : null) : props.col.type === 'boolean' ? (v === true ? 'true' : v === false ? 'false' : '') : (v ?? '')
  editing.value = true
  await nextTick()
  box.value?.querySelector('input, select')?.focus()
}
let pickedUser = null
async function commit() {
  saving.value = true
  let value = draft.value
  if (props.col.type === 'boolean') value = value === '' ? null : value === 'true'
  if (props.col.type === 'user') value = value ? { id: value, name: pickedUser ? userLabel(pickedUser) : userName.value } : null
  try {
    await props.save(props.row, props.col.key, value === '' ? null : value)
    editing.value = false
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="editing" ref="box" class="flex min-w-[10rem] items-center gap-1" @click.stop>
    <MediaInput
      v-if="col.type === 'media'"
      :model-value="draft"
      :item="col.item"
      :column="col.key"
      class="min-w-[14rem]"
      @update:model-value="(v) => ((draft = v), commit())"
    />
    <select v-else-if="hasOptions(col.type)" v-model="draft" class="field !py-1 text-xs" @keydown.enter="commit" @keydown.esc="editing = false">
      <option value="">—</option>
      <option v-for="o in options" :key="o" :value="o">{{ o }}</option>
    </select>
    <select v-else-if="col.type === 'boolean'" v-model="draft" class="field !py-1 text-xs" @keydown.enter="commit" @keydown.esc="editing = false">
      <option value="">—</option>
      <option value="true">Yes</option>
      <option value="false">No</option>
    </select>
    <EntityPicker v-else-if="col.type === 'user'" v-model="draft" class="min-w-[12rem]" :fetcher="pick.users" :label-of="userLabel" :sublabel-of="userSub" :initial="raw && typeof raw === 'object' ? [{ id: raw.id, full_name: raw.name }] : []" @select="(u) => (pickedUser = u)" />
    <input
      v-else
      v-model="draft"
      class="field !py-1 text-xs"
      :type="col.type === 'number' ? 'number' : col.type === 'date' ? 'date' : col.type === 'file' ? 'url' : 'text'"
      :placeholder="col.type === 'file' ? 'https://…' : ''"
      step="any"
      @keydown.enter="commit"
      @keydown.esc="editing = false"
    />
    <button v-if="col.type !== 'media'" type="button" class="rounded-md p-1 text-success hover:bg-success/10" :disabled="saving" aria-label="Save" @click="commit"><Check class="h-3.5 w-3.5" /></button>
    <button type="button" class="rounded-md p-1 text-muted hover:bg-surface-hover" aria-label="Cancel" @click="editing = false"><X class="h-3.5 w-3.5" /></button>
  </div>

  <div v-else class="group/cell inline-flex max-w-full min-w-0 items-center gap-1.5" :class="editable && isCustom && 'cursor-text'" @click="editable && isCustom && ($event.stopPropagation(), start())">
    <span v-if="col.type === 'auto_number'" class="font-mono text-xs text-muted">{{ offset + index + 1 }}</span>
    <AppBadge v-else-if="isCustomStatus(col)" :tone="statusTone(raw, options)" :dot="!!raw">{{ raw || '—' }}</AppBadge>
    <StatusBadge v-else-if="col.type === 'status'" :status="raw" :kind="col.options?.kind || 'asset'" />
    <AppBadge v-else-if="col.type === 'boolean'" :tone="raw === true ? 'emerald' : 'slate'">{{ raw === true ? 'Yes' : raw === false ? 'No' : '—' }}</AppBadge>
    <AppBadge v-else-if="col.type === 'select' && raw">{{ raw }}</AppBadge>
    <span v-else-if="col.type === 'user'" class="flex min-w-0 items-center gap-2">
      <template v-if="userName">
        <UserAvatar :name="userName" size="xs" />
        <span class="truncate text-sm">{{ userName }}</span>
      </template>
      <span v-else class="text-muted">{{ row.department_name && col.key === 'assigned_to' ? row.department_name : '—' }}</span>
    </span>
    <MediaValue v-else-if="col.type === 'media'" :value="raw" class="min-w-0" />
    <a v-else-if="col.type === 'file' && raw" :href="raw" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-sm text-accent hover:underline" @click.stop><FileText class="h-3.5 w-3.5" /> Open</a>
    <span v-else-if="col.type === 'date'" class="text-sm whitespace-nowrap">
      {{ display }}
      <span v-if="row[`${col.key}_by`]" class="block text-[11px] text-muted">by {{ row[`${col.key}_by`] }}</span>
    </span>
    <span v-else class="truncate text-sm" :class="display === '—' && 'text-muted'">{{ display }}</span>
    <Pencil v-if="editable && isCustom" class="h-3 w-3 shrink-0 text-muted opacity-0 transition group-hover/cell:opacity-100" />
  </div>
</template>
