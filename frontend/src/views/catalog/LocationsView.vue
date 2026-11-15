<script setup>
import { MapPin } from 'lucide-vue-next'
import { locationsApi } from '@/api'
import { pick } from '@/api/pickers'
import CrudPage from '@/components/ui/CrudPage.vue'

const fields = [
  { key: 'name', label: 'Name', required: true },
  { key: 'code', label: 'Code', required: true },
  { key: 'parent', label: 'Parent location', type: 'picker', fetcher: pick.locations, initial: (r) => (r.parent ? [{ id: r.parent, name: r.parent_name }] : []) },
  { key: 'is_active', label: 'Active', type: 'checkbox' },
  { key: 'address', label: 'Address', type: 'textarea', span: true },
]
</script>

<template>
  <CrudPage title="Locations" singular="Location" subtitle="Buildings, rooms and storage where assets live" :api="locationsApi" table="locations" resource="/locations" :fields="fields" :icon="MapPin" can-write can-delete>
    <template #cell-code="{ value }"><span class="font-mono text-xs">{{ value }}</span></template>
  </CrudPage>
</template>
