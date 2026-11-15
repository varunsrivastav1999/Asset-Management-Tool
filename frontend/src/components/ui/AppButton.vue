<script setup>
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'

const props = defineProps({
  variant: { type: String, default: 'primary' }, // primary | secondary | ghost | danger | subtle
  size: { type: String, default: 'md' }, // sm | md | lg | icon
  type: { type: String, default: 'button' },
  loading: Boolean,
  disabled: Boolean,
  icon: { type: [Object, Function], default: null },
  to: { type: [String, Object], default: null },
  block: Boolean,
})

const classes = computed(() => [
  'relative inline-flex select-none items-center justify-center gap-2 rounded-xl font-medium whitespace-nowrap transition-all duration-200',
  'active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50',
  {
    sm: 'h-8 px-3 text-xs',
    md: 'h-10 px-4 text-sm',
    lg: 'h-12 px-6 text-base',
    icon: 'h-10 w-10 text-sm',
  }[props.size],
  {
    primary:
      'bg-gradient-accent text-accent-ink shadow-[0_8px_24px_-8px_var(--glow)] hover:shadow-[0_10px_32px_-6px_var(--glow)] hover:brightness-110',
    secondary: 'glass text-ink hover:bg-surface-hover hover:border-line-strong',
    ghost: 'text-muted hover:text-ink hover:bg-surface-hover',
    subtle: 'bg-accent/10 text-accent hover:bg-accent/20',
    danger: 'bg-danger/90 text-white hover:bg-danger shadow-[0_8px_24px_-10px_var(--danger)]',
  }[props.variant],
  props.block && 'w-full',
])
</script>

<template>
  <RouterLink v-if="to && !disabled" :to="to" :class="classes"><component :is="icon" v-if="icon" class="h-4 w-4 shrink-0" /><slot /></RouterLink>
  <button v-else :type="type" :class="classes" :disabled="disabled || loading" :aria-busy="loading">
    <Loader2 v-if="loading" class="h-4 w-4 shrink-0 animate-spin" />
    <component :is="icon" v-else-if="icon" class="h-4 w-4 shrink-0" />
    <slot />
  </button>
</template>
