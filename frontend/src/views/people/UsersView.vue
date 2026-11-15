<script setup>
import ReminderButton from '@/components/reminders/ReminderButton.vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Columns3, Plus, UserCheck, UserX, Users } from 'lucide-vue-next'
import { departmentsApi, usersApi } from '@/api'
import { parseError } from '@/api/http'
import { useList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import ColumnsPanel from '@/components/table/ColumnsPanel.vue'
import { useTableConfig } from '@/composables/useTableConfig'
import AppPagination from '@/components/ui/AppPagination.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UserAvatar from '@/components/ui/UserAvatar.vue'
import { ROLES } from '@/utils/constants'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const cfg = useTableConfig('users', { resource: '/users', names: { plural: 'People', singular: 'Person' } })
const names = cfg.names
const list = useList(usersApi.list, {
  filters: { search: '', role: '', department: '', is_active: 'true', ordering: '' },
  extraParams: () => cfg.params.value,
  onData: cfg.setFromList,
})
watch(cfg.pageItemId, () => list.load())
const columnsOpen = ref(false)
const sortBy = (key) => (list.filters.ordering = list.filters.ordering === key ? `-${key}` : key)
const departments = ref([])
onMounted(async () => {
  list.load()
  departments.value = (await departmentsApi.list({ page_size: 200 })).results
})

const open = ref(false)
const editing = ref(null)
const saving = ref(false)
const errors = ref({})
const form = reactive({})

function openForm(u = null) {
  if (!auth.isAdmin) return u && router.push({ name: 'assets', query: { search: u.email } })
  editing.value = u
  errors.value = {}
  Object.assign(form, {
    email: u?.email || '',
    first_name: u?.first_name || '',
    last_name: u?.last_name || '',
    role: u?.role || 'employee',
    department: u?.department ? String(u.department) : '',
    employee_id: u?.employee_id || '',
    job_title: u?.job_title || '',
    phone: u?.phone || '',
    password: '',
  })
  open.value = true
}

async function save() {
  saving.value = true
  errors.value = {}
  const data = { ...form, department: form.department || null, employee_id: form.employee_id || null }
  if (!data.password) delete data.password
  try {
    editing.value ? await usersApi.update(editing.value.id, data) : await usersApi.create(data)
    ui.success(editing.value ? 'User updated' : 'User created')
    open.value = false
    list.load()
  } catch (e) {
    const { message, fields } = parseError(e)
    errors.value = fields
    ui.error(message)
  } finally {
    saving.value = false
  }
}

async function toggleActive(u) {
  try {
    if (u.is_active) {
      if (!(await ui.confirm({ title: `Deactivate ${u.full_name}?`, message: 'They will no longer be able to sign in. History is preserved.', confirmText: 'Deactivate', danger: true }))) return
      await usersApi.remove(u.id)
    } else {
      await usersApi.activate(u.id)
    }
    ui.success(u.is_active ? 'User deactivated' : 'User reactivated')
    open.value = false
    list.load()
  } catch (e) {
    ui.error(parseError(e).message)
  }
}

const roleTone = { admin: 'rose', manager: 'violet', employee: 'primary' }

const bulkConfig = computed(() => ({
  resource: '/users',
  params: () => ({ ...list.params(), ...cfg.params.value }),
  count: list.count.value,
  singular: names.value.singular,
  plural: names.value.plural,
  canDelete: auth.isAdmin,
  canExport: auth.isManager,
  deleteVerb: 'Deactivate',
}))
</script>

<template>
  <div>
    <PageHeader :title="names.plural" :subtitle="names.description || 'Employees, managers and administrators'">
      <template #actions>
        <ReminderButton :section="cfg.pageItemId.value" />
        <AppButton variant="secondary" :icon="Columns3" @click="columnsOpen = true">Columns</AppButton>
        <AppButton v-if="auth.isAdmin" :icon="Plus" @click="openForm()">Add {{ names.singular }}</AppButton>
      </template>
    </PageHeader>

    <div class="card p-3 sm:p-4">
      <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px_200px_150px]">
        <SearchInput v-model="list.filters.search" placeholder="Search name, email, employee ID…" />
        <AppSelect v-model="list.filters.role" placeholder="All roles" :options="ROLES" aria-label="Role" />
        <AppSelect v-model="list.filters.department" placeholder="All departments" :options="departments.map((d) => ({ value: String(d.id), label: d.name }))" aria-label="Department" />
        <AppSelect v-model="list.filters.is_active" :options="[{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]" placeholder="Everyone" aria-label="Status" />
      </div>
      <div class="mt-3">
        <ConfigurableTable
          :bulk="bulkConfig"
          :columns="cfg.visibleColumns.value"
          :rows="list.items.value"
          :loading="list.loading.value"
          :offset="(list.page.value - 1) * 25"
          :ordering="list.filters.ordering"
          clickable
          @row-click="openForm"
          @sort="sortBy"
          @changed="list.load()"
        >
          <template #cell-full_name="{ row }">
            <div class="flex items-center gap-3">
              <UserAvatar :name="row.full_name || row.email" :src="row.avatar" size="sm" />
              <div class="min-w-0">
                <p class="truncate font-medium">{{ row.full_name || row.email }} <AppBadge v-if="!row.is_active" class="ml-1">inactive</AppBadge></p>
                <p class="truncate text-xs text-muted">{{ row.email }}<template v-if="row.employee_id"> · {{ row.employee_id }}</template></p>
              </div>
            </div>
          </template>
          <template #cell-role="{ row }"><AppBadge :tone="roleTone[row.role]">{{ row.role }}</AppBadge></template>
          <template #empty><EmptyState :icon="Users" :title="`No ${names.plural.toLowerCase()} match`" /></template>
        </ConfigurableTable>
        <AppPagination v-model="list.page.value" :pages="list.pages.value" :count="list.count.value" />
      </div>
    </div>

    <ColumnsPanel v-model:open="columnsOpen" :cfg="cfg" title="People table columns" />
    <AppModal v-model:open="open" :title="editing ? `Edit ${editing.full_name || editing.email}` : 'Add person'" size="lg">
      <form id="user-form" class="grid gap-4 sm:grid-cols-2" autocomplete="off" @submit.prevent="save">
        <AppInput v-model="form.first_name" label="First name" required :error="errors.first_name" />
        <AppInput v-model="form.last_name" label="Last name" required :error="errors.last_name" />
        <AppInput v-model="form.email" label="Email" type="email" required :error="errors.email" />
        <AppInput v-model="form.employee_id" label="Employee ID" :error="errors.employee_id" />
        <AppSelect v-model="form.role" label="Role" :options="ROLES" :error="errors.role" />
        <AppSelect v-model="form.department" label="Department" placeholder="None" :options="departments.map((d) => ({ value: String(d.id), label: d.name }))" />
        <AppInput v-model="form.job_title" label="Job title" />
        <AppInput v-model="form.phone" label="Phone" type="tel" />
        <AppInput
          v-model="form.password"
          class="sm:col-span-2"
          :label="editing ? 'New password' : 'Password'"
          type="password"
          autocomplete="new-password"
          :hint="editing ? 'Leave blank to keep the current password' : 'Leave blank for employees who never sign in (assignment only)'"
          :error="errors.password"
        />
      </form>
      <template #footer>
        <AppButton v-if="editing && editing.id !== auth.user?.id" variant="ghost" class="sm:mr-auto" :icon="editing.is_active ? UserX : UserCheck" @click="toggleActive(editing)">
          {{ editing.is_active ? 'Deactivate' : 'Reactivate' }}
        </AppButton>
        <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
        <AppButton type="submit" form="user-form" :loading="saving">Save</AppButton>
      </template>
    </AppModal>
  </div>
</template>
