<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Copy, DatabaseBackup, Download, HardDrive, RefreshCw, RotateCcw, Trash2, Upload } from 'lucide-vue-next'
import { backupsApi } from '@/api'
import { downloadFile, parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import DataTable from '@/components/ui/DataTable.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import AppModal from '@/components/ui/AppModal.vue'
import { formatDateTime } from '@/utils/format'

const ui = useUiStore()
const state = ref(null)
const loading = ref(true)
const requesting = ref(false)
let poll = null

async function load() {
  try {
    state.value = await backupsApi.status()
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    loading.value = false
  }
  schedulePoll()
}

/** While a backup is queued, check every few seconds until it appears. */
function schedulePoll() {
  clearTimeout(poll)
  if (state.value?.pending) poll = setTimeout(load, 3000)
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(poll))

async function backupNow() {
  requesting.value = true
  try {
    state.value = await backupsApi.create()
    ui.success(state.value.service_online ? 'Backup started — it appears here in a few seconds.' : 'Backup queued — it runs when the backup service is back.')
    schedulePoll()
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    requesting.value = false
  }
}

async function download(b) {
  try {
    await downloadFile(`/backups/${encodeURIComponent(b.name)}/`, { filename: b.name })
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

async function remove(b) {
  const ok = await ui.confirm({
    title: `Delete the backup from ${formatDateTime(b.created_at)}?`,
    message: `${b.name} (${size(b.size)}) is removed permanently. This cannot be undone.`,
    confirmText: 'Delete backup',
    danger: true,
    action: () => backupsApi.remove(b.name),
  })
  if (ok) {
    ui.success('Backup deleted')
    load()
  }
}

// --- upload ---------------------------------------------------------------------
const fileInput = ref(null)
const uploading = ref(false)
const progress = ref(0)
async function onPick(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.dump')) return ui.error('Choose a .dump file made by Back up now or the daily backup.')
  uploading.value = true
  progress.value = 0
  try {
    const saved = await backupsApi.upload(file, (p) => (progress.value = p))
    ui.success(`Uploaded as ${saved.name}`)
    load()
  } catch (err) {
    ui.error(parseError(err).message)
  } finally {
    uploading.value = false
  }
}

// --- restore instructions -------------------------------------------------------
const restoreOf = ref(null)
const restoreSteps = computed(() => {
  const name = restoreOf.value?.name || ''
  return [
    { label: 'Stop the app (the database must not be in use)', cmd: 'docker compose stop api worker beat' },
    { label: 'Restore this backup (replaces all current data)', cmd: `docker compose run --rm backup restore ${name}` },
    { label: 'Start the app again', cmd: 'docker compose start api worker beat' },
  ]
})
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ui.success('Copied')
  } catch {
    ui.warning(text)
  }
}

const KIND = { manual: { label: 'Manual', tone: 'violet' }, uploaded: { label: 'Uploaded', tone: 'amber' }, auto: { label: 'Daily', tone: 'slate' } }

function size(bytes) {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let n = bytes / 1024
  let i = 0
  while (n >= 1024 && i < units.length - 1) (n /= 1024), i++
  return `${n.toFixed(n < 10 ? 1 : 0)} ${units[i]}`
}

const backups = computed(() => state.value?.backups || [])
const latest = computed(() => backups.value[0])
const columns = [
  { key: 'created_at', label: 'Created' },
  { key: 'kind', label: 'Type' },
  { key: 'size', label: 'Size', align: 'right' },
  { key: 'actions', label: '', align: 'right' },
]
</script>

<template>
  <div>
    <PageHeader title="Backups" subtitle="Database backups made automatically every day and whenever you need one.">
      <template #actions>
        <AppButton variant="secondary" :icon="RefreshCw" aria-label="Refresh" @click="load" />
        <AppButton variant="secondary" :icon="Upload" :loading="uploading" @click="fileInput.click()">{{ uploading ? `Uploading ${progress}%` : 'Upload backup' }}</AppButton>
        <input ref="fileInput" type="file" accept=".dump" class="hidden" data-testid="backup-file" @change="onPick" />
        <AppButton :icon="DatabaseBackup" :loading="requesting || !!state?.pending" @click="backupNow">{{ state?.pending ? 'Backing up…' : 'Back up now' }}</AppButton>
      </template>
    </PageHeader>

    <div v-if="state" class="mb-4 grid gap-3 sm:grid-cols-3">
      <div class="card p-4">
        <p class="text-xs text-muted uppercase">Backup service</p>
        <p class="mt-1 flex items-center gap-2 font-medium">
          <AppBadge :tone="state.service_online ? 'emerald' : 'rose'" dot>{{ state.service_online ? 'Running' : 'Not running' }}</AppBadge>
        </p>
        <p v-if="!state.service_online" class="mt-2 text-xs text-muted">Start it with <code>docker compose up -d backup</code>.</p>
      </div>
      <div class="card p-4">
        <p class="text-xs text-muted uppercase">Schedule</p>
        <p class="mt-1 font-medium">Daily at {{ state.schedule }}</p>
        <p class="mt-1 text-xs text-muted">Keeps the newest {{ state.keep }} daily backups; manual ones stay until deleted.</p>
      </div>
      <div class="card p-4">
        <p class="text-xs text-muted uppercase">Latest backup</p>
        <p class="mt-1 font-medium">{{ latest ? formatDateTime(latest.created_at) : 'None yet' }}</p>
        <p class="mt-1 text-xs text-muted">{{ backups.length }} stored</p>
      </div>
    </div>

    <div class="card p-2 sm:p-3">
      <DataTable :columns="columns" :rows="backups" :loading="loading" row-key="name">
        <template #cell-created_at="{ row }">
          <div class="min-w-0">
            <p class="font-medium">{{ formatDateTime(row.created_at) }}</p>
            <p class="truncate font-mono text-xs text-muted">{{ row.name }}</p>
          </div>
        </template>
        <template #cell-kind="{ row }"><AppBadge :tone="(KIND[row.kind] || KIND.auto).tone">{{ (KIND[row.kind] || KIND.auto).label }}</AppBadge></template>
        <template #cell-size="{ row }"><span class="tabular-nums">{{ size(row.size) }}</span></template>
        <template #cell-actions="{ row }">
          <div class="flex justify-end gap-1">
            <AppButton size="sm" variant="ghost" :icon="RotateCcw" :aria-label="`Restore ${row.name}`" @click.stop="restoreOf = row" />
            <AppButton size="sm" variant="ghost" :icon="Download" :aria-label="`Download ${row.name}`" @click.stop="download(row)" />
            <AppButton size="sm" variant="ghost" :icon="Trash2" :aria-label="`Delete ${row.name}`" @click.stop="remove(row)" />
          </div>
        </template>
        <template #empty><EmptyState :icon="HardDrive" title="No backups yet" message="Click “Back up now”, or wait for the daily backup." /></template>
      </DataTable>
    </div>

    <p class="mt-4 text-xs text-muted">
      Upload a <code>.dump</code> file (from Download, or another installation) to keep it here or restore it. Restoring replaces all current data: use
      <b>Restore…</b> on a backup for the exact steps.
    </p>

    <AppModal :open="!!restoreOf" :title="`Restore ${restoreOf?.name || ''}`" subtitle="Run these on the server, in the app's folder" size="lg" @update:open="(v) => !v && (restoreOf = null)">
      <div class="space-y-3" data-testid="restore-steps">
        <p class="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
          Everything added or changed after {{ restoreOf ? formatDateTime(restoreOf.created_at) : '' }} is lost. Take a <b>Back up now</b> first if you might need today's data.
        </p>
        <ol class="space-y-2">
          <li v-for="(s, i) in restoreSteps" :key="i" class="rounded-2xl border border-line p-3">
            <p class="mb-1.5 text-xs text-muted">{{ i + 1 }}. {{ s.label }}</p>
            <div class="flex items-center gap-2">
              <code class="min-w-0 flex-1 overflow-x-auto rounded-lg bg-surface-hover px-3 py-2 font-mono text-xs whitespace-nowrap">{{ s.cmd }}</code>
              <AppButton size="sm" variant="ghost" :icon="Copy" :aria-label="`Copy step ${i + 1}`" @click="copy(s.cmd)" />
            </div>
          </li>
        </ol>
      </div>
      <template #footer><AppButton variant="secondary" @click="restoreOf = null">Close</AppButton></template>
    </AppModal>
  </div>
</template>
