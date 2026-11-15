<script setup>
import { PackageOpen } from 'lucide-vue-next'
defineProps({ title: { type: String, default: 'Nothing here yet' }, message: String, icon: { type: [Object, Function], default: () => PackageOpen } })
</script>

<template>
  <div class="flex flex-col items-center justify-center px-6 py-14 text-center">
    <div class="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-accent/10 text-accent shadow-[0_0_40px_-8px_var(--glow)]">
      <component :is="icon" class="h-7 w-7" />
    </div>
    <h3 class="text-base font-semibold">{{ title }}</h3>
    <p v-if="message" class="mt-1 max-w-sm text-sm text-muted">{{ message }}</p>
    <div v-if="$slots.default" class="mt-5"><slot /></div>
  </div>
</template>
