<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Loader2, SearchX } from 'lucide-vue-next'
import { recordsApi } from '@/api'
import EmptyState from '@/components/ui/EmptyState.vue'
import AppButton from '@/components/ui/AppButton.vue'

/** Target of a table row's QR code: /r/<code> → the row in its table. */
const route = useRoute()
const router = useRouter()
const notFound = ref(false)

onMounted(async () => {
  try {
    const row = await recordsApi.lookup(String(route.params.code))
    router.replace({ path: row.route, query: { open: row.code } })
  } catch {
    notFound.value = true
  }
})
</script>

<template>
  <div class="card mx-auto mt-10 max-w-md">
    <EmptyState v-if="notFound" :icon="SearchX" title="Entry not found" :message="`No entry you can access has the code “${route.params.code}”.`">
      <AppButton to="/scan">Scan another</AppButton>
    </EmptyState>
    <div v-else class="flex items-center justify-center gap-3 p-10 text-muted"><Loader2 class="h-5 w-5 animate-spin" /> Opening {{ route.params.code }}…</div>
  </div>
</template>
