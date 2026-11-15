<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { PanelLeft, Plus, RotateCcw, Save, Undo2 } from 'lucide-vue-next'
import { sidebarApi, tablesApi } from '@/api'
import { parseError } from '@/api/http'
import { useSidebarStore } from '@/stores/sidebar'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppModal from '@/components/ui/AppModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import IconPicker from '@/components/settings/IconPicker.vue'
import RoleChecklist from '@/components/settings/RoleChecklist.vue'
import SidebarTreeEditor from '@/components/settings/SidebarTreeEditor.vue'
import SidebarNav from '@/components/SidebarNav.vue'
import ColorField from '@/components/settings/ColorField.vue'

const ui = useUiStore()
const sidebar = useSidebarStore()
const router = useRouter()

const tree = ref([])
const loading = ref(true)
const dirty = ref(false)
const savingOrder = ref(false)
const open = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
const form = reactive({})
const previewRole = ref('employee')
const tableOptions = ref([])

async function load() {
  loading.value = true
  try {
    tree.value = (await sidebarApi.tree()).items
    dirty.value = false
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  load()
  tableOptions.value = (await tablesApi.registry().catch(() => ({ tables: [] }))).tables.map((t) => ({ value: t.key, label: `${t.label} table` }))
})

/** Known in-app routes for the route picker (excludes dynamic/detail routes). */
const routeOptions = computed(() =>
  router
    .getRoutes()
    .filter((r) => r.meta?.title && !r.path.includes(':') && r.path !== '/login')
    .map((r) => ({ value: r.path === '' ? '/' : r.path, label: `${r.meta.title} — ${r.path || '/'}` }))
    .sort((a, b) => a.label.localeCompare(b.label)),
)

const groups = computed(() => {
  const out = []
  const walk = (nodes, depth) =>
    nodes.forEach((n) => {
      if (n.type === 'group' && n.id !== editing.value?.id) {
        out.push({ value: n.id, label: `${'— '.repeat(depth)}${n.name}` })
        walk(n.children || [], depth + 1)
      }
    })
  walk(tree.value, 0)
  return out
})

function flatten() {
  const out = []
  const walk = (nodes, parent) =>
    nodes.forEach((n, i) => {
      out.push({ id: n.id, parent, order: i })
      if (n.type === 'group') walk(n.children || [], n.id)
    })
  walk(tree.value, null)
  return out
}

async function saveOrder() {
  savingOrder.value = true
  try {
    await sidebarApi.reorder(flatten())
    ui.success('Sidebar order saved')
    dirty.value = false
    sidebar.load()
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    savingOrder.value = false
  }
}

function openForm(item = null, parent = null) {
  editing.value = item
  errors.value = {}
  Object.assign(form, {
    name: item?.name || '',
    type: item?.type || 'page',
    icon: item?.icon || '',
    route: item?.route || '',
    url: item?.url || '',
    open_in_new_tab: item?.open_in_new_tab ?? true,
    parent: item ? item.parent ?? '' : parent?.id ?? '',
    visible_roles: item ? [...item.visible_roles] : ['admin', 'manager', 'employee'],
    is_active: item?.is_active ?? true,
    color: item?.color || '',
    icon_color: item?.icon_color || '',
    active_color: item?.active_color || '',
    gradient: item?.gradient ?? false,
    glow: item?.glow ?? false,
    table: item?.table || '',
  })
  open.value = true
}

async function save() {
  if (dirty.value && !(await ui.confirm({ title: 'Unsaved order changes', message: 'Saving this item reloads the tree and discards your unsaved drag-and-drop changes.', confirmText: 'Continue' })))
    return
  saving.value = true
  errors.value = {}
  const payload = { ...form, parent: form.parent === '' ? null : form.parent }
  try {
    editing.value ? await sidebarApi.update(editing.value.id, payload) : await sidebarApi.create(payload)
    ui.success(editing.value ? 'Item updated' : 'Item added')
    open.value = false
    await load()
    sidebar.load()
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  const nested = item.type === 'group' && item.children?.length
  const ok = await ui.confirm({
    title: `Delete ${item.name || 'divider'}?`,
    message: nested ? `This group and its ${item.children.length} item(s) will be removed from the menu.` : 'It will disappear from everyone’s menu.',
    confirmText: 'Delete',
    danger: true,
  })
  if (!ok) return
  try {
    await sidebarApi.remove(item.id)
    ui.success('Item deleted')
    open.value = false
    await load()
    sidebar.load()
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

async function reset() {
  if (!(await ui.confirm({ title: 'Reset sidebar to defaults?', message: 'All custom items and ordering are replaced with the default menu.', confirmText: 'Reset', danger: true }))) return
  await sidebarApi.reset()
  ui.success('Sidebar reset')
  await load()
  sidebar.load()
}

/** Live preview of the item being edited, rendered in both themes. */
const previewItem = computed(() => [
  {
    id: 'preview',
    type: form.type === 'group' ? 'group' : form.type === 'link' ? 'link' : 'page',
    name: form.name || 'Menu item',
    icon: form.icon,
    route: '/__preview',
    url: form.url || '#',
    open_in_new_tab: form.open_in_new_tab,
    color: form.color,
    icon_color: form.icon_color,
    active_color: form.active_color,
    gradient: form.gradient,
    glow: form.glow,
    children: form.type === 'group' ? [{ id: 'c', type: 'page', name: 'Child page', icon: 'boxes', route: '/__child' }] : undefined,
  },
])

/** Client-side preview of what a role will see (mirrors the server's filtering). */
const preview = computed(() => {
  const role = previewRole.value
  const walk = (nodes) => {
    const out = []
    for (const n of nodes) {
      if (!n.is_active || !n.visible_roles.includes(role)) continue
      if (n.type === 'group') {
        const children = walk(n.children || [])
        if (children.length) out.push({ ...n, children })
      } else if (!(n.type === 'divider' && (!out.length || out.at(-1).type === 'divider'))) out.push(n)
    }
    while (out.length && out.at(-1).type === 'divider') out.pop()
    return out
  }
  return walk(tree.value)
})

watch(() => form.type, (t) => {
  if (t === 'divider') form.name = ''
})

const beforeUnload = (e) => {
  if (dirty.value) e.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(async () => !dirty.value || (await ui.confirm({ title: 'Discard unsaved order?', confirmText: 'Discard', danger: true })))
</script>

<template>
  <div>
    <PageHeader title="Sidebar settings" subtitle="Drag items to reorder or move them between groups, then save. Everyone's menu updates live.">
      <template #actions>
        <AppButton variant="ghost" :icon="RotateCcw" @click="reset">Reset</AppButton>
        <AppButton variant="secondary" :icon="Plus" @click="openForm()">Add item</AppButton>
        <AppButton :icon="Save" :disabled="!dirty" :loading="savingOrder" @click="saveOrder">Save order</AppButton>
      </template>
    </PageHeader>

    <Transition name="fade">
      <div v-if="dirty" class="glass-strong sticky top-[4.5rem] z-10 mb-3 flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm">
        <span class="h-2 w-2 animate-pulse rounded-full bg-warning" /> Unsaved order changes
        <div class="ml-auto flex gap-2">
          <AppButton size="sm" variant="ghost" :icon="Undo2" @click="load">Discard</AppButton>
          <AppButton size="sm" :icon="Save" :loading="savingOrder" @click="saveOrder">Save</AppButton>
        </div>
      </div>
    </Transition>

    <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
      <section class="card min-w-0 p-3 sm:p-4">
        <div v-if="loading" class="space-y-2"><div v-for="i in 8" :key="i" class="skeleton h-12" /></div>
        <EmptyState v-else-if="!tree.length" :icon="PanelLeft" title="The sidebar is empty" message="Add items or restore the default menu.">
          <AppButton :icon="Plus" @click="openForm()">Add item</AppButton>
        </EmptyState>
        <SidebarTreeEditor v-else v-model="tree" @changed="dirty = true" @edit="openForm" @remove="remove" @add-child="(g) => openForm(null, g)" />
      </section>

      <aside class="card h-fit min-w-0 p-4 lg:sticky lg:top-20">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold">Preview as</h2>
          <AppSelect v-model="previewRole" class="w-32" aria-label="Preview role" :options="[{ value: 'admin', label: 'Admin' }, { value: 'manager', label: 'Manager' }, { value: 'employee', label: 'Employee' }]" />
        </div>
        <div class="pointer-events-none rounded-2xl border border-line p-2"><SidebarNav :items="preview" /></div>
      </aside>
    </div>

    <AppModal v-model:open="open" :title="editing ? `Edit ${editing.name || 'divider'}` : 'Add sidebar item'" size="lg">
      <form id="sidebar-form" class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <AppSelect
          v-model="form.type"
          label="Type"
          :options="[{ value: 'page', label: 'Page (in-app)' }, { value: 'link', label: 'External link' }, { value: 'group', label: 'Group' }, { value: 'divider', label: 'Divider' }]"
          :error="errors.type"
        />
        <AppSelect v-model="form.parent" label="Inside group" placeholder="Top level" :options="groups" :error="errors.parent" />
        <AppInput v-if="form.type !== 'divider'" v-model="form.name" class="sm:col-span-2" label="Name" required :error="errors.name" />
        <template v-if="form.type === 'page'">
          <AppInput v-model="form.route" label="Route" list="known-routes" placeholder="/assets" required :error="errors.route" />
          <datalist id="known-routes"><option v-for="r in routeOptions" :key="r.value" :value="r.value">{{ r.label }}</option></datalist>
          <p class="self-end pb-2 text-xs text-muted">Pick a page or type a path with filters, e.g. <code>/assets?status=in_repair</code>.</p>
        </template>
        <template v-if="form.type === 'link'">
          <AppInput v-model="form.url" label="URL" type="url" placeholder="https://" required :error="errors.url" />
          <label class="flex items-center gap-2 self-end pb-2 text-sm"><input v-model="form.open_in_new_tab" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Open in a new tab</label>
        </template>
        <AppSelect v-if="form.type === 'page'" v-model="form.table" class="sm:col-span-2" label="Table on this page" placeholder="Detect from route" :options="tableOptions" />
        <IconPicker v-if="form.type !== 'divider'" v-model="form.icon" class="sm:col-span-2" />
        <fieldset v-if="form.type !== 'divider'" class="rounded-2xl border border-line p-4 sm:col-span-2">
          <legend class="px-1 text-sm font-semibold">Appearance</legend>
          <div class="grid gap-4 sm:grid-cols-3">
            <ColorField v-model="form.color" label="Label color" :error="errors.color" />
            <ColorField v-model="form.icon_color" label="Icon color" :error="errors.icon_color" />
            <ColorField v-model="form.active_color" label="Active color" hint="Highlight when open" :error="errors.active_color" />
          </div>
          <div class="mt-3 flex flex-wrap gap-4">
            <label class="flex items-center gap-2 text-sm"><input v-model="form.gradient" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Gradient highlight</label>
            <label class="flex items-center gap-2 text-sm"><input v-model="form.glow" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Glow</label>
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-2" aria-label="Live preview">
            <div v-for="t in ['theme-dark', 'theme-light']" :key="t" :class="t" class="rounded-2xl border border-line bg-bg p-2 text-ink">
              <p class="mb-1 px-1 text-[10px] tracking-wider text-muted uppercase">{{ t === 'theme-dark' ? 'Dark' : 'Light' }} · active</p>
              <div class="pointer-events-none"><SidebarNav :items="previewItem" force-active="preview" /></div>
              <div class="pointer-events-none opacity-90"><SidebarNav :items="previewItem.map((i) => ({ ...i, id: 'preview-idle' }))" force-active="none" /></div>
            </div>
          </div>
          <p class="mt-2 text-xs text-muted">Leave a color empty to follow the theme. Changes reach every open browser instantly.</p>
        </fieldset>
        <p v-if="errors.icon" class="text-xs text-danger sm:col-span-2">{{ errors.icon }}</p>
        <RoleChecklist v-model="form.visible_roles" class="sm:col-span-2" :error="errors.visible_roles" />
        <p class="text-xs text-muted sm:col-span-2">Hiding an item only removes it from the menu — page access is still enforced by each role's permissions.</p>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.is_active" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Active</label>
      </form>
      <template #footer>
        <AppButton v-if="editing" variant="ghost" class="sm:mr-auto" @click="remove(editing)">Delete</AppButton>
        <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
        <AppButton type="submit" form="sidebar-form" :loading="saving">Save</AppButton>
      </template>
    </AppModal>
  </div>
</template>
