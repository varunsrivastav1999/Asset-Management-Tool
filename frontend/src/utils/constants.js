export const ASSET_STATUS = {
  in_stock: { label: 'In stock', tone: 'primary', color: '#10b981' },
  assigned: { label: 'Assigned', tone: 'violet', color: '#a78bfa' },
  in_repair: { label: 'In repair', tone: 'amber', color: '#fbbf24' },
  retired: { label: 'Retired', tone: 'slate', color: '#94a3b8' },
  lost: { label: 'Lost', tone: 'rose', color: '#fb7185' },
}

export const CONDITIONS = [
  { value: 'new', label: 'New' },
  { value: 'good', label: 'Good' },
  { value: 'fair', label: 'Fair' },
  { value: 'poor', label: 'Poor' },
  { value: 'damaged', label: 'Damaged' },
]

export const HANDOVER_TYPES = {
  issue: { label: 'Issue', tone: 'violet', icon: 'ArrowUpRight', hint: 'Give in-stock assets to an employee or department.' },
  transfer: { label: 'Transfer', tone: 'primary', icon: 'ArrowLeftRight', hint: 'Move assets from their current holder to someone else.' },
  return: { label: 'Return', tone: 'emerald', icon: 'ArrowDownLeft', hint: 'Bring assets back into stock from their holder.' },
}

export const HANDOVER_STATUS = {
  pending: { label: 'Pending sign-off', tone: 'amber' },
  completed: { label: 'Completed', tone: 'emerald' },
  cancelled: { label: 'Cancelled', tone: 'slate' },
}

export const MAINTENANCE_STATUS = {
  scheduled: { label: 'Scheduled', tone: 'primary' },
  in_progress: { label: 'In progress', tone: 'amber' },
  completed: { label: 'Completed', tone: 'emerald' },
  cancelled: { label: 'Cancelled', tone: 'slate' },
}

export const MAINTENANCE_KINDS = [
  { value: 'preventive', label: 'Preventive' },
  { value: 'corrective', label: 'Repair' },
  { value: 'inspection', label: 'Inspection' },
  { value: 'calibration', label: 'Calibration' },
]

export const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'manager', label: 'Manager' },
  { value: 'employee', label: 'Employee' },
]

export const FIELD_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'boolean', label: 'Yes / No' },
  { value: 'select', label: 'Select' },
]

export const CATEGORY_ICONS = ['box', 'laptop', 'monitor', 'smartphone', 'printer', 'armchair', 'car', 'wrench', 'camera', 'server', 'headphones', 'tablet', 'keyboard', 'truck', 'lamp']

export const EVENT_META = {
  created: { tone: 'primary', label: 'Created' },
  updated: { tone: 'slate', label: 'Updated' },
  received: { tone: 'emerald', label: 'Received' },
  issued: { tone: 'violet', label: 'Issued' },
  returned: { tone: 'emerald', label: 'Returned' },
  transferred: { tone: 'primary', label: 'Transferred' },
  status_changed: { tone: 'amber', label: 'Status changed' },
  maintenance_scheduled: { tone: 'primary', label: 'Maintenance scheduled' },
  maintenance_started: { tone: 'amber', label: 'Maintenance started' },
  maintenance_completed: { tone: 'emerald', label: 'Maintenance completed' },
  photo_added: { tone: 'slate', label: 'Photo added' },
  imported: { tone: 'primary', label: 'Imported' },
}
