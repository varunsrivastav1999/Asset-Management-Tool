import { describe, expect, it } from 'vitest'
import { cleanParams, daysUntil, formatDate, formatMoney, initials, timeAgo } from '@/utils/format'

describe('format utils', () => {
  it('treats ISO calendar dates as local dates (no off-by-one)', () => {
    const d = formatDate('2026-01-15')
    expect(d).toMatch(/15/)
    expect(d).toMatch(/2026/)
  })

  it('returns fallbacks for empty or invalid values', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('not a date')).toBe('—')
    expect(formatMoney('')).toBe('—')
    expect(timeAgo(undefined)).toBe('—')
  })

  it('formats money and falls back on unknown currency codes', () => {
    expect(formatMoney(1234.5, 'USD')).toMatch(/1,234\.50/)
    expect(formatMoney(10, 'XXXX')).toBe('10.00 XXXX')
  })

  it('builds initials', () => {
    expect(initials('Ada Lovelace')).toBe('AL')
    expect(initials('eve@example.com')).toBe('EE')
    expect(initials('')).toBe('?')
  })

  it('computes relative time', () => {
    const now = Date.now()
    expect(timeAgo(new Date(now - 30_000).toISOString(), now)).toBe('just now')
    expect(timeAgo(new Date(now - 2 * 3600_000).toISOString(), now)).toMatch(/2 hours ago/)
  })

  it('counts days until a date', () => {
    const t = new Date()
    t.setDate(t.getDate() + 3)
    const iso = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
    expect(daysUntil(iso)).toBe(3)
  })

  it('drops empty query params', () => {
    expect(cleanParams({ a: '', b: null, c: 0, d: [], e: ['x'], f: 'y' })).toEqual({ c: 0, e: ['x'], f: 'y' })
  })
})

describe('currency defaults', () => {
  it('uses the configured currency and Indian digit grouping', async () => {
    const { appConfig } = await import('@/config')
    expect(appConfig.currency).toBe('INR')
    expect(formatMoney(150000)).toBe('₹1,50,000.00')
    expect(formatMoney(1250000, undefined, { compact: true })).toMatch(/^₹12\.5\s?L/)
    expect(formatMoney(99.5, 'USD')).toContain('99.50') // per-asset currencies still work
  })
})
