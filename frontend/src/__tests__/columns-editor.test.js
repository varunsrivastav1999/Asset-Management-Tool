import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { api } = vi.hoisted(() => ({ api: { listColumns: vi.fn(), createColumn: vi.fn(), updateColumn: vi.fn(), deleteColumn: vi.fn() } }))
vi.mock('@/api', () => ({ tablesApi: api }))
vi.mock('@/api/http', () => ({ parseError: (e) => ({ message: e?.message || 'x', fields: e?.fields || {} }) }))

import TableColumnsEditor from '@/components/settings/TableColumnsEditor.vue'
import ConfirmHost from '@/components/ui/ConfirmHost.vue'

const cols = [
  { id: 1, key: 'sno', name: 'S.No', type: 'auto_number', is_builtin: true },
  { id: 2, key: 'code', name: 'Code', type: 'text', is_builtin: true },
  { id: 3, key: 'name', name: 'Name', type: 'text', is_builtin: false },
  { id: 4, key: 'qty', name: 'Qty', type: 'number', is_builtin: false },
]
let wrappers = []
const mountIt = (c, opts) => {
  const w = mount(c, { attachTo: document.body, ...opts })
  wrappers.push(w)
  return w
}
beforeEach(() => {
  setActivePinia(createPinia())
  Object.values(api).forEach((f) => f.mockReset())
  api.listColumns.mockResolvedValue(cols.map((c) => ({ ...c })))
})
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers = []
  document.body.innerHTML = ''
})

describe('columns of an existing table', () => {
  it('lists columns; built-ins are locked, custom ones can be deleted', async () => {
    const w = mountIt(TableColumnsEditor, { props: { item: 9 } })
    await flushPromises()
    expect(api.listColumns).toHaveBeenCalledWith(9)
    expect(w.findAll('li')).toHaveLength(3) // S.No is not editable here
    expect(w.find('[aria-label="Delete column Code"]').exists()).toBe(false)
    expect(w.find('[aria-label="Delete column Name"]').exists()).toBe(true)
  })

  it('adds a column (status with its options) and tells the dialog', async () => {
    api.createColumn.mockResolvedValue({ id: 5, key: 'state', name: 'State', type: 'status', is_builtin: false })
    const w = mountIt(TableColumnsEditor, { props: { item: 9 } })
    await flushPromises()
    await w.find('input[aria-label="New column name"]').setValue('State')
    await w.find('select[aria-label="New column type"]').setValue('status')
    await w.find('input[aria-label="Statuses"]').setValue('New, Used')
    await w.findAll('button').find((b) => b.text() === 'Add column').trigger('click')
    await flushPromises()
    expect(api.createColumn).toHaveBeenCalledWith(expect.objectContaining({ sidebar_item: 9, name: 'State', type: 'status', options: ['New', 'Used'] }))
    expect(w.findAll('li')).toHaveLength(4)
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('renames on blur and deletes after confirming', async () => {
    mountIt(ConfirmHost)
    api.updateColumn.mockResolvedValue({ ...cols[3], name: 'Quantity' })
    api.deleteColumn.mockResolvedValue('')
    const w = mountIt(TableColumnsEditor, { props: { item: 9 } })
    await flushPromises()
    const input = w.find('input[aria-label="Name of column Qty"]')
    await input.setValue('Quantity')
    await input.trigger('blur')
    await flushPromises()
    expect(api.updateColumn).toHaveBeenCalledWith(4, { name: 'Quantity' })
    await w.find('[aria-label="Delete column Name"]').trigger('click')
    await flushPromises()
    expect(api.deleteColumn).not.toHaveBeenCalled()
    document.body.querySelector('[data-testid="confirm-dialog"] [data-confirm]').click()
    await flushPromises()
    expect(api.deleteColumn).toHaveBeenCalledWith(3)
    expect(w.find('[aria-label="Delete column Name"]').exists()).toBe(false)
  })
})
