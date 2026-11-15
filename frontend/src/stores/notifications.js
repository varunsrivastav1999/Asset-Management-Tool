import { defineStore } from 'pinia'
import { ref } from 'vue'
import { notificationsApi } from '@/api'
import { tokenStore } from '@/api/http'
import { RealtimeClient, realtimeUrl } from '@/services/realtime'
import { useUiStore } from './ui'
import { useSidebarStore } from './sidebar'

export const useNotificationsStore = defineStore('notifications', () => {
  const items = ref([])
  const unread = ref(0)
  const loading = ref(false)
  const status = ref('offline') // offline | connecting | online | reconnecting
  /** Bumped on every server `dashboard.update`; views watch it to refetch. */
  const dashboardTick = ref(0)
  const lastEvent = ref(null)
  /** Bumped when an admin changes the dashboard widget layout. */
  const layoutTick = ref(0)
  /** Last table-column config change: { item, n } (tables reload when it's theirs). */
  const columnsEvent = ref({ item: null, n: 0 })
  let client = null
  let offRefresh = null

  async function load() {
    loading.value = true
    try {
      const data = await notificationsApi.list({ page_size: 30 })
      items.value = data.results
      unread.value = (await notificationsApi.unreadCount()).unread
    } finally {
      loading.value = false
    }
  }

  function handle(msg) {
    const ui = useUiStore()
    if (msg.type === 'auth.ok') {
      unread.value = msg.unread
    } else if (msg.type === 'notification') {
      const n = msg.notification
      if (!items.value.some((i) => i.id === n.id)) {
        items.value.unshift(n)
        items.value = items.value.slice(0, 50)
        unread.value += n.is_read ? 0 : 1
      }
      const type = { critical: 'error', warning: 'warning', success: 'success' }[n.level] || 'info'
      ui.toast(n.message, { title: n.title, type, action: n.link ? { label: 'Open', to: n.link } : null })
    } else if (msg.type === 'dashboard.update') {
      lastEvent.value = msg
      dashboardTick.value++
    } else if (msg.type === 'dashboard.layout') {
      layoutTick.value++
    } else if (msg.type === 'sidebar.update') {
      useSidebarStore().load()
    } else if (msg.type === 'table.columns') {
      columnsEvent.value = { item: msg.item, n: columnsEvent.value.n + 1 }
    }
  }

  function connect() {
    if (client) return
    client = new RealtimeClient({ url: realtimeUrl(), getToken: tokenStore.get, onMessage: handle, onStatus: (s) => (status.value = s) })
    client.start()
    offRefresh = tokenStore.on('refreshed', () => client?.reauth())
    load().catch(() => {})
  }

  function disconnect() {
    client?.stop()
    client = null
    offRefresh?.()
    items.value = []
    unread.value = 0
  }

  async function markRead(n) {
    if (n.is_read) return
    n.is_read = true
    unread.value = Math.max(0, unread.value - 1)
    await notificationsApi.read(n.id).catch(() => {})
  }

  async function markAllRead() {
    items.value.forEach((n) => (n.is_read = true))
    unread.value = 0
    await notificationsApi.readAll()
  }

  return { items, unread, loading, status, dashboardTick, layoutTick, columnsEvent, lastEvent, load, connect, disconnect, markRead, markAllRead, handle }
})
