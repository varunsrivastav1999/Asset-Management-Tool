import { assetsApi, categoriesApi, departmentsApi, locationsApi, usersApi, vendorsApi } from './index'

export const pick = {
  users: (search) => usersApi.list({ search, is_active: true, page_size: 20 }),
  departments: (search) => departmentsApi.list({ search, is_active: true, page_size: 50 }),
  locations: (search) => locationsApi.list({ search, is_active: true, page_size: 50 }),
  vendors: (search) => vendorsApi.list({ search, is_active: true, page_size: 50 }),
  categories: (search) => categoriesApi.list({ search, is_active: true }),
  assets: (filters = {}) => (search) => assetsApi.list({ search, page_size: 20, ...filters }),
}

export const userLabel = (u) => u.full_name || u.email
export const userSub = (u) => [u.email, u.department_name].filter(Boolean).join(' · ')
export const assetLabel = (a) => `${a.asset_tag} · ${a.name}`
export const assetSub = (a) => [a.category?.name, a.serial_number, a.assigned_to?.full_name].filter(Boolean).join(' · ')
