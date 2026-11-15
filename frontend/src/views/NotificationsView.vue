<script setup>
import { onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { BellOff, CheckCheck, Trash2 } from 'lucide-vue-next'
import { notificationsApi } from '@/api'
import { useList } from '@/composables/useList'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppTabs from '@/components/ui/AppTabs.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { formatDateTime, timeAgo } from '@/utils/format'

const store = useNotificationsStore()
const ui = useUiStore()
const router = useRouter()
const list = useList(notificationsApi.list, { filters: { is_read: '', category: '' } })
onMounted(list.load)
watch(() => store.items.length, () => list.load())

const levelTone = { critical: 'rose', warning: 'amber', success: 'emerald', info: 'primary' }
async function open(n) {
  if (!n.is_read) {
    await store.markRead(n)
    n.is_read = true
  }
  if (n.link) router.push(n.link)
}
async function readAll() {
  await store.markAllRead()
  list.load()
}
async function clearRead() {
  const res = await notificationsApi.clearRead()
  ui.success(`${res.deleted} notifications cleared`)
  list.load()
}
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <PageHeader title="Notifications" :subtitle="`${store.unread} unread`">
      <template #actions>
        <AppButton variant="secondary" :icon="CheckCheck" :disabled="!store.unread" @click="readAll">Mark all read</AppButton>
        <AppButton variant="ghost" :icon="Trash2" @click="clearRead">Clear read</AppButton>
      </template>
    </PageHeader>
    <div class="card p-3 sm:p-4">
      <AppTabs
        :model-value="list.filters.is_read === 'false' ? 'unread' : 'all'"
        :tabs="[{ value: 'all', label: 'All' }, { value: 'unread', label: 'Unread', count: store.unread }]"
        @update:model-value="(v) => (list.filters.is_read = v === 'unread' ? 'false' : '')"
      />
      <div v-if="list.loading.value && !list.items.value.length" class="mt-3 space-y-2"><div v-for="i in 5" :key="i" class="skeleton h-16" /></div>
      <EmptyState v-else-if="!list.items.value.length" :icon="BellOff" title="No notifications" message="Alerts about warranties, maintenance and handovers appear here." />
      <TransitionGroup v-else tag="ul" name="list" class="mt-3 divide-y divide-line">
        <li v-for="n in list.items.value" :key="n.id">
          <button class="flex w-full gap-3 rounded-xl px-2 py-3 text-left transition hover:bg-surface-hover" @click="open(n)">
            <span class="mt-2 h-2 w-2 shrink-0 rounded-full" :class="n.is_read ? 'bg-line-strong' : 'bg-accent shadow-[0_0_8px_var(--accent)]'" />
            <span class="min-w-0 flex-1">
              <span class="flex flex-wrap items-center gap-2">
                <span class="text-sm" :class="!n.is_read && 'font-semibold'">{{ n.title }}</span>
                <AppBadge :tone="levelTone[n.level]">{{ n.category }}</AppBadge>
              </span>
              <span class="mt-0.5 block text-sm text-muted">{{ n.message }}</span>
              <span class="mt-1 block text-xs text-muted/80" :title="formatDateTime(n.created_at)">{{ timeAgo(n.created_at) }}</span>
            </span>
          </button>
        </li>
      </TransitionGroup>
      <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
    </div>
  </div>
</template>
