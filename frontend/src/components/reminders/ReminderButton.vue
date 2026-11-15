<script setup>
import { Bell } from 'lucide-vue-next'
import AppButton from '@/components/ui/AppButton.vue'
import { useAuthStore } from '@/stores/auth'

/** "Reminders" shortcut shown in a section's page header (managers and admins). */
defineProps({ section: { type: [Number, String], default: null } })
const auth = useAuthStore()
</script>

<template>
  <AppButton v-if="auth.isManager" variant="ghost" :icon="Bell" :to="section ? { path: '/reminders', query: { section } } : '/reminders'">Reminders</AppButton>
</template>
