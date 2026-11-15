<script setup>
import { ArrowLeft } from 'lucide-vue-next'

defineProps({ title: String, subtitle: String, back: [String, Object], crumbs: { type: Array, default: () => [] } })
</script>

<template>
  <header class="mb-6 flex animate-fade-up flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
    <div class="min-w-0 lg:flex-1">
      <nav v-if="crumbs.length" aria-label="Breadcrumb" class="mb-2 flex flex-wrap items-center gap-1 text-xs text-muted">
        <template v-for="(c, i) in crumbs" :key="i">
          <span v-if="i" aria-hidden="true">/</span>
          <RouterLink v-if="c.to" :to="c.to" class="inline-flex items-center gap-1 transition hover:text-accent"><ArrowLeft v-if="i === 0" class="h-3.5 w-3.5" />{{ c.label }}</RouterLink>
          <span v-else aria-current="page" class="text-ink/80">{{ c.label }}</span>
        </template>
      </nav>
      <RouterLink v-else-if="back" :to="back" class="mb-2 inline-flex items-center gap-1 text-xs text-muted transition hover:text-accent">
        <ArrowLeft class="h-3.5 w-3.5" /> Back
      </RouterLink>
      <h1 class="truncate text-2xl font-semibold sm:text-3xl"><slot name="title">{{ title }}</slot></h1>
      <p v-if="subtitle || $slots.subtitle" class="mt-1 text-sm text-muted"><slot name="subtitle">{{ subtitle }}</slot></p>
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2 lg:max-w-[65%] lg:justify-end"><slot name="actions" /></div>
  </header>
</template>
