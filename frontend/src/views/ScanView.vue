<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Camera, CameraOff, Flashlight, Keyboard, ScanLine } from 'lucide-vue-next'
import { assetsApi } from '@/api'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'

const router = useRouter()
const ui = useUiStore()
const video = ref(null)
const state = ref('idle') // idle | starting | scanning | denied | unsupported | resolving
const manual = ref('')
const torchOn = ref(false)
const torchSupported = ref(false)
const secure = typeof window !== 'undefined' && window.isSecureContext
let controls = null
let lastCode = ''

async function resolve(code) {
  const value = String(code || '').trim()
  if (!value || state.value === 'resolving') return
  state.value = 'resolving'
  try {
    const asset = await assetsApi.lookup(value)
    navigator.vibrate?.(40)
    stop()
    router.push(`/assets/${asset.id}`)
  } catch (e) {
    ui.warning(e.response?.status === 404 ? `No asset found for “${value}”` : 'Lookup failed, try again.')
    state.value = controls ? 'scanning' : 'idle'
    setTimeout(() => (lastCode = ''), 2500)
  }
}

async function start() {
  if (!navigator.mediaDevices?.getUserMedia) {
    state.value = 'unsupported'
    return
  }
  state.value = 'starting'
  try {
    const { BrowserMultiFormatReader } = await import('@zxing/browser')
    const reader = new BrowserMultiFormatReader(undefined, { delayBetweenScanAttempts: 150 })
    controls = await reader.decodeFromConstraints({ video: { facingMode: { ideal: 'environment' } } }, video.value, (result) => {
      if (!result) return
      const text = result.getText()
      if (text && text !== lastCode) {
        lastCode = text
        resolve(text)
      }
    })
    torchSupported.value = !!controls.switchTorch
    state.value = 'scanning'
  } catch (e) {
    state.value = e?.name === 'NotAllowedError' ? 'denied' : 'unsupported'
  }
}
function stop() {
  controls?.stop()
  controls = null
  if (state.value !== 'resolving') state.value = 'idle'
}
async function toggleTorch() {
  torchOn.value = !torchOn.value
  await controls?.switchTorch?.(torchOn.value).catch(() => (torchOn.value = false))
}

onMounted(() => (secure ? start() : (state.value = 'unsupported')))
onBeforeUnmount(stop)
</script>

<template>
  <div class="mx-auto max-w-xl">
    <PageHeader title="Scan asset" subtitle="Point the camera at a QR code or barcode label." />

    <div class="card relative overflow-hidden p-2">
      <div class="relative aspect-[3/4] overflow-hidden rounded-2xl bg-black sm:aspect-video">
        <video ref="video" class="h-full w-full object-cover" muted playsinline />
        <div v-if="state === 'scanning' || state === 'resolving'" class="pointer-events-none absolute inset-0 grid place-items-center">
          <div class="relative h-56 w-56 rounded-3xl border-2 border-white/30 shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]">
            <span class="absolute inset-x-4 h-0.5 animate-[scan_2.2s_ease-in-out_infinite] bg-gradient-accent shadow-[0_0_20px_var(--accent)]" />
            <span v-for="c in ['top-0 left-0 border-t-4 border-l-4 rounded-tl-3xl', 'top-0 right-0 border-t-4 border-r-4 rounded-tr-3xl', 'bottom-0 left-0 border-b-4 border-l-4 rounded-bl-3xl', 'bottom-0 right-0 border-b-4 border-r-4 rounded-br-3xl']" :key="c" class="absolute h-8 w-8 border-accent" :class="c" />
          </div>
        </div>
        <div v-if="!['scanning', 'resolving'].includes(state)" class="absolute inset-0 grid place-items-center p-6 text-center text-white/80">
          <div>
            <CameraOff v-if="state === 'denied' || state === 'unsupported'" class="mx-auto mb-3 h-10 w-10 text-white/50" />
            <ScanLine v-else class="mx-auto mb-3 h-10 w-10 animate-pulse text-white/60" />
            <p v-if="state === 'denied'" class="text-sm">Camera permission was denied. Enable it in your browser settings, or type the code below.</p>
            <p v-else-if="state === 'unsupported'" class="text-sm">Camera scanning isn't available here{{ !secure ? ' (requires HTTPS)' : '' }}. Type the code below.</p>
            <p v-else-if="state === 'starting'" class="text-sm">Starting camera…</p>
            <AppButton v-else :icon="Camera" @click="start">Start camera</AppButton>
          </div>
        </div>
        <div v-if="state === 'resolving'" class="absolute inset-x-0 bottom-4 text-center text-sm text-white">Looking up…</div>
      </div>
      <div v-if="state === 'scanning'" class="flex justify-center gap-2 p-3">
        <AppButton v-if="torchSupported" variant="secondary" size="sm" :icon="Flashlight" @click="toggleTorch">{{ torchOn ? 'Torch off' : 'Torch' }}</AppButton>
        <AppButton variant="ghost" size="sm" :icon="CameraOff" @click="stop">Stop</AppButton>
      </div>
    </div>

    <form class="card mt-4 flex items-end gap-2 p-4" @submit.prevent="resolve(manual)">
      <AppInput v-model="manual" class="flex-1" label="Enter code manually" :icon="Keyboard" placeholder="AST-000123 or serial number" autocapitalize="characters" />
      <AppButton type="submit" :loading="state === 'resolving'">Find</AppButton>
    </form>
  </div>
</template>

<style scoped>
@keyframes scan {
  0%, 100% { top: 12%; }
  50% { top: 86%; }
}
</style>
