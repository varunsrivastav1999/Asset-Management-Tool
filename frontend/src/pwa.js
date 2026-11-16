import { registerSW } from 'virtual:pwa-register'

const CHECK_EVERY_MS = 15 * 60 * 1000

/**
 * Keep installed / long-open copies of the app current. The service worker caches the app for offline use, so
 * without this a tab can keep running an old build after a deploy. We look for a new version on start, every
 * 15 minutes and whenever the tab becomes visible again, then ask before reloading (unsaved input is never lost).
 */
export function setupAppUpdates(ui) {
  if (!('serviceWorker' in navigator) || import.meta.env.DEV) return
  let registration = null
  let notified = false
  const updateSW = registerSW({
    immediate: true,
    onNeedRefresh() {
      if (notified) return
      notified = true
      ui.toast('A new version of the app is ready.', {
        title: 'Update available',
        timeout: 0,
        action: { label: 'Reload now', onClick: () => updateSW(true) },
      })
    },
    onRegisteredSW(_url, reg) {
      registration = reg || null
      if (registration) setInterval(() => registration.update().catch(() => {}), CHECK_EVERY_MS)
    },
  })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') registration?.update().catch(() => {})
  })
}
