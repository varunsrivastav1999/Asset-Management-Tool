<script setup>
import { VueDraggable } from 'vue-draggable-plus'
import { EyeOff, ExternalLink, GripVertical, Minus, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import AppBadge from '@/components/ui/AppBadge.vue'
import { iconFor } from '@/utils/icons'

defineOptions({ name: 'SidebarTreeEditor' })
const list = defineModel({ type: Array, required: true })
defineProps({ depth: { type: Number, default: 0 } })
const emit = defineEmits(['edit', 'remove', 'add-child', 'changed'])

const ROLE_TONE = { admin: 'rose', manager: 'violet', employee: 'primary' }
</script>

<template>
  <VueDraggable
    v-model="list"
    group="sidebar"
    :force-fallback="true"
    :fallback-tolerance="3"
    handle=".drag-handle"
    :animation="160"
    ghost-class="opacity-40"
    class="space-y-1.5"
    :class="depth > 0 && 'min-h-10 rounded-xl border border-dashed border-line p-1.5'"
    @end="emit('changed')"
    @add="emit('changed')"
  >
    <div v-for="item in list" :key="item.id" class="rounded-2xl border border-line bg-surface-strong/40" :class="!item.is_active && 'opacity-55'">
      <div class="flex items-center gap-2 px-2 py-2">
        <button type="button" class="drag-handle cursor-grab touch-none rounded-lg p-1.5 text-muted hover:bg-surface-hover active:cursor-grabbing" :aria-label="`Drag ${item.name || 'divider'}`">
          <GripVertical class="h-4 w-4" />
        </button>
        <span v-if="item.type === 'divider'" class="flex flex-1 items-center gap-2 text-xs text-muted"><Minus class="h-4 w-4" /> Divider</span>
        <template v-else>
          <span class="grid h-8 w-8 shrink-0 place-items-center rounded-xl" :class="item.type === 'group' ? 'bg-accent/15 text-accent' : 'bg-surface-hover text-muted'">
            <component :is="iconFor(item.icon)" class="h-4 w-4" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-1.5 truncate text-sm font-medium">
              {{ item.name }}
              <EyeOff v-if="!item.is_active" class="h-3.5 w-3.5 text-muted" />
              <ExternalLink v-if="item.type === 'link'" class="h-3 w-3 text-muted" />
            </p>
            <p class="truncate text-xs text-muted">{{ item.type === 'group' ? `Group · ${item.children?.length || 0} item(s)` : item.route || item.url }}</p>
          </div>
        </template>
        <div class="hidden gap-1 md:flex">
          <AppBadge v-for="r in item.visible_roles" :key="r" :tone="ROLE_TONE[r]">{{ r }}</AppBadge>
        </div>
        <div class="flex shrink-0">
          <button v-if="item.type === 'group'" type="button" class="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-ink" :aria-label="`Add item to ${item.name}`" @click="emit('add-child', item)"><Plus class="h-4 w-4" /></button>
          <button type="button" class="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-ink" :aria-label="`Edit ${item.name || 'divider'}`" @click="emit('edit', item)"><Pencil class="h-4 w-4" /></button>
          <button type="button" class="rounded-lg p-1.5 text-muted hover:bg-danger/10 hover:text-danger" :aria-label="`Delete ${item.name || 'divider'}`" @click="emit('remove', item)"><Trash2 class="h-4 w-4" /></button>
        </div>
      </div>
      <div v-if="item.type === 'group'" class="px-2 pb-2 pl-6 sm:pl-10">
        <SidebarTreeEditor
          v-model="item.children"
          :depth="depth + 1"
          @edit="emit('edit', $event)"
          @remove="emit('remove', $event)"
          @add-child="emit('add-child', $event)"
          @changed="emit('changed')"
        />
      </div>
    </div>
  </VueDraggable>
</template>
