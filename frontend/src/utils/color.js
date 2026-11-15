/** Validated hex color (#rgb, #rrggbb, #rrggbbaa) or null. */
export function normalizeHex(value) {
  if (typeof value !== 'string') return null
  const v = value.trim()
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(v) ? v : null
}

/** Convert a hex color to rgba() with the given alpha (0–1). Returns null for invalid input. */
export function withAlpha(hex, alpha) {
  const v = normalizeHex(hex)
  if (!v) return null
  let h = v.slice(1)
  if (h.length === 3) h = [...h].map((c) => c + c).join('')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export const COLOR_PRESETS = ['#10b981', '#84cc16', '#22c55e', '#65a30d', '#a78bfa', '#c084fc', '#f472b6', '#fb7185', '#f97316', '#fbbf24', '#a3e635', '#34d399', '#2dd4bf', '#94a3b8']
