<script setup>
import { ref } from 'vue'
import { UploadCloud } from 'lucide-vue-next'

const props = defineProps({ accept: String, multiple: Boolean, hint: String, disabled: Boolean })
const emit = defineEmits(['files'])
const over = ref(false)
const input = ref(null)

function handle(list) {
  const files = [...(list || [])]
  if (files.length) emit('files', props.multiple ? files : [files[0]])
  if (input.value) input.value.value = ''
}
</script>

<template>
  <label
    class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition"
    :class="[over ? 'border-accent bg-accent/5' : 'border-line-strong hover:border-accent/60', disabled && 'pointer-events-none opacity-50']"
    @dragover.prevent="over = true"
    @dragleave.prevent="over = false"
    @drop.prevent="over = false; handle($event.dataTransfer.files)"
  >
    <UploadCloud class="h-8 w-8 text-accent" />
    <span class="text-sm font-medium">Drop file{{ multiple ? 's' : '' }} here or <span class="text-accent">browse</span></span>
    <span v-if="hint" class="text-xs text-muted">{{ hint }}</span>
    <input ref="input" type="file" class="sr-only" :accept="accept" :multiple="multiple" @change="handle($event.target.files)" />
  </label>
</template>
