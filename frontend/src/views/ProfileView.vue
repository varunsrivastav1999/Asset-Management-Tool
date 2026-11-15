<script setup>
import { reactive, ref } from 'vue'
import { Camera, KeyRound, Monitor, Moon, Save, Sun } from 'lucide-vue-next'
import { authApi } from '@/api'
import { parseError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import UserAvatar from '@/components/ui/UserAvatar.vue'
import NotificationPreferences from '@/components/reminders/NotificationPreferences.vue'

const auth = useAuthStore()
const theme = useThemeStore()
const ui = useUiStore()
const profile = reactive({ first_name: auth.user?.first_name || '', last_name: auth.user?.last_name || '', job_title: auth.user?.job_title || '', phone: auth.user?.phone || '' })
const pwd = reactive({ current_password: '', new_password: '', confirm: '' })
const errors = ref({})
const pwdErrors = ref({})
const saving = ref(false)
const changing = ref(false)

async function saveProfile() {
  saving.value = true
  errors.value = {}
  try {
    auth.setUser(await authApi.updateMe(profile))
    ui.success('Profile saved')
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}
async function uploadAvatar(ev) {
  const file = ev.target.files?.[0]
  if (!file) return
  const form = new FormData()
  form.append('avatar', file)
  try {
    auth.setUser(await authApi.updateMe(form))
    ui.success('Avatar updated')
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    ev.target.value = ''
  }
}
async function changePassword() {
  pwdErrors.value = {}
  if (pwd.new_password !== pwd.confirm) return (pwdErrors.value = { confirm: 'Passwords do not match.' })
  changing.value = true
  try {
    await authApi.changePassword({ current_password: pwd.current_password, new_password: pwd.new_password })
    Object.assign(pwd, { current_password: '', new_password: '', confirm: '' })
    ui.success('Password changed')
    auth.refreshProfile().catch(() => {}) // clears the default-password reminder
  } catch (e) {
    const { message, fields } = parseError(e)
    pwdErrors.value = fields
    ui.error(message)
  } finally {
    changing.value = false
  }
}
const modes = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-4">
    <PageHeader title="Profile & settings" />
    <section class="card flex flex-col items-center gap-4 p-6 sm:flex-row">
      <label class="group relative cursor-pointer" aria-label="Change avatar">
        <UserAvatar :name="auth.user?.full_name || auth.user?.email" :src="auth.user?.avatar" size="lg" />
        <span class="absolute inset-0 grid place-items-center rounded-full bg-black/50 opacity-0 transition group-hover:opacity-100"><Camera class="h-5 w-5 text-white" /></span>
        <input type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" @change="uploadAvatar" />
      </label>
      <div class="text-center sm:text-left">
        <p class="text-lg font-semibold">{{ auth.user?.full_name }}</p>
        <p class="text-sm text-muted">{{ auth.user?.email }}</p>
        <div class="mt-2 flex flex-wrap justify-center gap-2 sm:justify-start">
          <AppBadge tone="violet">{{ auth.role }}</AppBadge>
          <AppBadge v-if="auth.user?.department_name">{{ auth.user.department_name }}</AppBadge>
          <AppBadge v-if="auth.user?.employee_id">ID {{ auth.user.employee_id }}</AppBadge>
        </div>
      </div>
    </section>

    <section class="card p-6">
      <h2 class="mb-4 font-semibold">Appearance</h2>
      <div class="grid grid-cols-3 gap-2">
        <button v-for="m in modes" :key="m.value" class="flex flex-col items-center gap-2 rounded-2xl border p-4 text-sm transition" :class="theme.mode === m.value ? 'border-accent bg-accent/10' : 'border-line hover:border-line-strong'" @click="theme.setMode(m.value)">
          <component :is="m.icon" class="h-5 w-5" /> {{ m.label }}
        </button>
      </div>
    </section>

    <form class="card p-6" @submit.prevent="saveProfile">
      <h2 class="mb-4 font-semibold">Personal details</h2>
      <div class="grid gap-4 sm:grid-cols-2">
        <AppInput v-model="profile.first_name" label="First name" :error="errors.first_name" />
        <AppInput v-model="profile.last_name" label="Last name" :error="errors.last_name" />
        <AppInput v-model="profile.job_title" label="Job title" />
        <AppInput v-model="profile.phone" label="Phone" type="tel" />
      </div>
      <div class="mt-4 flex justify-end"><AppButton type="submit" :icon="Save" :loading="saving">Save</AppButton></div>
    </form>

    <NotificationPreferences />

    <form id="password" class="card scroll-mt-24 p-6" @submit.prevent="changePassword">
      <h2 class="mb-4 font-semibold">Change password</h2>
      <div class="grid gap-4 sm:grid-cols-3">
        <AppInput v-model="pwd.current_password" label="Current" type="password" autocomplete="current-password" :error="pwdErrors.current_password" />
        <AppInput v-model="pwd.new_password" label="New" type="password" autocomplete="new-password" :error="pwdErrors.new_password" />
        <AppInput v-model="pwd.confirm" label="Confirm" type="password" autocomplete="new-password" :error="pwdErrors.confirm" />
      </div>
      <div class="mt-4 flex justify-end"><AppButton type="submit" variant="secondary" :icon="KeyRound" :loading="changing" :disabled="!pwd.current_password || !pwd.new_password">Update password</AppButton></div>
    </form>
  </div>
</template>
