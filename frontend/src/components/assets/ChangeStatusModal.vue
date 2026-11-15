<script setup>
import { computed, ref, watch } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import { assetsApi } from '@/api'
import { parseError } from '@/api/http'
import { useUiStore } from '@/stores/ui'
import { ASSET_STATUS } from '@/utils/constants'

const open = defineModel('open', { type: Boolean })
const props = defineProps({ asset: Object })
const emit = defineEmits(['changed'])
const ui = useUiStore()
const target = ref('')
const notes = ref('')
const saving = ref(false)

const holder = computed(() => !!(props.asset?.assigned_to || props.asset?.department))
/** Mirrors the backend status machine so only valid targets are offered. */
const options = computed(() => {
  const cur = props.asset?.status
  return Object.entries(ASSET_STATUS)
    .filter(([s]) => s !== cur)
    .map(([value, meta]) => {
      let reason = ''
      if (cur === 'retired' && value !== 'in_stock') reason = 'Retired assets can only be reinstated to stock'
      else if (value === 'in_stock' && holder.value) reason = 'Use a return handover'
      else if (value === 'assigned' && !holder.value) reason = 'Use an issue handover'
      else if (value === 'retired' && holder.value) reason = 'Return it first'
      return { value, meta, reason }
    })
})

watch(open, (v) => {
  if (v) {
    target.value = options.value.find((o) => !o.reason)?.value || ''
    notes.value = ''
  }
})

async function save() {
  saving.value = true
  try {
    const updated = await assetsApi.changeStatus(props.asset.id, target.value, notes.value)
    ui.success(`Status changed to ${ASSET_STATUS[target.value].label}`)
    emit('changed', updated)
    open.value = false
  } catch (e) {
    ui.error(parseError(e).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal v-model:open="open" title="Change status" :subtitle="asset?.asset_tag" size="sm">
    <div class="grid gap-2">
      <button
        v-for="o in options"
        :key="o.value"
        type="button"
        class="flex items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left text-sm transition"
        :class="[target === o.value ? 'border-accent bg-accent/10' : 'border-line hover:border-line-strong', o.reason && 'cursor-not-allowed opacity-50']"
        :disabled="!!o.reason"
        @click="target = o.value"
      >
        <span class="flex items-center gap-2.5"><span class="h-2.5 w-2.5 rounded-full" :style="{ background: o.meta.color }" />{{ o.meta.label }}</span>
        <span v-if="o.reason" class="text-xs text-muted">{{ o.reason }}</span>
      </button>
    </div>
    <AppInput v-model="notes" class="mt-4" label="Notes" textarea :rows="2" placeholder="Why is the status changing?" />
    <template #footer>
      <AppButton variant="secondary" @click="open = false">Cancel</AppButton>
      <AppButton :loading="saving" :disabled="!target" @click="save">Update status</AppButton>
    </template>
  </AppModal>
</template>
