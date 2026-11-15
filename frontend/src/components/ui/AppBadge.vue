<script setup>
defineProps({ tone: { type: String, default: 'slate' }, dot: Boolean })
const tones = {
  primary: 'bg-primary-soft text-primary border-primary/30',
  lime: 'bg-lime-500/12 text-lime-700 dark:text-lime-300 border-lime-500/25',
  violet: 'bg-violet-500/12 text-violet-700 dark:text-violet-300 border-violet-500/25',
  amber: 'bg-amber-500/12 text-amber-800 dark:text-amber-300 border-amber-500/25',
  emerald: 'bg-emerald-500/12 text-emerald-800 dark:text-emerald-300 border-emerald-500/25',
  rose: 'bg-rose-500/12 text-rose-700 dark:text-rose-300 border-rose-500/25',
  slate: 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20',
}
</script>

<template>
  <span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap" :class="tones[tone] || tones.slate">
    <span v-if="dot" class="h-1.5 w-1.5 rounded-full bg-current shadow-[0_0_8px_currentColor]" />
    <slot />
  </span>
</template>
