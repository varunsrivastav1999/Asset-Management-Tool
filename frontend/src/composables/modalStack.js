/**
 * Shared stack for every overlay (modals, sheets, confirm dialogs).
 * - Later overlays always render above earlier ones (z-index from stack depth), whatever their DOM order.
 * - Only the top overlay reacts to Esc / traps focus.
 * - Body scroll is locked while any overlay is open and restored when the last one closes.
 */
import { ref } from 'vue'

const stack = ref([])
let savedOverflow = ''
let seq = 0

export const Z_BASE = 60
export const Z_CONFIRM = 200

export function openOverlay() {
  const id = ++seq
  if (!stack.value.length) {
    savedOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  stack.value.push(id)
  return id
}

export function closeOverlay(id) {
  stack.value = stack.value.filter((x) => x !== id)
  if (!stack.value.length) document.body.style.overflow = savedOverflow
}

export const isTop = (id) => stack.value.at(-1) === id
export const depth = (id) => Math.max(0, stack.value.indexOf(id))
export const openCount = () => stack.value.length

/** Keep keyboard focus inside `el` (Tab / Shift+Tab wrap around). */
export function trapFocus(e, el) {
  if (e.key !== 'Tab' || !el) return
  const nodes = [...el.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(
    (n) => !n.disabled && !n.closest('[hidden], [aria-hidden="true"], [style*="display: none"]'),
  )
  if (!nodes.length) return
  const first = nodes[0]
  const last = nodes[nodes.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}
