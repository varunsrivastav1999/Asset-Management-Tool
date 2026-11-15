<script setup>
import { onMounted, ref } from 'vue'
import { BadgeCheck, Save, Send } from 'lucide-vue-next'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import { remindersApi } from '@/api'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const prefs = ref(null)
const errors = ref({})
const saving = ref(false)
const code = ref('')
const codeSent = ref(false)
const verifying = ref(false)
const TZ = (() => {
  try {
    return Intl.supportedValuesOf('timeZone')
  } catch {
    return ['UTC']
  }
})()
const TRI = [
  { value: 'inherit', label: 'Default' },
  { value: 'on', label: 'On' },
  { value: 'off', label: 'Off' },
]
const toTri = (v) => (v === null || v === undefined ? 'inherit' : v ? 'on' : 'off')
const fromTri = (v) => (v === 'inherit' ? null : v === 'on')

onMounted(async () => {
  const data = await remindersApi.preferences()
  data.sections = data.sections.map((s) => ({ ...s, emailTri: toTri(s.email), smsTri: toTri(s.sms) }))
  prefs.value = data
})

async function save() {
  saving.value = true
  errors.value = {}
  try {
    const p = prefs.value
    const res = await remindersApi.savePreferences({
      phone: p.phone,
      quiet_start: p.quiet_start,
      quiet_end: p.quiet_end,
      timezone: p.timezone,
      default: p.default,
      sections: p.sections.map((s) => ({ id: s.id, email: fromTri(s.emailTri), sms: fromTri(s.smsTri) })),
    })
    res.sections = res.sections.map((s) => ({ ...s, emailTri: toTri(s.email), smsTri: toTri(s.sms) }))
    prefs.value = res
    ui.success('Notification preferences saved')
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}
async function sendCode() {
  verifying.value = true
  try {
    await save()
    await remindersApi.verifyPhone()
    codeSent.value = true
    ui.success('We sent a 6-digit code to your phone.')
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    verifying.value = false
  }
}
async function confirmCode() {
  verifying.value = true
  try {
    await remindersApi.verifyPhone(code.value.trim())
    prefs.value.phone_verified = true
    codeSent.value = false
    code.value = ''
    ui.success('Phone verified')
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    verifying.value = false
  }
}
</script>

<template>
  <form class="card p-6" @submit.prevent="save">
    <h2 class="mb-1 font-semibold">Notifications</h2>
    <p class="mb-4 text-sm text-muted">Choose how reminders reach you. Your choices are always respected.</p>
    <div v-if="!prefs" class="space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-10" /></div>
    <template v-else>
      <div class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <AppInput v-model="prefs.phone" label="Mobile number (with country code)" type="tel" placeholder="+1 555 0100" :error="errors.phone" />
        <div class="flex items-center gap-2 pb-1">
          <AppBadge v-if="prefs.phone_verified" tone="emerald"><BadgeCheck class="h-3.5 w-3.5" /> Verified</AppBadge>
          <AppButton v-else size="sm" variant="secondary" :icon="Send" :loading="verifying" :disabled="!prefs.phone" @click="sendCode">Verify</AppButton>
        </div>
      </div>
      <div v-if="codeSent" class="mt-3 flex items-end gap-2">
        <AppInput v-model="code" class="w-40" label="Code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
        <AppButton size="sm" :loading="verifying" :disabled="code.length !== 6" @click="confirmCode">Confirm</AppButton>
      </div>
      <p class="mt-1 text-xs text-muted">SMS reminders are only sent to a verified number.</p>

      <div class="mt-5 grid gap-4 sm:grid-cols-3">
        <AppInput v-model="prefs.quiet_start" label="Quiet hours from" type="time" :error="errors.quiet_start" />
        <AppInput v-model="prefs.quiet_end" label="until" type="time" :error="errors.quiet_end" />
        <AppSelect v-model="prefs.timezone" label="Timezone" :options="TZ.map((t) => ({ value: t, label: t }))" :error="errors.timezone" />
      </div>
      <p class="mt-1 text-xs text-muted">Email and SMS that fall in your quiet hours are delivered when they end. In-app notifications still appear.</p>

      <div class="mt-5 overflow-x-auto rounded-2xl border border-line">
        <table class="w-full text-sm">
          <thead class="text-xs tracking-wide text-muted uppercase">
            <tr class="border-b border-line"><th class="px-4 py-2 text-left font-medium">Section</th><th class="px-4 py-2 font-medium">Email</th><th class="px-4 py-2 font-medium">SMS</th></tr>
          </thead>
          <tbody>
            <tr class="border-b border-line bg-primary-soft/40">
              <td class="px-4 py-2 font-medium">All sections (default)</td>
              <td class="px-4 py-2 text-center"><input v-model="prefs.default.email" type="checkbox" class="h-4 w-4 accent-[var(--primary)]" aria-label="Email by default" /></td>
              <td class="px-4 py-2 text-center"><input v-model="prefs.default.sms" type="checkbox" class="h-4 w-4 accent-[var(--primary)]" aria-label="SMS by default" /></td>
            </tr>
            <tr v-for="s in prefs.sections" :key="s.id" class="border-b border-line last:border-0">
              <td class="px-4 py-2">{{ s.name }}</td>
              <td class="px-2 py-1.5"><AppSelect v-model="s.emailTri" class="mx-auto w-28" :aria-label="`${s.name} email`" :options="TRI" /></td>
              <td class="px-2 py-1.5"><AppSelect v-model="s.smsTri" class="mx-auto w-28" :aria-label="`${s.name} SMS`" :options="TRI" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="mt-4 flex justify-end"><AppButton type="submit" :icon="Save" :loading="saving">Save notification settings</AppButton></div>
    </template>
  </form>
</template>
