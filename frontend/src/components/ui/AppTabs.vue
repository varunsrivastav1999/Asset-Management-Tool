<script setup>
const model = defineModel({ type: String })
defineProps({ tabs: { type: Array, required: true } }) // [{ value, label, count? }]
</script>

<template>
  <div class="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1" role="tablist">
    <button
      v-for="t in tabs"
      :key="t.value"
      role="tab"
      :aria-selected="model === t.value"
      class="relative shrink-0 rounded-xl px-3.5 py-2 text-sm font-medium transition"
      :class="model === t.value ? 'glass text-ink' : 'text-muted hover:text-ink'"
      @click="model = t.value"
    >
      {{ t.label }}
      <span v-if="t.count !== undefined" class="ml-1.5 rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent">{{ t.count }}</span>
      <span v-if="model === t.value" class="absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full bg-gradient-accent" />
    </button>
  </div>
</template>
