export type Project = {
  id: string
  name: string
  description: string
  start_date: string
  end_date: string
  budget: number
  currency: string
  status: 'PLANNING' | 'PRODUCTION' | 'COMPLETED'
  production_state_version: number
  workday_start: string
  workday_end: string
  scenes?: Scene[]
  resources?: Resource[]
  documents?: DocumentRecord[]
}

export type Shot = {
  id: string
  shot_number: string
  description: string
  frame_size: string
  camera_movement: string
  estimated_duration_minutes: number
  status: string
}

export type Requirement = {
  id: string
  scene_id: string
  category: string
  name: string
  required_resource_id?: string
  required_value?: string
  is_hard_constraint: boolean
  source: string
  confirmation_status: 'SUGGESTED' | 'CONFIRMED' | 'REJECTED'
  fulfillment_status: 'SATISFIED' | 'UNKNOWN' | 'FAILED'
  confidence?: number
}

export type Scene = {
  id: string
  scene_number: string
  title: string
  description: string
  location_id?: string
  estimated_duration_minutes: number
  setup_minutes: number
  priority: number
  status: string
  is_locked: boolean
  shots: Shot[]
  requirements: Requirement[]
}

export type Resource = {
  id: string
  name: string
  type: 'CAST' | 'CREW' | 'EQUIPMENT' | 'LOCATION'
  subtype: string
  email?: string
  status: string
  address?: string
  availability?: Array<{ id: string; date: string; available_from: string; available_until: string; status: string; notes: string }>
}

export type DocumentRecord = {
  id: string
  type: string
  current_version: number
  created_at: string
  versions: Array<{ id: string; version_number: number; original_filename: string; file_type: string; file_hash: string; created_at: string }>
}

export type PreventIssue = {
  id: string
  severity: 'CRITICAL' | 'WARNING' | 'INFO'
  category: string
  title: string
  description: string
  recommended_action: string
  source: string
  status: string
  proposed_patch?: { action: string; scene_id: string } | null
}

export type PreventRun = {
  id: string
  overall_score: number
  status: 'READY' | 'NEEDS_REVIEW' | 'NOT_READY'
  completed_at: string
  ai_used: boolean
  token_usage: number
  category_scores: Record<string, number>
  issues: PreventIssue[]
}

export type ScheduleItem = {
  id: string
  scene_id: string
  shooting_date: string
  planned_start: string
  planned_end: string
  planned_duration_minutes: number
  location_id?: string
  order_index: number
  scene_number: string
  scene_title: string
  scene_status: string
  actual_start?: string | null
  actual_end?: string | null
  delay_minutes?: number
}

export type Schedule = {
  id: string
  project_id: string
  version_number: number
  type: string
  status: string
  parent_schedule_id?: string
  items: ScheduleItem[]
}

export type Incident = {
  id: string
  project_id: string
  category: string
  scene_id?: string
  title: string
  description: string
  reported_at: string
  status: string
  estimated_duration_minutes?: number
  impacts?: Array<{ id: string; scene_id: string; impact_type: string; severity: string; confirmed: boolean }>
}

export type RecoveryPlanItem = {
  id: string
  scene_id: string
  scene_number: string
  scene_title: string
  shooting_date?: string
  start_time?: string
  end_time?: string
  action: 'KEEP' | 'MOVE' | 'DEFER' | 'UNRESOLVED'
  reason: string
}

export type RecoveryPlan = {
  id: string
  type: 'FASTEST' | 'CHEAPEST' | 'MINIMUM_CHANGE'
  status: 'DRAFT' | 'VALID' | 'APPROVED' | 'REJECTED'
  estimated_finish_time?: string
  estimated_delay_minutes: number
  estimated_extra_cost: number
  moved_scene_count: number
  unresolved_scene_count: number
  score: number
  ai_explanation?: string
  items: RecoveryPlanItem[]
  cost_breakdown: Array<{ id: string; category: string; quantity: number; unit: string; rate: number; amount: number; description: string }>
}

export type Notification = {
  id: string
  recipient_email: string
  subject: string
  body: string
  status: string
}

export type DashboardData = {
  project: Project
  totals: { scenes: number; completed: number; resources: number; open_incidents: number }
  prevent: PreventRun | null
  active_schedule: Schedule | null
  recent_incidents: Incident[]
}
