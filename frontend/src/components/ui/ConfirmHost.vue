<script setup>
import { useUiStore } from '@/stores/ui'
import ConfirmDialog from './ConfirmDialog.vue'
import AppInput from './AppInput.vue'

const ui = useUiStore()
</script>

<template>
  <ConfirmDialog
    :open="!!ui.confirmState"
    :title="ui.confirmState?.title"
    :message="ui.confirmState?.message"
    :confirm-text="ui.confirmState?.confirmText"
    :danger="ui.confirmState?.danger"
    :loading="ui.confirmState?.loading"
    :error="ui.confirmState?.error"
    @confirm="ui.acceptConfirm()"
    @cancel="ui.resolveConfirm(false)"
  >
    <AppInput
      v-if="ui.confirmState?.input"
      v-model="ui.confirmState.value"
      :label="ui.confirmState.input.label"
      :placeholder="ui.confirmState.input.placeholder"
      textarea
      :rows="2"
    />
  </ConfirmDialog>
</template>
