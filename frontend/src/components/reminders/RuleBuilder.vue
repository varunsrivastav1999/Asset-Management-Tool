<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Send } from 'lucide-vue-next'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import EntityPicker from '@/components/ui/EntityPicker.vue'
import { remindersApi, tablesApi } from '@/api'
import { parseError } from '@/api/http'
import { pick, userLabel, userSub } from '@/api/pickers'
import { useSidebarStore } from '@/stores/sidebar'
import { useUiStore } from '@/stores/ui'
import { ASSET_STATUS } from '@/utils/constants'

const open = defineModel('open', { type: Boolean })
const props = defineProps({ rule: Object, templates: { type: Array, default: () => [] }, presetSection: { type: [Number, String], default: null } })
const emit = defineEmits(['saved', 'edit-templates'])
const ui = useUiStore()
const sidebar = useSidebarStore()

const TRIGGERS = [
  { value: 'warranty_expiry', label: 'Warranty expiry (N days before)' },
  { value: 'maintenance_due', label: 'Maintenance due (N days before)' },
  { value: 'overdue_return', label: 'Overdue return' },
  { value: 'handover_pending', label: 'Handover awaiting signature' },
  { value: 'new_receipt', label: 'New goods receipt' },
  { value: 'low_stock', label: 'Low stock' },
  { value: 'status_change', label: 'Asset status change' },
  { value: 'custom_date', label: 'Custom date column (before/after)' },
  { value: 'manual', label: 'Manual — “Send now” only' },
]
const RECIPIENTS = [
  { value: 'holder', label: 'Asset holder' },
  { value: 'department_head', label: 'Department head' },
  { value: 'managers', label: 'All managers' },
  { value: 'users', label: 'Specific users' },
  { value: 'custom', label: 'Custom emails / phones' },
]
const ATTACH = [
  { value: 'bill', label: 'Bill / invoice', hint: 'Uploaded file, or a generated PDF' },
  { value: 'receipt_pdf', label: 'Handover / receiving PDF' },
  { value: 'export_csv', label: 'Section export (CSV)' },
  { value: 'export_xlsx', label: 'Section export (Excel)' },
  { value: 'export_pdf', label: 'Section export (PDF)' },
]
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const TIMEZONES = (() => {
  try {
    return Intl.supportedValuesOf('timeZone')
  } catch {
    return ['UTC', 'Europe/London', 'Europe/Berlin', 'Asia/Kolkata', 'America/New_York']
  }
})()

const form = reactive({})
const errors = ref({})
const saving = ref(false)
const testing = ref(false)
const dateColumns = ref([])
const pickedUsers = ref([])

const sections = computed(() => sidebar.pages.filter((p) => p.table).map((p) => ({ value: p.id, label: p.name })))
const section = computed(() => sidebar.pages.find((p) => p.id === Number(form.section)))

watch(open, (v) => {
  if (!v) return
  errors.value = {}
  const r = props.rule
  Object.assign(form, {
    name: r?.name || '',
    section: r?.section ?? (props.presetSection ? Number(props.presetSection) : ''),
    trigger: r?.trigger || 'warranty_expiry',
    days: (r?.trigger_config?.days || [30, 7, 1]).join(', '),
    threshold: r?.trigger_config?.threshold ?? 5,
    to_status: r?.trigger_config?.to_status || '',
    min_age_hours: r?.trigger_config?.min_age_hours ?? 24,
    column: r?.trigger_config?.column || '',
    channels: r ? [...r.channels] : ['email', 'in_app'],
    types: r ? [...(r.recipients?.types || [])] : ['holder', 'managers'],
    user_ids: r?.recipients?.user_ids || [],
    emails: (r?.recipients?.emails || []).join(', '),
    phones: (r?.recipients?.phones || []).join(', '),
    kind: r?.schedule?.kind || 'daily',
    time: r?.schedule?.time || '09:00',
    timezone: r?.schedule?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    weekday: r?.schedule?.weekday ?? 0,
    date: r?.schedule?.date || '',
    template: r?.template || props.templates[0]?.id || '',
    attachments: r ? [...r.attachments] : [],
    is_active: r?.is_active ?? false,
  })
})
watch(
  () => [form.section, form.trigger],
  async () => {
    dateColumns.value = []
    if (form.trigger !== 'custom_date' || !section.value) return
    const data = await tablesApi.columns(section.value.table, section.value.id).catch(() => ({ columns: [] }))
    dateColumns.value = data.columns.filter((c) => c.type === 'date' && !c.is_builtin).map((c) => ({ value: c.key, label: c.name }))
  },
)
watch(() => form.trigger, (t) => t === 'manual' && (form.kind = 'manual'))

function toggle(list, value) {
  const i = form[list].indexOf(value)
  i === -1 ? form[list].push(value) : form[list].splice(i, 1)
}
const splitList = (s) => String(s || '').split(/[,\n;]+/).map((x) => x.trim()).filter(Boolean)

function payload() {
  const cfg = {}
  if (['warranty_expiry', 'maintenance_due', 'custom_date'].includes(form.trigger)) cfg.days = splitList(form.days).map(Number)
  if (form.trigger === 'low_stock') cfg.threshold = Number(form.threshold)
  if (form.trigger === 'status_change' && form.to_status) cfg.to_status = form.to_status
  if (form.trigger === 'handover_pending') cfg.min_age_hours = Number(form.min_age_hours)
  if (form.trigger === 'custom_date') cfg.column = form.column
  const schedule = { kind: form.kind, time: form.time, timezone: form.timezone }
  if (form.kind === 'weekly') schedule.weekday = Number(form.weekday)
  if (form.kind === 'once') schedule.date = form.date
  return {
    name: form.name,
    section: form.section || null,
    trigger: form.trigger,
    trigger_config: cfg,
    channels: form.channels,
    recipients: { types: form.types, user_ids: form.user_ids, emails: splitList(form.emails), phones: splitList(form.phones) },
    schedule,
    template: form.template,
    attachments: form.attachments,
    is_active: form.is_active,
  }
}

async function save() {
  saving.value = true
  errors.value = {}
  try {
    const rule = props.rule ? await remindersApi.updateRule(props.rule.id, payload()) : await remindersApi.createRule(payload())
    ui.success(`Rule “${rule.name}” saved`)
    emit('saved', rule)
    open.value = false
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

async function testSend() {
  if (!props.rule) return
  testing.value = true
  try {
    const res = await remindersApi.testRule(props.rule.id)
    const skipped = res.logs.filter((l) => l.status === 'skipped')
    if (res.queued) ui.success(`Test sent to you on ${res.queued} channel(s).`)
    if (skipped.length) ui.warning(skipped.map((l) => `${l.channel}: ${l.error}`).join('\n'), { title: 'Some channels were skipped' })
    if (!res.queued && !skipped.length) ui.warning('Nothing to send — check the channels and your contact details.')
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    testing.value = false
  }
}
const errText = (k) => (typeof errors.value[k] === 'object' ? Object.values(errors.value[k]).join(' ') : errors.value[k])
</script>

<template>
  <AppModal v-model:open="open" :title="rule ? `Edit “${rule.name}”` : 'New reminder rule'" size="xl">
    <form id="rule-form" class="space-y-6" novalidate @submit.prevent="save">
      <section class="grid gap-4 sm:grid-cols-2">
        <AppInput v-model="form.name" label="Rule name" required :error="errors.name" />
        <AppSelect v-model="form.section" label="Section" placeholder="— none —" :options="sections" :error="errors.section" />
        <AppSelect v-model="form.trigger" label="When" :options="TRIGGERS" :error="errors.trigger" />
        <AppInput v-if="['warranty_expiry', 'maintenance_due', 'custom_date'].includes(form.trigger)" v-model="form.days" label="Days before (negative = after)" placeholder="30, 7, 1" :error="errText('trigger_config')" />
        <AppInput v-if="form.trigger === 'low_stock'" v-model="form.threshold" label="Alert when in-stock count is below" type="number" min="0" :error="errText('trigger_config')" />
        <AppSelect v-if="form.trigger === 'status_change'" v-model="form.to_status" label="Only when changed to" placeholder="Any status" :options="Object.entries(ASSET_STATUS).map(([value, m]) => ({ value, label: m.label }))" />
        <AppInput v-if="form.trigger === 'handover_pending'" v-model="form.min_age_hours" label="Waiting at least (hours)" type="number" min="0" />
        <AppSelect v-if="form.trigger === 'custom_date'" v-model="form.column" class="sm:col-span-2" label="Date column" placeholder="Pick a custom date column of the section" :options="dateColumns" :error="errText('trigger_config')" />
      </section>

      <section>
        <p class="label">Send to</p>
        <div class="flex flex-wrap gap-2">
          <button v-for="r in RECIPIENTS" :key="r.value" type="button" role="checkbox" :aria-checked="form.types.includes(r.value)" class="chip px-3 py-1.5 text-sm" :class="form.types.includes(r.value) ? 'border-transparent bg-primary-soft text-primary' : 'text-muted'" @click="toggle('types', r.value)">{{ r.label }}</button>
        </div>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <EntityPicker v-if="form.types.includes('users')" v-model="form.user_ids" class="sm:col-span-2" multiple label="Users" :fetcher="pick.users" :label-of="userLabel" :sublabel-of="userSub" :initial="pickedUsers" @select="(u) => pickedUsers.push(u)" />
          <template v-if="form.types.includes('custom')">
            <AppInput v-model="form.emails" label="Emails" placeholder="ops@example.com, …" />
            <AppInput v-model="form.phones" label="Phones" placeholder="+1 555 0100, …" />
          </template>
        </div>
        <p v-if="errors.recipients" class="mt-1 text-xs text-danger">{{ errText('recipients') }}</p>
      </section>

      <section class="grid gap-4 sm:grid-cols-2">
        <div>
          <p class="label">Channels</p>
          <div class="flex flex-wrap gap-2">
            <button v-for="c in [{ value: 'email', label: 'Email' }, { value: 'sms', label: 'SMS' }, { value: 'in_app', label: 'In-app' }]" :key="c.value" type="button" role="checkbox" :aria-checked="form.channels.includes(c.value)" class="chip px-3 py-1.5 text-sm" :class="form.channels.includes(c.value) ? 'border-transparent bg-primary-soft text-primary' : 'text-muted'" @click="toggle('channels', c.value)">{{ c.label }}</button>
          </div>
          <p v-if="errors.channels" class="mt-1 text-xs text-danger">{{ errText('channels') }}</p>
          <p class="mt-1 text-xs text-muted">SMS can't carry files — it gets a short message with an expiring link.</p>
        </div>
        <div class="flex items-end gap-2">
          <AppSelect v-model="form.template" class="flex-1" label="Template" :options="templates.map((t) => ({ value: t.id, label: t.name }))" :error="errors.template" />
          <AppButton variant="ghost" size="sm" class="mb-0.5" @click="emit('edit-templates')">Manage</AppButton>
        </div>
      </section>

      <section class="grid gap-4 sm:grid-cols-4">
        <AppSelect v-model="form.kind" label="Schedule" :disabled="form.trigger === 'manual'" :options="[{ value: 'daily', label: 'Daily' }, { value: 'weekly', label: 'Weekly' }, { value: 'once', label: 'Once' }, { value: 'manual', label: 'Manual only' }]" :error="errText('schedule')" />
        <AppSelect v-if="form.kind === 'weekly'" v-model="form.weekday" label="On" :options="WEEKDAYS.map((d, i) => ({ value: i, label: d }))" />
        <AppInput v-if="form.kind === 'once'" v-model="form.date" label="Date" type="date" />
        <AppInput v-if="form.kind !== 'manual'" v-model="form.time" label="Time" type="time" />
        <AppSelect v-if="form.kind !== 'manual'" v-model="form.timezone" label="Timezone" :options="TIMEZONES.map((t) => ({ value: t, label: t }))" />
      </section>

      <section>
        <p class="label">Attachments (email)</p>
        <div class="grid gap-2 sm:grid-cols-2">
          <label v-for="a in ATTACH" :key="a.value" class="flex items-start gap-2 rounded-xl border border-line px-3 py-2 text-sm">
            <input type="checkbox" class="mt-0.5 h-4 w-4 accent-[var(--primary)]" :checked="form.attachments.includes(a.value)" @change="toggle('attachments', a.value)" />
            <span>{{ a.label }}<span v-if="a.hint" class="block text-xs text-muted">{{ a.hint }}</span></span>
          </label>
        </div>
        <p v-if="errors.attachments" class="mt-1 text-xs text-danger">{{ errText('attachments') }}</p>
        <p class="mt-1 text-xs text-muted">Exports use the section's column names. Over 10 MB, a signed link that expires is sent instead.</p>
      </section>

      <label class="flex items-center gap-2 text-sm"><input v-model="form.is_active" type="checkbox" class="h-4 w-4 accent-[var(--primary)]" /> Active (runs on schedule)</label>
    </form>
    <template #footer>
      <AppButton v-if="rule" variant="ghost" class="sm:mr-auto" :icon="Send" :loading="testing" @click="testSend">Send test to me</AppButton>
      <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
      <AppButton type="submit" form="rule-form" :loading="saving">Save rule</AppButton>
    </template>
  </AppModal>
</template>
