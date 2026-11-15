<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import SignaturePadLib from 'signature_pad'
import { Eraser, Undo2 } from 'lucide-vue-next'

const model = defineModel({ type: String, default: '' })
defineProps({ label: { type: String, default: 'Signature' }, error: String })
const canvas = ref(null)
const wrapper = ref(null)
let pad = null
let observer = null

function resize() {
  if (!canvas.value || !wrapper.value) return
  const data = pad?.toData()
  const ratio = Math.max(window.devicePixelRatio || 1, 1)
  const { width } = wrapper.value.getBoundingClientRect()
  canvas.value.width = width * ratio
  canvas.value.height = 180 * ratio
  canvas.value.getContext('2d').scale(ratio, ratio)
  pad?.clear()
  if (data?.length) pad.fromData(data)
}

function emitValue() {
  model.value = pad && !pad.isEmpty() ? pad.toDataURL('image/png') : ''
}
function clear() {
  pad?.clear()
  emitValue()
}
function undo() {
  const data = pad?.toData()
  if (data?.length) {
    data.pop()
    pad.fromData(data)
    emitValue()
  }
}

onMounted(() => {
  // Ink is always dark on a paper-like surface so it prints correctly on receipts.
  pad = new SignaturePadLib(canvas.value, { penColor: '#0b1220', minWidth: 0.8, maxWidth: 2.6, throttle: 8 })
  pad.addEventListener('endStroke', emitValue)
  resize()
  observer = new ResizeObserver(() => resize())
  observer.observe(wrapper.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  pad?.off()
})
</script>

<template>
  <div class="min-w-0">
    <div class="mb-1.5 flex items-center justify-between">
      <span class="label mb-0">{{ label }}</span>
      <div class="flex gap-1">
        <button type="button" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted hover:bg-surface-hover hover:text-ink" @click="undo"><Undo2 class="h-3.5 w-3.5" /> Undo</button>
        <button type="button" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted hover:bg-surface-hover hover:text-ink" @click="clear"><Eraser class="h-3.5 w-3.5" /> Clear</button>
      </div>
    </div>
    <div ref="wrapper" class="relative overflow-hidden rounded-2xl border-2 border-dashed bg-white" :class="error ? 'border-danger' : 'border-line-strong'">
      <canvas ref="canvas" class="block h-[180px] w-full touch-none" aria-label="Signature area — draw with your finger, pen or mouse" />
      <div class="pointer-events-none absolute inset-x-6 bottom-8 border-b border-slate-300" />
      <span v-if="!model" class="pointer-events-none absolute inset-0 grid place-items-center text-sm text-slate-400">Sign here</span>
    </div>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ error }}</p>
  </div>
</template>
