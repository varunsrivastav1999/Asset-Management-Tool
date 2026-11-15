import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { COLUMN_TYPES, hasOptions, isCustomStatus, parseOptions, statusTone } from '@/utils/columnTypes'
import TableCell from '@/components/table/TableCell.vue'

describe('column types', () => {
  it('offers Status when adding a column', () => {
    expect(COLUMN_TYPES.map((t) => t.value)).toContain('status')
    expect(hasOptions('status') && hasOptions('select') && !hasOptions('text')).toBe(true)
    expect(parseOptions('status', ' Open, , Done ')).toEqual(['Open', 'Done'])
    expect(parseOptions('text', 'a,b')).toEqual([])
  })

  it('colours statuses by meaning, otherwise stably by position', () => {
    expect(statusTone('Done')).toBe('emerald')
    expect(statusTone('In progress')).toBe('amber')
    expect(statusTone('Blocked')).toBe('rose')
    expect(statusTone('Tier A', ['Tier A', 'Tier B'])).not.toBe(statusTone('Tier B', ['Tier A', 'Tier B']))
    expect(statusTone('')).toBe('slate')
  })

  it('renders a custom status as a badge and keeps built-in asset statuses working', () => {
    setActivePinia(createPinia())
    expect(isCustomStatus({ type: 'status', options: ['Open'] })).toBe(true)
    expect(isCustomStatus({ type: 'status', options: { kind: 'asset' } })).toBe(false)
    const custom = mount(TableCell, { props: { col: { key: 'state', type: 'status', options: ['Open', 'Done'] }, row: { custom_data: { state: 'Done' } }, index: 0 } })
    expect(custom.text()).toBe('Done')
    expect(custom.html()).toContain('emerald')
    const builtin = mount(TableCell, { props: { col: { key: 'status', type: 'status', is_builtin: true, options: { kind: 'asset' } }, row: { status: 'in_repair' }, index: 0 } })
    expect(builtin.text()).toMatch(/repair/i)
  })
})
