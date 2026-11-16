<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  CircleAlert,
  CircleCheck,
  Copy,
  DatabaseBackup,
  Download,
  HardDrive,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-vue-next";
import { backupsApi } from "@/api";
import { downloadFile, parseError } from "@/api/http";
import { useUiStore } from "@/stores/ui";
import PageHeader from "@/components/ui/PageHeader.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppBadge from "@/components/ui/AppBadge.vue";
import DataTable from "@/components/ui/DataTable.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import AppModal from "@/components/ui/AppModal.vue";
import AppInput from "@/components/ui/AppInput.vue";
import { formatDateTime } from "@/utils/format";

const ui = useUiStore();
const state = ref(null);
const loading = ref(true);
const requesting = ref(false);
let poll = null;

async function load() {
  try {
    const wasRestoring = restoring.value;
    state.value = await backupsApi.status();
    if (wasRestoring && !restoring.value) restoreFinished(restore.value);
  } catch (e) {
    ui.error(parseError(e).message);
  } finally {
    loading.value = false;
  }
  schedulePoll();
}

const restore = computed(() => state.value?.restore || null);
const restoring = computed(() =>
  ["queued", "running"].includes(restore.value?.state),
);

/** While a backup or restore is in progress, check every few seconds until it finishes. */
function schedulePoll() {
  clearTimeout(poll);
  if (state.value?.pending || restoring.value) poll = setTimeout(load, 3000);
}
onMounted(load);
onBeforeUnmount(() => clearTimeout(poll));

async function backupNow() {
  requesting.value = true;
  try {
    state.value = await backupsApi.create();
    ui.success(
      state.value.service_online
        ? "Backup started — it appears here in a few seconds."
        : "Backup queued — it runs when the backup service is back.",
    );
    schedulePoll();
  } catch (e) {
    ui.error(parseError(e).message);
  } finally {
    requesting.value = false;
  }
}

async function download(b) {
  try {
    await downloadFile(`/backups/${encodeURIComponent(b.name)}/`, {
      filename: b.name,
    });
  } catch (e) {
    ui.error(parseError(e).message);
  }
}

async function remove(b) {
  const ok = await ui.confirm({
    title: `Delete the backup from ${formatDateTime(b.created_at)}?`,
    message: `${b.name} (${size(b.size)}) is removed permanently. This cannot be undone.`,
    confirmText: "Delete backup",
    danger: true,
    action: () => backupsApi.remove(b.name),
  });
  if (ok) {
    ui.success("Backup deleted");
    load();
  }
}

// --- upload ---------------------------------------------------------------------
const fileInput = ref(null);
const uploading = ref(false);
const progress = ref(0);
async function onPick(e) {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".dump"))
    return ui.error(
      "Choose a .dump file made by Back up now or the daily backup.",
    );
  uploading.value = true;
  progress.value = 0;
  try {
    const saved = await backupsApi.upload(file, (p) => (progress.value = p));
    ui.success(`Uploaded as ${saved.name}`);
    load();
  } catch (err) {
    ui.error(parseError(err).message);
  } finally {
    uploading.value = false;
  }
}

// --- restore -------------------------------------------------------------------
const restoreOf = ref(null);
const confirmName = ref("");
const starting = ref(false);
const reloading = ref(false);
const serverCmd = computed(
  () => `docker compose run --rm backup restore ${restoreOf.value?.name || ""}`,
);

function openRestore(b) {
  restoreOf.value = b;
  confirmName.value = "";
}

async function startRestore() {
  starting.value = true;
  try {
    state.value = await backupsApi.restore(restoreOf.value.name);
    restoreOf.value = null;
    schedulePoll();
  } catch (e) {
    ui.error(parseError(e).message);
  } finally {
    starting.value = false;
  }
}

/** The data was replaced: reload so every screen (and the signed-in user) comes from the restored database. */
function restoreFinished(r) {
  if (r?.state === "done") {
    reloading.value = true;
    ui.success(`Restored ${r.name}. Reloading…`);
    setTimeout(() => window.location.reload(), 2500);
  } else if (r?.state === "failed") {
    ui.error(r.message || "Restore failed; your data was not changed.");
  }
}
const recentResult = computed(() => {
  const r = restore.value;
  return r && !restoring.value && r.at && Date.now() / 1000 - r.at < 86400
    ? r
    : null;
});
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    ui.success("Copied");
  } catch {
    ui.warning(text);
  }
}

const KIND = {
  manual: { label: "Manual", tone: "violet" },
  uploaded: { label: "Uploaded", tone: "amber" },
  safety: { label: "Before restore", tone: "lime" },
  auto: { label: "Daily", tone: "slate" },
};

function size(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let n = bytes / 1024;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) ((n /= 1024), i++);
  return `${n.toFixed(n < 10 ? 1 : 0)} ${units[i]}`;
}

const backups = computed(() => state.value?.backups || []);
const latest = computed(() => backups.value[0]);
const columns = [
  { key: "created_at", label: "Created" },
  { key: "kind", label: "Type" },
  { key: "size", label: "Size", align: "right" },
  { key: "actions", label: "", align: "right" },
];
</script>

<template>
  <div>
    <PageHeader
      title="Backups"
      subtitle="Database backups made automatically every day and whenever you need one."
    >
      <template #actions>
        <AppButton
          variant="secondary"
          :icon="RefreshCw"
          aria-label="Refresh"
          @click="load"
        />
        <AppButton
          variant="secondary"
          :icon="Upload"
          :loading="uploading"
          @click="fileInput.click()"
          >{{
            uploading ? `Uploading ${progress}%` : "Upload backup"
          }}</AppButton
        >
        <input
          ref="fileInput"
          type="file"
          accept=".dump"
          class="hidden"
          data-testid="backup-file"
          @change="onPick"
        />
        <AppButton
          :icon="DatabaseBackup"
          :loading="requesting || !!state?.pending"
          @click="backupNow"
          >{{ state?.pending ? "Backing up…" : "Back up now" }}</AppButton
        >
      </template>
    </PageHeader>

    <div
      v-if="restoring || reloading"
      class="card mb-4 flex items-start gap-3 border-primary/40 p-4"
      data-testid="restore-progress"
      role="status"
    >
      <LoaderCircle class="mt-0.5 h-5 w-5 shrink-0 animate-spin text-primary" />
      <div class="min-w-0">
        <p class="font-medium">
          {{
            reloading
              ? "Restore finished. Reloading the app…"
              : `Restoring ${restore.name}`
          }}
        </p>
        <p v-if="!reloading" class="mt-0.5 text-sm text-muted">
          {{ restore.message }}… The app keeps working until the restored data
          is switched in, which takes a moment. Don't change data meanwhile: it
          would be replaced.
        </p>
      </div>
    </div>
    <div
      v-else-if="recentResult"
      class="card mb-4 flex items-start gap-3 p-4"
      :class="
        recentResult.state === 'done'
          ? 'border-emerald-500/40'
          : 'border-rose-500/40'
      "
      data-testid="restore-result"
    >
      <component
        :is="recentResult.state === 'done' ? CircleCheck : CircleAlert"
        class="mt-0.5 h-5 w-5 shrink-0"
        :class="
          recentResult.state === 'done' ? 'text-emerald-500' : 'text-rose-500'
        "
      />
      <div class="min-w-0">
        <p class="font-medium">
          {{
            recentResult.state === "done"
              ? `Restored ${recentResult.name}`
              : `Restore of ${recentResult.name} failed`
          }}
        </p>
        <p class="mt-0.5 text-sm text-muted">
          {{
            recentResult.state === "done"
              ? "The data you had before is kept as a “Before restore” backup."
              : recentResult.message
          }}
          {{ formatDateTime(new Date(recentResult.at * 1000).toISOString()) }}
        </p>
      </div>
    </div>

    <div v-if="state" class="mb-4 grid gap-3 sm:grid-cols-3">
      <div class="card p-4">
        <p class="text-xs text-muted uppercase">Backup service</p>
        <p class="mt-1 flex items-center gap-2 font-medium">
          <AppBadge :tone="state.service_online ? 'emerald' : 'rose'" dot>{{
            state.service_online ? "Running" : "Not running"
          }}</AppBadge>
        </p>
        <p v-if="!state.service_online" class="mt-2 text-xs text-muted">
          Start it with <code>docker compose up -d backup</code>.
        </p>
      </div>
      <div class="card p-4">
        <p class="text-xs text-muted uppercase">Schedule</p>
        <p class="mt-1 font-medium">Daily at {{ state.schedule }}</p>
        <p class="mt-1 text-xs text-muted">
          Keeps the newest {{ state.keep }} daily backups; manual ones stay
          until deleted.
        </p>
      </div>
      <div class="card p-4">
        <p class="text-xs text-muted uppercase">Latest backup</p>
        <p class="mt-1 font-medium">
          {{ latest ? formatDateTime(latest.created_at) : "None yet" }}
        </p>
        <p class="mt-1 text-xs text-muted">{{ backups.length }} stored</p>
      </div>
    </div>

    <div class="card p-2 sm:p-3">
      <DataTable
        :columns="columns"
        :rows="backups"
        :loading="loading"
        row-key="name"
      >
        <template #cell-created_at="{ row }">
          <div class="min-w-0">
            <p class="font-medium">{{ formatDateTime(row.created_at) }}</p>
            <p class="truncate font-mono text-xs text-muted">{{ row.name }}</p>
          </div>
        </template>
        <template #cell-kind="{ row }"
          ><AppBadge :tone="(KIND[row.kind] || KIND.auto).tone">{{
            (KIND[row.kind] || KIND.auto).label
          }}</AppBadge></template
        >
        <template #cell-size="{ row }"
          ><span class="tabular-nums">{{ size(row.size) }}</span></template
        >
        <template #cell-actions="{ row }">
          <div class="flex justify-end gap-1">
            <AppButton
              size="sm"
              variant="ghost"
              :icon="RotateCcw"
              :aria-label="`Restore ${row.name}`"
              :disabled="restoring"
              @click.stop="openRestore(row)"
            />
            <AppButton
              size="sm"
              variant="ghost"
              :icon="Download"
              :aria-label="`Download ${row.name}`"
              @click.stop="download(row)"
            />
            <AppButton
              size="sm"
              variant="ghost"
              :icon="Trash2"
              :aria-label="`Delete ${row.name}`"
              @click.stop="remove(row)"
            />
          </div>
        </template>
        <template #empty
          ><EmptyState
            :icon="HardDrive"
            title="No backups yet"
            message="Click “Back up now”, or wait for the daily backup."
        /></template>
      </DataTable>
    </div>

    <p class="mt-4 text-xs text-muted">
      Upload a <code>.dump</code> file (from Download, or another installation)
      to keep it here or restore it. Restoring replaces all current data; the
      data you had is saved first as a “Before restore” backup, so a restore can
      be undone.
    </p>

    <AppModal
      :open="!!restoreOf"
      :title="`Restore ${restoreOf?.name || ''}`"
      subtitle="Replace all current data with this backup"
      size="lg"
      @update:open="(v) => !v && (restoreOf = null)"
    >
      <form
        id="restore-form"
        class="space-y-4"
        data-testid="restore-steps"
        @submit.prevent="confirmName === restoreOf?.name && startRestore()"
      >
        <div
          class="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm"
        >
          Everything added or changed after
          {{ restoreOf ? formatDateTime(restoreOf.created_at) : "" }} is
          replaced. The current data is saved first as a
          <b>Before restore</b> backup, so you can go back to it. Everyone is
          signed in again from the restored data when it finishes.
        </div>
        <AppInput
          v-model="confirmName"
          label="Type the backup's name to confirm"
          :placeholder="restoreOf?.name"
          autocomplete="off"
          spellcheck="false"
          data-testid="restore-confirm"
        />
        <details class="rounded-2xl border border-line p-3 text-sm">
          <summary class="cursor-pointer text-muted">
            Or restore from the server's terminal
          </summary>
          <p class="mt-2 mb-1.5 text-xs text-muted">
            Run in the app's folder (no safety backup is taken this way):
          </p>
          <div class="flex items-center gap-2">
            <code
              class="min-w-0 flex-1 overflow-x-auto rounded-lg bg-surface-hover px-3 py-2 font-mono text-xs whitespace-nowrap"
              >{{ serverCmd }}</code
            >
            <AppButton
              size="sm"
              variant="ghost"
              :icon="Copy"
              aria-label="Copy command"
              @click="copy(serverCmd)"
            />
          </div>
        </details>
      </form>
      <template #footer>
        <AppButton variant="secondary" @click="restoreOf = null"
          >Cancel</AppButton
        >
        <AppButton
          type="submit"
          form="restore-form"
          variant="danger"
          :icon="RotateCcw"
          :loading="starting"
          :disabled="confirmName !== restoreOf?.name"
          data-testid="restore-start"
        >
          Restore now
        </AppButton>
      </template>
    </AppModal>
  </div>
</template>
