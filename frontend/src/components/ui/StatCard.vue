<script setup>
defineProps({
  label: String,
  value: [String, Number],
  hint: String,
  icon: { type: [Object, Function], default: null },
  tone: { type: String, default: 'accent' },
  to: [String, Object],
  loading: Boolean,
})
const glows = {
  accent: 'from-emerald-400/25 to-transparent text-accent',
  violet: 'from-violet-400/25 to-transparent text-violet-400',
  amber: 'from-amber-400/25 to-transparent text-amber-400',
  rose: 'from-rose-400/25 to-transparent text-rose-400',
  emerald: 'from-emerald-400/25 to-transparent text-emerald-400',
}
</script>

<template>
  <component :is="to ? 'RouterLink' : 'div'" :to="to" class="card group relative block overflow-hidden p-4 transition hover:-translate-y-0.5 hover:border-line-strong sm:p-5">
    <div class="absolute -top-10 -right-10 h-28 w-28 rounded-full bg-gradient-to-br opacity-70 blur-2xl transition group-hover:opacity-100" :class="glows[tone]" />
    <div class="relative flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="text-xs font-medium tracking-wide text-muted uppercase">{{ label }}</p>
        <div v-if="loading" class="skeleton mt-2 h-8 w-20" />
        <p v-else class="mt-1.5 truncate font-display text-2xl font-semibold 2xl:text-3xl">{{ value }}</p>
        <p v-if="hint" class="mt-1 truncate text-xs text-muted">{{ hint }}</p>
      </div>
      <div v-if="icon" class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-surface-hover" :class="glows[tone].split(' ').pop()">
        <component :is="icon" class="h-5 w-5" />
      </div>
    </div>
  </component>
</template>
