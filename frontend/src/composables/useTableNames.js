import { computed } from 'vue'
import { useSidebarStore } from '@/stores/sidebar'

/** Names an admin gave a built-in table (e.g. "Assets" → "Equipment"), for pages without a table config. */
export function useTableNames(table, defaults = {}) {
  const sidebar = useSidebarStore()
  return computed(() => {
    const page = sidebar.pages.find((p) => p.table === table && p.table_meta && !p.route.includes('?'))
    const m = page?.table_meta || {}
    const plural = m.name || defaults.plural || 'Items'
    return { plural, singular: m.singular || defaults.singular || plural, description: m.description || '', route: page?.route || defaults.route }
  })
}
