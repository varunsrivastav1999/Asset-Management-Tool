import { defineStore } from 'pinia'
import { ref } from 'vue'
import { parseError } from '@/api/http'

let seq = 0

export const useUiStore = defineStore('ui', () => {
  const toasts = ref([])
  const confirmState = ref(null)
  const sidebarCollapsed = ref(false)

  function toast(message, { type = 'info', title = '', timeout = 4500, action = null } = {}) {
    const id = ++seq
    toasts.value.push({ id, message, type, title, action })
    if (toasts.value.length > 5) toasts.value.shift()
    if (timeout) setTimeout(() => dismiss(id), timeout)
    return id
  }
  const success = (m, o) => toast(m, { ...o, type: 'success' })
  const error = (m, o) => toast(m, { timeout: 7000, ...o, type: 'error' })
  const warning = (m, o) => toast(m, { ...o, type: 'warning' })

  function dismiss(id) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  /**
   * Promise-based confirmation: `if (await ui.confirm({...})) …`.
   * With `action`, the dialog stays open showing a spinner while the async action runs; it resolves with the
   * action's result on success, keeps the dialog open with the error on failure, and resolves `false` on cancel.
   */
  function confirm({ title = 'Are you sure?', message = '', confirmText = 'Confirm', danger = false, input = null, action = null } = {}) {
    if (confirmState.value) confirmState.value.resolve(false)
    return new Promise((resolve) => {
      confirmState.value = { title, message, confirmText, danger, input, action, value: '', loading: false, error: '', resolve }
    })
  }
  async function acceptConfirm() {
    const state = confirmState.value
    if (!state || state.loading) return
    const payload = state.input ? { value: state.value } : true
    if (!state.action) {
      confirmState.value = null
      state.resolve(payload)
      return
    }
    state.loading = true
    state.error = ''
    try {
      const result = await state.action(payload)
      confirmState.value = null
      state.resolve(result ?? true)
    } catch (e) {
      state.loading = false
      state.error = parseError(e).message
    }
  }
  function resolveConfirm(result) {
    const state = confirmState.value
    if (state?.loading) return
    confirmState.value = null
    state?.resolve(result)
  }

  return { toasts, toast, success, error, warning, dismiss, confirmState, confirm, acceptConfirm, resolveConfirm, sidebarCollapsed }
})
