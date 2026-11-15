<script setup>
import { Store } from 'lucide-vue-next'
import { vendorsApi } from '@/api'
import CrudPage from '@/components/ui/CrudPage.vue'

const fields = [
  { key: 'name', label: 'Name', required: true },
  { key: 'contact_name', label: 'Contact person' },
  { key: 'email', label: 'Email', type: 'email' },
  { key: 'phone', label: 'Phone', type: 'tel' },
  { key: 'website', label: 'Website', type: 'url', span: true },
  { key: 'address', label: 'Address', type: 'textarea', span: true },
  { key: 'notes', label: 'Notes', type: 'textarea', span: true },
  { key: 'is_active', label: 'Active', type: 'checkbox' },
]
</script>

<template>
  <CrudPage title="Vendors" singular="Vendor" subtitle="Suppliers and service providers" :api="vendorsApi" table="vendors" resource="/vendors" :fields="fields" :icon="Store" can-write can-delete />
</template>
