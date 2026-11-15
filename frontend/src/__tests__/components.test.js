import { describe, expect, it, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import AppPagination from '@/components/ui/AppPagination.vue'
import DataTable from '@/components/ui/DataTable.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

describe('StatusBadge', () => {
  it('renders the label for asset, handover and maintenance statuses', () => {
    expect(mount(StatusBadge, { props: { status: 'in_repair' } }).text()).toBe('In repair')
    expect(mount(StatusBadge, { props: { status: 'pending', kind: 'handover' } }).text()).toBe('Pending sign-off')
    expect(mount(StatusBadge, { props: { status: 'in_progress', kind: 'maintenance' } }).text()).toBe('In progress')
  })
})

describe('AppPagination', () => {
  it('is hidden for a single page and emits page changes', async () => {
    expect(mount(AppPagination, { props: { modelValue: 1, pages: 1 } }).find('nav').exists()).toBe(false)
    const w = mount(AppPagination, { props: { modelValue: 5, pages: 10, count: 250 } })
    const labels = w.findAll('button').map((b) => b.text()).filter(Boolean)
    expect(labels).toEqual(['1', '4', '5', '6', '10'])
    await w.find('[aria-label="Next page"]').trigger('click')
    expect(w.emitted('update:modelValue')[0]).toEqual([6])
  })
})

describe('DataTable', () => {
  it('renders rows, nested keys and toggles selection', async () => {
    const w = mount(DataTable, {
      props: {
        columns: [{ key: 'name', label: 'Name' }, { key: 'owner.name', label: 'Owner' }],
        rows: [{ id: 1, name: 'Laptop', owner: { name: 'Ada' } }, { id: 2, name: 'Chair', owner: null }],
        selectable: true,
        selected: [],
      },
    })
    expect(w.text()).toContain('Laptop')
    expect(w.text()).toContain('Ada')
    await w.find('input[aria-label="Select all"]').trigger('change')
    expect(w.emitted('update:selected')[0]).toEqual([[1, 2]])
  })
})

describe('stores', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('auth role helpers: managers include admins, superusers are admins', () => {
    const auth = useAuthStore()
    auth.setUser({ role: 'manager' })
    expect(auth.isManager).toBe(true)
    expect(auth.isAdmin).toBe(false)
    expect(auth.hasRole('manager')).toBe(true)
    expect(auth.hasRole('admin')).toBe(false)
    auth.setUser({ role: 'employee', is_superuser: true })
    expect(auth.isAdmin).toBe(true)
    auth.setUser({ role: 'employee' })
    expect(auth.hasRole('manager')).toBe(false)
    expect(auth.hasRole()).toBe(true)
  })

  it('ui confirm resolves with the user choice and toasts are capped', async () => {
    const ui = useUiStore()
    const p = ui.confirm({ title: 'Delete?' })
    expect(ui.confirmState.title).toBe('Delete?')
    ui.resolveConfirm(true)
    await expect(p).resolves.toBe(true)
    for (let i = 0; i < 8; i++) ui.toast(`t${i}`, { timeout: 0 })
    expect(ui.toasts).toHaveLength(5)
    expect(ui.toasts.at(-1).message).toBe('t7')
  })
})
