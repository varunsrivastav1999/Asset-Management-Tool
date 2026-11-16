<script setup>
import { computed } from 'vue'
import { FileText, Film, Image as ImageIcon } from 'lucide-vue-next'
import { downloadFile, parseError } from '@/api/http'
import { mediaApi } from '@/api'
import { useMediaPreview } from '@/composables/useMediaPreview'
import { useUiStore } from '@/stores/ui'

/** A Media cell value: photo thumbnail (or file icon) and name; click opens the file. */
const props = defineProps({ value: { type: Object, default: null }, size: { type: String, default: 'sm' } })
const ui = useUiStore()
const preview = useMediaPreview(() => props.value)
const kind = computed(() => (props.value?.type?.startsWith('image/') ? 'image' : props.value?.type?.startsWith('video/') ? 'video' : 'file'))
const box = computed(() => (props.size === 'lg' ? 'h-16 w-16' : 'h-8 w-8'))

function open() {
  downloadFile(mediaApi.url(props.value.id), { filename: props.value.name, open: kind.value !== 'file' }).catch((e) => ui.error(parseError(e).message))
}
</script>

<template>
  <span v-if="!value?.id" class="text-sm text-muted">—</span>
  <button v-else type="button" class="inline-flex max-w-full min-w-0 items-center gap-2 rounded-lg text-left hover:text-accent" :title="`Open ${value.name}`" :aria-label="`Open ${value.name}`" @click.stop="open">
    <span class="grid shrink-0 place-items-center overflow-hidden rounded-lg border border-line bg-surface-hover" :class="box">
      <img v-if="preview" :src="preview" :alt="value.name" class="h-full w-full object-cover" />
      <ImageIcon v-else-if="kind === 'image'" class="h-4 w-4 text-muted" />
      <Film v-else-if="kind === 'video'" class="h-4 w-4 text-muted" />
      <FileText v-else class="h-4 w-4 text-muted" />
    </span>
    <span class="truncate text-sm">{{ value.name }}</span>
  </button>
</template>
