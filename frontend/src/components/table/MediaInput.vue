<script setup>
import { ref } from 'vue'
import { Upload, X } from 'lucide-vue-next'
import { mediaApi } from '@/api'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import AppButton from '@/components/ui/AppButton.vue'
import MediaValue from '@/components/table/MediaValue.vue'

/** Upload / replace / remove the file of a Media column. v-model is the cell value ({ id, name, type, size }). */
const props = defineProps({ item: { type: [Number, String], required: true }, column: { type: String, required: true }, label: String, error: String })
const model = defineModel({ type: Object, default: null })
const emit = defineEmits(['uploaded'])
const ui = useUiStore()
const input = ref(null)
const busy = ref(false)
const ACCEPT = '.jpg,.jpeg,.png,.webp,.gif,.pdf,.docx,.xlsx,.pptx,.csv,.txt,.mp4'

async function onPick(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  busy.value = true
  try {
    model.value = await mediaApi.upload(props.item, props.column, file)
    emit('uploaded', model.value)
  } catch (err) {
    ui.error(parseError(err).message)
  } finally {
    busy.value = false
  }
}
defineExpose({ pick: () => input.value?.click() })
</script>

<template>
  <div>
    <span v-if="label" class="label">{{ label }}</span>
    <div class="flex min-w-0 items-center gap-2">
      <MediaValue v-if="model?.id" :value="model" class="min-w-0 flex-1" />
      <AppButton size="sm" variant="subtle" :icon="Upload" :loading="busy" @click.stop="input.click()">{{ model?.id ? 'Replace' : 'Upload' }}</AppButton>
      <button v-if="model?.id" type="button" class="rounded-lg p-1.5 text-muted hover:bg-danger/10 hover:text-danger" aria-label="Remove file" @click.stop="model = null"><X class="h-4 w-4" /></button>
      <input ref="input" type="file" class="hidden" :accept="ACCEPT" data-testid="media-file" @change="onPick" />
    </div>
    <p class="mt-1 text-[11px] text-muted">Photo, PDF, Office, CSV/TXT or MP4 · up to 15 MB</p>
    <p v-if="error" class="mt-1 text-xs text-danger">{{ error }}</p>
  </div>
</template>
