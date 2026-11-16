import { downloadFile, http } from './http'

const unwrap = (p) => p.then((r) => r.data)

/** Generic REST resource helper. */
function resource(base) {
  return {
    list: (params) => unwrap(http.get(`${base}/`, { params })),
    get: (id) => unwrap(http.get(`${base}/${id}/`)),
    create: (data, config) => unwrap(http.post(`${base}/`, data, config)),
    update: (id, data) => unwrap(http.patch(`${base}/${id}/`, data)),
    remove: (id) => unwrap(http.delete(`${base}/${id}/`)),
    action: (id, name, data, config) => unwrap(http.post(`${base}/${id}/${name}/`, data, config)),
  }
}

export const authApi = {
  login: (email, password) => unwrap(http.post('/auth/login/', { email, password })),
  logout: () => unwrap(http.post('/auth/logout/')),
  me: () => unwrap(http.get('/auth/me/')),
  updateMe: (data) => unwrap(http.patch('/auth/me/', data)),
  changePassword: (data) => unwrap(http.post('/auth/change-password/', data)),
}

export const usersApi = { ...resource('/users'), activate: (id) => unwrap(http.post(`/users/${id}/activate/`)) }
export const departmentsApi = resource('/departments')
export const categoriesApi = resource('/categories')
export const locationsApi = resource('/locations')
export const vendorsApi = resource('/vendors')

export const assetsApi = {
  ...resource('/assets'),
  history: (id, params) => unwrap(http.get(`/assets/${id}/history/`, { params })),
  lookup: (code) => unwrap(http.get('/assets/lookup/', { params: { code } })),
  changeStatus: (id, status, notes) => unwrap(http.post(`/assets/${id}/change-status/`, { status, notes })),
  uploadPhoto: (id, file, { caption = '', isPrimary = false } = {}) => {
    const form = new FormData()
    form.append('image', file)
    form.append('caption', caption)
    form.append('is_primary', isPrimary ? 'true' : 'false')
    return unwrap(http.post(`/assets/${id}/photos/`, form))
  },
  updatePhoto: (id, photoId, data) => unwrap(http.patch(`/assets/${id}/photos/${photoId}/`, data)),
  deletePhoto: (id, photoId) => unwrap(http.delete(`/assets/${id}/photos/${photoId}/`)),
  bulkUpdate: (data) => unwrap(http.post('/assets/bulk-update/', data)),
  importFile: (file, dryRun) => {
    const form = new FormData()
    form.append('file', file)
    form.append('dry_run', dryRun ? 'true' : 'false')
    return unwrap(http.post('/assets/import/', form, { timeout: 120000 }))
  },
}

export const myAssetsApi = resource('/my-assets')
export const receiptsApi = resource('/receipts')
export const handoversApi = {
  ...resource('/handovers'),
  sign: (id, data) => unwrap(http.post(`/handovers/${id}/sign/`, data)),
  cancel: (id, reason) => unwrap(http.post(`/handovers/${id}/cancel/`, { reason })),
}
export const maintenanceApi = resource('/maintenance')
export const notificationsApi = {
  list: (params) => unwrap(http.get('/notifications/', { params })),
  unreadCount: () => unwrap(http.get('/notifications/unread-count/')),
  read: (id) => unwrap(http.post(`/notifications/${id}/read/`)),
  readAll: () => unwrap(http.post('/notifications/read-all/')),
  clearRead: () => unwrap(http.post('/notifications/clear-read/')),
  remove: (id) => unwrap(http.delete(`/notifications/${id}/`)),
}
export const auditApi = resource('/audit-logs')
export const dashboardApi = { stats: () => unwrap(http.get('/dashboard/stats/')) }

export const sidebarApi = {
  mine: () => unwrap(http.get('/sidebar/')),
  tree: () => unwrap(http.get('/sidebar-items/tree/')),
  create: (data) => unwrap(http.post('/sidebar-items/', data)),
  update: (id, data) => unwrap(http.patch(`/sidebar-items/${id}/`, data)),
  remove: (id) => unwrap(http.delete(`/sidebar-items/${id}/`)),
  reorder: (items) => unwrap(http.post('/sidebar-items/reorder/', { items })),
  reset: () => unwrap(http.post('/sidebar-items/reset/')),
}

export const widgetsApi = {
  layout: () => unwrap(http.get('/dashboard/')),
  list: () => unwrap(http.get('/dashboard-widgets/')),
  sources: () => unwrap(http.get('/dashboard-widgets/sources/')),
  create: (data) => unwrap(http.post('/dashboard-widgets/', data)),
  update: (id, data) => unwrap(http.patch(`/dashboard-widgets/${id}/`, data)),
  remove: (id) => unwrap(http.delete(`/dashboard-widgets/${id}/`)),
  reorder: (ids) => unwrap(http.post('/dashboard-widgets/reorder/', { ids })),
  reset: () => unwrap(http.post('/dashboard-widgets/reset/')),
}

export const tablesApi = {
  registry: () => unwrap(http.get('/tables/')),
  columns: (table, item) => unwrap(http.get(`/tables/${table}/columns/`, { params: item ? { item } : {} })),
  savePrefs: (item, hidden, shown) => unwrap(http.put('/tables/prefs/', { item, hidden, shown })),
  clearPrefs: (item) => unwrap(http.delete('/tables/prefs/', { params: { item } })),
  listColumns: (sidebarItem) => unwrap(http.get('/table-columns/', { params: { sidebar_item: sidebarItem } })),
  createColumn: (data) => unwrap(http.post('/table-columns/', data)),
  updateColumn: (id, data) => unwrap(http.patch(`/table-columns/${id}/`, data)),
  deleteColumn: (id) => unwrap(http.delete(`/table-columns/${id}/`)),
  reorderColumns: (sidebarItem, ids) => unwrap(http.post('/table-columns/reorder/', { sidebar_item: sidebarItem, ids })),
  resetColumns: (sidebarItem) => unwrap(http.post('/table-columns/reset/', { sidebar_item: sidebarItem })),
  /** PATCH custom column values on a row: base is the resource path, e.g. '/assets'. */
  setCustom: (base, id, data) => unwrap(http.patch(`${base}/${id}/custom-data/`, data)),
}

export const definitionsApi = {
  list: (params) => unwrap(http.get('/table-definitions/', { params })),
  create: (data) => unwrap(http.post('/table-definitions/', data)),
  update: (id, data) => unwrap(http.patch(`/table-definitions/${id}/`, data)),
  remove: (id) => unwrap(http.delete(`/table-definitions/${id}/`)),
  deleteCheck: (id) => unwrap(http.get(`/table-definitions/${id}/delete-check/`)),
}

export const recordsApi = {
  list: (params) => unwrap(http.get('/records/', { params })),
  create: (item, data) => unwrap(http.post('/records/', data, { params: { table_item: item } })),
  update: (item, id, data) => unwrap(http.patch(`/records/${id}/`, data, { params: { table_item: item } })),
  remove: (item, id) => unwrap(http.delete(`/records/${id}/`, { params: { table_item: item } })),
  archive: (item, body) => unwrap(http.post('/records/bulk-archive/', body, { params: { table_item: item } })),
  move: (item, body) => unwrap(http.post('/records/bulk-move/', body, { params: { table_item: item } })),
  get: (item, id) => unwrap(http.get(`/records/${id}/`, { params: { table_item: item } })),
  lookup: (code) => unwrap(http.get('/records/lookup/', { params: { code } })),
  qrPath: (id) => `/records/${id}/qr/`,
  barcodePath: (id) => `/records/${id}/barcode/`,
  /** Opens an A4 label sheet (PDF) for { ids } or { all: true }. */
  labels: (item, body) => downloadFile('/records/labels/', { method: 'post', params: { table_item: item }, data: body, open: true }),
  importFile: (item, file, dryRun) => {
    const form = new FormData()
    form.append('file', file)
    form.append('dry_run', dryRun ? 'true' : 'false')
    return unwrap(http.post('/records/import/', form, { params: { table_item: item }, timeout: 120000 }))
  },
}

export const remindersApi = {
  rules: (params) => unwrap(http.get('/reminders/rules/', { params })),
  createRule: (data) => unwrap(http.post('/reminders/rules/', data)),
  updateRule: (id, data) => unwrap(http.patch(`/reminders/rules/${id}/`, data)),
  deleteRule: (id) => unwrap(http.delete(`/reminders/rules/${id}/`)),
  testRule: (id) => unwrap(http.post(`/reminders/rules/${id}/test/`)),
  sendNow: (id) => unwrap(http.post(`/reminders/rules/${id}/send-now/`)),
  templates: () => unwrap(http.get('/reminders/templates/')),
  createTemplate: (data) => unwrap(http.post('/reminders/templates/', data)),
  updateTemplate: (id, data) => unwrap(http.patch(`/reminders/templates/${id}/`, data)),
  deleteTemplate: (id) => unwrap(http.delete(`/reminders/templates/${id}/`)),
  preview: (data) => unwrap(http.post('/reminders/templates/preview/', data)),
  variables: () => unwrap(http.get('/reminders/templates/variables/')),
  logs: (params) => unwrap(http.get('/reminders/logs/', { params })),
  retryLog: (id) => unwrap(http.post(`/reminders/logs/${id}/retry/`)),
  channels: () => unwrap(http.get('/reminders/channels/')),
  saveChannels: (data) => unwrap(http.put('/reminders/channels/', data)),
  preferences: () => unwrap(http.get('/reminders/preferences/')),
  savePreferences: (data) => unwrap(http.put('/reminders/preferences/', data)),
  verifyPhone: (code) => unwrap(http.post('/reminders/preferences/verify-phone/', code ? { code } : {})),
}

export const backupsApi = {
  status: () => unwrap(http.get('/backups/')),
  create: () => unwrap(http.post('/backups/')),
  remove: (name) => unwrap(http.delete(`/backups/${encodeURIComponent(name)}/`)),
}

export const mediaApi = {
  /** Upload a file for a Media column; resolves to the cell value { id, name, type, size }. */
  upload: (item, column, file) => {
    const form = new FormData()
    form.append('file', file)
    form.append('table_item', item)
    form.append('column', column)
    return unwrap(http.post('/table-media/', form, { timeout: 120000 }))
  },
  url: (id) => `/table-media/${id}/`,
}
