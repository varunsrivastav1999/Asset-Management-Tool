<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { onClickOutside } from '@vueuse/core'
import {
  Bell,
  Boxes,
  ChevronsLeft,
  ClipboardList,
  LogOut,
  Menu,
  Moon,
  Search,
  Sun,
  User,
  X,
} from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useThemeStore } from '@/stores/theme'
import { useUiStore } from '@/stores/ui'
import UserAvatar from '@/components/ui/UserAvatar.vue'
import BrandName from '@/components/ui/BrandName.vue'
import SidebarNav from '@/components/SidebarNav.vue'
import { useSidebarStore } from '@/stores/sidebar'
import { iconFor } from '@/utils/icons'
import { timeAgo } from '@/utils/format'

const auth = useAuthStore()
const notes = useNotificationsStore()
const theme = useThemeStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const sidebar = useSidebarStore()

/** Mobile bottom bar: first in-menu pages, with Scan (if the menu has it) as the centre action. */
const bottomNav = computed(() => {
  const pages = sidebar.pages
  const scan = pages.find((p) => p.route === '/scan')
  const rest = pages.filter((p) => p !== scan).slice(0, scan ? 3 : 4)
  const items = rest.map((p) => ({ ...p, fab: false }))
  if (scan) items.splice(Math.min(2, items.length), 0, { ...scan, fab: true })
  return items
})

const isActive = (item) => {
  const path = (item.route || '').split('?')[0]
  return path === '/' ? route.path === '/' : route.path === path || route.path.startsWith(`${path}/`)
}

const drawer = ref(false)
const bellOpen = ref(false)
const userOpen = ref(false)
const bellRef = ref(null)
const userRef = ref(null)
onClickOutside(bellRef, () => (bellOpen.value = false))
onClickOutside(userRef, () => (userOpen.value = false))
watch(() => route.fullPath, () => {
  drawer.value = false
  bellOpen.value = false
  userOpen.value = false
})

const globalSearch = ref('')
function submitSearch() {
  const q = globalSearch.value.trim()
  router.push({ name: 'assets', query: q ? { search: q } : {} })
  globalSearch.value = ''
}

function openNotification(n) {
  notes.markRead(n)
  bellOpen.value = false
  if (n.link) router.push(n.link)
}

async function logout() {
  notes.disconnect()
  sidebar.reset()
  await auth.logout()
  router.replace({ name: 'login' })
}

const levelDot = { critical: 'bg-danger', warning: 'bg-warning', success: 'bg-success', info: 'bg-accent' }
const statusInfo = computed(
  () =>
    ({
      online: { cls: 'bg-success', text: 'Live' },
      connecting: { cls: 'bg-warning animate-pulse', text: 'Connecting' },
      reconnecting: { cls: 'bg-warning animate-pulse', text: 'Reconnecting' },
      offline: { cls: 'bg-muted', text: 'Offline' },
    })[notes.status],
)

function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    document.getElementById('global-search')?.focus()
  }
}
onMounted(() => {
  sidebar.load()
  notes.connect()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="flex min-h-dvh">
    <!-- Desktop sidebar -->
    <aside
      class="glass sticky top-0 z-30 hidden h-dvh shrink-0 flex-col border-y-0 border-l-0 transition-[width] duration-300 lg:flex"
      :class="ui.sidebarCollapsed ? 'w-[76px]' : 'w-64'"
    >
      <div class="flex h-16 items-center gap-3 px-5">
        <div class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-accent shadow-[0_0_24px_-4px_var(--glow)]">
          <Boxes class="h-5 w-5 text-accent-ink" />
        </div>
        <BrandName v-if="!ui.sidebarCollapsed" class="line-clamp-2 text-sm leading-tight" />
      </div>
      <nav class="flex-1 overflow-y-auto px-3 py-4" aria-label="Main">
        <div v-if="!sidebar.loaded" class="space-y-2 px-1"><div v-for="i in 8" :key="i" class="skeleton h-9" /></div>
        <p v-else-if="sidebar.error && !sidebar.items.length" class="px-3 text-xs text-muted">Menu unavailable. <button class="text-accent" @click="sidebar.load()">Retry</button></p>
        <SidebarNav v-else :items="sidebar.items" :collapsed="ui.sidebarCollapsed" />
      </nav>
      <div class="border-t border-line p-3">
        <button class="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-muted hover:bg-surface-hover hover:text-ink" @click="ui.sidebarCollapsed = !ui.sidebarCollapsed">
          <ChevronsLeft class="h-[18px] w-[18px] shrink-0 transition" :class="ui.sidebarCollapsed && 'rotate-180'" />
          <span v-if="!ui.sidebarCollapsed">Collapse</span>
        </button>
      </div>
    </aside>

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- Top bar -->
      <header class="glass sticky top-0 z-30 flex h-16 items-center gap-3 border-x-0 border-t-0 px-4 sm:px-6">
        <button class="grid h-10 w-10 place-items-center rounded-xl text-muted hover:bg-surface-hover lg:hidden" aria-label="Open menu" @click="drawer = true">
          <Menu class="h-5 w-5" />
        </button>
        <form class="relative hidden max-w-md flex-1 sm:block" role="search" @submit.prevent="submitSearch">
          <Search class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted" />
          <input id="global-search" v-model="globalSearch" class="field !rounded-full !bg-surface pr-14 pl-9" placeholder="Search assets, serials, people…" aria-label="Search assets" />
          <kbd class="absolute top-1/2 right-3 hidden -translate-y-1/2 rounded-md border border-line px-1.5 text-[10px] text-muted md:block">⌘K</kbd>
        </form>
        <div class="flex-1 sm:hidden">
          <span class="font-display font-semibold">{{ route.meta.title }}</span>
        </div>

        <div class="ml-auto flex items-center gap-1 sm:gap-2">
          <span class="hidden items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[11px] text-muted md:inline-flex" :title="`Realtime: ${statusInfo.text}`">
            <span class="h-1.5 w-1.5 rounded-full" :class="statusInfo.cls" /> {{ statusInfo.text }}
          </span>
          <button class="grid h-10 w-10 place-items-center rounded-xl text-muted hover:bg-surface-hover hover:text-ink" :aria-label="theme.isDark ? 'Switch to light theme' : 'Switch to dark theme'" @click="theme.toggle()">
            <Transition name="fade" mode="out-in">
              <Sun v-if="theme.isDark" key="sun" class="h-5 w-5" />
              <Moon v-else key="moon" class="h-5 w-5" />
            </Transition>
          </button>

          <div ref="bellRef" class="relative">
            <button class="relative grid h-10 w-10 place-items-center rounded-xl text-muted hover:bg-surface-hover hover:text-ink" aria-label="Notifications" @click="bellOpen = !bellOpen">
              <Bell class="h-5 w-5" />
              <span v-if="notes.unread" class="absolute top-1.5 right-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold text-white shadow-[0_0_10px_var(--danger)]">
                {{ notes.unread > 99 ? '99+' : notes.unread }}
              </span>
            </button>
            <Transition name="fade">
              <div v-if="bellOpen" class="glass-strong fixed inset-x-3 top-16 z-40 overflow-hidden rounded-2xl sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-96">
                <div class="flex items-center justify-between border-b border-line px-4 py-3">
                  <p class="font-semibold">Notifications</p>
                  <button v-if="notes.unread" class="text-xs text-accent hover:underline" @click="notes.markAllRead()">Mark all read</button>
                </div>
                <ul class="max-h-96 overflow-y-auto">
                  <li v-if="!notes.items.length" class="px-4 py-10 text-center text-sm text-muted">You're all caught up ✨</li>
                  <li v-for="n in notes.items.slice(0, 12)" :key="n.id">
                    <button class="flex w-full gap-3 px-4 py-3 text-left transition hover:bg-surface-hover" @click="openNotification(n)">
                      <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="[levelDot[n.level], n.is_read && 'opacity-30']" />
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-sm" :class="!n.is_read && 'font-semibold'">{{ n.title }}</span>
                        <span class="line-clamp-2 block text-xs text-muted">{{ n.message }}</span>
                        <span class="mt-0.5 block text-[11px] text-muted/80">{{ timeAgo(n.created_at) }}</span>
                      </span>
                    </button>
                  </li>
                </ul>
                <RouterLink to="/notifications" class="block border-t border-line px-4 py-2.5 text-center text-xs font-medium text-accent hover:bg-surface-hover">View all</RouterLink>
              </div>
            </Transition>
          </div>

          <div ref="userRef" class="relative">
            <button class="flex items-center gap-2 rounded-full p-1 pr-1 hover:bg-surface-hover sm:pr-3" aria-label="Account menu" @click="userOpen = !userOpen">
              <UserAvatar :name="auth.user?.full_name || auth.user?.email" :src="auth.user?.avatar" size="sm" />
              <span class="hidden text-left leading-tight sm:block">
                <span class="block max-w-32 truncate text-sm font-medium">{{ auth.user?.full_name || auth.user?.email }}</span>
                <span class="block text-[11px] text-muted capitalize">{{ auth.role }}</span>
              </span>
            </button>
            <Transition name="fade">
              <div v-if="userOpen" class="glass-strong absolute right-0 z-40 mt-2 w-56 overflow-hidden rounded-2xl p-1.5">
                <RouterLink to="/profile" class="flex items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-surface-hover"><User class="h-4 w-4" /> Profile & settings</RouterLink>
                <RouterLink to="/handovers?awaiting_me=1" class="flex items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-surface-hover"><ClipboardList class="h-4 w-4" /> Awaiting my signature</RouterLink>
                <button class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-danger hover:bg-danger/10" @click="logout"><LogOut class="h-4 w-4" /> Sign out</button>
              </div>
            </Transition>
          </div>
        </div>
      </header>

      <main class="mx-auto w-full max-w-[1400px] flex-1 px-4 pt-6 pb-28 sm:px-6 lg:px-8 lg:pb-10">
        <RouterView v-slot="{ Component, route: r }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="r.path" />
          </Transition>
        </RouterView>
      </main>
    </div>

    <!-- Mobile bottom navigation -->
    <nav class="glass-strong safe-bottom fixed inset-x-0 bottom-0 z-30 border-x-0 border-b-0 lg:hidden" aria-label="Quick navigation">
      <div class="mx-auto grid max-w-md items-end px-2 pt-1.5 pb-1.5" :style="{ gridTemplateColumns: `repeat(${bottomNav.length + 1}, minmax(0, 1fr))` }">
        <template v-for="item in bottomNav" :key="item.id">
          <RouterLink v-if="item.fab" :to="item.route" class="-mt-7 flex flex-col items-center gap-1" :aria-label="item.name">
            <span class="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-accent text-accent-ink shadow-[0_10px_30px_-6px_var(--glow)] ring-4 ring-bg transition active:scale-95">
              <component :is="iconFor(item.icon)" class="h-6 w-6" />
            </span>
            <span class="text-[10px] font-medium text-muted">{{ item.name }}</span>
          </RouterLink>
          <RouterLink v-else :to="item.route" class="flex min-w-0 flex-col items-center gap-1 rounded-xl py-1.5 text-[10px] font-medium transition" :class="isActive(item) ? 'text-accent' : 'text-muted'">
            <component :is="iconFor(item.icon)" class="h-5 w-5" />
            <span class="max-w-full truncate">{{ item.name }}</span>
          </RouterLink>
        </template>
        <button class="flex flex-col items-center gap-1 rounded-xl py-1.5 text-[10px] font-medium text-muted" @click="drawer = true">
          <Menu class="h-5 w-5" /> More
        </button>
      </div>
    </nav>

    <!-- Mobile drawer -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="drawer" class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm lg:hidden" @click="drawer = false" />
      </Transition>
      <Transition enter-active-class="transition duration-300 ease-out" enter-from-class="-translate-x-full" leave-active-class="transition duration-200 ease-in" leave-to-class="-translate-x-full">
        <aside v-if="drawer" class="glass-strong fixed inset-y-0 left-0 z-50 flex w-[82%] max-w-xs flex-col rounded-r-3xl lg:hidden" aria-label="Menu">
          <div class="flex h-16 items-center justify-between px-5">
            <BrandName class="text-base" />
            <button class="grid h-9 w-9 place-items-center rounded-xl text-muted hover:bg-surface-hover" aria-label="Close menu" @click="drawer = false"><X class="h-5 w-5" /></button>
          </div>
          <form class="px-4 pb-2" role="search" @submit.prevent="submitSearch">
            <input v-model="globalSearch" class="field" placeholder="Search assets…" aria-label="Search assets" />
          </form>
          <nav class="flex-1 overflow-y-auto px-3 py-3" aria-label="Menu">
            <SidebarNav :items="sidebar.items" />
          </nav>
          <div class="safe-bottom border-t border-line p-3">
            <button class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-danger" @click="logout"><LogOut class="h-[18px] w-[18px]" /> Sign out</button>
          </div>
        </aside>
      </Transition>
    </Teleport>
  </div>
</template>
