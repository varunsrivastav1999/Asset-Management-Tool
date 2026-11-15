<script setup>
import { ShieldAlert } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'

/** Shown while the signed-in account still uses the first-run default (or printed) password. */
const auth = useAuthStore()
</script>

<template>
  <div v-if="auth.user?.must_change_password" role="alert" class="mb-5 flex flex-col gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm sm:flex-row sm:items-center" data-testid="default-password-banner">
    <ShieldAlert class="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-300" aria-hidden="true" />
    <p class="min-w-0 flex-1 text-amber-900 dark:text-amber-100">
      <b>You're still using the default password.</b>
      Anyone on your network who knows it can sign in as an administrator — please change it now.
    </p>
    <RouterLink to="/profile#password" class="shrink-0 rounded-xl bg-primary px-3 py-1.5 text-center text-sm font-medium text-primary-ink hover:bg-primary-hover">Change password</RouterLink>
  </div>
</template>
