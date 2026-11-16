import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h, ref } from 'vue'

vi.mock('@/api/http', () => ({ http: { post: vi.fn(), get: vi.fn() }, downloadFile: vi.fn(), parseError: () => ({ message: 'x' }) }))

import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import { TABLE_LAYOUT } from '@/composables/useTableConfig'

const columns = [
  { key: 'sno', name: 'S.No', type: 'auto_number', is_builtin: true },
  { key: 'name', name: 'Name', type: 'text', is_builtin: false },
  { key: 'code', name: 'Code', type: 'text', is_builtin: true },
  { key: 'state', name: 'State', type: 'status', options: ['Open', 'Done'], is_builtin: false },
  { key: 'qty', name: 'Qty', type: 'number', is_builtin: false },
]
const rows = [{ id: 1, code: 'TIC-00001', custom_data: { name: 'Printer', state: 'Open', qty: 2 } }]

const mountWith = (layout) => {
  setActivePinia(createPinia())
  return mount(ConfigurableTable, {
    props: { columns, rows, extraColumns: [{ key: '_actions', label: '' }] },
    slots: { 'cell-_actions': ({ row }) => h('button', { 'aria-label': `Edit ${row.code}` }, 'Edit') },
    global: { provide: { [TABLE_LAYOUT]: ref(layout) } },
  })
}

describe('Display as: Cards', () => {
  it('renders each row as a card with title, code, badges, fields and actions', () => {
    const w = mountWith('cards')
    const card = w.find('[data-testid="row-cards"] article')
    expect(card.exists()).toBe(true)
    expect(w.find('table').exists()).toBe(false)
    expect(card.find('.text-base').text()).toBe('Printer') // first text column is the title
    expect(card.text()).toContain('TIC-00001')
    expect(card.text()).toContain('Open') // status as a badge
    expect(card.find('dl').text()).toContain('Qty')
    expect(card.find('[aria-label="Edit TIC-00001"]').exists()).toBe(true)
    expect(card.text()).not.toContain('S.No')
  })

  it('stays a table by default', () => {
    const w = mountWith('table')
    expect(w.find('table').exists()).toBe(true)
    expect(w.find('[data-testid="row-cards"]').exists()).toBe(false)
  })
})
