import { ref, watchEffect } from 'vue'
import { http } from '@/api/http'
import { mediaApi } from '@/api'

// Media files are private: fetched with the user's token and shown from an object URL (cached per file).
const cache = new Map()

export function mediaObjectUrl(id) {
  if (!cache.has(id)) {
    const p = http.get(mediaApi.url(id), { responseType: 'blob' }).then((r) => URL.createObjectURL(r.data))
    p.catch(() => cache.delete(id)) // let a later render retry
    cache.set(id, p)
  }
  return cache.get(id)
}

/** Reactive preview URL for an image value ({ id, type }); null for other files or while loading. */
export function useMediaPreview(value) {
  const url = ref(null)
  watchEffect(() => {
    const v = value()
    url.value = null
    if (v?.id && String(v.type || '').startsWith('image/')) {
      mediaObjectUrl(v.id)
        .then((u) => value()?.id === v.id && (url.value = u))
        .catch(() => {})
    }
  })
  return url
}
