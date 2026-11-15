import { reactive } from 'vue'

/**
 * Display settings from the server (`GET /api/app-config/`): DEFAULT_CURRENCY and CURRENCY_LOCALE.
 * Reactive, so amounts re-render once the real values arrive. Defaults match the server defaults.
 */
export const appConfig = reactive({ currency: 'INR', currencyLocale: 'en-IN' })

export async function loadAppConfig(http) {
  try {
    const { data } = await http.get('/app-config/')
    if (data?.currency) appConfig.currency = data.currency
    if (data?.currency_locale) appConfig.currencyLocale = data.currency_locale
  } catch {
    // Keep the defaults; formatting still works offline.
  }
}
