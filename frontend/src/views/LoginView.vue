<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Boxes, Eye, EyeOff, Lock, Mail, QrCode, ShieldCheck, Zap } from 'lucide-vue-next'
import AppButton from '@/components/ui/AppButton.vue'
import BrandName from '@/components/ui/BrandName.vue'
import { APP_NAME } from '@/brand'
import AppInput from '@/components/ui/AppInput.vue'
import { useAuthStore } from '@/stores/auth'
import { parseError } from '@/api/http'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const show = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!email.value || !password.value) {
    error.value = 'Enter your email and password.'
    return
  }
  loading.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') && !route.query.next.startsWith('//') ? route.query.next : '/'
    router.replace(next)
  } catch (e) {
    error.value = e.response?.status === 429 ? 'Too many attempts. Please wait a minute and try again.' : parseError(e, 'Unable to sign in.').message
  } finally {
    loading.value = false
  }
}

const features = [
  { icon: QrCode, title: 'Scan & track', text: 'QR and barcode labels for every asset.' },
  { icon: Zap, title: 'Live updates', text: 'Real-time dashboard and alerts.' },
  { icon: ShieldCheck, title: 'Signed handovers', text: 'Digital sign-off with PDF receipts.' },
]
</script>

<template>
  <div class="grid min-h-dvh lg:grid-cols-2">
    <section class="relative hidden overflow-hidden p-12 lg:flex lg:flex-col lg:justify-between">
      <div class="flex items-center gap-3">
        <div class="grid h-10 w-10 place-items-center rounded-xl bg-gradient-accent shadow-[0_0_30px_-4px_var(--glow)]"><Boxes class="h-5 w-5 text-accent-ink" /></div>
        <BrandName class="text-xl" />
      </div>
      <div class="max-w-lg animate-fade-up">
        <h1 class="text-5xl leading-[1.05] font-semibold">Every asset.<br /><span class="text-gradient">Accounted for.</span></h1>
        <p class="mt-5 text-lg text-muted">Receive, issue, transfer and maintain your equipment, furniture and fleet — with a complete, signed audit trail.</p>
        <div class="mt-10 grid gap-3">
          <div v-for="(f, i) in features" :key="f.title" class="card flex animate-fade-up items-center gap-4 p-4" :style="{ animationDelay: `${150 + i * 90}ms` }">
            <div class="grid h-10 w-10 place-items-center rounded-xl bg-accent/10 text-accent"><component :is="f.icon" class="h-5 w-5" /></div>
            <div>
              <p class="font-medium">{{ f.title }}</p>
              <p class="text-sm text-muted">{{ f.text }}</p>
            </div>
          </div>
        </div>
      </div>
      <p class="text-xs text-muted">© {{ new Date().getFullYear() }} {{ APP_NAME }}</p>
    </section>

    <section class="flex items-center justify-center p-5 sm:p-10">
      <form class="card w-full max-w-md animate-fade-up p-6 sm:p-8" novalidate @submit.prevent="submit">
        <div class="mb-8 flex items-center gap-3 lg:hidden">
          <div class="grid h-10 w-10 place-items-center rounded-xl bg-gradient-accent"><Boxes class="h-5 w-5 text-accent-ink" /></div>
          <BrandName class="text-xl" />
        </div>
        <h2 class="text-2xl font-semibold">Welcome back</h2>
        <p class="mt-1 text-sm text-muted">Sign in to manage your organisation's assets.</p>

        <div class="mt-7 space-y-4">
          <AppInput v-model="email" label="Email" type="email" autocomplete="username" :icon="Mail" placeholder="you@company.com" required />
          <div class="relative">
            <AppInput v-model="password" label="Password" :type="show ? 'text' : 'password'" autocomplete="current-password" :icon="Lock" placeholder="••••••••" required />
            <button type="button" class="absolute right-3 bottom-2.5 text-muted hover:text-ink" :aria-label="show ? 'Hide password' : 'Show password'" @click="show = !show">
              <EyeOff v-if="show" class="h-4 w-4" />
              <Eye v-else class="h-4 w-4" />
            </button>
          </div>
        </div>

        <Transition name="fade">
          <p v-if="error" class="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
        </Transition>

        <AppButton type="submit" size="lg" block class="mt-6" :loading="loading">Sign in</AppButton>
      </form>
    </section>
  </div>
</template>
