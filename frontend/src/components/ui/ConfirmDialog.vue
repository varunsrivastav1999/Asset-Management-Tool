<script setup>
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { Loader2, TriangleAlert } from 'lucide-vue-next'
import { closeOverlay, openOverlay, isTop, trapFocus, Z_CONFIRM } from '@/composables/modalStack'

/**
 * Reusable confirmation card. Teleported to <body> above every other overlay so it can never be
 * hidden behind a modal, clipped by `overflow: hidden`, or trapped in a stacking context.
 */
const props = defineProps({
  open: Boolean,
  title: { type: String, default: 'Are you sure?' },
  message: String,
  confirmText: { type: String, default: 'Confirm' },
  cancelText: { type: String, default: 'Cancel' },
  danger: Boolean,
  loading: Boolean,
  error: String,
})
const emit = defineEmits(['confirm', 'cancel'])
const card = ref(null)
const cancelBtn = ref(null)
const titleId = useId()
let overlayId = null
let lastFocus = null

function cancel() {
  if (!props.loading) emit('cancel')
}
function onKey(e) {
  if (!overlayId || !isTop(overlayId)) return
  if (e.key === 'Escape') {
    e.stopPropagation()
    e.preventDefault()
    cancel()
  } else trapFocus(e, card.value)
}
watch(
  () => props.open,
  async (v) => {
    if (v && !overlayId) {
      lastFocus = document.activeElement
      overlayId = openOverlay()
      document.addEventListener('keydown', onKey, true)
      await nextTick()
      // Destructive actions default to the safe choice.
      ;(props.danger ? cancelBtn.value : card.value?.querySelector('[data-confirm]'))?.focus()
    } else if (!v && overlayId) {
      release()
    }
  },
  { immediate: true },
)
function release() {
  closeOverlay(overlayId)
  overlayId = null
  document.removeEventListener('keydown', onKey, true)
  lastFocus?.focus?.({ preventScroll: true })
}
onBeforeUnmount(() => overlayId && release())
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 flex items-center justify-center p-4" :style="{ zIndex: Z_CONFIRM }" data-testid="confirm-dialog">
        <div class="absolute inset-0 bg-black/55 backdrop-blur-sm" aria-hidden="true" @click="cancel" />
        <div
          ref="card"
          role="alertdialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="glass-strong relative w-full max-w-md animate-fade-up rounded-3xl p-6"
        >
          <div class="flex items-start gap-4">
            <span v-if="danger" class="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-danger/12 text-danger"><TriangleAlert class="h-5 w-5" /></span>
            <div class="min-w-0 flex-1">
              <h2 :id="titleId" class="text-lg font-semibold">{{ title }}</h2>
              <p v-if="message" class="mt-1.5 text-sm whitespace-pre-line text-muted">{{ message }}</p>
              <div v-if="$slots.default" class="mt-3"><slot /></div>
              <p v-if="error" class="mt-3 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
            </div>
          </div>
          <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button
              ref="cancelBtn"
              type="button"
              class="h-10 rounded-xl px-4 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-ink disabled:opacity-50"
              :disabled="loading"
              @click="cancel"
            >
              {{ cancelText }}
            </button>
            <button
              type="button"
              data-confirm
              class="inline-flex h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition disabled:opacity-60"
              :class="danger ? 'bg-danger text-white hover:brightness-110' : 'bg-primary text-primary-ink hover:bg-primary-hover'"
              :disabled="loading"
              :aria-busy="loading"
              @click="emit('confirm')"
            >
              <Loader2 v-if="loading" class="h-4 w-4 animate-spin" />
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
