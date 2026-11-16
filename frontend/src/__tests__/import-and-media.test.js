import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { upload, get } = vi.hoisted(() => ({ upload: vi.fn(), get: vi.fn() }))
vi.mock('@/api', () => ({ mediaApi: { upload: (...a) => upload(...a), url: (id) => `/table-media/${id}/` } }))
vi.mock('@/api/http', () => ({
  http: { get: (...a) => get(...a) },
  downloadFile: vi.fn(async () => {}),
  parseError: (e) => ({ message: e?.message || 'failed', fields: {} }),
}))

import ImportDialog from '@/components/ui/ImportDialog.vue'
import MediaInput from '@/components/table/MediaInput.vue'
import MediaValue from '@/components/table/MediaValue.vue'
import { COLUMN_TYPES } from '@/utils/columnTypes'

let wrappers = []
const mountIt = (c, opts) => {
  const w = mount(c, { attachTo: document.body, ...opts })
  wrappers.push(w)
  return w
}
beforeEach(() => {
  setActivePinia(createPinia())
  upload.mockReset()
  get.mockReset()
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview')
})
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers = []
  document.body.innerHTML = ''
})

// Dialogs are teleported to <body>, so look the input up in the document.
const pickFile = async (_w, selector, file) => {
  const input = document.body.querySelector(selector)
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  input.dispatchEvent(new Event('change'))
  await flushPromises()
}

describe('ImportDialog', () => {
  const file = new File(['Product\nOffice\n'], 'rows.csv', { type: 'text/csv' })

  it('validates first, shows row errors, and blocks import until fixed', async () => {
    const importFn = vi.fn().mockRejectedValue({ response: { status: 400, data: { errors: [{ row: 3, errors: { Seats: 'Invalid value for “Seats”.' } }], created: 0 } } })
    const w = mountIt(ImportDialog, { props: { open: true, title: 'Import licences', importFn } })
    await flushPromises()
    await pickFile(w, 'input[type=file]', file)
    document.body.querySelectorAll('button').forEach((b) => b.textContent.trim() === 'Validate' && b.click())
    await flushPromises()
    expect(importFn).toHaveBeenCalledWith(file, true)
    const report = document.body.querySelector('[data-testid="import-report"]').textContent
    expect(report).toContain('Row 3')
    expect(report).toContain('Seats')
    const importBtn = [...document.body.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Import')
    expect(importBtn.disabled).toBe(true)
  })

  it('imports after a clean validation and tells the page to reload', async () => {
    const importFn = vi.fn().mockResolvedValueOnce({ created: 2, total: 2, errors: [], ignored_columns: ['Notes'] }).mockResolvedValueOnce({ created: 2, total: 2, errors: [] })
    const w = mountIt(ImportDialog, { props: { open: true, title: 'Import licences', importFn, noun: 'licences' } })
    await flushPromises()
    await pickFile(w, 'input[type=file]', file)
    const click = (label) => [...document.body.querySelectorAll('button')].find((b) => b.textContent.trim() === label).click()
    click('Validate')
    await flushPromises()
    expect(document.body.textContent).toContain('Ready: 2 to create')
    expect(document.body.textContent).toContain('Ignored columns')
    click('Import')
    await flushPromises()
    expect(importFn).toHaveBeenLastCalledWith(file, false)
    expect(w.emitted('imported')).toHaveLength(1)
  })
})

describe('Media column', () => {
  it('offers Media in the column types', () => {
    expect(COLUMN_TYPES.find((t) => t.value === 'media')).toBeTruthy()
  })

  it('uploads a file and sets the cell value', async () => {
    const value = { id: 'a1b2', name: 'receipt.pdf', type: 'application/pdf', size: 1200 }
    upload.mockResolvedValue(value)
    const w = mountIt(MediaInput, { props: { item: 7, column: 'proof', modelValue: null } })
    await pickFile(w, '[data-testid="media-file"]', new File(['%PDF'], 'receipt.pdf'))
    expect(upload).toHaveBeenCalledWith(7, 'proof', expect.any(File))
    expect(w.emitted('update:modelValue')[0]).toEqual([value])
  })

  it('shows a private photo as a thumbnail fetched with the login, other files by name', async () => {
    get.mockResolvedValue({ data: new Blob(['x']) })
    const photo = mountIt(MediaValue, { props: { value: { id: 'p1', name: 'desk.jpg', type: 'image/jpeg' } } })
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/table-media/p1/', { responseType: 'blob' })
    expect(photo.find('img').attributes('src')).toBe('blob:preview')
    const doc = mountIt(MediaValue, { props: { value: { id: 'd1', name: 'manual.pdf', type: 'application/pdf' } } })
    expect(doc.find('img').exists()).toBe(false)
    expect(doc.text()).toContain('manual.pdf')
  })
})
