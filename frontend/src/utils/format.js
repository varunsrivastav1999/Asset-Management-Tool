import { appConfig } from '@/config'

const dateFmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

function toDate(value) {
  if (!value) return null
  // Plain ISO dates ("2026-01-15") are calendar dates: parse as local, not UTC.
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split('-').map(Number)
    return new Date(y, m - 1, d)
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDate(value, fallback = '—') {
  const d = toDate(value)
  return d ? dateFmt.format(d) : fallback
}

export function formatDateTime(value, fallback = '—') {
  const d = toDate(value)
  return d ? dateTimeFmt.format(d) : fallback
}

export function timeAgo(value, now = Date.now()) {
  const d = toDate(value)
  if (!d) return '—'
  const seconds = Math.round((d.getTime() - now) / 1000)
  const units = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

/** Amount in `currency` (default: the app's DEFAULT_CURRENCY), grouped for the configured locale (en-IN: ₹1,00,000). */
export function formatMoney(value, currency = appConfig.currency, { compact = false } = {}) {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  try {
    return new Intl.NumberFormat(appConfig.currencyLocale || undefined, {
      style: 'currency',
      currency: currency || appConfig.currency,
      notation: compact ? 'compact' : 'standard',
      maximumFractionDigits: compact ? 1 : 2,
    }).format(n)
  } catch {
    return `${n.toFixed(2)} ${currency}`
  }
}

export function formatNumber(value) {
  return new Intl.NumberFormat(appConfig.currencyLocale || undefined).format(Number(value) || 0)
}

export function initials(name = '') {
  return (
    name
      .split(/[\s@.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join('') || '?'
  )
}

export function daysUntil(value) {
  const d = toDate(value)
  if (!d) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((d - today) / 86400000)
}

export function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function cleanParams(obj) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== '' && v !== null && v !== undefined && !(Array.isArray(v) && !v.length)))
}

/**
 * A name as it reads mid-sentence: "Assets" → "assets", but acronyms and proper names typed by an admin keep
 * their capitals ("QA Busy", "IT kit", "PCs" stay as they are).
 */
export function inSentence(name) {
  const s = String(name ?? '')
  if (s.length < 2) return s.toLowerCase()
  const firstWord = s.split(/\s+/)[0]
  const hasInnerCapital = /[A-Z]/.test(firstWord.slice(1))
  return hasInnerCapital ? s : s[0].toLowerCase() + s.slice(1)
}
