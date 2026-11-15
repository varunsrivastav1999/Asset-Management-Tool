import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { sidebarApi } from '@/api'

/** The signed-in user's navigation, rendered entirely from the API (role-filtered server-side). */
export const useSidebarStore = defineStore('sidebar', () => {
  const items = ref([])
  const loaded = ref(false)
  const error = ref(false)
  let inflight = null

  function load() {
    if (!inflight) {
      inflight = sidebarApi
        .mine()
        .then((data) => {
          items.value = data.items
          error.value = false
        })
        .catch(() => {
          error.value = true
        })
        .finally(() => {
          loaded.value = true
          inflight = null
        })
    }
    return inflight
  }

  function reset() {
    items.value = []
    loaded.value = false
  }

  /** Flat list of in-app pages, in menu order (used for the mobile bottom bar). */
  const pages = computed(() => {
    const out = []
    const walk = (nodes) =>
      nodes.forEach((n) => {
        if (n.type === 'page') out.push(n)
        if (n.children) walk(n.children)
      })
    walk(items.value)
    return out
  })

  return { items, loaded, error, pages, load, reset }
})
