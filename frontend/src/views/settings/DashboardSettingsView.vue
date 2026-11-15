<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { BarChart3, Eye, EyeOff, GripVertical, LayoutGrid, Pencil, Plus, RotateCcw, Table2, Trash2, TrendingUp } from 'lucide-vue-next'
import { widgetsApi } from '@/api'
import { parseError } from '@/api/http'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import IconPicker from '@/components/settings/IconPicker.vue'
import RoleChecklist from '@/components/settings/RoleChecklist.vue'

const ui = useUiStore()
const notes = useNotificationsStore()
const widgets = ref([])
const sources = ref([])
const sizes = ref([])
const loading = ref(true)
const saving = ref(false)
const open = ref(false)
const editing = ref(null)
const errors = ref({})
const form = reactive({})

const TYPE_ICON = { stat: TrendingUp, chart: BarChart3, table: Table2 }
const SIZE_SPAN = { sm: 'col-span-1', md: 'sm:col-span-2', lg: 'sm:col-span-2 xl:col-span-3', full: 'sm:col-span-2 xl:col-span-4' }
const CHART_LABELS = { doughnut: 'Doughnut', bar: 'Bar (vertical)', hbar: 'Bar (horizontal)', line: 'Line' }
const TONES = ['accent', 'violet', 'amber', 'rose', 'emerald']

async function load() {
  try {
    const [list, meta] = await Promise.all([widgetsApi.list(), sources.value.length ? null : widgetsApi.sources()])
    widgets.value = list
    if (meta) {
      sources.value = meta.sources
      sizes.value = meta.sizes.map(([value, label]) => ({ value, label }))
    }
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)
// Another admin edited the layout: refresh (unless we're mid-edit).
watch(() => notes.layoutTick, () => !open.value && load())

const sourceMap = computed(() => Object.fromEntries(sources.value.map((s) => [s.key, s])))
const sourceOptions = computed(() =>
  sources.value.filter((s) => s.types.includes(form.type)).map((s) => ({ value: s.key, label: `${s.label}${s.scope === 'org' ? '' : ' (personal)'}` })),
)
const current = computed(() => sourceMap.value[form.data_source])
const allowedRoles = computed(() => current.value?.allowed_roles || ['admin', 'manager', 'employee'])

watch(() => form.type, (t, old) => {
  if (!open.value || !old || t === old) return
  if (!sourceMap.value[form.data_source]?.types.includes(t)) form.data_source = sourceOptions.value[0]?.value || ''
  if (t === 'stat') form.size = 'sm'
})
watch(() => form.data_source, () => {
  if (!open.value) return
  form.visible_roles = (form.visible_roles || []).filter((r) => allowedRoles.value.includes(r))
  const charts = current.value?.charts || []
  if (form.type === 'chart' && charts.length && !charts.includes(form.chart_type)) form.chart_type = charts[0]
  if (!editing.value && current.value) form.title ||= current.value.label
})

function openForm(w = null) {
  editing.value = w
  errors.value = {}
  Object.assign(form, {
    title: w?.title || '',
    type: w?.type || 'stat',
    data_source: w?.data_source || '',
    chart_type: w?.chart_type || '',
    size: w?.size || 'sm',
    visible_roles: w ? [...w.visible_roles] : ['admin', 'manager'],
    is_active: w?.is_active ?? true,
    tone: w?.config?.tone || 'accent',
    icon: w?.config?.icon || '',
  })
  open.value = true
  if (!w) form.data_source = sourceOptions.value[0]?.value || ''
}

async function save() {
  saving.value = true
  errors.value = {}
  const { tone, icon, ...rest } = form
  const payload = { ...rest, config: form.type === 'stat' ? { tone, ...(icon ? { icon } : {}) } : {} }
  try {
    editing.value ? await widgetsApi.update(editing.value.id, payload) : await widgetsApi.create(payload)
    ui.success(editing.value ? 'Widget updated' : 'Widget added')
    open.value = false
    load()
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

async function toggleActive(w) {
  await widgetsApi.update(w.id, { is_active: !w.is_active }).catch((e) => ui.error(parseError(e).message))
  load()
}

async function remove(w) {
  if (!(await ui.confirm({ title: `Delete “${w.title}”?`, confirmText: 'Delete widget', danger: true }))) return
  try {
    await widgetsApi.remove(w.id)
    ui.success('Widget deleted')
    open.value = false
    load()
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

async function onSort() {
  try {
    await widgetsApi.reorder(widgets.value.map((w) => w.id))
  } catch (e) {
    ui.error(parseError(e).message)
    load()
  }
}

async function reset() {
  if (!(await ui.confirm({ title: 'Reset dashboard to defaults?', message: 'All widgets are replaced with the default layout for every role.', confirmText: 'Reset', danger: true }))) return
  await widgetsApi.reset()
  ui.success('Dashboard reset')
  load()
}
</script>

<template>
  <div>
    <PageHeader title="Dashboard settings" subtitle="Choose which widgets each role sees. Drag cards to rearrange — changes go live for everyone instantly.">
      <template #actions>
        <AppButton variant="ghost" :icon="RotateCcw" @click="reset">Reset</AppButton>
        <AppButton variant="secondary" :icon="Eye" to="/">View dashboard</AppButton>
        <AppButton :icon="Plus" @click="openForm()">Add widget</AppButton>
      </template>
    </PageHeader>

    <div v-if="loading" class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"><div v-for="i in 8" :key="i" class="skeleton h-28" /></div>
    <div v-else-if="!widgets.length" class="card">
      <EmptyState :icon="LayoutGrid" title="No widgets" message="Add your first widget or restore the defaults."><AppButton :icon="Plus" @click="openForm()">Add widget</AppButton></EmptyState>
    </div>
    <VueDraggable
      v-else
      v-model="widgets"
      :animation="180"
      :force-fallback="true"
      :fallback-tolerance="3"
      handle=".drag-handle"
      ghost-class="opacity-40"
      class="grid grid-flow-row-dense grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
      @end="onSort"
    >
      <article
        v-for="w in widgets"
        :key="w.id"
        class="card group relative flex min-h-28 flex-col p-4 transition"
        :class="[SIZE_SPAN[w.size], !w.is_active && 'opacity-50', w.type === 'stat' ? '' : 'min-h-40']"
      >
        <div class="flex items-start gap-2">
          <button class="drag-handle -ml-1 cursor-grab touch-none rounded-lg p-1 text-muted hover:bg-surface-hover active:cursor-grabbing" :aria-label="`Drag ${w.title}`">
            <GripVertical class="h-4 w-4" />
          </button>
          <component :is="TYPE_ICON[w.type]" class="mt-1 h-4 w-4 shrink-0 text-accent" />
          <div class="min-w-0 flex-1">
            <p class="truncate font-medium">{{ w.title }}</p>
            <p class="truncate text-xs text-muted">{{ sourceMap[w.data_source]?.label || w.data_source }}<template v-if="w.chart_type"> · {{ CHART_LABELS[w.chart_type] }}</template></p>
          </div>
        </div>
        <div class="mt-auto flex flex-wrap items-center gap-1.5 pt-3">
          <AppBadge v-for="r in w.visible_roles" :key="r" :tone="{ admin: 'rose', manager: 'violet', employee: 'primary' }[r]">{{ r }}</AppBadge>
          <div class="ml-auto flex gap-0.5">
            <button class="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-ink" :aria-label="w.is_active ? 'Hide widget' : 'Show widget'" @click="toggleActive(w)">
              <EyeOff v-if="w.is_active" class="h-4 w-4" />
              <Eye v-else class="h-4 w-4" />
            </button>
            <button class="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-ink" :aria-label="`Edit ${w.title}`" @click="openForm(w)"><Pencil class="h-4 w-4" /></button>
            <button class="rounded-lg p-1.5 text-muted hover:bg-danger/10 hover:text-danger" :aria-label="`Delete ${w.title}`" @click="remove(w)"><Trash2 class="h-4 w-4" /></button>
          </div>
        </div>
      </article>
    </VueDraggable>

    <AppModal v-model:open="open" :title="editing ? `Edit “${editing.title}”` : 'Add widget'" size="lg">
      <form id="widget-form" class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <AppSelect v-model="form.type" label="Widget type" :options="[{ value: 'stat', label: 'Stat card' }, { value: 'chart', label: 'Chart' }, { value: 'table', label: 'Table' }]" :error="errors.type" />
        <AppSelect v-model="form.data_source" label="Data source" :options="sourceOptions" :error="errors.data_source" />
        <AppInput v-model="form.title" class="sm:col-span-2" label="Title" required :error="errors.title" />
        <AppSelect v-if="form.type === 'chart'" v-model="form.chart_type" label="Chart style" :options="(current?.charts || []).map((c) => ({ value: c, label: CHART_LABELS[c] }))" :error="errors.chart_type" />
        <AppSelect v-model="form.size" label="Size" :options="sizes" :error="errors.size" />
        <template v-if="form.type === 'stat'">
          <div>
            <span class="label">Accent</span>
            <div class="flex gap-2">
              <button v-for="t in TONES" :key="t" type="button" class="h-8 w-8 rounded-full ring-offset-2 ring-offset-bg transition" :class="[{ accent: 'bg-emerald-400', violet: 'bg-violet-400', amber: 'bg-amber-400', rose: 'bg-rose-400', emerald: 'bg-emerald-400' }[t], form.tone === t && 'ring-2 ring-accent']" :aria-label="t" @click="form.tone = t" />
            </div>
          </div>
          <IconPicker v-model="form.icon" class="sm:col-span-2" />
        </template>
        <RoleChecklist v-model="form.visible_roles" class="sm:col-span-2" :allowed="allowedRoles" :error="errors.visible_roles" />
        <p v-if="current?.scope === 'org'" class="text-xs text-muted sm:col-span-2">This source shows organisation-wide data, so it can only be shown to admins and managers.</p>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.is_active" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Visible on the dashboard</label>
      </form>
      <template #footer>
        <AppButton v-if="editing" variant="ghost" class="sm:mr-auto" :icon="Trash2" @click="remove(editing)">Delete</AppButton>
        <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
        <AppButton type="submit" form="widget-form" :loading="saving">Save</AppButton>
      </template>
    </AppModal>
  </div>
</template>
