import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { tablesApi } from '@/api'
import { parseError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useSidebarStore } from '@/stores/sidebar'
import { useUiStore } from '@/stores/ui'
import { APP_NAME } from '@/brand'

/**
 * Column configuration for a table page.
 *
 * The sidebar page is chosen by matching the current URL against the menu (so a second menu entry such as
 * "/assets?status=in_repair" can carry its own columns); otherwise the server uses the table's default page.
 * Columns usually arrive together with the rows (`with_columns=1`) via `setFromList`.
 */
export function useTableConfig(table, { resource, names: defaults = {} } = {}) {
  const route = useRoute()
  const sidebar = useSidebarStore()
  const notes = useNotificationsStore()
  const auth = useAuthStore()
  const ui = useUiStore()

  const columns = ref([])
  const meta = ref(null)
  const item = ref(null)
  const supportsCustom = ref(false)

  const pageItemId = computed(() => {
    const candidates = sidebar.pages.filter((p) => p.table === table)
    if (!candidates.length) return null
    // Admin-created tables are distinct pages: only an exact route match counts.
    if (table === 'custom') return candidates.find((p) => p.route === route.path)?.id ?? null
    const here = route.fullPath
    const exact = candidates.find((p) => p.route === here)
    if (exact) return exact.id
    const samePath = candidates.filter((p) => p.route.split('?')[0] === route.path)
    // Prefer the plain page ("/assets") over filtered variants when the URL has ad-hoc filters.
    return (samePath.find((p) => !p.route.includes('?')) || samePath[0] || candidates[0]).id
  })

  /** Admin-editable names: list payload > menu entry > hard-coded defaults. */
  const names = computed(() => {
    const page = sidebar.pages.find((p) => p.id === pageItemId.value)
    const m = meta.value || page?.table_meta || {}
    const plural = m.name || defaults.plural || 'Items'
    return { plural, singular: m.singular || defaults.singular || plural, description: m.description || '', icon: m.icon || '' }
  })

  const params = computed(() => ({ with_columns: 1, ...(pageItemId.value ? { table_item: pageItemId.value } : {}) }))
  const visibleColumns = computed(() => columns.value.filter((c) => c.visible))
  const canEdit = computed(() => auth.isAdmin && !!item.value)
  const canEditValues = computed(() => auth.isManager && supportsCustom.value)

  function setFromList(data) {
    if (!data?.table) return
    columns.value = data.table.columns
    item.value = data.table.item
    meta.value = data.table.meta || null
    supportsCustom.value = data.table.supports_custom
  }

  async function reload() {
    try {
      const data = await tablesApi.columns(table, pageItemId.value)
      columns.value = data.columns
      item.value = data.item
      supportsCustom.value = data.supports_custom
    } catch (e) {
      ui.error(parseError(e).message)
    }
  }

  /** Toggle a column for this user only (persisted server-side). */
  async function toggle(col) {
    if (col.is_required || !item.value) return
    col.visible = !col.visible
    const hidden = columns.value.filter((c) => !c.visible && c.is_visible).map((c) => c.key)
    const shown = columns.value.filter((c) => c.visible && !c.is_visible).map((c) => c.key)
    try {
      const res = await tablesApi.savePrefs(item.value, hidden, shown)
      columns.value = res.columns
    } catch (e) {
      col.visible = !col.visible
      ui.error(parseError(e).message)
    }
  }

  async function resetMine() {
    if (!item.value) return
    await tablesApi.clearPrefs(item.value)
    await reload()
  }

  async function setCustomValue(row, key, value) {
    const res = await tablesApi.setCustom(resource, row.id, { [key]: value })
    row.custom_data = res.custom_data
  }

  // An admin changed this page's columns somewhere: refresh.
  watch(
    () => notes.columnsEvent.n,
    () => notes.columnsEvent.item && notes.columnsEvent.item === item.value && reload(),
  )

  // The browser tab follows the table's current name (custom tables, renamed built-ins), not the route's static title.
  watch(
    () => names.value.plural,
    (plural) => {
      if (plural) document.title = `${plural} · ${APP_NAME}`
    },
    { immediate: true },
  )

  return { columns, visibleColumns, item, meta, names, supportsCustom, params, pageItemId, canEdit, canEditValues, setFromList, reload, toggle, resetMine, setCustomValue }
}
