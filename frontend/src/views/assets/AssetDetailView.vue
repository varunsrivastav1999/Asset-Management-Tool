<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  Barcode,
  Download,
  ImagePlus,
  Pencil,
  Printer,
  QrCode,
  RefreshCcw,
  Star,
  Trash2,
  Wrench,
} from 'lucide-vue-next'
import { assetsApi, maintenanceApi } from '@/api'
import { blobUrl, downloadFile, parseError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useTableNames } from '@/composables/useTableNames'
import AppButton from '@/components/ui/AppButton.vue'
import AppTabs from '@/components/ui/AppTabs.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import CategoryIcon from '@/components/ui/CategoryIcon.vue'
import UserAvatar from '@/components/ui/UserAvatar.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import FileDrop from '@/components/ui/FileDrop.vue'
import AppModal from '@/components/ui/AppModal.vue'
import ChangeStatusModal from '@/components/assets/ChangeStatusModal.vue'
import AssetTimeline from '@/components/assets/AssetTimeline.vue'
import MaintenanceFormModal from '@/components/workflows/MaintenanceFormModal.vue'
import { daysUntil, formatDate, formatDateTime, formatMoney } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const notes = useNotificationsStore()

const asset = ref(null)
const loading = ref(true)
const error = ref('')
const tab = ref('overview')
const statusOpen = ref(false)
const maintOpen = ref(false)
const photoOpen = ref(null)
const uploading = ref(false)
const qrUrl = ref('')
const barcodeUrl = ref('')
const maintenance = ref([])
const timeline = ref(null)

async function load() {
  error.value = ''
  try {
    asset.value = await assetsApi.get(route.params.id)
    if (auth.isManager) {
      maintenance.value = (await maintenanceApi.list({ asset: route.params.id, page_size: 50 })).results
    }
    loadCodes()
  } catch (e) {
    error.value = e.response?.status === 404 ? 'not-found' : parseError(e).message
  } finally {
    loading.value = false
  }
}
async function loadCodes() {
  revokeCodes()
  try {
    ;[qrUrl.value, barcodeUrl.value] = await Promise.all([blobUrl(`/assets/${asset.value.id}/qr/`), blobUrl(`/assets/${asset.value.id}/barcode/`)])
  } catch {
    /* codes are non-critical */
  }
}
function revokeCodes() {
  ;[qrUrl.value, barcodeUrl.value].forEach((u) => u && URL.revokeObjectURL(u))
}
onMounted(load)
onBeforeUnmount(revokeCodes)
watch(() => route.params.id, (v, old) => v && v !== old && load())
watch(() => notes.dashboardTick, async () => {
  if (!asset.value) return
  asset.value = await assetsApi.get(route.params.id).catch(() => asset.value)
  timeline.value?.reload()
})

const tabs = computed(() => [
  { value: 'overview', label: 'Overview' },
  { value: 'photos', label: 'Photos', count: asset.value?.photos?.length || 0 },
  { value: 'history', label: 'History' },
  ...(auth.isManager ? [{ value: 'maintenance', label: 'Maintenance', count: maintenance.value.length }] : []),
])

const holderName = computed(() => asset.value?.assigned_to?.full_name || asset.value?.department_name)
const warrantyDays = computed(() => daysUntil(asset.value?.warranty_expiry))

const details = computed(() => {
  const a = asset.value
  if (!a) return []
  return [
    ['Category', a.category?.name],
    ['Serial number', a.serial_number],
    ['Manufacturer', a.manufacturer],
    ['Model', a.model],
    ['Condition', a.condition_display],
    ['Location', a.location_name],
    ['Vendor', a.vendor_name],
    ['Purchase date', formatDate(a.purchase_date)],
    ['Cost', a.purchase_cost ? formatMoney(a.purchase_cost, a.currency) : null],
    ['Invoice #', a.invoice_number],
    ['PO #', a.po_number],
    ['Receipt', a.receipt_reference],
    ['Service interval', a.maintenance_interval_days ? `${a.maintenance_interval_days} days` : null],
    ['Next service', formatDate(a.next_maintenance_date, null)],
    ['Created', `${formatDateTime(a.created_at)}${a.created_by_name ? ` by ${a.created_by_name}` : ''}`],
  ]
})
const customValues = computed(() =>
  (asset.value?.custom_fields || []).map((f) => {
    const v = asset.value.custom_data?.[f.key]
    return [f.label, v === true ? 'Yes' : v === false ? 'No' : f.field_type === 'date' ? formatDate(v, null) : v]
  }),
)

function startHandover(type) {
  router.push({ name: 'handover-new', query: { type, assets: String(asset.value.id) } })
}

async function uploadPhotos(files) {
  uploading.value = true
  try {
    for (const f of files) await assetsApi.uploadPhoto(asset.value.id, f)
    ui.success(files.length > 1 ? `${files.length} photos uploaded` : 'Photo uploaded')
    asset.value = await assetsApi.get(asset.value.id)
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    uploading.value = false
  }
}
async function makePrimary(p) {
  await assetsApi.updatePhoto(asset.value.id, p.id, { is_primary: true })
  asset.value = await assetsApi.get(asset.value.id)
}
async function deletePhoto(p) {
  if (!(await ui.confirm({ title: 'Delete photo?', confirmText: 'Delete', danger: true }))) return
  try {
    await assetsApi.deletePhoto(asset.value.id, p.id)
    ui.success('Photo deleted')
    photoOpen.value = null
    asset.value = await assetsApi.get(asset.value.id)
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

async function remove() {
  const ok = await ui.confirm({
    title: `Delete ${asset.value.asset_tag}?`,
    message: 'This permanently removes the asset and its history. Assets that were part of a handover cannot be deleted — retire them instead.',
    confirmText: 'Delete asset',
    danger: true,
  })
  if (!ok) return
  try {
    await assetsApi.remove(asset.value.id)
    ui.success('Asset deleted')
    router.replace('/assets')
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

async function maintenanceAction(rec, action) {
  try {
    if (action === 'complete') {
      const res = await ui.confirm({ title: 'Complete maintenance', confirmText: 'Mark complete', input: { label: 'Cost (optional)', placeholder: 'e.g. 120.00' } })
      if (!res) return
      const cost = res.value?.trim()
      await maintenanceApi.action(rec.id, 'complete', cost ? { cost } : {})
    } else {
      await maintenanceApi.action(rec.id, action)
    }
    ui.success('Maintenance updated')
    load()
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

const printLabel = () => downloadFile('/assets/labels/', { method: 'post', data: { ids: [asset.value.id] }, open: true }).catch((e) => ui.error(parseError(e).message))
const assetNames = useTableNames('assets', { plural: 'Assets', singular: 'Asset', route: '/assets' })
</script>

<template>
  <div>
    <div v-if="loading" class="space-y-4">
      <div class="skeleton h-10 w-72" />
      <div class="grid gap-4 lg:grid-cols-3"><div class="skeleton h-80 lg:col-span-2" /><div class="skeleton h-80" /></div>
    </div>

    <div v-else-if="error" class="card mx-auto max-w-md">
      <EmptyState :title="error === 'not-found' ? `${assetNames.singular} not found` : `Could not load ${assetNames.singular.toLowerCase()}`" :message="error === 'not-found' ? 'It may have been deleted, or you do not have access.' : error">
        <AppButton :to="assetNames.route">Back to {{ assetNames.plural.toLowerCase() }}</AppButton>
      </EmptyState>
    </div>

    <template v-else-if="asset">
      <PageHeader :crumbs="[{ label: assetNames.plural, to: assetNames.route }, { label: asset.asset_tag }]">
        <template #title>
          <span class="flex min-w-0 items-center gap-3">
            <CategoryIcon :name="asset.category?.icon" :color="asset.category?.color" />
            <span class="truncate">{{ asset.name }}</span>
          </span>
        </template>
        <template #subtitle>
          <span class="flex flex-wrap items-center gap-2"><span class="font-mono">{{ asset.asset_tag }}</span><StatusBadge :status="asset.status" /></span>
        </template>
        <template v-if="auth.isManager" #actions>
          <AppButton v-if="asset.status === 'in_stock'" :icon="ArrowUpRight" @click="startHandover('issue')">Issue</AppButton>
          <template v-if="asset.status === 'assigned'">
            <AppButton :icon="ArrowDownLeft" @click="startHandover('return')">Return</AppButton>
            <AppButton variant="secondary" :icon="ArrowLeftRight" @click="startHandover('transfer')">Transfer</AppButton>
          </template>
          <AppButton v-if="asset.status === 'in_repair' && (asset.assigned_to || asset.department)" variant="secondary" :icon="ArrowDownLeft" @click="startHandover('return')">Return</AppButton>
          <AppButton variant="secondary" :icon="RefreshCcw" @click="statusOpen = true">Status</AppButton>
          <AppButton variant="secondary" :icon="Wrench" @click="maintOpen = true">Service</AppButton>
          <AppButton variant="secondary" size="icon" :icon="Pencil" :to="`/assets/${asset.id}/edit`" aria-label="Edit" />
          <AppButton variant="ghost" size="icon" :icon="Trash2" aria-label="Delete" @click="remove" />
        </template>
      </PageHeader>

      <div class="grid gap-4 lg:grid-cols-3">
        <div class="min-w-0 space-y-4 lg:col-span-2">
          <AppTabs v-model="tab" :tabs="tabs" />

          <Transition name="fade" mode="out-in">
            <section v-if="tab === 'overview'" key="o" class="space-y-4">
              <div v-if="asset.photos?.length" class="card overflow-hidden">
                <img :src="asset.photos[0].image" :alt="asset.name" class="h-56 w-full object-cover sm:h-72" />
              </div>
              <div class="card p-5">
                <h2 class="mb-4 font-semibold">Details</h2>
                <dl class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                  <div v-for="[k, v] in details.filter(([, v]) => v)" :key="k" class="flex justify-between gap-4 border-b border-line/60 pb-2 text-sm sm:block sm:border-0 sm:pb-0">
                    <dt class="text-xs text-muted">{{ k }}</dt>
                    <dd class="truncate text-right sm:mt-0.5 sm:text-left">{{ v }}</dd>
                  </div>
                </dl>
                <p v-if="asset.description" class="mt-5 border-t border-line pt-4 text-sm text-muted">{{ asset.description }}</p>
              </div>
              <div v-if="customValues.length" class="card p-5">
                <h2 class="mb-4 font-semibold">{{ asset.category?.name }} specifics</h2>
                <dl class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                  <div v-for="[k, v] in customValues" :key="k" class="flex justify-between gap-4 text-sm sm:block">
                    <dt class="text-xs text-muted">{{ k }}</dt>
                    <dd class="sm:mt-0.5">{{ v ?? '—' }}</dd>
                  </div>
                </dl>
              </div>
              <div v-if="asset.notes" class="card p-5 text-sm"><h2 class="mb-2 font-semibold">Notes</h2><p class="whitespace-pre-line text-muted">{{ asset.notes }}</p></div>
            </section>

            <section v-else-if="tab === 'photos'" key="p" class="card space-y-4 p-5">
              <FileDrop v-if="auth.isManager" accept="image/jpeg,image/png,image/webp" multiple hint="JPEG, PNG or WEBP up to 10 MB · max 12 photos" :disabled="uploading" @files="uploadPhotos" />
              <div v-if="asset.photos?.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <button v-for="p in asset.photos" :key="p.id" class="group relative aspect-square overflow-hidden rounded-2xl ring-1 ring-line" @click="photoOpen = p">
                  <img :src="p.image" :alt="p.caption || asset.name" class="h-full w-full object-cover transition duration-500 group-hover:scale-105" loading="lazy" />
                  <AppBadge v-if="p.is_primary" tone="primary" class="absolute top-2 left-2">Cover</AppBadge>
                </button>
              </div>
              <EmptyState v-else-if="!auth.isManager" :icon="ImagePlus" title="No photos" />
            </section>

            <section v-else-if="tab === 'history'" key="h" class="card p-5">
              <AssetTimeline ref="timeline" :asset-id="asset.id" />
            </section>

            <section v-else-if="tab === 'maintenance'" key="m" class="card p-5">
              <div class="mb-4 flex items-center justify-between">
                <h2 class="font-semibold">Service records</h2>
                <AppButton size="sm" variant="subtle" :icon="Wrench" @click="maintOpen = true">Schedule</AppButton>
              </div>
              <EmptyState v-if="!maintenance.length" :icon="Wrench" title="No maintenance yet" />
              <ul v-else class="divide-y divide-line">
                <li v-for="m in maintenance" :key="m.id" class="flex flex-wrap items-center gap-3 py-3">
                  <div class="min-w-0 flex-1">
                    <p class="truncate text-sm font-medium">{{ m.title }} <span class="text-xs text-muted">· {{ m.kind_display }}</span></p>
                    <p class="text-xs text-muted">{{ formatDate(m.scheduled_date) }}<template v-if="m.cost"> · {{ formatMoney(m.cost, asset.currency) }}</template><template v-if="m.technician"> · {{ m.technician }}</template></p>
                  </div>
                  <StatusBadge kind="maintenance" :status="m.status" />
                  <div class="flex gap-1">
                    <AppButton v-if="m.status === 'scheduled'" size="sm" variant="subtle" @click="maintenanceAction(m, 'start')">Start</AppButton>
                    <AppButton v-if="['scheduled', 'in_progress'].includes(m.status)" size="sm" variant="secondary" @click="maintenanceAction(m, 'complete')">Complete</AppButton>
                    <AppButton v-if="['scheduled', 'in_progress'].includes(m.status)" size="sm" variant="ghost" @click="maintenanceAction(m, 'cancel')">Cancel</AppButton>
                  </div>
                </li>
              </ul>
            </section>
          </Transition>
        </div>

        <aside class="space-y-4">
          <div class="card p-5">
            <h2 class="mb-3 text-sm font-semibold text-muted">Current holder</h2>
            <div v-if="holderName" class="flex items-center gap-3">
              <UserAvatar :name="holderName" />
              <div class="min-w-0">
                <p class="truncate font-medium">{{ holderName }}</p>
                <p class="truncate text-xs text-muted">{{ asset.assigned_to?.email || 'Department' }}<template v-if="asset.assigned_at"> · since {{ formatDate(asset.assigned_at) }}</template></p>
              </div>
            </div>
            <p v-else class="text-sm text-muted">Not assigned{{ asset.location_name ? ` · ${asset.location_name}` : '' }}</p>
          </div>

          <div class="card p-5">
            <h2 class="mb-3 text-sm font-semibold text-muted">Warranty</h2>
            <template v-if="asset.warranty_expiry">
              <p class="font-display text-2xl font-semibold" :class="warrantyDays < 0 ? 'text-danger' : warrantyDays <= 30 ? 'text-warning' : ''">
                {{ warrantyDays < 0 ? 'Expired' : `${warrantyDays} days` }}
              </p>
              <p class="text-xs text-muted">{{ warrantyDays < 0 ? 'on' : 'until' }} {{ formatDate(asset.warranty_expiry) }}</p>
              <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-line">
                <div class="h-full rounded-full bg-gradient-accent transition-all duration-700" :style="{ width: `${Math.max(0, Math.min(100, (warrantyDays / 365) * 100))}%` }" />
              </div>
            </template>
            <p v-else class="text-sm text-muted">No warranty recorded.</p>
          </div>

          <div class="card p-5">
            <div class="mb-3 flex items-center justify-between">
              <h2 class="flex items-center gap-2 text-sm font-semibold text-muted"><QrCode class="h-4 w-4" /> Codes</h2>
              <AppButton v-if="auth.isManager" size="sm" variant="ghost" :icon="Printer" @click="printLabel">Label</AppButton>
            </div>
            <div class="flex flex-col items-center gap-3">
              <div class="rounded-2xl bg-white p-2"><img v-if="qrUrl" :src="qrUrl" alt="QR code" class="h-36 w-36" /><div v-else class="skeleton h-36 w-36" /></div>
              <p class="font-mono text-sm">{{ asset.asset_tag }}</p>
              <div class="flex flex-wrap justify-center gap-2">
                <AppButton size="sm" variant="secondary" :icon="Download" @click="downloadFile(`/assets/${asset.id}/qr/`, { filename: `${asset.asset_tag}-qr.png` })">QR</AppButton>
                <AppButton size="sm" variant="secondary" :icon="Barcode" @click="downloadFile(`/assets/${asset.id}/barcode/`, { filename: `${asset.asset_tag}-barcode.svg` })">Barcode</AppButton>
              </div>
            </div>
            <div v-if="barcodeUrl" class="mt-4 rounded-xl bg-white p-2"><img :src="barcodeUrl" alt="Barcode" class="mx-auto h-16" /></div>
          </div>
        </aside>
      </div>

      <ChangeStatusModal v-model:open="statusOpen" :asset="asset" @changed="(a) => { asset = a; timeline?.reload() }" />
      <MaintenanceFormModal v-model:open="maintOpen" :asset="asset" @saved="load" />

      <AppModal :open="!!photoOpen" size="lg" :title="photoOpen?.caption || 'Photo'" @update:open="(v) => !v && (photoOpen = null)">
        <img v-if="photoOpen" :src="photoOpen.image" :alt="photoOpen.caption" class="max-h-[65vh] w-full rounded-2xl object-contain" />
        <template v-if="auth.isManager" #footer>
          <AppButton variant="danger" :icon="Trash2" @click="deletePhoto(photoOpen)">Delete</AppButton>
          <AppButton v-if="!photoOpen?.is_primary" variant="secondary" :icon="Star" @click="makePrimary(photoOpen); photoOpen = null">Set as cover</AppButton>
        </template>
      </AppModal>
    </template>
  </div>
</template>
