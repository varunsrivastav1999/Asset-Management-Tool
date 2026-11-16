<script setup>
import { assetsApi } from '@/api'
import ImportDialog from '@/components/ui/ImportDialog.vue'

const open = defineModel('open', { type: Boolean })
const emit = defineEmits(['imported'])
</script>

<template>
  <ImportDialog v-model:open="open" title="Import assets" noun="assets" template-url="/assets/import-template/" :import-fn="assetsApi.importFile" @imported="emit('imported')">
    <template #hint>Leave <code class="text-accent">asset_tag</code> blank to create; fill it to update. Custom fields use <code class="text-accent">cf:key</code> columns.</template>
  </ImportDialog>
</template>
