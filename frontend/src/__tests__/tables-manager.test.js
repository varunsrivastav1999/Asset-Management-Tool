import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { api, push } = vi.hoisted(() => ({
  api: { list: vi.fn(), remove: vi.fn(), deleteCheck: vi.fn(), create: vi.fn(), update: vi.fn() },
  push: vi.fn(),
}))
vi.mock('@/api', () => ({ definitionsApi: api, sidebarApi: { tree: vi.fn(async () => ({ items: [] })) } }))
vi.mock('@/api/http', () => ({ parseError: (e) => ({ message: e?.message || 'failed', fields: {} }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ query: {} }) }))
vi.mock('@/stores/sidebar', () => ({ useSidebarStore: () => ({ load: vi.fn(async () => {}) }) }))

import TablesManager from '@/components/settings/TablesManager.vue'
import ConfirmHost from '@/components/ui/ConfirmHost.vue'

const keys = { id: 7, name: 'Keys', singular: 'Key', source: 'custom', row_count: 0, route: '/t/keys', roles: ['admin'], icon: 'list' }
const full = { ...keys, id: 8, name: 'Busy', route: '/t/busy', row_count: 3 }
const dialog = () => document.body.querySelector('[data-testid="confirm-dialog"]')

let wrappers = []
const mountIt = (c, opts = {}) => {
  const w = mount(c, { attachTo: document.body, ...opts })
  wrappers.push(w)
  return w
}
beforeEach(() => {
  setActivePinia(createPinia())
  Object.values(api).forEach((f) => f.mockReset())
  push.mockReset()
})
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers = []
  document.body.innerHTML = ''
})

describe('Tables tab: removing tables', () => {
  it('deletes an empty table after confirming, then refreshes the list and tells the menu', async () => {
    mountIt(ConfirmHost)
    api.list.mockResolvedValueOnce([keys]).mockResolvedValueOnce([])
    api.deleteCheck.mockResolvedValue({ can_delete: true, reason: null, row_count: 0 })
    api.remove.mockResolvedValue('') // 204
    const w = mountIt(TablesManager)
    await flushPromises()
    await w.find('[aria-label="Delete Keys"]').trigger('click')
    await flushPromises()
    expect(dialog().textContent).toContain('Delete the table “Keys”?')
    expect(api.remove).not.toHaveBeenCalled()
    dialog().querySelector('[data-confirm]').click()
    await flushPromises()
    expect(api.remove).toHaveBeenCalledWith(7)
    expect(w.text()).not.toContain('Keys') // gone from the list without a reload
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('a table with rows is not deleted; the dialog offers to open it instead', async () => {
    mountIt(ConfirmHost)
    api.list.mockResolvedValue([full])
    api.deleteCheck.mockResolvedValue({ can_delete: false, reason: '“Busy” still has 3 record(s).', row_count: 3 })
    const w = mountIt(TablesManager)
    await flushPromises()
    await w.find('[aria-label="Delete Busy"]').trigger('click')
    await flushPromises()
    expect(dialog().textContent).toContain('3 record(s)')
    dialog().querySelector('[data-confirm]').click()
    await flushPromises()
    expect(api.remove).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/t/busy')
    expect(w.emitted('changed')).toBeUndefined()
  })

  it('keeps the dialog open with the server message when deletion is refused', async () => {
    mountIt(ConfirmHost)
    api.list.mockResolvedValue([keys])
    api.deleteCheck.mockResolvedValue({ can_delete: true, reason: null, row_count: 0 })
    api.remove.mockRejectedValue(new Error('Someone just added a row'))
    const w = mountIt(TablesManager)
    await flushPromises()
    await w.find('[aria-label="Delete Keys"]').trigger('click')
    await flushPromises()
    dialog().querySelector('[data-confirm]').click()
    await flushPromises()
    expect(dialog().textContent).toContain('Someone just added a row')
    expect(w.text()).toContain('Keys')
  })
})
