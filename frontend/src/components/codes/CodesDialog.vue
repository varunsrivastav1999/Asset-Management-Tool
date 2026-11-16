<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { Barcode, Copy, Printer, QrCode } from 'lucide-vue-next'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import { blobUrl, downloadFile, parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'

/**
 * QR code + barcode for one entry (any table): preview, download, copy the code, print a label.
 * Images come from authenticated endpoints, so they're loaded as blobs.
 */
const props = defineProps({
  code: { type: String, default: '' },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  qrPath: { type: String, default: '' },
  barcodePath: { type: String, default: '' },
  params: { type: Object, default: () => ({}) },
  /** () => Promise; prints a label sheet (omit to hide the button). */
  printLabel: { type: Function, default: null },
})
const open = defineModel('open', { type: Boolean })
const ui = useUiStore()
const qr = ref('')
const bar = ref('')

function release() {
  ;[qr.value, bar.value].forEach((u) => u && URL.revokeObjectURL(u))
  qr.value = bar.value = ''
}
watch(
  () => [open.value, props.qrPath],
  async ([isOpen]) => {
    release()
    if (!isOpen || !props.qrPath) return
    try {
      ;[qr.value, bar.value] = await Promise.all([blobUrl(props.qrPath, props.params), blobUrl(props.barcodePath, props.params)])
    } catch (e) {
      ui.error(parseError(e).message)
    }
  },
  { immediate: true },
)
onBeforeUnmount(release)

const save = (path, fmt, ext) =>
  downloadFile(path, { params: { ...props.params, fmt }, filename: `${props.code}-${ext}` }).catch((e) => ui.error(parseError(e).message))

async function copy() {
  try {
    await navigator.clipboard.writeText(props.code)
    ui.success(`Copied ${props.code}`)
  } catch {
    ui.warning(props.code)
  }
}

const printing = ref(false)
async function print() {
  printing.value = true
  try {
    await props.printLabel()
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    printing.value = false
  }
}
</script>

<template>
  <AppModal v-model:open="open" :title="title || code" :subtitle="subtitle" size="md">
    <div class="flex flex-col items-center gap-4" data-testid="codes-dialog">
      <button type="button" class="font-mono text-lg font-semibold tracking-wider text-accent" :aria-label="`Copy ${code}`" @click="copy">
        {{ code }} <Copy class="ml-1 inline h-4 w-4 align-[-2px] text-muted" />
      </button>
      <div class="grid w-full gap-4 sm:grid-cols-2">
        <figure class="flex flex-col items-center gap-2 rounded-2xl border border-line p-3">
          <div class="rounded-xl bg-white p-2"><img v-if="qr" :src="qr" alt="QR code" class="h-40 w-40" /><div v-else class="skeleton h-40 w-40" /></div>
          <figcaption class="text-xs text-muted">Scan with a phone camera or the in-app scanner</figcaption>
          <AppButton size="sm" variant="secondary" :icon="QrCode" @click="save(qrPath, 'png', 'qr.png')">Download QR</AppButton>
        </figure>
        <figure class="flex flex-col items-center justify-between gap-2 rounded-2xl border border-line p-3">
          <div class="flex min-h-40 w-full items-center rounded-xl bg-white p-2"><img v-if="bar" :src="bar" alt="Barcode" class="mx-auto max-h-24 w-full object-contain" /><div v-else class="skeleton h-20 w-full" /></div>
          <figcaption class="text-xs text-muted">Code128 for handheld barcode scanners</figcaption>
          <AppButton size="sm" variant="secondary" :icon="Barcode" @click="save(barcodePath, 'svg', 'barcode.svg')">Download barcode</AppButton>
        </figure>
      </div>
    </div>
    <template #footer>
      <AppButton variant="secondary" @click="open = false">Close</AppButton>
      <AppButton v-if="printLabel" :icon="Printer" :loading="printing" @click="print">Print label</AppButton>
    </template>
  </AppModal>
</template>
