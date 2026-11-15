<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, Download, FileText, Pencil, Plus, RotateCw, Send, Trash2 } from 'lucide-vue-next'
import { remindersApi } from '@/api'
import { downloadFile, parseError } from '@/api/http'
import { useList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { useSidebarStore } from '@/stores/sidebar'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppTabs from '@/components/ui/AppTabs.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import DataTable from '@/components/ui/DataTable.vue'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import RuleBuilder from '@/components/reminders/RuleBuilder.vue'
import TemplateEditor from '@/components/reminders/TemplateEditor.vue'
import { formatDateTime, timeAgo } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const sidebar = useSidebarStore()

const tab = ref(['rules', 'templates', 'logs', 'channels'].includes(route.query.tab) ? route.query.tab : 'rules')
watch(tab, (t) => router.replace({ query: { ...route.query, tab: t } }))
const tabs = computed(() => [
  { value: 'rules', label: 'Rules' },
  { value: 'templates', label: 'Templates' },
  { value: 'logs', label: 'Logs' },
  ...(auth.isAdmin ? [{ value: 'channels', label: 'Channels' }] : []),
])
const sectionFilter = ref(route.query.section ? Number(route.query.section) : '')
const sectionName = computed(() => sidebar.pages.find((p) => p.id === sectionFilter.value)?.name)

// --- rules ---
const rules = ref([])
const templates = ref([])
const loadingRules = ref(true)
async function loadRules() {
  loadingRules.value = true
  try {
    const [r, t] = await Promise.all([remindersApi.rules({ page_size: 200, ...(sectionFilter.value ? { section: sectionFilter.value } : {}) }), remindersApi.templates()])
    rules.value = r.results ?? r
    templates.value = t
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    loadingRules.value = false
  }
}
onMounted(loadRules)
watch(sectionFilter, (v) => {
  router.replace({ query: { ...route.query, section: v || undefined } })
  loadRules()
})

const builderOpen = ref(false)
const editingRule = ref(null)
const openRule = (r = null) => {
  editingRule.value = r
  builderOpen.value = true
}
async function toggleActive(r) {
  try {
    const updated = await remindersApi.updateRule(r.id, { is_active: !r.is_active })
    Object.assign(r, updated)
    ui.success(updated.is_active ? `“${r.name}” is active` : `“${r.name}” paused`)
  } catch (e) {
    ui.error(parseError(e).message)
  }
}
async function sendNow(r) {
  const ok = await ui.confirm({ title: `Send “${r.name}” now?`, message: 'Messages go out immediately to every matching recipient.', confirmText: 'Send now', action: () => remindersApi.sendNow(r.id) })
  if (ok) ui.success('Queued — check the Logs tab for delivery.')
}
async function removeRule(r) {
  const ok = await ui.confirm({ title: `Delete the rule “${r.name}”?`, message: 'Past log entries are kept. This cannot be undone.', confirmText: 'Delete rule', danger: true, action: () => remindersApi.deleteRule(r.id) })
  if (ok) {
    ui.success('Rule deleted')
    loadRules()
  }
}
const TRIGGER_LABEL = {
  warranty_expiry: 'Warranty expiry',
  maintenance_due: 'Maintenance due',
  overdue_return: 'Overdue return',
  handover_pending: 'Pending signature',
  new_receipt: 'New receipt',
  low_stock: 'Low stock',
  status_change: 'Status change',
  custom_date: 'Custom date',
  manual: 'Manual',
}
const describeSchedule = (s) =>
  ({ daily: `Daily at ${s.time}`, weekly: `Weekly (${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][s.weekday || 0]}) at ${s.time}`, once: `Once on ${s.date} at ${s.time}`, manual: 'Manual only' })[s.kind] +
  (s.kind !== 'manual' ? ` · ${s.timezone}` : '')

// --- templates ---
const tplOpen = ref(false)
const editingTpl = ref(null)
const openTemplate = (t = null) => {
  editingTpl.value = t
  tplOpen.value = true
}
async function removeTemplate(t) {
  const ok = await ui.confirm({ title: `Delete the template “${t.name}”?`, message: 'Templates used by rules cannot be deleted.', confirmText: 'Delete', danger: true, action: () => remindersApi.deleteTemplate(t.id) })
  if (ok) {
    ui.success('Template deleted')
    loadRules()
  }
}

// --- logs ---
const logs = useList(remindersApi.logs, { filters: { search: '', status: route.query.status || '', channel: '', is_test: '' }, syncUrl: false })
watch(tab, (t) => t === 'logs' && logs.load(), { immediate: true })
const LOG_TONE = { sent: 'emerald', failed: 'rose', queued: 'amber', skipped: 'slate' }
async function retry(log) {
  try {
    Object.assign(log, await remindersApi.retryLog(log.id))
    ui.success('Retried')
  } catch (e) {
    ui.error(parseError(e).message)
  }
}
const exportLogs = () => downloadFile('/reminders/logs/export/', { params: logs.params() }).catch((e) => ui.error(parseError(e).message))

// --- channels (admin) ---
const channels = reactive({})
const channelsLoaded = ref(false)
const savingChannels = ref(false)
watch(tab, async (t) => {
  if (t !== 'channels' || channelsLoaded.value) return
  Object.assign(channels, await remindersApi.channels())
  channelsLoaded.value = true
}, { immediate: true })
async function saveChannels() {
  savingChannels.value = true
  try {
    const { smtp_configured: _a, sms_configured: _b, from_email: _c, updated_at: _d, ...data } = channels
    Object.assign(channels, await remindersApi.saveChannels(data))
    ui.success('Channel settings saved')
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    savingChannels.value = false
  }
}
</script>

<template>
  <div>
    <PageHeader title="Reminders" :subtitle="sectionName ? `Rules for ${sectionName}` : 'Email, SMS and in-app reminders for every section'">
      <template #actions>
        <AppButton v-if="tab === 'templates'" :icon="Plus" @click="openTemplate()">New template</AppButton>
        <AppButton v-else-if="tab === 'logs'" variant="secondary" :icon="Download" @click="exportLogs">Export CSV</AppButton>
        <AppButton v-else-if="tab === 'rules'" :icon="Plus" @click="openRule()">New rule</AppButton>
      </template>
    </PageHeader>

    <div class="card p-3 sm:p-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <AppTabs v-model="tab" :tabs="tabs" />
        <AppSelect v-if="tab === 'rules'" v-model="sectionFilter" class="sm:w-56" aria-label="Section" placeholder="All sections" :options="sidebar.pages.filter((p) => p.table).map((p) => ({ value: p.id, label: p.name }))" />
      </div>

      <!-- Rules -->
      <div v-if="tab === 'rules'" class="mt-4">
        <div v-if="loadingRules" class="space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-20" /></div>
        <EmptyState v-else-if="!rules.length" :icon="Bell" title="No reminder rules" message="Create a rule to email, text or notify people automatically.">
          <AppButton :icon="Plus" @click="openRule()">New rule</AppButton>
        </EmptyState>
        <ul v-else class="grid gap-3 lg:grid-cols-2">
          <li v-for="r in rules" :key="r.id" class="rounded-2xl border border-line p-4 transition hover:border-line-strong">
            <div class="flex items-start gap-3">
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium">{{ r.name }}</p>
                <p class="mt-0.5 text-xs text-muted">{{ TRIGGER_LABEL[r.trigger] }} · {{ r.section_name || 'No section' }} · {{ describeSchedule(r.schedule) }}</p>
                <div class="mt-2 flex flex-wrap gap-1.5">
                  <AppBadge v-for="c in r.channels" :key="c" tone="primary">{{ c.replace('_', '-') }}</AppBadge>
                  <AppBadge v-for="a in r.attachments" :key="a" tone="slate">{{ a.replace('_', ' ') }}</AppBadge>
                </div>
                <p class="mt-2 text-xs text-muted">
                  {{ r.next_run_at ? `Next: ${formatDateTime(r.next_run_at)}` : 'Not scheduled' }}<template v-if="r.last_run_at"> · last ran {{ timeAgo(r.last_run_at) }}</template>
                </p>
              </div>
              <label class="relative inline-flex cursor-pointer items-center" :title="r.is_active ? 'Active' : 'Paused'">
                <input type="checkbox" class="peer sr-only" :checked="r.is_active" :aria-label="`${r.name} active`" @change="toggleActive(r)" />
                <span class="h-6 w-11 rounded-full bg-line-strong transition peer-checked:bg-primary peer-focus-visible:ring-4 peer-focus-visible:ring-[var(--primary-ring)]" />
                <span class="absolute left-0.5 h-5 w-5 rounded-full bg-white shadow transition peer-checked:translate-x-5" />
              </label>
            </div>
            <div class="mt-3 flex flex-wrap gap-1 border-t border-line pt-3">
              <AppButton size="sm" variant="ghost" :icon="Pencil" @click="openRule(r)">Edit</AppButton>
              <AppButton size="sm" variant="ghost" :icon="Send" @click="sendNow(r)">Send now</AppButton>
              <AppButton size="sm" variant="ghost" :icon="FileText" @click="tab = 'logs'; logs.filters.search = r.name">Logs</AppButton>
              <AppButton size="sm" variant="ghost" class="ml-auto" :icon="Trash2" :aria-label="`Delete ${r.name}`" @click="removeRule(r)" />
            </div>
          </li>
        </ul>
      </div>

      <!-- Templates -->
      <div v-else-if="tab === 'templates'" class="mt-4">
        <EmptyState v-if="!templates.length" title="No templates"><AppButton :icon="Plus" @click="openTemplate()">New template</AppButton></EmptyState>
        <ul v-else class="divide-y divide-line">
          <li v-for="t in templates" :key="t.id" class="flex items-center gap-3 py-3">
            <div class="min-w-0 flex-1">
              <p class="truncate font-medium">{{ t.name }}</p>
              <p class="truncate text-xs text-muted">{{ t.subject }}</p>
            </div>
            <AppButton size="sm" variant="ghost" :icon="Pencil" @click="openTemplate(t)">Edit</AppButton>
            <AppButton size="sm" variant="ghost" :icon="Trash2" :aria-label="`Delete ${t.name}`" @click="removeTemplate(t)" />
          </li>
        </ul>
      </div>

      <!-- Logs -->
      <div v-else-if="tab === 'logs'" class="mt-4">
        <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px_150px]">
          <SearchInput v-model="logs.filters.search" placeholder="Search recipient, rule, subject…" />
          <AppSelect v-model="logs.filters.status" aria-label="Status" placeholder="All statuses" :options="['sent', 'failed', 'queued', 'skipped'].map((s) => ({ value: s, label: s }))" />
          <AppSelect v-model="logs.filters.channel" aria-label="Channel" placeholder="All channels" :options="[{ value: 'email', label: 'Email' }, { value: 'sms', label: 'SMS' }, { value: 'in_app', label: 'In-app' }]" />
        </div>
        <DataTable
          class="mt-3"
          :columns="[
            { key: 'created_at', label: 'When' },
            { key: 'rule_name', label: 'Rule' },
            { key: 'recipient_address', label: 'Recipient' },
            { key: 'channel', label: 'Channel' },
            { key: 'status', label: 'Status' },
            { key: 'actions', label: '', align: 'right', mobile: false },
          ]"
          :rows="logs.items.value"
          :loading="logs.loading.value"
        >
          <template #cell-created_at="{ value }"><span class="text-sm whitespace-nowrap text-muted" :title="formatDateTime(value)">{{ timeAgo(value) }}</span></template>
          <template #cell-rule_name="{ row }">
            <p class="truncate text-sm">{{ row.rule_name }} <AppBadge v-if="row.is_test">test</AppBadge></p>
            <p class="truncate text-xs text-muted">{{ row.subject }}</p>
          </template>
          <template #cell-recipient_address="{ row }"><span class="text-sm">{{ row.recipient_name || row.recipient_address }}</span></template>
          <template #cell-status="{ row }">
            <AppBadge :tone="LOG_TONE[row.status]" dot>{{ row.status }}</AppBadge>
            <p v-if="row.error" class="mt-0.5 max-w-xs truncate text-[11px] text-muted" :title="row.error">{{ row.error }}</p>
          </template>
          <template #cell-actions="{ row }"><AppButton v-if="row.status === 'failed'" size="sm" variant="secondary" :icon="RotateCw" @click="retry(row)">Retry</AppButton></template>
          <template #empty><EmptyState :icon="FileText" title="No deliveries yet" /></template>
        </DataTable>
        <AppPagination v-model="logs.page.value" :pages="logs.pages.value" :count="logs.count.value" />
      </div>

      <!-- Channels -->
      <form v-else-if="tab === 'channels' && channelsLoaded" class="mt-4 grid gap-4 sm:grid-cols-2" @submit.prevent="saveChannels">
        <div class="rounded-2xl border border-line p-4 sm:col-span-2">
          <p class="text-sm">
            Email:
            <AppBadge :tone="channels.smtp_configured ? 'emerald' : 'amber'">{{ channels.smtp_configured ? `SMTP configured · from ${channels.from_email}` : 'SMTP not configured (console only)' }}</AppBadge>
            · SMS:
            <AppBadge :tone="channels.sms_configured ? 'emerald' : 'amber'">{{ channels.sms_configured ? `${channels.sms_provider} ready` : 'API key missing' }}</AppBadge>
          </p>
          <p class="mt-2 text-xs text-muted">Passwords and API keys are read from environment variables (SMTP_*, SMS_API_KEY) and are never shown here.</p>
        </div>
        <label class="flex items-center gap-2 text-sm"><input v-model="channels.email_enabled" type="checkbox" class="h-4 w-4 accent-[var(--primary)]" /> Email enabled</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="channels.sms_enabled" type="checkbox" class="h-4 w-4 accent-[var(--primary)]" /> SMS enabled</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="channels.in_app_enabled" type="checkbox" class="h-4 w-4 accent-[var(--primary)]" /> In-app enabled</label>
        <span />
        <AppInput v-model="channels.sender_name" label="Email sender name" />
        <AppSelect v-model="channels.sms_provider" label="SMS provider" :options="[{ value: 'console', label: 'Console (development)' }, { value: 'twilio', label: 'Twilio' }, { value: 'msg91', label: 'MSG91' }]" />
        <AppInput v-model="channels.sms_sender_id" label="SMS sender ID" maxlength="11" />
        <AppInput v-model="channels.daily_cap" label="Daily send cap" type="number" min="0" />
        <AppInput v-model="channels.email_per_minute" label="Emails per minute" type="number" min="1" />
        <AppInput v-model="channels.sms_per_minute" label="SMS per minute" type="number" min="1" />
        <div class="flex justify-end sm:col-span-2"><AppButton type="submit" :loading="savingChannels">Save settings</AppButton></div>
      </form>
    </div>

    <RuleBuilder v-model:open="builderOpen" :rule="editingRule" :templates="templates" :preset-section="sectionFilter || null" @saved="loadRules" @edit-templates="builderOpen = false; tab = 'templates'" />
    <TemplateEditor v-model:open="tplOpen" :template="editingTpl" @saved="loadRules" />
  </div>
</template>
