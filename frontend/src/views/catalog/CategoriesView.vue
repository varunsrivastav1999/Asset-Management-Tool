<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { GripVertical, Plus, Shapes, Trash2 } from 'lucide-vue-next'
import { categoriesApi } from '@/api'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import CategoryIcon from '@/components/ui/CategoryIcon.vue'
import { CATEGORY_ICONS, FIELD_TYPES } from '@/utils/constants'

const ui = useUiStore()
const categories = ref([])
const loading = ref(true)
const search = ref('')
const open = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
const form = reactive({ name: '', parent: '', icon: 'box', color: '#10b981', description: '', is_active: true, custom_fields: [] })
const COLORS = ['#10b981', '#84cc16', '#22c55e', '#65a30d', '#a78bfa', '#f472b6', '#fb7185', '#f59e0b', '#34d399', '#94a3b8']

async function load() {
  loading.value = true
  try {
    categories.value = await categoriesApi.list()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const tree = computed(() => {
  const q = search.value.toLowerCase()
  const match = (c) => !q || c.name.toLowerCase().includes(q)
  const roots = categories.value.filter((c) => !c.parent)
  const out = []
  const walk = (node, depth) => {
    if (match(node) || categories.value.some((c) => c.parent === node.id && match(c))) out.push({ ...node, depth })
    categories.value.filter((c) => c.parent === node.id).forEach((c) => walk(c, depth + 1))
  }
  roots.forEach((r) => walk(r, 0))
  return out
})

function openForm(c = null) {
  editing.value = c
  errors.value = {}
  Object.assign(form, {
    name: c?.name || '',
    parent: c?.parent ? String(c.parent) : '',
    icon: c?.icon || 'box',
    color: c?.color || '#10b981',
    description: c?.description || '',
    is_active: c?.is_active ?? true,
    custom_fields: (c?.custom_fields || []).map((f) => ({ ...f, optionsText: (f.options || []).join(', ') })),
  })
  open.value = true
}

function addField() {
  form.custom_fields.push({ key: '', label: '', field_type: 'text', required: false, help_text: '', optionsText: '', order: form.custom_fields.length })
}
function slug(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 60)
}
function onLabel(f) {
  if (!f._keyTouched) f.key = slug(f.label)
}
function move(i, dir) {
  const j = i + dir
  if (j < 0 || j >= form.custom_fields.length) return
  const arr = form.custom_fields
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

async function save() {
  saving.value = true
  errors.value = {}
  const payload = {
    ...form,
    parent: form.parent || null,
    custom_fields: form.custom_fields.map((f, i) => ({
      key: f.key,
      label: f.label,
      field_type: f.field_type,
      required: f.required,
      help_text: f.help_text || '',
      order: i,
      options: f.field_type === 'select' ? f.optionsText.split(',').map((o) => o.trim()).filter(Boolean) : [],
    })),
  }
  try {
    editing.value ? await categoriesApi.update(editing.value.id, payload) : await categoriesApi.create(payload)
    ui.success(`Category ${editing.value ? 'updated' : 'created'}`)
    open.value = false
    load()
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = e.response?.data || fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

async function remove(c) {
  if (!(await ui.confirm({ title: `Delete ${c.name}?`, message: 'Categories in use by assets or with sub-categories cannot be deleted.', confirmText: 'Delete', danger: true }))) return
  try {
    await categoriesApi.remove(c.id)
    ui.success('Category deleted')
    open.value = false
    load()
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

const parentOptions = computed(() => categories.value.filter((c) => c.id !== editing.value?.id).map((c) => ({ value: String(c.id), label: c.name })))
const fieldErr = (i) => (Array.isArray(errors.value.custom_fields) ? errors.value.custom_fields[i] || {} : {})
</script>

<template>
  <div>
    <PageHeader title="Categories" subtitle="Asset types, hierarchy and their custom fields">
      <template #actions><AppButton :icon="Plus" @click="openForm()">New category</AppButton></template>
    </PageHeader>

    <div class="card p-3 sm:p-4">
      <SearchInput v-model="search" placeholder="Search categories…" />
      <div v-if="loading" class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><div v-for="i in 6" :key="i" class="skeleton h-24" /></div>
      <EmptyState v-else-if="!tree.length" :icon="Shapes" title="No categories" message="Create categories like Laptops, Furniture or Vehicles.">
        <AppButton :icon="Plus" @click="openForm()">New category</AppButton>
      </EmptyState>
      <TransitionGroup v-else tag="div" name="list" class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <button v-for="c in tree" :key="c.id" class="group flex items-start gap-3 rounded-2xl border border-line p-4 text-left transition hover:-translate-y-0.5 hover:border-line-strong hover:bg-surface-hover" @click="openForm(c)">
          <CategoryIcon :name="c.icon" :color="c.color" />
          <div class="min-w-0 flex-1">
            <p class="truncate font-medium">{{ c.name }} <AppBadge v-if="!c.is_active" class="ml-1">inactive</AppBadge></p>
            <p class="truncate text-xs text-muted">{{ c.parent_name ? `in ${c.parent_name} · ` : '' }}{{ c.asset_count }} assets · {{ c.custom_fields.length + c.inherited_fields.length }} fields</p>
            <div class="mt-2 flex flex-wrap gap-1">
              <span v-for="f in [...c.inherited_fields, ...c.custom_fields].slice(0, 4)" :key="f.key" class="chip text-[10px] text-muted">{{ f.label }}</span>
            </div>
          </div>
        </button>
      </TransitionGroup>
    </div>

    <AppModal v-model:open="open" :title="editing ? `Edit ${editing.name}` : 'New category'" size="lg">
      <form id="cat-form" class="space-y-5" @submit.prevent="save">
        <div class="grid gap-4 sm:grid-cols-2">
          <AppInput v-model="form.name" label="Name" required :error="errors.name" />
          <AppSelect v-model="form.parent" label="Parent category" placeholder="None (top level)" :options="parentOptions" :error="errors.parent" />
          <div>
            <span class="label">Icon</span>
            <div class="flex flex-wrap gap-1.5">
              <button v-for="i in CATEGORY_ICONS" :key="i" type="button" class="rounded-xl p-0.5 transition" :class="form.icon === i ? 'ring-2 ring-accent' : 'opacity-60 hover:opacity-100'" :aria-label="i" @click="form.icon = i">
                <CategoryIcon :name="i" :color="form.color" size="sm" />
              </button>
            </div>
          </div>
          <div>
            <span class="label">Color</span>
            <div class="flex flex-wrap gap-2">
              <button v-for="c in COLORS" :key="c" type="button" class="h-8 w-8 rounded-full ring-offset-2 ring-offset-bg transition" :class="form.color === c && 'ring-2 ring-accent'" :style="{ background: c }" :aria-label="c" @click="form.color = c" />
            </div>
          </div>
          <AppInput v-model="form.description" class="sm:col-span-2" label="Description" textarea :rows="2" />
          <label class="flex items-center gap-2 text-sm"><input v-model="form.is_active" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Active (available for new assets)</label>
        </div>

        <div>
          <div class="mb-2 flex items-center justify-between">
            <div>
              <h3 class="font-semibold">Custom fields</h3>
              <p class="text-xs text-muted">Sub-categories inherit these fields.</p>
            </div>
            <AppButton size="sm" variant="subtle" :icon="Plus" @click="addField">Add field</AppButton>
          </div>
          <p v-if="editing?.inherited_fields?.length" class="mb-2 text-xs text-muted">Inherited: {{ editing.inherited_fields.map((f) => f.label).join(', ') }}</p>
          <p v-if="typeof errors.custom_fields === 'string' || (Array.isArray(errors.custom_fields) && typeof errors.custom_fields[0] === 'string')" class="mb-2 text-xs text-danger">{{ errors.custom_fields }}</p>
          <TransitionGroup tag="div" name="list" class="space-y-2">
            <div v-for="(f, i) in form.custom_fields" :key="i" class="rounded-2xl border border-line p-3">
              <div class="grid items-end gap-3 sm:grid-cols-[auto_1fr_1fr_140px_auto]">
                <div class="hidden flex-col sm:flex">
                  <button type="button" class="text-muted hover:text-ink" aria-label="Move up" @click="move(i, -1)">▲</button>
                  <GripVertical class="h-4 w-4 text-muted" />
                  <button type="button" class="text-muted hover:text-ink" aria-label="Move down" @click="move(i, 1)">▼</button>
                </div>
                <AppInput v-model="f.label" label="Label" required :error="fieldErr(i).label" @input="onLabel(f)" />
                <AppInput v-model="f.key" label="Key" :error="fieldErr(i).key" @input="f._keyTouched = true" />
                <AppSelect v-model="f.field_type" label="Type" :options="FIELD_TYPES" />
                <AppButton variant="ghost" size="icon" :icon="Trash2" aria-label="Remove field" @click="form.custom_fields.splice(i, 1)" />
              </div>
              <div class="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <AppInput v-if="f.field_type === 'select'" v-model="f.optionsText" label="Options (comma separated)" :error="fieldErr(i).options" />
                <AppInput v-else v-model="f.help_text" label="Help text" />
                <label class="flex items-center gap-2 text-sm"><input v-model="f.required" type="checkbox" class="h-4 w-4 accent-[var(--accent)]" /> Required</label>
              </div>
            </div>
          </TransitionGroup>
        </div>
      </form>
      <template #footer>
        <AppButton v-if="editing" variant="ghost" class="sm:mr-auto" :icon="Trash2" @click="remove(editing)">Delete</AppButton>
        <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
        <AppButton type="submit" form="cat-form" :loading="saving">Save</AppButton>
      </template>
    </AppModal>
  </div>
</template>
