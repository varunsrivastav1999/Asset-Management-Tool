import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { recordLookup, assetLookup, blobUrl, downloadFile } = vi.hoisted(() => ({
  recordLookup: vi.fn(),
  assetLookup: vi.fn(),
  blobUrl: vi.fn(async (p) => `blob:${p}`),
  downloadFile: vi.fn(async () => {}),
}))
vi.mock('@/api', () => ({ recordsApi: { lookup: (...a) => recordLookup(...a) }, assetsApi: { lookup: (...a) => assetLookup(...a) } }))
vi.mock('@/api/http', () => ({ blobUrl: (...a) => blobUrl(...a), downloadFile: (...a) => downloadFile(...a), parseError: (e) => ({ message: e?.message || 'x' }) }))

import { resolveScan } from '@/utils/scan'
import CodesDialog from '@/components/codes/CodesDialog.vue'

const notFound = () => Object.assign(new Error('nf'), { response: { status: 404 } })
const row = { id: 9, code: 'LIC-00012', route: '/t/licences' }

beforeEach(() => {
  setActivePinia(createPinia())
  ;[recordLookup, assetLookup, blobUrl, downloadFile].forEach((f) => f.mockClear())
  recordLookup.mockReset()
  assetLookup.mockReset()
})
afterEach(() => (document.body.innerHTML = ''))

describe('resolveScan', () => {
  it('opens a table row from its QR link or its code', async () => {
    recordLookup.mockResolvedValue(row)
    await expect(resolveScan('https://192.168.1.45:2025/r/LIC-00012')).resolves.toEqual({ path: '/t/licences', query: { open: 'LIC-00012' } })
    await expect(resolveScan('lic-00012')).resolves.toEqual({ path: '/t/licences', query: { open: 'LIC-00012' } })
    expect(assetLookup).not.toHaveBeenCalled()
  })

  it('still opens assets, and falls back between kinds on "not found"', async () => {
    assetLookup.mockResolvedValue({ id: 4 })
    await expect(resolveScan('SN-ABC-123')).resolves.toBe('/assets/4')
    recordLookup.mockRejectedValue(notFound())
    await expect(resolveScan('AST-00004')).resolves.toBe('/assets/4') // looked like a row code, was an asset
    assetLookup.mockRejectedValue(notFound())
    await expect(resolveScan('NOPE')).rejects.toMatchObject({ response: { status: 404 } })
  })
})

describe('CodesDialog', () => {
  it('shows the QR and barcode, and downloads / prints them', async () => {
    const printLabel = vi.fn(async () => {})
    mount(CodesDialog, {
      attachTo: document.body,
      props: { open: true, code: 'LIC-00012', title: 'LIC-00012 · Office', qrPath: '/records/9/qr/', barcodePath: '/records/9/barcode/', params: { table_item: 3 }, printLabel },
    })
    await flushPromises()
    expect(blobUrl).toHaveBeenCalledWith('/records/9/qr/', { table_item: 3 })
    expect(blobUrl).toHaveBeenCalledWith('/records/9/barcode/', { table_item: 3 })
    const dialog = document.body.querySelector('[data-testid="codes-dialog"]')
    expect(dialog.querySelector('img[alt="QR code"]').getAttribute('src')).toBe('blob:/records/9/qr/')
    const click = (label) => [...document.body.querySelectorAll('button')].find((b) => b.textContent.trim() === label).click()
    click('Download QR')
    expect(downloadFile).toHaveBeenCalledWith('/records/9/qr/', { params: { table_item: 3, fmt: 'png' }, filename: 'LIC-00012-qr.png' })
    click('Print label')
    await flushPromises()
    expect(printLabel).toHaveBeenCalledOnce()
  })
})
