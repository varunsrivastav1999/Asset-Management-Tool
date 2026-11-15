<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { ArrowLeftRight, LayoutGrid, PackagePlus, RefreshCw } from 'lucide-vue-next'
import { widgetsApi } from '@/api'
import { parseError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import DashboardWidget from '@/components/dashboard/DashboardWidget.vue'

const auth = useAuthStore()
const notes = useNotificationsStore()
const widgets = ref([])
const canEdit = ref(false)
const loading = ref(true)
const error = ref('')
const pulse = ref(false)

const SIZE = {
  sm: 'col-span-1',
  md: 'sm:col-span-2',
  lg: 'sm:col-span-2 xl:col-span-3',
  full: 'sm:col-span-2 xl:col-span-4',
}

async function load() {
  error.value = ''
  try {
    const data = await widgetsApi.layout()
    widgets.value = data.widgets
    canEdit.value = data.can_edit
  } catch (e) {
    error.value = parseError(e).message
  } finally {
    loading.value = false
  }
}
const liveReload = useDebounceFn(async () => {
  await load()
  pulse.value = true
  setTimeout(() => (pulse.value = false), 1200)
}, 800)
watch(() => notes.dashboardTick, liveReload)
watch(() => notes.layoutTick, load)
onMounted(load)

const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
})
</script>

<template>
  <div>
    <PageHeader>
      <template #title>{{ greeting }}, <span class="text-gradient">{{ auth.user?.first_name || 'there' }}</span></template>
      <template #subtitle>
        <span class="inline-flex items-center gap-2">
          Here's what's happening with your assets
          <span class="inline-flex items-center gap-1.5 text-xs transition" :class="pulse ? 'text-accent' : 'text-muted/70'">
            <span class="h-1.5 w-1.5 rounded-full" :class="pulse ? 'animate-ping bg-accent' : notes.status === 'online' ? 'bg-success' : 'bg-muted'" />
            {{ notes.status === 'online' ? 'live' : 'offline' }}
          </span>
        </span>
      </template>
      <template #actions>
        <AppButton variant="ghost" size="icon" :icon="RefreshCw" aria-label="Refresh" @click="load" />
        <AppButton v-if="canEdit" variant="secondary" :icon="LayoutGrid" to="/settings/dashboard">Customize</AppButton>
        <AppButton v-if="auth.isManager" variant="secondary" :icon="PackagePlus" to="/receiving/new">Receive</AppButton>
        <AppButton v-if="auth.isManager" :icon="ArrowLeftRight" to="/handovers/new">New handover</AppButton>
      </template>
    </PageHeader>

    <p v-if="error" class="card mb-6 p-4 text-sm text-danger">{{ error }}</p>

    <div v-if="loading" class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div v-for="i in 4" :key="`s${i}`" class="skeleton h-28" />
      <div class="skeleton h-80 sm:col-span-2 xl:col-span-3" />
      <div class="skeleton h-80" />
    </div>

    <div v-else-if="!widgets.length" class="card">
      <EmptyState :icon="LayoutGrid" title="Your dashboard is empty" :message="canEdit ? 'Add widgets to build the dashboard for each role.' : 'An administrator hasn’t configured widgets for your role yet.'">
        <AppButton v-if="canEdit" :icon="LayoutGrid" to="/settings/dashboard">Add widgets</AppButton>
      </EmptyState>
    </div>

    <TransitionGroup v-else tag="div" name="list" class="grid grid-flow-row-dense grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div v-for="(w, i) in widgets" :key="w.id" class="min-w-0 animate-fade-up" :class="SIZE[w.size]" :style="{ animationDelay: `${Math.min(i, 10) * 40}ms` }">
        <DashboardWidget :widget="w" />
      </div>
    </TransitionGroup>
  </div>
</template>
