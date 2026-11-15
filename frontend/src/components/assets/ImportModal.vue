<script setup>
import { ref, watch } from 'vue'
import { CheckCircle2, Download, FileSpreadsheet, TriangleAlert } from 'lucide-vue-next'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import FileDrop from '@/components/ui/FileDrop.vue'
import { assetsApi } from '@/api'
import { downloadFile, parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'

const open = defineModel('open', { type: Boolean })
const emit = defineEmits(['imported'])
const ui = useUiStore()
const file = ref(null)
const report = ref(null)
const busy = ref(false)

watch(open, (v) => {
  if (v) {
    file.value = null
    report.value = null
  }
})

async function run(dryRun) {
  if (!file.value) return
  busy.value = true
  try {
    report.value = await assetsApi.importFile(file.value, dryRun)
    if (!dryRun) {
      ui.success(`Imported: ${report.value.created} created, ${report.value.updated} updated`)
      emit('imported')
      open.value = false
    }
  } catch (e) {
    if (e.response?.status === 400 && e.response.data?.errors) report.value = e.response.data
    else ui.error(parseError(e).message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal v-model:open="open" title="Import assets" subtitle="CSV or Excel (.xlsx), up to 5 MB" size="lg">
    <div class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-line bg-surface-hover/40 px-4 py-3 text-sm">
        <span class="text-muted">Leave <code class="text-accent">asset_tag</code> blank to create; fill it to update. Custom fields use <code class="text-accent">cf:key</code> columns.</span>
        <AppButton size="sm" variant="subtle" :icon="Download" @click="downloadFile('/assets/import-template/')">Template</AppButton>
      </div>
      <FileDrop accept=".csv,.xlsx" hint="The whole file is validated — nothing is saved if any row fails." @files="(f) => { file = f[0]; report = null }" />
      <p v-if="file" class="flex items-center gap-2 text-sm"><FileSpreadsheet class="h-4 w-4 text-accent" /> {{ file.name }} <span class="text-muted">({{ (file.size / 1024).toFixed(1) }} KB)</span></p>

      <div v-if="report" class="rounded-2xl border p-4" :class="report.errors?.length ? 'border-danger/40 bg-danger/5' : 'border-success/40 bg-success/5'">
        <p class="flex items-center gap-2 font-medium">
          <TriangleAlert v-if="report.errors?.length" class="h-5 w-5 text-danger" />
          <CheckCircle2 v-else class="h-5 w-5 text-success" />
          <template v-if="report.errors?.length">{{ report.errors.length }} row(s) need fixing</template>
          <template v-else>Ready: {{ report.created }} to create, {{ report.updated }} to update ({{ report.total }} rows)</template>
        </p>
        <ul v-if="report.errors?.length" class="mt-3 max-h-56 space-y-1.5 overflow-y-auto text-sm">
          <li v-for="err in report.errors.slice(0, 100)" :key="err.row" class="rounded-lg bg-surface-strong/50 px-3 py-2">
            <span class="font-mono text-xs text-danger">Row {{ err.row }}</span>
            <span v-for="(msg, field) in err.errors" :key="field" class="ml-2 text-muted"><b class="text-ink">{{ field }}</b>: {{ msg }}</span>
          </li>
        </ul>
      </div>
    </div>
    <template #footer>
      <AppButton variant="secondary" @click="open = false">Close</AppButton>
      <AppButton variant="secondary" :disabled="!file" :loading="busy" @click="run(true)">Validate</AppButton>
      <AppButton :disabled="!file || (report && report.errors?.length > 0)" :loading="busy" @click="run(false)">Import</AppButton>
    </template>
  </AppModal>
</template>
