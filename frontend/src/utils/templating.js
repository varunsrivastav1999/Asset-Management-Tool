/** Client-side mirror of the backend's {{variable}} renderer, for instant previews. */
const VAR_RE = /\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}/g

export const SAMPLE = {
  asset_name: 'Dell Latitude 7440',
  asset_tag: 'AST-000042',
  due_date: '15 Dec 2026',
  days_left: '7',
  user_name: 'Eve Employee',
  recipient_name: 'Max Manager',
  department: 'Engineering',
  section_name: 'Assets',
  reference: 'HND-000123',
  status: 'Assigned',
  category: 'Laptops',
  count: '3',
  item_name: 'Dell Latitude 7440',
  link: 'https://assets.example.com/assets/42',
  org_name: 'Asset Management Tools',
}

export function renderTemplate(text, context = SAMPLE) {
  return String(text || '').replace(VAR_RE, (_, name) => (name in context ? String(context[name]) : ''))
}
