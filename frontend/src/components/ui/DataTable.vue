<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-vue-next'

const selected = defineModel('selected', { type: Array, default: () => [] })
const props = defineProps({
  columns: { type: Array, required: true }, // [{ key, label, class?, align?, mobile?: false, sortable?, width? }]
  /** Current ordering, e.g. 'name' or '-name' (for header sort indicators). */
  ordering: { type: String, default: '' },
  rows: { type: Array, default: () => [] },
  loading: Boolean,
  rowKey: { type: String, default: 'id' },
  selectable: Boolean,
  clickable: Boolean,
  skeletonRows: { type: Number, default: 6 },
})
const emit = defineEmits(['row-click', 'sort'])
const sortState = (key) => (props.ordering === key ? 'asc' : props.ordering === `-${key}` ? 'desc' : null)

const allSelected = computed(() => props.rows.length > 0 && props.rows.every((r) => selected.value.includes(r[props.rowKey])))
function toggleAll() {
  const ids = props.rows.map((r) => r[props.rowKey])
  selected.value = allSelected.value ? selected.value.filter((id) => !ids.includes(id)) : [...new Set([...selected.value, ...ids])]
}
function toggle(id) {
  selected.value = selected.value.includes(id) ? selected.value.filter((x) => x !== id) : [...selected.value, id]
}
const value = (row, key) => key.split('.').reduce((o, k) => o?.[k], row)
const mobileCols = computed(() => props.columns.filter((c) => c.mobile !== false))

// Row actions stay pinned to the right edge, so Edit/Delete never scroll out of reach on narrow screens
// or wide (admin-configured) tables. A column can opt in/out with `sticky: true|false`.
// Pinning only kicks in while columns are actually hidden to the right; otherwise the column is ordinary
// and blends into the glass card. When pinned, a soft fade (not a solid box) separates it from the content.
const isPinned = (c) => c.sticky ?? (c.key === 'actions' || c.key === '_actions')
const scroller = ref(null)
const table = ref(null)
const hiddenRight = ref(false)
function measure() {
  const el = scroller.value
  hiddenRight.value = !!el && el.scrollLeft + el.clientWidth < el.scrollWidth - 1
}
useResizeObserver(scroller, measure)
useResizeObserver(table, measure)
onMounted(measure)
watch(() => [props.rows, props.columns], () => nextTick(measure))
const pinnedClass = computed(() =>
  hiddenRight.value ? 'sticky right-0 z-[1] bg-[linear-gradient(to_right,transparent,var(--surface-solid)_2rem)] pl-10' : '',
)
</script>

<template>
  <div>
    <!-- Desktop / tablet -->
    <div ref="scroller" class="hidden overflow-x-auto md:block" :data-overflowing="hiddenRight || undefined" @scroll.passive="measure">
      <table ref="table" class="w-full text-left text-sm">
        <thead>
          <tr class="border-b border-line text-xs tracking-wide text-muted uppercase">
            <th v-if="selectable" class="w-10 px-4 py-3">
              <input type="checkbox" class="h-4 w-4 accent-[var(--accent)]" :checked="allSelected" aria-label="Select all" @change="toggleAll" />
            </th>
            <th
              v-for="c in columns"
              :key="c.key"
              class="px-4 py-3 font-medium whitespace-nowrap"
              :class="[c.class, c.align === 'right' && 'text-right', isPinned(c) && pinnedClass]"
              :style="c.width ? { width: `${c.width}px`, minWidth: `${c.width}px` } : undefined"
              :aria-sort="sortState(c.key) === 'asc' ? 'ascending' : sortState(c.key) === 'desc' ? 'descending' : undefined"
            >
              <button v-if="c.sortable" type="button" class="inline-flex items-center gap-1 uppercase transition hover:text-ink" :class="sortState(c.key) && 'text-accent'" @click="emit('sort', c.key)">
                {{ c.label }}
                <ArrowUp v-if="sortState(c.key) === 'asc'" class="h-3 w-3" />
                <ArrowDown v-else-if="sortState(c.key) === 'desc'" class="h-3 w-3" />
                <ArrowUpDown v-else class="h-3 w-3 opacity-40" />
              </button>
              <template v-else>{{ c.label }}</template>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading && !rows.length">
            <tr v-for="i in skeletonRows" :key="`s${i}`" class="border-b border-line/60">
              <td v-if="selectable" class="px-4 py-4"><div class="skeleton h-4 w-4" /></td>
              <td v-for="c in columns" :key="c.key" class="px-4 py-4"><div class="skeleton h-4" :style="{ width: `${40 + ((i * 17 + c.key.length * 7) % 50)}%` }" /></td>
            </tr>
          </template>
          <tr
            v-for="(row, ri) in rows"
            v-else
            :key="row[rowKey]"
            class="border-b border-line/60 transition-colors last:border-0"
            :class="[clickable && 'cursor-pointer hover:bg-surface-hover', selected.includes(row[rowKey]) && 'bg-accent/5', loading && 'opacity-60']"
            @click="clickable && emit('row-click', row)"
          >
            <td v-if="selectable" class="px-4 py-3" @click.stop>
              <input type="checkbox" class="h-4 w-4 accent-[var(--accent)]" :checked="selected.includes(row[rowKey])" :aria-label="`Select ${row[rowKey]}`" @change="toggle(row[rowKey])" />
            </td>
            <td v-for="c in columns" :key="c.key" class="px-4 py-3" :class="[c.class, c.align === 'right' && 'text-right', isPinned(c) && pinnedClass]">
              <slot :name="`cell-${c.key}`" :row="row" :value="value(row, c.key)" :index="ri">{{ value(row, c.key) ?? '—' }}</slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Mobile cards -->
    <div class="space-y-2 md:hidden">
      <template v-if="loading && !rows.length">
        <div v-for="i in 4" :key="`m${i}`" class="rounded-2xl border border-line p-4"><div class="skeleton mb-2 h-4 w-2/3" /><div class="skeleton h-3 w-1/2" /></div>
      </template>
      <div
        v-for="(row, ri) in rows"
        v-else
        :key="row[rowKey]"
        class="relative rounded-2xl border border-line bg-surface-strong/40 p-4 transition active:scale-[0.99]"
        :class="[selected.includes(row[rowKey]) && 'border-accent/50 bg-accent/5', loading && 'opacity-60']"
        @click="clickable && emit('row-click', row)"
      >
        <label v-if="selectable" class="absolute top-3 right-3 p-1" @click.stop>
          <input type="checkbox" class="h-4 w-4 accent-[var(--accent)]" :checked="selected.includes(row[rowKey])" @change="toggle(row[rowKey])" />
        </label>
        <slot name="mobile" :row="row" :index="ri">
          <dl class="grid grid-cols-2 gap-x-3 gap-y-2 text-sm" :class="selectable && 'pr-8'">
            <template v-for="c in mobileCols" :key="c.key">
              <dt class="text-xs text-muted">{{ c.label }}</dt>
              <dd class="min-w-0 truncate text-right"><slot :name="`cell-${c.key}`" :row="row" :value="value(row, c.key)" :index="ri">{{ value(row, c.key) ?? '—' }}</slot></dd>
            </template>
          </dl>
        </slot>
      </div>
    </div>

    <div v-if="!loading && !rows.length"><slot name="empty" /></div>
  </div>
</template>
