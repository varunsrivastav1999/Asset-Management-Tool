<script setup>
import { Building2 } from 'lucide-vue-next'
import { departmentsApi } from '@/api'
import { pick, userLabel } from '@/api/pickers'
import { useAuthStore } from '@/stores/auth'
import CrudPage from '@/components/ui/CrudPage.vue'

const auth = useAuthStore()
const fields = [
  { key: 'name', label: 'Name', required: true },
  { key: 'code', label: 'Code', required: true },
  { key: 'head', label: 'Department head', type: 'picker', fetcher: pick.users, labelOf: userLabel, initial: (r) => (r.head_detail ? [r.head_detail] : []), span: true },
  { key: 'description', label: 'Description', type: 'textarea', span: true },
  { key: 'is_active', label: 'Active', type: 'checkbox' },
]
</script>

<template>
  <CrudPage title="Departments" singular="Department" :api="departmentsApi" table="departments" resource="/departments" :fields="fields" :icon="Building2" :can-write="auth.isAdmin" :can-delete="auth.isAdmin">
    <template #cell-code="{ value }"><span class="font-mono text-xs">{{ value }}</span></template>
  </CrudPage>
</template>
