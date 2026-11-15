/** Column types an admin can pick for custom columns (built-in auto-number columns are not offered). */
export const COLUMN_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'boolean', label: 'Yes / No' },
  { value: 'select', label: 'Select' },
  { value: 'status', label: 'Status' },
  { value: 'user', label: 'User' },
  { value: 'file', label: 'File / link' },
]

export const COLUMN_TYPE_LABEL = { ...Object.fromEntries(COLUMN_TYPES.map((t) => [t.value, t.label])), auto_number: 'Auto number' }

export const DEFAULT_STATUS_OPTIONS = ['Open', 'In progress', 'Done']

/** Types whose values are picked from a list of options. */
export const hasOptions = (type) => type === 'select' || type === 'status'

export const optionsPlaceholder = (type) => (type === 'status' ? DEFAULT_STATUS_OPTIONS.join(', ') : 'Option A, Option B')

/** "a, b , ,c" → ["a", "b", "c"]; empty for types without options (the server fills default statuses). */
export const parseOptions = (type, text) => (hasOptions(type) ? String(text || '').split(',').map((o) => o.trim()).filter(Boolean) : [])

/** True for a custom status column (built-in status columns carry `{ kind }` instead of a list). */
export const isCustomStatus = (col) => col?.type === 'status' && Array.isArray(col.options)

const TONE_WORDS = [
  ['emerald', /\b(done|complete|completed|closed|active|approved|resolved|ok|available|paid|yes)\b/i],
  ['amber', /\b(progress|pending|waiting|review|hold|open|planned|scheduled|draft)\b/i],
  ['rose', /\b(blocked|failed|lost|cancel+ed|rejected|overdue|broken|inactive|expired|no)\b/i],
]
const FALLBACK_TONES = ['violet', 'lime', 'primary', 'amber', 'emerald', 'rose']

/** Badge colour for a status value: by meaning when recognisable, else stable by its position in the list. */
export function statusTone(value, options = []) {
  if (!value) return 'slate'
  const hit = TONE_WORDS.find(([, re]) => re.test(value))
  if (hit) return hit[0]
  const i = options.indexOf(value)
  return FALLBACK_TONES[(i < 0 ? value.length : i) % FALLBACK_TONES.length]
}
