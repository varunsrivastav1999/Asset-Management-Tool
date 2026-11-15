import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { parseError } from '@/api/http'
import { cleanParams } from '@/utils/format'

/**
 * Paginated, filterable list bound to the URL query string (so filters survive reloads/back).
 * `fetcher(params)` must return a DRF paginated payload.
 */
export function useList(fetcher, { filters: initial = {}, pageSize = 25, syncUrl = true, debounce = 300, extraParams = null, onData = null } = {}) {
  const route = syncUrl ? useRoute() : null
  const router = syncUrl ? useRouter() : null

  const fromQuery = (key, fallback) => {
    const v = route?.query[key]
    if (v === undefined) return fallback
    if (Array.isArray(fallback)) return String(v).split(',').filter(Boolean)
    if (typeof fallback === 'boolean') return v === 'true'
    return v
  }

  const filters = reactive(Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, fromQuery(k, v)])))
  const page = ref(Number(route?.query.page) || 1)
  const items = ref([])
  const count = ref(0)
  const pages = ref(1)
  const loading = ref(false)
  const error = ref('')
  let seq = 0
  let timer = null

  function params() {
    const f = Object.fromEntries(Object.entries(filters).map(([k, v]) => [k, Array.isArray(v) ? v.join(',') : v]))
    return cleanParams({ ...f, page: page.value, page_size: pageSize })
  }

  async function load() {
    const mine = ++seq
    loading.value = true
    error.value = ''
    try {
      const data = await fetcher({ ...params(), ...(extraParams ? extraParams() : {}) })
      if (mine !== seq) return
      onData?.(data)
      items.value = data.results ?? data
      count.value = data.count ?? items.value.length
      pages.value = data.pages ?? 1
    } catch (e) {
      if (mine !== seq) return
      if (e?.response?.status === 404 && page.value > 1) {
        page.value = 1
        return
      }
      error.value = parseError(e).message
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  function syncQuery() {
    if (!router) return
    const query = cleanParams({ ...params(), page_size: undefined, page: page.value > 1 ? page.value : undefined })
    router.replace({ query }).catch(() => {})
  }

  watch(
    () => JSON.stringify(filters),
    () => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        if (page.value !== 1) page.value = 1
        else {
          syncQuery()
          load()
        }
      }, debounce)
    },
  )
  watch(page, () => {
    syncQuery()
    load()
  })
  onBeforeUnmount(() => clearTimeout(timer))

  function reset() {
    Object.entries(initial).forEach(([k, v]) => (filters[k] = Array.isArray(v) ? [...v] : v))
  }

  return { filters, page, items, count, pages, loading, error, load, reset, params }
}
