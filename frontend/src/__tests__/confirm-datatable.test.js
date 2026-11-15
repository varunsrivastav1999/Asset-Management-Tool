import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, ref } from 'vue'

const post = vi.fn()
const downloadFile = vi.fn(async () => {})
vi.mock('@/api/http', () => ({
  http: { post: (...a) => post(...a) },
  downloadFile: (...a) => downloadFile(...a),
  parseError: (e) => ({ message: e?.message || 'failed', fields: {} }),
}))

import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import ConfirmHost from '@/components/ui/ConfirmHost.vue'
import AppModal from '@/components/ui/AppModal.vue'
import ConfigurableTable from '@/components/table/ConfigurableTable.vue'
import { useUiStore } from '@/stores/ui'
import { openCount } from '@/composables/modalStack'

const esc = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
const dialog = () => document.body.querySelector('[data-testid="confirm-dialog"]')

let wrappers = []
const mountAttached = (comp, opts) => {
  const w = mount(comp, { attachTo: document.body, ...opts })
  wrappers.push(w)
  return w
}

beforeEach(() => {
  setActivePinia(createPinia())
  post.mockReset()
  downloadFile.mockClear()
})
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers = []
  document.body.innerHTML = ''
  document.body.style.overflow = ''
})

describe('ConfirmDialog', () => {
  it('teleports to <body> above everything, shows the text and emits confirm/cancel', async () => {
    const w = mountAttached(ConfirmDialog, { props: { open: true, title: 'Delete 5 assets?', message: 'This cannot be undone.', confirmText: 'Delete 5', danger: true } })
    await nextTick()
    const d = dialog()
    expect(d).toBeTruthy()
    expect(w.element.contains?.(d) ?? false).toBe(false) // rendered outside the component tree (teleported)
    expect(document.body.contains(d)).toBe(true)
    expect(d.style.zIndex).toBe('200')
    expect(d.textContent).toContain('Delete 5 assets?')
    expect(d.textContent).toContain('This cannot be undone.')
    // Destructive dialogs focus the safe choice.
    expect(document.activeElement.textContent.trim()).toBe('Cancel')
    d.querySelector('[data-confirm]').click()
    expect(w.emitted('confirm')).toHaveLength(1)
    esc()
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('locks interaction while loading', async () => {
    const w = mountAttached(ConfirmDialog, { props: { open: true, loading: true } })
    await nextTick()
    const buttons = [...dialog().querySelectorAll('button')]
    expect(buttons.every((b) => b.disabled)).toBe(true)
    expect(dialog().querySelector('[data-confirm]').getAttribute('aria-busy')).toBe('true')
    esc()
    expect(w.emitted('cancel')).toBeUndefined()
  })

  it('traps focus inside the card', async () => {
    mountAttached(ConfirmDialog, { props: { open: true, danger: true } })
    await nextTick()
    const [cancel, confirm] = dialog().querySelectorAll('button')
    confirm.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(cancel)
  })
})

describe('overlay stacking (the original bug)', () => {
  it('shows the confirm above an open modal; Esc closes only the top layer; scroll lock is restored', async () => {
    const Page = defineComponent({
      setup() {
        const open = ref(true)
        return () => [h(AppModal, { open: open.value, 'onUpdate:open': (v) => (open.value = v), title: 'Edit category' }, () => h('p', 'form')), h(ConfirmHost)]
      },
    })
    mountAttached(Page)
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')
    const modalLayer = document.body.querySelector('[role="dialog"]').closest('.fixed')
    const ui = useUiStore()
    const answer = ui.confirm({ title: 'Delete category?', danger: true })
    await nextTick()
    await nextTick()
    expect(Number(dialog().style.zIndex)).toBeGreaterThan(Number(modalLayer.style.zIndex))
    expect(openCount()).toBe(2)

    esc()
    await expect(answer).resolves.toBe(false)
    await nextTick()
    await nextTick()
    expect(document.body.querySelector('[role="dialog"]')).toBeTruthy() // edit modal still open
    expect(document.body.style.overflow).toBe('hidden')

    esc() // now the modal is on top
    await nextTick()
    await nextTick()
    expect(openCount()).toBe(0)
    expect(document.body.style.overflow).toBe('')
  })
})

describe('ui.confirm with an async action', () => {
  it('shows a spinner, resolves with the result, and keeps the dialog open on error', async () => {
    mountAttached(ConfirmHost)
    const ui = useUiStore()
    let finish
    const p = ui.confirm({ title: 'Delete?', action: () => new Promise((r) => (finish = r)) })
    await nextTick()
    ui.acceptConfirm()
    await nextTick()
    expect(ui.confirmState.loading).toBe(true)
    finish({ deleted: 3 })
    await expect(p).resolves.toEqual({ deleted: 3 })
    expect(ui.confirmState).toBeNull()

    const p2 = ui.confirm({ title: 'Delete?', action: () => Promise.reject(new Error('Server says no')) })
    await nextTick()
    await ui.acceptConfirm()
    expect(ui.confirmState.error).toBe('Server says no')
    expect(ui.confirmState.loading).toBe(false)
    ui.resolveConfirm(false)
    await expect(p2).resolves.toBe(false)
  })
})

describe('ui.confirm after a DELETE (204, empty body)', () => {
  it.each([[''], [undefined], [null]])('resolves truthy when the action returns %j so the caller refreshes', async (body) => {
    mountAttached(ConfirmHost)
    const ui = useUiStore()
    const p = ui.confirm({ title: 'Delete?', danger: true, action: async () => body })
    await nextTick()
    await ui.acceptConfirm()
    await expect(p).resolves.toBe(true)
    expect(ui.confirmState).toBeNull()
  })

  it('still resolves false on cancel', async () => {
    mountAttached(ConfirmHost)
    const ui = useUiStore()
    const action = vi.fn()
    const p = ui.confirm({ title: 'Delete?', action })
    await nextTick()
    ui.resolveConfirm(false)
    await expect(p).resolves.toBe(false)
    expect(action).not.toHaveBeenCalled()
  })
})

describe('ConfigurableTable bulk actions', () => {
  const columns = [
    { key: 'sno', name: 'S.No', type: 'auto_number', is_builtin: true },
    { key: 'name', name: 'Item', type: 'text', is_builtin: true },
  ]
  const rows = [
    { id: 1, name: 'Laptop' },
    { id: 2, name: 'Chair' },
  ]
  const bulk = (over = {}) => ({
    resource: '/assets',
    params: () => ({ search: 'x', table_item: 3, page: 2, page_size: 25, with_columns: 1 }),
    count: 60,
    singular: 'Asset',
    plural: 'Assets',
    canDelete: true,
    canExport: true,
    statusOptions: [{ value: 'retired', label: 'Retired' }],
    ...over,
  })

  it('renders checkboxes, the bulk bar and "select all N results"', async () => {
    const w = mountAttached(ConfigurableTable, { props: { columns, rows, bulk: bulk() } })
    expect(w.findAll('tbody input[type=checkbox]')).toHaveLength(2)
    await w.find('input[aria-label="Select all"]').trigger('change')
    expect(w.text()).toContain('2 assets selected')
    expect(w.text()).toContain('Select all 60 assets')
    await w.findAll('button').find((b) => b.text() === 'Select all 60 assets').trigger('click')
    expect(w.text()).toContain('60 assets selected')
  })

  it('bulk delete confirms with the count, sends one call, reports skipped rows and refreshes', async () => {
    mountAttached(ConfirmHost)
    const w = mountAttached(ConfigurableTable, { props: { columns, rows, bulk: bulk(), selected: [1, 2], 'onUpdate:selected': (v) => w.setProps({ selected: v }) } })
    post.mockResolvedValue({ data: { deleted: 1, deleted_ids: [1], skipped: [{ id: 2, label: 'Chair', reason: 'Assigned' }], verb: 'deleted' } })
    await w.findAll('button').find((b) => b.text() === 'Delete').trigger('click')
    await nextTick()
    expect(dialog().textContent).toContain('Delete 2 assets?')
    expect(post).not.toHaveBeenCalled() // nothing happens before confirming
    dialog().querySelector('[data-confirm]').click()
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/assets/bulk-delete/', { ids: [1, 2] }, { params: { search: 'x', table_item: 3 } })
    const ui = useUiStore()
    expect(ui.toasts.map((t) => t.message).join(' ')).toContain('Chair: Assigned')
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('"select all N" bulk delete sends all:true with the current filters', async () => {
    mountAttached(ConfirmHost)
    const w = mountAttached(ConfigurableTable, { props: { columns, rows, bulk: bulk() } })
    post.mockResolvedValue({ data: { deleted: 60, skipped: [] } })
    await w.find('input[aria-label="Select all"]').trigger('change')
    await w.findAll('button').find((b) => b.text() === 'Select all 60 assets').trigger('click')
    await w.findAll('button').find((b) => b.text() === 'Delete').trigger('click')
    await nextTick()
    expect(dialog().textContent).toContain('Delete 60 assets?')
    dialog().querySelector('[data-confirm]').click()
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/assets/bulk-delete/', { all: true }, { params: { search: 'x', table_item: 3 } })
  })

  it('exports selected rows / all rows as CSV with the right scope', async () => {
    const w = mountAttached(ConfigurableTable, { props: { columns, rows, bulk: bulk(), selected: [2] } })
    await w.findAll('button').find((b) => b.text() === 'Export CSV').trigger('click')
    expect(downloadFile).toHaveBeenLastCalledWith('/assets/export-table/', { params: { search: 'x', table_item: 3, file_format: 'csv', scope: 'selected', ids: '2' } })
    await w.findAll('button').find((b) => b.text().startsWith('Export')).trigger('click')
    await w.findAll('button').find((b) => b.text() === 'All assets (CSV)').trigger('click')
    expect(downloadFile).toHaveBeenLastCalledWith('/assets/export-table/', { params: { search: 'x', table_item: 3, file_format: 'csv', scope: 'all' } })
  })

  it('hides bulk features without permission', () => {
    const w = mountAttached(ConfigurableTable, { props: { columns, rows, bulk: null } })
    expect(w.findAll('tbody input[type=checkbox]')).toHaveLength(0)
    expect(w.text()).not.toContain('Export')
  })
})
