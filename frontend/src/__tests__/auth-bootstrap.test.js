import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const refreshAccess = vi.fn()
vi.mock('@/api/http', () => ({ refreshAccess: (...a) => refreshAccess(...a), tokenStore: { set: vi.fn(), clear: vi.fn() } }))
vi.mock('@/api', () => ({ authApi: { login: vi.fn(async () => ({ access: 't', user: { id: 1 } })), logout: vi.fn() } }))

import { useAuthStore } from '@/stores/auth'

beforeEach(() => {
  setActivePinia(createPinia())
  refreshAccess.mockReset()
  localStorage.clear()
})

describe('session restore', () => {
  it('skips the refresh call for a first-time visitor (no 401 noise)', async () => {
    const auth = useAuthStore()
    await auth.bootstrap()
    expect(refreshAccess).not.toHaveBeenCalled()
    expect(auth.ready).toBe(true)
    expect(auth.isAuthenticated).toBe(false)
  })

  it('restores the session after a previous sign-in, and forgets it after logout', async () => {
    await useAuthStore().login('a@example.com', 'x')
    setActivePinia(createPinia()) // new page load
    refreshAccess.mockResolvedValue({ user: { id: 1 } })
    const auth = useAuthStore()
    await auth.bootstrap()
    expect(refreshAccess).toHaveBeenCalledTimes(1)
    expect(auth.isAuthenticated).toBe(true)
    await auth.logout()
    setActivePinia(createPinia())
    await useAuthStore().bootstrap()
    expect(refreshAccess).toHaveBeenCalledTimes(1)
  })

  it('drops the hint when the server rejects the cookie', async () => {
    localStorage.setItem('amt.session', '1')
    refreshAccess.mockRejectedValue(new Error('401'))
    await useAuthStore().bootstrap()
    expect(localStorage.getItem('amt.session')).toBeNull()
  })
})
