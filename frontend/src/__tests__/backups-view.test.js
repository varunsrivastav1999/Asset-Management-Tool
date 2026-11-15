import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const status = vi.fn()
const create = vi.fn()
const remove = vi.fn()
const downloadFile = vi.fn(async () => {})
vi.mock('@/api', () => ({ backupsApi: { status: (...a) => status(...a), create: (...a) => create(...a), remove: (...a) => remove(...a) } }))
vi.mock('@/api/http', () => ({ downloadFile: (...a) => downloadFile(...a), parseError: (e) => ({ message: e?.message || 'failed' }) }))

import BackupsView from '@/views/settings/BackupsView.vue'
import ConfirmHost from '@/components/ui/ConfirmHost.vue'

const base = { service_online: true, pending: 0, schedule: '02:00', keep: 7 }
const files = [{ name: 'manual-20261116-101500.dump', kind: 'manual', size: 2_621_440, created_at: '2026-11-16T10:15:00Z' }]

let wrappers = []
const mountView = (comp) => {
  const w = mount(comp, { attachTo: document.body, global: { stubs: { RouterLink: true } } })
  wrappers.push(w)
  return w
}
beforeEach(() => {
  setActivePinia(createPinia())
  ;[status, create, remove, downloadFile].forEach((f) => f.mockReset())
})
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers = []
  document.body.innerHTML = ''
})

describe('BackupsView', () => {
  it('lists backups with size and service state, and downloads one', async () => {
    status.mockResolvedValue({ ...base, backups: files })
    const w = mountView(BackupsView)
    await flushPromises()
    expect(w.text()).toContain('Running')
    expect(w.text()).toContain('Daily at 02:00')
    expect(w.text()).toContain('2.5 MB')
    await w.find('[aria-label="Download manual-20261116-101500.dump"]').trigger('click')
    expect(downloadFile).toHaveBeenCalledWith('/backups/manual-20261116-101500.dump/', { filename: 'manual-20261116-101500.dump' })
  })

  it('"Back up now" queues a backup', async () => {
    status.mockResolvedValue({ ...base, backups: [] })
    create.mockResolvedValue({ ...base, pending: 1, backups: [] })
    const w = mountView(BackupsView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Back up now').trigger('click')
    await flushPromises()
    expect(create).toHaveBeenCalledOnce()
    expect(w.text()).toContain('Backing up…')
  })

  it('deletes only after confirming, then refreshes', async () => {
    mountView(ConfirmHost)
    status.mockResolvedValue({ ...base, backups: files })
    remove.mockResolvedValue('')
    const w = mountView(BackupsView)
    await flushPromises()
    await w.find('[aria-label="Delete manual-20261116-101500.dump"]').trigger('click')
    await flushPromises()
    expect(remove).not.toHaveBeenCalled()
    document.body.querySelector('[data-testid="confirm-dialog"] [data-confirm]').click()
    await flushPromises()
    expect(remove).toHaveBeenCalledWith('manual-20261116-101500.dump')
    expect(status).toHaveBeenCalledTimes(2)
  })
})
