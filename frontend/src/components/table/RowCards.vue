<script setup>
import { computed } from 'vue'

/**
 * Card layout for a configurable table (Sidebar settings → a page's "Display as: Cards").
 * Uses the page's own visible columns: a photo (Media) column becomes the card image, the first text column the
 * title, status/select/yes-no columns badges, and the rest labelled fields. Cells render through the `cell` slot,
 * so they look and edit exactly like the table view; `actions` holds the row buttons.
 */
const props = defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  loading: Boolean,
  selectable: Boolean,
  clickable: Boolean,
  rowKey: { type: String, default: 'id' },
})
const selected = defineModel('selected', { type: Array, default: () => [] })
const emit = defineEmits(['row-click'])

const BADGES = new Set(['status', 'select', 'boolean'])
const shown = computed(() => props.columns.filter((c) => c.type !== 'auto_number'))
const media = computed(() => shown.value.find((c) => c.type === 'media'))
const title = computed(() => shown.value.find((c) => c.type === 'text' && c.key !== 'code' && c !== media.value) || shown.value[0])
const code = computed(() => shown.value.find((c) => c.key === 'code' || c.key === 'asset_tag'))
const badges = computed(() => shown.value.filter((c) => BADGES.has(c.type) && c !== title.value))
const fields = computed(() => shown.value.filter((c) => ![media.value, title.value, code.value].includes(c) && !badges.value.includes(c)).slice(0, 6))

const hasMedia = (row) => {
  const c = media.value
  return !!(c && (c.is_builtin ? row[c.key] : row.custom_data?.[c.key])?.id)
}
const toggle = (id) => (selected.value = selected.value.includes(id) ? selected.value.filter((x) => x !== id) : [...selected.value, id])
</script>

<template>
  <div data-testid="row-cards">
    <div v-if="loading && !rows.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <div v-for="i in 6" :key="i" class="rounded-2xl border border-line p-4"><div class="skeleton mb-3 h-5 w-2/3" /><div class="skeleton h-3 w-1/2" /></div>
    </div>
    <div v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" :class="loading && 'opacity-60'">
      <article
        v-for="(row, index) in rows"
        :key="row[rowKey]"
        class="group relative flex min-w-0 flex-col gap-3 rounded-2xl border border-line bg-surface-strong/40 p-4 transition hover:border-primary/40 hover:shadow-sm"
        :class="[clickable && 'cursor-pointer', selected.includes(row[rowKey]) && 'border-primary/50 bg-primary-soft/30']"
        @click="clickable && emit('row-click', row)"
      >
        <div class="flex min-w-0 items-start gap-3">
          <input
            v-if="selectable"
            type="checkbox"
            class="mt-1 h-4 w-4 shrink-0 accent-[var(--accent)]"
            :checked="selected.includes(row[rowKey])"
            :aria-label="`Select ${row[rowKey]}`"
            @click.stop
            @change="toggle(row[rowKey])"
          />
          <div v-if="hasMedia(row)" class="shrink-0" @click.stop><slot name="cell" :row="row" :col="media" :index="index" :size="'lg'" /></div>
          <div class="min-w-0 flex-1">
            <div class="truncate text-base font-semibold"><slot name="cell" :row="row" :col="title" :index="index" /></div>
            <div v-if="code" class="mt-0.5 font-mono text-xs text-muted"><slot name="cell" :row="row" :col="code" :index="index" /></div>
          </div>
        </div>
        <div v-if="badges.length" class="flex flex-wrap gap-1.5">
          <span v-for="c in badges" :key="c.key" class="inline-flex min-w-0 items-center gap-1 text-xs" :title="c.name"><slot name="cell" :row="row" :col="c" :index="index" /></span>
        </div>
        <dl v-if="fields.length" class="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
          <div v-for="c in fields" :key="c.key" class="min-w-0">
            <dt class="truncate text-[11px] tracking-wide text-muted uppercase">{{ c.name }}</dt>
            <dd class="min-w-0 truncate"><slot name="cell" :row="row" :col="c" :index="index" /></dd>
          </div>
        </dl>
        <div v-if="$slots.actions" class="mt-auto flex justify-end border-t border-line/60 pt-2" @click.stop><slot name="actions" :row="row" /></div>
      </article>
    </div>
    <div v-if="!loading && !rows.length"><slot name="empty" /></div>
  </div>
</template>
