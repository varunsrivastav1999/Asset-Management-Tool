import axios from 'axios'

/**
 * Access token lives only in memory; the refresh token is an HttpOnly cookie the
 * browser sends to /api/auth/refresh/. A single in-flight refresh is shared by all
 * requests that hit a 401 at the same time.
 */
let accessToken = null
let refreshPromise = null
const listeners = { refreshed: new Set(), expired: new Set() }

export const tokenStore = {
  get: () => accessToken,
  set: (t) => {
    accessToken = t
  },
  clear: () => {
    accessToken = null
  },
  on(event, fn) {
    listeners[event].add(fn)
    return () => listeners[event].delete(fn)
  },
}

export const http = axios.create({
  baseURL: '/api',
  withCredentials: true,
  timeout: 30000,
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
})

http.interceptors.request.use((config) => {
  if (accessToken && !config.skipAuth) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

export function refreshAccess() {
  if (!refreshPromise) {
    refreshPromise = axios
      .post('/api/auth/refresh/', null, { withCredentials: true, timeout: 15000 })
      .then(({ data }) => {
        accessToken = data.access
        listeners.refreshed.forEach((fn) => fn(data))
        return data
      })
      .catch((err) => {
        accessToken = null
        throw err
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

http.interceptors.response.use(
  (res) => res,
  async (error) => {
    const { config, response } = error
    const isAuthCall = config?.url?.startsWith('/auth/')
    if (response?.status === 401 && config && !config._retried && !isAuthCall) {
      config._retried = true
      try {
        await refreshAccess()
        config.headers.Authorization = `Bearer ${accessToken}`
        return http(config)
      } catch {
        listeners.expired.forEach((fn) => fn())
      }
    }
    return Promise.reject(error)
  },
)

/** Flatten DRF error payloads into a readable message plus a field map. */
export function parseError(error, fallback = 'Something went wrong. Please try again.') {
  if (!error?.response) {
    return { message: error?.code === 'ECONNABORTED' ? 'The request timed out.' : 'Network error — check your connection.', fields: {} }
  }
  const data = error.response.data
  if (data instanceof Blob) return { message: fallback, fields: {} }
  if (typeof data === 'string') return { message: error.response.status >= 500 ? fallback : data, fields: {} }
  const fields = {}
  let message = data?.detail || data?.non_field_errors?.[0] || ''
  if (data && typeof data === 'object') {
    for (const [key, value] of Object.entries(data)) {
      if (['detail', 'code', 'non_field_errors'].includes(key)) continue
      if (Array.isArray(value)) fields[key] = value.map((v) => (typeof v === 'string' ? v : JSON.stringify(v))).join(' ')
      else if (value && typeof value === 'object') fields[key] = value
      else fields[key] = String(value)
    }
  }
  if (!message) {
    const first = Object.entries(fields)[0]
    if (first) {
      const [k, v] = first
      message = typeof v === 'string' ? `${k.replace(/_/g, ' ')}: ${v}` : 'Please fix the highlighted fields.'
    }
  }
  if (error.response.status === 403 && !message) message = 'You do not have permission to do that.'
  return { message: message || fallback, fields }
}

/** Download a binary endpoint (PDF, XLSX…) using the authenticated client. */
export async function downloadFile(url, { params, method = 'get', data, filename, open = false } = {}) {
  const res = await http.request({ url, method, params, data, responseType: 'blob' })
  const disposition = res.headers['content-disposition'] || ''
  const name = filename || /filename="?([^";]+)"?/.exec(disposition)?.[1] || 'download'
  const blobUrl = URL.createObjectURL(res.data)
  if (open) {
    const win = window.open(blobUrl, '_blank', 'noopener')
    if (!win) triggerDownload(blobUrl, name)
  } else {
    triggerDownload(blobUrl, name)
  }
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000)
}

function triggerDownload(href, name) {
  const a = document.createElement('a')
  a.href = href
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/** Fetch an authenticated image (QR, barcode) as an object URL. */
export async function blobUrl(url, params) {
  const res = await http.get(url, { params, responseType: 'blob' })
  return URL.createObjectURL(res.data)
}
