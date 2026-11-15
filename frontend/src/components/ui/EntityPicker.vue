<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { Check, ChevronsUpDown, Loader2, Search, X } from 'lucide-vue-next'

/**
 * Async searchable picker. `fetcher(search)` returns an array (or DRF page) of items.
 * v-model holds an id (or an array of ids when `multiple`); `initial` seeds labels for
 * already-selected values so they render without an extra request.
 */
const model = defineModel({ type: [Number, String, Array, null], default: null })
const props = defineProps({
  fetcher: { type: Function, required: true },
  label: String,
  placeholder: { type: String, default: 'Search…' },
  multiple: Boolean,
  labelOf: { type: Function, default: (i) => i.name ?? i.full_name ?? i.email ?? String(i.id) },
  sublabelOf: { type: Function, default: () => '' },
  disabledOf: { type: Function, default: () => false },
  initial: { type: Array, default: () => [] },
  error: [String, Array],
  required: Boolean,
  clearable: { type: Boolean, default: true },
})
const emit = defineEmits(['select'])

const id = useId()
const root = ref(null)
const field = ref(null)
const listEl = ref(null)
const pos = ref({})
const open = ref(false)
const query = ref('')
const options = ref([])
const loading = ref(false)
const known = ref(new Map(props.initial.map((i) => [i.id, i])))
const active = ref(0)
let timer = null
let seq = 0

watch(() => props.initial, (list) => list.forEach((i) => known.value.set(i.id, i)))

const selectedIds = computed(() => (props.multiple ? model.value || [] : model.value != null && model.value !== '' ? [model.value] : []))
const selectedItems = computed(() => selectedIds.value.map((sid) => known.value.get(sid)).filter(Boolean))

async function search() {
  const mine = ++seq
  loading.value = true
  try {
    const data = await props.fetcher(query.value)
    if (mine !== seq) return
    options.value = Array.isArray(data) ? data : data.results || []
    options.value.forEach((o) => known.value.set(o.id, o))
    active.value = 0
  } catch {
    if (mine === seq) options.value = []
  } finally {
    if (mine === seq) loading.value = false
  }
}

watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(search, 250)
})
watch(open, (v) => v && search())
onBeforeUnmount(() => clearTimeout(timer))
onClickOutside(root, () => (open.value = false), { ignore: [listEl] })

/**
 * The option list is teleported to <body> with fixed positioning so it is never clipped by a
 * scrolling modal/card (overflow) and always stacks above overlays. It follows the field and flips
 * upward when there isn't room below.
 */
function place() {
  const el = field.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const below = window.innerHeight - r.bottom
  const up = below < 260 && r.top > below
  pos.value = {
    left: `${Math.max(8, r.left)}px`,
    width: `${Math.min(r.width, window.innerWidth - 16)}px`,
    ...(up ? { bottom: `${window.innerHeight - r.top + 6}px` } : { top: `${r.bottom + 6}px` }),
    maxHeight: `${Math.max(160, Math.min(256, (up ? r.top : below) - 16))}px`,
  }
}
watch(open, async (v) => {
  if (v) {
    await nextTick()
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
  } else {
    window.removeEventListener('scroll', place, true)
    window.removeEventListener('resize', place)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', place, true)
  window.removeEventListener('resize', place)
})

function pick(item) {
  if (props.disabledOf(item)) return
  known.value.set(item.id, item)
  if (props.multiple) {
    const ids = selectedIds.value
    model.value = ids.includes(item.id) ? ids.filter((x) => x !== item.id) : [...ids, item.id]
  } else {
    model.value = item.id
    open.value = false
  }
  emit('select', item)
  query.value = ''
}
function remove(itemId) {
  model.value = props.multiple ? selectedIds.value.filter((x) => x !== itemId) : null
}
function onKey(e) {
  if (!open.value && ['ArrowDown', 'Enter'].includes(e.key)) {
    open.value = true
    e.preventDefault()
    return
  }
  if (e.key === 'ArrowDown') active.value = Math.min(active.value + 1, options.value.length - 1)
  else if (e.key === 'ArrowUp') active.value = Math.max(active.value - 1, 0)
  else if (e.key === 'Enter' && options.value[active.value]) pick(options.value[active.value])
  else if (e.key === 'Escape') open.value = false
  else return
  e.preventDefault()
}
</script>

<template>
  <div ref="root" class="relative">
    <label v-if="label" :for="id" class="label">{{ label }}<span v-if="required" class="text-danger"> *</span></label>
    <div
      ref="field"
      class="field flex min-h-[42px] cursor-text flex-wrap items-center gap-1.5 !py-1.5"
      :class="[open && 'border-accent ring-4 ring-[var(--glow)]', error && 'border-danger']"
      @click="open = true"
    >
      <template v-if="multiple">
        <span v-for="item in selectedItems" :key="item.id" class="chip bg-accent/10 text-accent">
          {{ labelOf(item) }}
          <button type="button" class="hover:text-ink" :aria-label="`Remove ${labelOf(item)}`" @click.stop="remove(item.id)"><X class="h-3 w-3" /></button>
        </span>
      </template>
      <span v-else-if="selectedItems[0] && !open" class="flex-1 truncate">{{ labelOf(selectedItems[0]) }}</span>
      <input
        v-if="multiple || open || !selectedItems[0]"
        :id="id"
        v-model="query"
        class="min-w-[6rem] flex-1 bg-transparent py-1 outline-none placeholder:text-muted/70"
        :placeholder="selectedItems.length && !multiple ? labelOf(selectedItems[0]) : placeholder"
        autocomplete="off"
        role="combobox"
        :aria-expanded="open"
        @focus="open = true"
        @keydown="onKey"
      />
      <button v-if="clearable && !multiple && selectedItems[0] && !open" type="button" class="text-muted hover:text-ink" aria-label="Clear" @click.stop="remove(selectedItems[0].id)"><X class="h-4 w-4" /></button>
      <ChevronsUpDown v-else class="h-4 w-4 shrink-0 text-muted" />
    </div>
    <Teleport to="body">
    <Transition name="fade">
      <ul v-if="open" ref="listEl" class="glass-strong fixed z-[150] overflow-y-auto rounded-2xl p-1.5" :style="pos" role="listbox">
        <li v-if="loading && !options.length" class="flex items-center gap-2 px-3 py-2.5 text-sm text-muted"><Loader2 class="h-4 w-4 animate-spin" /> Searching…</li>
        <li v-else-if="!options.length" class="flex items-center gap-2 px-3 py-2.5 text-sm text-muted"><Search class="h-4 w-4" /> No matches</li>
        <li
          v-for="(item, i) in options"
          :key="item.id"
          role="option"
          :aria-selected="selectedIds.includes(item.id)"
          class="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-sm"
          :class="[i === active && 'bg-surface-hover', disabledOf(item) && 'cursor-not-allowed opacity-45']"
          @mouseenter="active = i"
          @mousedown.prevent="pick(item)"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate">{{ labelOf(item) }}</p>
            <p v-if="sublabelOf(item)" class="truncate text-xs text-muted">{{ sublabelOf(item) }}</p>
          </div>
          <Check v-if="selectedIds.includes(item.id)" class="h-4 w-4 text-accent" />
        </li>
      </ul>
    </Transition>
    </Teleport>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ Array.isArray(error) ? error.join(' ') : error }}</p>
  </div>
</template>
