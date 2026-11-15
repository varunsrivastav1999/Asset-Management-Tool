<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import { closeOverlay, depth, isTop, openOverlay, trapFocus, Z_BASE } from '@/composables/modalStack'

const open = defineModel('open', { type: Boolean, default: false })
const props = defineProps({
  title: String,
  subtitle: String,
  size: { type: String, default: 'md' }, // sm | md | lg | xl
  persistent: Boolean,
})
const emit = defineEmits(['close'])
const panel = ref(null)
const overlayId = ref(null)
let lastFocus = null

const zIndex = computed(() => (overlayId.value ? Z_BASE + depth(overlayId.value) * 10 : Z_BASE))

function close() {
  if (props.persistent) return
  open.value = false
  emit('close')
}
function onKey(e) {
  if (!overlayId.value || !isTop(overlayId.value)) return // only the top-most overlay reacts
  if (e.key === 'Escape') {
    e.stopPropagation()
    close()
  } else trapFocus(e, panel.value)
}

function activate() {
  lastFocus = document.activeElement
  overlayId.value = openOverlay()
  document.addEventListener('keydown', onKey)
}
function deactivate() {
  if (!overlayId.value) return
  closeOverlay(overlayId.value)
  overlayId.value = null
  document.removeEventListener('keydown', onKey)
  lastFocus?.focus?.({ preventScroll: true })
}

watch(
  open,
  async (v) => {
    if (v) {
      activate()
      await nextTick()
      panel.value?.querySelector('input, select, textarea, button:not([data-close])')?.focus({ preventScroll: true })
    } else deactivate()
  },
  { immediate: true },
)
onBeforeUnmount(deactivate)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 flex items-end justify-center sm:items-center sm:p-6" :style="{ zIndex }">
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="close" />
        <Transition appear enter-active-class="transition duration-300 ease-out" enter-from-class="translate-y-8 opacity-0 sm:translate-y-2 sm:scale-95">
          <div
            ref="panel"
            role="dialog"
            aria-modal="true"
            :aria-label="title"
            class="glass-strong relative flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-3xl sm:rounded-3xl"
            :class="{ sm: 'sm:max-w-md', md: 'sm:max-w-xl', lg: 'sm:max-w-3xl', xl: 'sm:max-w-5xl' }[size]"
          >
            <div class="mx-auto mt-2 h-1.5 w-10 rounded-full bg-line-strong sm:hidden" />
            <header v-if="title" class="flex items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
              <div class="min-w-0">
                <h2 class="truncate text-lg font-semibold">{{ title }}</h2>
                <p v-if="subtitle" class="mt-0.5 text-sm text-muted">{{ subtitle }}</p>
              </div>
              <button data-close class="-mr-2 grid h-9 w-9 shrink-0 place-items-center rounded-xl text-muted hover:bg-surface-hover hover:text-ink" aria-label="Close" @click="close">
                <X class="h-5 w-5" />
              </button>
            </header>
            <div class="flex-1 overflow-y-auto px-5 py-5 sm:px-6"><slot /></div>
            <footer v-if="$slots.footer" class="safe-bottom flex flex-col-reverse gap-2 border-t border-line px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
              <slot name="footer" />
            </footer>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
