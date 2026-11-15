<script setup>
import { useThemeStore } from '@/stores/theme'
import ToastHost from '@/components/ui/ToastHost.vue'
import ConfirmHost from '@/components/ui/ConfirmHost.vue'

useThemeStore()
</script>

<template>
  <div class="aurora" aria-hidden="true"><span /><span /><span /></div>
  <RouterView />
  <ToastHost />
  <ConfirmHost />
</template>
