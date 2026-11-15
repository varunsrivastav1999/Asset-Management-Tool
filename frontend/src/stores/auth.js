import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api'
import { refreshAccess, tokenStore } from '@/api/http'

// Non-secret hint that a refresh cookie may exist, so first-time visitors don't trigger a guaranteed-401
// refresh call. The cookie itself stays HttpOnly; the server remains the only authority.
const HINT = 'amt.session'
const hint = {
  get: () => {
    try {
      return localStorage.getItem(HINT) === '1'
    } catch {
      return true // storage blocked: fall back to always trying
    }
  },
  set: (on) => {
    try {
      on ? localStorage.setItem(HINT, '1') : localStorage.removeItem(HINT)
    } catch {
      /* storage unavailable */
    }
  },
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const ready = ref(false)
  let bootPromise = null

  const isAuthenticated = computed(() => !!user.value)
  const role = computed(() => (user.value?.is_superuser ? 'admin' : user.value?.role))
  const isAdmin = computed(() => role.value === 'admin')
  const isManager = computed(() => role.value === 'admin' || role.value === 'manager')

  /** Restore a session from the refresh cookie (once per page load). */
  function bootstrap() {
    if (!bootPromise) {
      bootPromise = (hint.get() ? refreshAccess() : Promise.reject(new Error('no session')))
        .then((data) => {
          user.value = data.user
          hint.set(true)
        })
        .catch(() => {
          user.value = null
          hint.set(false)
        })
        .finally(() => {
          ready.value = true
        })
    }
    return bootPromise
  }

  async function login(email, password) {
    const data = await authApi.login(email, password)
    tokenStore.set(data.access)
    user.value = data.user
    ready.value = true
    hint.set(true)
    return data.user
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      /* already logged out server-side */
    }
    clearSession()
  }

  function clearSession() {
    tokenStore.clear()
    user.value = null
    hint.set(false)
  }

  async function refreshProfile() {
    user.value = await authApi.me()
  }

  function setUser(u) {
    user.value = u
  }

  function hasRole(...roles) {
    if (!roles.length) return true
    if (roles.includes('manager') && isManager.value) return true
    return roles.includes(role.value)
  }

  return { user, ready, isAuthenticated, role, isAdmin, isManager, bootstrap, login, logout, clearSession, refreshProfile, setUser, hasRole }
})
