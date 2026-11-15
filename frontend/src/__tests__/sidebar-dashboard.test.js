import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import SidebarNav from '@/components/SidebarNav.vue'
import DashboardWidget from '@/components/dashboard/DashboardWidget.vue'
import { useSidebarStore } from '@/stores/sidebar'
import { useNotificationsStore } from '@/stores/notifications'
import { iconFor } from '@/utils/icons'

vi.mock('@/api', () => ({
  sidebarApi: { mine: vi.fn(async () => ({ items: TREE })) },
  notificationsApi: {},
}))

const TREE = [
  {
    id: 1,
    type: 'group',
    name: 'Overview',
    children: [
      { id: 2, type: 'page', name: 'Dashboard', route: '/', icon: 'layout-dashboard' },
      { id: 3, type: 'page', name: 'Scan', route: '/scan', icon: 'scan-line' },
    ],
  },
  { id: 4, type: 'divider', name: '' },
  { id: 5, type: 'link', name: 'Wiki', url: 'https://wiki.example.com', open_in_new_tab: true, icon: 'book-open' },
]

function router() {
  const Stub = { template: '<div />' }
  return createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Stub }, { path: '/scan', component: Stub }] })
}

beforeEach(() => setActivePinia(createPinia()))

describe('SidebarNav', () => {
  it('renders groups, pages, dividers and safe external links from data', async () => {
    const r = router()
    r.push('/scan')
    await r.isReady()
    const w = mount(SidebarNav, { props: { items: TREE }, global: { plugins: [r] } })
    expect(w.text()).toContain('Overview')
    expect(w.findAll('a[href="/"], a[href="/scan"]')).toHaveLength(2)
    expect(w.find('hr').exists()).toBe(true)
    const ext = w.find('a[href="https://wiki.example.com"]')
    expect(ext.attributes('target')).toBe('_blank')
    expect(ext.attributes('rel')).toContain('noopener')
    // Active route is highlighted; "/" only matches exactly.
    const active = w.findAll('a').filter((a) => a.classes().includes('bg-accent/10'))
    expect(active.map((a) => a.text())).toEqual(['Scan'])
  })

  it('hides labels when collapsed', async () => {
    const r = router()
    r.push('/')
    await r.isReady()
    const w = mount(SidebarNav, { props: { items: TREE, collapsed: true }, global: { plugins: [r] } })
    expect(w.text()).not.toContain('Overview')
    expect(w.find('a[href="/scan"]').attributes('title')).toBe('Scan')
  })
})

describe('sidebar store', () => {
  it('loads the menu and exposes pages in order', async () => {
    const s = useSidebarStore()
    await s.load()
    expect(s.loaded).toBe(true)
    expect(s.pages.map((p) => p.route)).toEqual(['/', '/scan'])
  })

  it('reloads when the server broadcasts a sidebar change', async () => {
    const s = useSidebarStore()
    const spy = vi.spyOn(s, 'load')
    useNotificationsStore().handle({ type: 'sidebar.update' })
    expect(spy).toHaveBeenCalled()
  })

  it('bumps the layout tick on dashboard layout changes', () => {
    const n = useNotificationsStore()
    n.handle({ type: 'dashboard.layout' })
    expect(n.layoutTick).toBe(1)
  })
})

describe('icons', () => {
  it('falls back for unknown icon names', () => {
    expect(iconFor('definitely-not-an-icon')).toBeTruthy()
    expect(iconFor('boxes')).not.toBe(iconFor('definitely-not-an-icon'))
  })
})

describe('DashboardWidget', () => {
  const r = router()
  const mountW = (widget) => mount(DashboardWidget, { props: { widget }, global: { plugins: [r], stubs: { DoughnutChart: true, BarChart: true, LineChart: true } } })

  it('formats stat values by kind', () => {
    expect(mountW({ type: 'stat', title: 'Value', data: { value: '1250000', format: 'currency' } }).text()).toMatch(/₹12\.5\s?L/) // default currency INR, Indian grouping (lakh)
    expect(mountW({ type: 'stat', title: 'Util', data: { value: 42.5, format: 'percent' } }).text()).toContain('42.5%')
    expect(mountW({ type: 'stat', title: 'Count', data: { value: 1234, format: 'number' } }).text()).toContain('1,234')
  })

  it('picks the chart component from chart_type and handles empty data', () => {
    const data = { labels: ['A'], datasets: [{ label: 'x', data: [3] }] }
    expect(mountW({ type: 'chart', title: 'C', chart_type: 'line', data }).find('line-chart-stub').exists()).toBe(true)
    expect(mountW({ type: 'chart', title: 'C', chart_type: 'hbar', data }).find('bar-chart-stub').attributes('horizontal')).toBe('true')
    expect(mountW({ type: 'chart', title: 'C', chart_type: 'bar', data: { labels: [], datasets: [{ data: [] }] } }).text()).toContain('No data yet')
  })

  it('renders table rows as links and shows errors', () => {
    const w = mountW({ type: 'table', title: 'T', data: { columns: [{ key: 'asset', label: 'Asset' }], rows: [{ asset: 'AST-1 · Laptop', link: '/assets/1' }] } })
    expect(w.find('a[href="/assets/1"]').text()).toContain('AST-1')
    expect(mountW({ type: 'table', title: 'T', data: null, error: true }).text()).toContain('Data unavailable')
  })
})
