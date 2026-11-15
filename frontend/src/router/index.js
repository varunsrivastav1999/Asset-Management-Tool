import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { APP_NAME } from '@/brand'

const AppLayout = () => import('@/layouts/AppLayout.vue')

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true, title: 'Sign in' } },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: 'Dashboard' } },
      { path: 'assets', name: 'assets', component: () => import('@/views/assets/AssetsView.vue'), meta: { title: 'Assets' } },
      { path: 'assets/new', name: 'asset-new', component: () => import('@/views/assets/AssetFormView.vue'), meta: { title: 'New asset', roles: ['manager'] } },
      { path: 'assets/:id(\\d+)', name: 'asset', component: () => import('@/views/assets/AssetDetailView.vue'), meta: { title: 'Asset' } },
      { path: 'assets/:id(\\d+)/edit', name: 'asset-edit', component: () => import('@/views/assets/AssetFormView.vue'), meta: { title: 'Edit asset', roles: ['manager'] } },
      { path: 'a/:tag', name: 'asset-short', component: () => import('@/views/assets/AssetShortLinkView.vue'), meta: { title: 'Asset' } },
      { path: 'scan', name: 'scan', component: () => import('@/views/ScanView.vue'), meta: { title: 'Scan' } },
      { path: 'receiving', name: 'receipts', component: () => import('@/views/receiving/ReceiptsView.vue'), meta: { title: 'Receiving', roles: ['manager'] } },
      { path: 'receiving/new', name: 'receipt-new', component: () => import('@/views/receiving/ReceiptCreateView.vue'), meta: { title: 'Receive goods', roles: ['manager'] } },
      { path: 'receiving/:id(\\d+)', name: 'receipt', component: () => import('@/views/receiving/ReceiptDetailView.vue'), meta: { title: 'Goods receipt', roles: ['manager'] } },
      { path: 'handovers', name: 'handovers', component: () => import('@/views/handovers/HandoversView.vue'), meta: { title: 'Handovers' } },
      { path: 'handovers/new', name: 'handover-new', component: () => import('@/views/handovers/HandoverCreateView.vue'), meta: { title: 'New handover', roles: ['manager'] } },
      { path: 'handovers/:id(\\d+)', name: 'handover', component: () => import('@/views/handovers/HandoverDetailView.vue'), meta: { title: 'Handover' } },
      { path: 'maintenance', name: 'maintenance', component: () => import('@/views/MaintenanceView.vue'), meta: { title: 'Maintenance', roles: ['manager'] } },
      { path: 'catalog/categories', name: 'categories', component: () => import('@/views/catalog/CategoriesView.vue'), meta: { title: 'Categories', roles: ['manager'] } },
      { path: 'catalog/locations', name: 'locations', component: () => import('@/views/catalog/LocationsView.vue'), meta: { title: 'Locations', roles: ['manager'] } },
      { path: 'catalog/vendors', name: 'vendors', component: () => import('@/views/catalog/VendorsView.vue'), meta: { title: 'Vendors', roles: ['manager'] } },
      { path: 'people/users', name: 'users', component: () => import('@/views/people/UsersView.vue'), meta: { title: 'People', roles: ['manager'] } },
      { path: 'people/departments', name: 'departments', component: () => import('@/views/people/DepartmentsView.vue'), meta: { title: 'Departments', roles: ['manager'] } },
      { path: 'reminders', name: 'reminders', component: () => import('@/views/RemindersView.vue'), meta: { title: 'Reminders', roles: ['manager'] } },
      { path: 'notifications', name: 'notifications', component: () => import('@/views/NotificationsView.vue'), meta: { title: 'Notifications' } },
      { path: 'audit', name: 'audit', component: () => import('@/views/AuditLogView.vue'), meta: { title: 'Audit log', roles: ['admin'] } },
      { path: 'settings/sidebar', name: 'settings-sidebar', component: () => import('@/views/settings/SidebarSettingsView.vue'), meta: { title: 'Sidebar settings', roles: ['admin'] } },
      { path: 'settings/tables', name: 'settings-tables', component: () => import('@/views/settings/TablesSettingsView.vue'), meta: { title: 'Tables', roles: ['admin'] } },
      { path: 't/:slug', name: 'records', component: () => import('@/views/RecordsView.vue'), meta: { title: 'Table' } },
      { path: 'settings/dashboard', name: 'settings-dashboard', component: () => import('@/views/settings/DashboardSettingsView.vue'), meta: { title: 'Dashboard settings', roles: ['admin'] } },
      { path: 'profile', name: 'profile', component: () => import('@/views/ProfileView.vue'), meta: { title: 'Profile' } },
      { path: ':pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: 'Not found' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (to, from, saved) => saved || (to.path !== from.path ? { top: 0 } : undefined),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.bootstrap()
  if (to.meta.public) {
    return auth.isAuthenticated && to.name === 'login' ? { name: 'dashboard' } : true
  }
  if (!auth.isAuthenticated) return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  const roles = to.meta.roles
  if (roles && !auth.hasRole(...roles)) return { name: 'dashboard' }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · ${APP_NAME}` : APP_NAME
})

// A deploy can invalidate lazily-loaded chunks; reload once to pick up the new build.
router.onError((err, to) => {
  if (/Failed to fetch dynamically imported module|Importing a module script failed/.test(err?.message || '')) {
    if (!sessionStorage.getItem('chunk-reload')) {
      sessionStorage.setItem('chunk-reload', '1')
      window.location.assign(to.fullPath)
    }
  }
})

export default router
