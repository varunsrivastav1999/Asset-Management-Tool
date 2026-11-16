import '@fontsource-variable/inter'
import '@fontsource-variable/space-grotesk'
import './style.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { http, tokenStore } from './api/http'
import { loadAppConfig } from './config'
import { setupAppUpdates } from './pwa'
import { useAuthStore } from './stores/auth'
import { useUiStore } from './stores/ui'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// Refresh token rejected (expired/revoked): drop the session and go to login.
tokenStore.on('expired', () => {
  const auth = useAuthStore()
  if (!auth.isAuthenticated) return
  auth.clearSession()
  useUiStore().warning('Your session expired. Please sign in again.')
  const next = router.currentRoute.value.fullPath
  router.replace({ name: 'login', query: next && next !== '/' ? { next } : {} })
})

app.config.errorHandler = (err, _instance, info) => {
  console.error('[app error]', info, err)
  useUiStore().error('An unexpected error occurred.')
}

loadAppConfig(http)
setupAppUpdates(useUiStore(pinia))
router.isReady().then(() => sessionStorage.removeItem('chunk-reload'))
app.mount('#app')
