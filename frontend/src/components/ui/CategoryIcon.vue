<script setup>
import { computed } from 'vue'
import { Armchair, Box, Camera, Car, Headphones, Keyboard, Lamp, Laptop, Monitor, Printer, Server, Smartphone, Tablet, Truck, Wrench } from 'lucide-vue-next'

const props = defineProps({ name: String, color: String, size: { type: String, default: 'md' } })
const map = { box: Box, laptop: Laptop, monitor: Monitor, smartphone: Smartphone, printer: Printer, armchair: Armchair, car: Car, wrench: Wrench, camera: Camera, server: Server, headphones: Headphones, tablet: Tablet, keyboard: Keyboard, truck: Truck, lamp: Lamp }
const icon = computed(() => map[props.name] || Box)
</script>

<template>
  <span
    class="inline-grid shrink-0 place-items-center rounded-xl"
    :class="size === 'sm' ? 'h-8 w-8' : size === 'lg' ? 'h-14 w-14' : 'h-10 w-10'"
    :style="{ background: `${color || '#10b981'}1f`, color: color || '#10b981', boxShadow: `0 0 24px -10px ${color || '#10b981'}` }"
  >
    <component :is="icon" :class="size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-7 w-7' : 'h-5 w-5'" />
  </span>
</template>
