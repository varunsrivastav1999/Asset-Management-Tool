import { assetsApi, recordsApi } from '@/api'

/** Row codes of custom tables look like "LIC-00012" (asset tags use their own AST- numbering). */
export const RECORD_CODE = /^[A-Z0-9]{1,3}-\d{5,}$/i
const RECORD_LINK = /\/r\/([^/?#\s]+)/i
const ASSET_LINK = /\/a\/([^/?#\s]+)/i

const recordTarget = (r) => ({ path: r.route, query: { open: r.code } })
const assetTarget = (a) => `/assets/${a.id}`

/**
 * Turn anything scanned (QR link, barcode, typed code) into where to go. Tries the most specific match first and
 * falls back to the other kind, so one scanner handles asset tags, serial numbers and table-row codes.
 * Resolves to a router location, or rejects with a 404-like error when nothing matches.
 */
export async function resolveScan(raw) {
  const value = String(raw || '').trim()
  const recordLink = RECORD_LINK.exec(value)?.[1]
  if (recordLink) return recordTarget(await recordsApi.lookup(recordLink))
  const assetLink = ASSET_LINK.exec(value)?.[1]
  if (assetLink) return assetTarget(await assetsApi.lookup(value))

  const tries = RECORD_CODE.test(value)
    ? [() => recordsApi.lookup(value).then(recordTarget), () => assetsApi.lookup(value).then(assetTarget)]
    : [() => assetsApi.lookup(value).then(assetTarget), () => recordsApi.lookup(value).then(recordTarget)]
  let lastError
  for (const attempt of tries) {
    try {
      return await attempt()
    } catch (e) {
      lastError = e
      if (e?.response?.status !== 404) throw e
    }
  }
  throw lastError
}
