<script setup>
import { CheckCircle2, Info, TriangleAlert, XCircle, X } from 'lucide-vue-next'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const icons = { success: CheckCircle2, error: XCircle, warning: TriangleAlert, info: Info }
const tones = { success: 'text-success', error: 'text-danger', warning: 'text-warning', info: 'text-accent' }
</script>

<template>
  <div class="pointer-events-none fixed inset-x-0 top-3 z-[300] flex flex-col items-center gap-2 px-3 sm:top-auto sm:right-4 sm:bottom-4 sm:left-auto sm:items-end" aria-live="polite">
    <TransitionGroup name="list">
      <div v-for="t in ui.toasts" :key="t.id" class="glass-strong pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl px-4 py-3" role="status">
        <component :is="icons[t.type]" class="mt-0.5 h-5 w-5 shrink-0" :class="tones[t.type]" />
        <div class="min-w-0 flex-1 text-sm">
          <p v-if="t.title" class="font-semibold">{{ t.title }}</p>
          <p class="whitespace-pre-line text-muted" :class="!t.title && 'text-ink'">{{ t.message }}</p>
          <RouterLink v-if="t.action?.to" :to="t.action.to" class="mt-1 inline-block text-xs font-medium text-accent" @click="ui.dismiss(t.id)">{{ t.action.label }} →</RouterLink>
          <button v-else-if="t.action?.onClick" type="button" class="mt-1 inline-block text-xs font-semibold text-accent hover:underline" @click="ui.dismiss(t.id), t.action.onClick()">{{ t.action.label }}</button>
        </div>
        <button class="text-muted hover:text-ink" aria-label="Dismiss" @click="ui.dismiss(t.id)"><X class="h-4 w-4" /></button>
      </div>
    </TransitionGroup>
  </div>
</template>
