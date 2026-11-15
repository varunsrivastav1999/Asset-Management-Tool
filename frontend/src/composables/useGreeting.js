import { computed, onBeforeUnmount, ref } from 'vue'

/** Greeting for an hour of the day (0–23), in the viewer's local time. */
export function greetingFor(hour) {
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  return 'Good evening'
}

/**
 * Reactive time-of-day greeting that stays correct on screens left open (e.g. a wall dashboard):
 * it re-checks the clock every minute and when the tab becomes visible again.
 */
export function useGreeting(clock = () => new Date()) {
  const now = ref(clock())
  const tick = () => (now.value = clock())
  const timer = setInterval(tick, 60_000)
  const onVisible = () => document.visibilityState === 'visible' && tick()
  document.addEventListener('visibilitychange', onVisible)
  onBeforeUnmount(() => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisible)
  })
  return computed(() => greetingFor(now.value.getHours()))
}
