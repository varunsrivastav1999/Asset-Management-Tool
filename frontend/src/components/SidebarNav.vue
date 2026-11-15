<script setup>
import { useRoute } from 'vue-router'
import { ExternalLink } from 'lucide-vue-next'
import { iconFor } from '@/utils/icons'
import { normalizeHex, withAlpha } from '@/utils/color'

defineOptions({ name: 'SidebarNav' })
defineProps({
  items: { type: Array, default: () => [] },
  collapsed: Boolean,
  depth: { type: Number, default: 0 },
  /** Force a specific item to render as active (used by previews). */
  forceActive: { type: [Number, String], default: null },
})

const route = useRoute()
function isActive(item, forced) {
  if (forced !== null && forced !== undefined) return item.id === forced
  if (!item.route) return false
  const path = item.route.split('?')[0]
  return path === '/' ? route.path === '/' : route.path === path || route.path.startsWith(`${path}/`)
}

/** Inline styles from the item's DB colors; empty colors fall back to the theme. */
function linkStyle(item, active) {
  const style = {}
  const label = normalizeHex(item.color)
  const accent = normalizeHex(item.active_color) || label
  if (label) style.color = label
  if (active && accent) {
    style.background = item.gradient
      ? `linear-gradient(100deg, ${withAlpha(accent, 0.28)}, ${withAlpha(normalizeHex(item.color) || accent, 0.06)})`
      : withAlpha(accent, 0.16)
    if (item.glow) style.boxShadow = `0 0 22px -6px ${withAlpha(accent, 0.75)}, inset 0 0 0 1px ${withAlpha(accent, 0.25)}`
  }
  return style
}
function iconStyle(item, active) {
  const c = normalizeHex(item.icon_color) || (active && normalizeHex(item.active_color)) || null
  const style = c ? { color: c } : {}
  if (item.glow && (c || normalizeHex(item.color))) style.filter = `drop-shadow(0 0 6px ${withAlpha(c || item.color, 0.8)})`
  return style
}
function barStyle(item) {
  const a = normalizeHex(item.active_color) || normalizeHex(item.color)
  if (!a) return {}
  return { background: item.gradient ? `linear-gradient(180deg, ${a}, ${normalizeHex(item.color) || a})` : a, boxShadow: `0 0 12px ${withAlpha(a, 0.7)}` }
}
</script>

<template>
  <template v-for="item in items" :key="item.id">
    <hr v-if="item.type === 'divider'" class="my-3 border-line" />

    <div v-else-if="item.type === 'group'" :class="depth === 0 ? 'mb-4' : 'mb-1'">
      <p
        v-if="!collapsed"
        class="flex items-center gap-2 px-3 font-semibold text-muted/80 uppercase"
        :class="depth === 0 ? 'mb-1.5 text-[10px] tracking-[0.14em]' : 'mt-1 mb-1 text-[10px] tracking-wider'"
        :style="normalizeHex(item.color) ? { color: item.color } : undefined"
      >
        <component :is="iconFor(item.icon)" v-if="item.icon && depth > 0" class="h-3.5 w-3.5" :style="iconStyle(item, false)" />
        {{ item.name }}
      </p>
      <hr v-else-if="depth === 0" class="mx-3 mb-2 border-line" />
      <div :class="depth > 0 && !collapsed && 'ml-3 border-l border-line pl-1'">
        <SidebarNav :items="item.children" :collapsed="collapsed" :depth="depth + 1" :force-active="forceActive" />
      </div>
    </div>

    <a
      v-else-if="item.type === 'link'"
      :href="item.url"
      :target="item.open_in_new_tab ? '_blank' : undefined"
      :rel="item.open_in_new_tab ? 'noopener noreferrer' : undefined"
      :title="collapsed ? item.name : undefined"
      class="group mb-0.5 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-ink"
      :style="linkStyle(item, false)"
    >
      <component :is="iconFor(item.icon, ExternalLink)" class="h-[18px] w-[18px] shrink-0" :style="iconStyle(item, false)" />
      <span v-if="!collapsed" class="flex-1 truncate">{{ item.name }}</span>
      <ExternalLink v-if="!collapsed && item.open_in_new_tab" class="h-3 w-3 opacity-50" />
    </a>

    <RouterLink
      v-else
      :to="item.route"
      :title="collapsed ? item.name : undefined"
      class="group relative mb-0.5 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition"
      :class="isActive(item, forceActive) ? 'bg-accent/10 text-ink' : 'text-muted hover:bg-surface-hover hover:text-ink'"
      :style="linkStyle(item, isActive(item, forceActive))"
    >
      <span
        v-if="isActive(item, forceActive)"
        class="absolute top-2 bottom-2 left-0 w-1 rounded-r-full bg-gradient-accent shadow-[0_0_12px_var(--glow)]"
        :style="barStyle(item)"
      />
      <component
        :is="iconFor(item.icon)"
        class="h-[18px] w-[18px] shrink-0"
        :class="isActive(item, forceActive) && !item.icon_color && !item.active_color && 'text-accent'"
        :style="iconStyle(item, isActive(item, forceActive))"
      />
      <span v-if="!collapsed" class="truncate">{{ item.name }}</span>
    </RouterLink>
  </template>
</template>
