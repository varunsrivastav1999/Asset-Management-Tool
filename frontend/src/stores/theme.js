import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

const KEY = 'ams-theme'

function readStored() {
  try {
    return localStorage.getItem(KEY) || 'system'
  } catch {
    return 'system'
  }
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref(readStored()) // 'light' | 'dark' | 'system'
  const media = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null
  const systemDark = ref(media?.matches ?? true)
  media?.addEventListener?.('change', (e) => (systemDark.value = e.matches))

  const isDark = computed(() => (mode.value === 'system' ? systemDark.value : mode.value === 'dark'))

  function apply() {
    document.documentElement.classList.toggle('dark', isDark.value)
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', isDark.value ? '#060912' : '#eef2f9')
  }

  watch(isDark, apply, { immediate: true })
  watch(mode, (m) => {
    try {
      localStorage.setItem(KEY, m)
    } catch {
      /* private mode */
    }
  })

  function setMode(m) {
    mode.value = m
  }
  function toggle() {
    mode.value = isDark.value ? 'light' : 'dark'
  }

  return { mode, isDark, setMode, toggle }
})
