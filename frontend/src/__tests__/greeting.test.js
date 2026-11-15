import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { greetingFor, useGreeting } from '@/composables/useGreeting'

describe('greetingFor', () => {
  it.each([
    [5, 'Good morning'],
    [11, 'Good morning'],
    [12, 'Good afternoon'],
    [16, 'Good afternoon'],
    [17, 'Good evening'],
    [23, 'Good evening'],
    [0, 'Good evening'],
    [4, 'Good evening'],
  ])('%i:00 → %s', (hour, text) => expect(greetingFor(hour)).toBe(text))
})

describe('useGreeting', () => {
  afterEach(() => vi.useRealTimers())

  it('updates on an open screen when the time of day changes', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 10, 16, 11, 59, 30))
    const w = mount(defineComponent({ setup: () => { const g = useGreeting(); return () => h('p', g.value) } }))
    expect(w.text()).toBe('Good morning')
    vi.setSystemTime(new Date(2026, 10, 16, 12, 0, 30))
    vi.advanceTimersByTime(60_000)
    await w.vm.$nextTick()
    expect(w.text()).toBe('Good afternoon')
    w.unmount()
  })
})
