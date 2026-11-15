<script setup>
import { Compass } from 'lucide-vue-next'
import EmptyState from '@/components/ui/EmptyState.vue'
import AppButton from '@/components/ui/AppButton.vue'
</script>

<template>
  <div class="card mx-auto mt-10 max-w-md">
    <EmptyState :icon="Compass" title="Page not found" message="The page you're looking for drifted off into space.">
      <AppButton to="/">Back to dashboard</AppButton>
    </EmptyState>
  </div>
</template>
