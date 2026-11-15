import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import TableCell from '@/components/table/TableCell.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import SidebarNav from '@/components/SidebarNav.vue'
import { normalizeHex, withAlpha } from '@/utils/color'

beforeEach(() => setActivePinia(createPinia()))

const router = () => {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }] })
  r.push('/assets')
  return r
}
const col = (over) => ({ key: 'k', name: 'K', type: 'text', is_builtin: true, options: [], ...over })
const cell = (props) => mount(TableCell, { props, global: { plugins: [createPinia()], stubs: { EntityPicker: true } } })

describe('color utils', () => {
  it('validates hex colors and converts to rgba', () => {
    expect(normalizeHex('#10b981')).toBe('#10b981')
    expect(normalizeHex('#abc')).toBe('#abc')
    expect(normalizeHex('red')).toBeNull()
    expect(normalizeHex('javascript:alert(1)')).toBeNull()
    expect(withAlpha('#ff0000', 0.5)).toBe('rgba(255, 0, 0, 0.5)')
    expect(withAlpha('#f00', 1)).toBe('rgba(255, 0, 0, 1)')
    expect(withAlpha('nope', 1)).toBeNull()
  })
})

describe('SidebarNav colors', () => {
  it('applies label, icon and active colors from the DB', async () => {
    const r = router()
    await r.isReady()
    const items = [{ id: 1, type: 'page', name: 'Assets', route: '/assets', icon: 'boxes', color: '#ff0000', icon_color: '#00ff00', active_color: '#0000ff', glow: true }]
    const w = mount(SidebarNav, { props: { items }, global: { plugins: [r] } })
    const link = w.find('a')
    expect(link.attributes('style')).toContain('color: rgb(255, 0, 0)')
    expect(link.attributes('style')).toContain('rgba(0, 0, 255, 0.16)') // active highlight
    expect(link.attributes('style')).toContain('box-shadow') // glow
    expect(w.find('svg').attributes('style')).toContain('color: rgb(0, 255, 0)')
  })

  it('ignores invalid colors instead of injecting them', async () => {
    const r = router()
    await r.isReady()
    const items = [{ id: 1, type: 'page', name: 'X', route: '/x', color: 'url(javascript:1)' }]
    expect(mount(SidebarNav, { props: { items }, global: { plugins: [r] } }).find('a').attributes('style') || '').not.toContain('javascript')
  })
})

describe('TableCell', () => {
  it('renders each column type', () => {
    expect(cell({ col: col({ type: 'auto_number' }), row: {}, index: 2, offset: 25 }).text()).toBe('28')
    expect(cell({ col: col({ type: 'number', options: { format: 'currency' } }), row: { k: '1234.5', currency: 'USD' } }).text()).toContain('$1,234.50')
    expect(cell({ col: col({ type: 'boolean' }), row: { k: true } }).text()).toBe('Yes')
    expect(cell({ col: col({ type: 'status', options: { kind: 'handover' } }), row: { k: 'pending' } }).text()).toBe('Pending sign-off')
    expect(cell({ col: col({ type: 'date', key: 'received_date' }), row: { received_date: '2026-02-03', received_date_by: 'Ada' } }).text()).toContain('by Ada')
    expect(cell({ col: col({ type: 'user', key: 'assigned_to' }), row: { assigned_to: { full_name: 'Eve Employee' } } }).text()).toContain('Eve Employee')
    expect(cell({ col: col({ key: 'category.name' }), row: { category: { name: 'Laptops' } } }).text()).toBe('Laptops')
    expect(cell({ col: col({}), row: {} }).text()).toBe('—')
  })

  it('reads custom columns from custom_data and only links safe files', () => {
    expect(cell({ col: col({ is_builtin: false, key: 'cc' }), row: { custom_data: { cc: 'CC1' } } }).text()).toBe('CC1')
    const f = cell({ col: col({ is_builtin: false, key: 'doc', type: 'file' }), row: { custom_data: { doc: 'https://x.io/a.pdf' } } })
    expect(f.find('a').attributes('rel')).toContain('noopener')
  })

  it('edits custom values inline and saves through the callback', async () => {
    const save = vi.fn(async () => {})
    const row = { id: 7, custom_data: { cc: 'CC1' } }
    const w = cell({ col: col({ is_builtin: false, key: 'cc', type: 'select', options: ['CC1', 'CC2'] }), row, editable: true, save })
    await w.find('div').trigger('click')
    await w.find('select').setValue('CC2')
    await w.find('button[aria-label="Save"]').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith(row, 'cc', 'CC2')
  })

  it('does not allow editing built-in columns', async () => {
    const w = cell({ col: col({ key: 'k' }), row: { k: 'v' }, editable: true, save: vi.fn() })
    await w.find('div').trigger('click')
    expect(w.find('input').exists()).toBe(false)
  })
})

describe('ConfigurableTable', () => {
  it('builds headers from config, sorts sortable columns and honours cell overrides', async () => {
    const columns = [
      col({ key: 'sno', name: 'S.No', type: 'auto_number' }),
      col({ key: 'name', name: 'Item', is_sortable: true }),
      col({ key: 'cc', name: 'Cost centre', is_builtin: false }),
    ]
    const w = mount(ConfigurableTable, {
      props: { columns, rows: [{ id: 1, name: 'Laptop', custom_data: { cc: 'CC9' } }], ordering: '-name' },
      slots: { 'cell-name': '<b class="override">custom {{ params.row.name }}</b>' },
      global: { plugins: [createPinia()] },
    })
    const headers = w.findAll('th').map((t) => t.text())
    expect(headers).toEqual(['S.No', 'Item', 'Cost centre'])
    expect(w.find('th[aria-sort="descending"]').exists()).toBe(true)
    expect(w.find('.override').text()).toBe('custom Laptop')
    expect(w.text()).toContain('CC9')
    await w.find('th button').trigger('click')
    expect(w.emitted('sort')[0]).toEqual(['name'])
  })
})
