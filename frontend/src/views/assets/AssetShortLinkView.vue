<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Loader2, SearchX } from 'lucide-vue-next'
import { assetsApi } from '@/api'
import EmptyState from '@/components/ui/EmptyState.vue'
import AppButton from '@/components/ui/AppButton.vue'

const route = useRoute()
const router = useRouter()
const notFound = ref(false)

onMounted(async () => {
  try {
    const asset = await assetsApi.lookup(String(route.params.tag))
    router.replace(`/assets/${asset.id}`)
  } catch {
    notFound.value = true
  }
})
</script>

<template>
  <div class="card mx-auto mt-10 max-w-md">
    <EmptyState v-if="notFound" :icon="SearchX" title="Asset not found" :message="`No asset you can access matches “${route.params.tag}”.`">
      <AppButton to="/scan">Scan another</AppButton>
    </EmptyState>
    <div v-else class="flex items-center justify-center gap-3 p-10 text-muted"><Loader2 class="h-5 w-5 animate-spin" /> Opening {{ route.params.tag }}…</div>
  </div>
</template>
