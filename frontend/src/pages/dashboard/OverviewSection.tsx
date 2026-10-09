import { Activity, AlertTriangle, ArrowUpRight, CalendarDays, CheckCircle2, Clock3, ShieldCheck, Users } from 'lucide-react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, formatDateTime } from '../../lib/api'
import { useApp } from '../../lib/AppContext'
import { useLoad } from '../../lib/hooks'
import type { DashboardData } from '../../lib/types'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, Metric } from '../../components/ui'
import type { GoToTab } from './types'

export function OverviewSection({ onGo, onProductionData }: { onGo: GoToTab; onProductionData: () => void }) {
  const { activeProjectId, activeProject } = useApp()
  const { data, loading, error, reload } = useLoad(
    () => activeProjectId ? api<DashboardData>(`/projects/${activeProjectId}/dashboard`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )

  if (loading) return <LoadingState />
  if (error || !data) return <ErrorState error={error} retry={() => reload().catch(() => undefined)} />

  const score = data.prevent?.overall_score ?? 0
  const scoreData = [{ name: 'Start', score: Math.max(0, score - 18) }, { name: 'Review', score: Math.max(0, score - 7) }, { name: 'Now', score }]
  const nextItems = data.active_schedule?.items.slice(0, 4) ?? []

  return (
    <>
      <div className="metric-grid four">
        <Metric label="Readiness score" value={data.prevent ? `${score.toFixed(0)}%` : 'Not run'} detail={data.prevent?.status.replace('_', ' ') ?? 'Run PREVENT to establish baseline'} tone={score >= 85 ? 'success' : score > 0 ? 'warning' : 'default'} />
        <Metric label="Scenes completed" value={`${data.totals.completed} / ${data.totals.scenes}`} detail={`${Math.round((data.totals.completed / Math.max(1, data.totals.scenes)) * 100)}% production progress`} tone={data.totals.completed === data.totals.scenes && data.totals.scenes > 0 ? 'success' : 'default'} />
        <Metric label="Active resources" value={data.totals.resources} detail="Cast, crew, equipment & locations" />
        <Metric label="Open incidents" value={data.totals.open_incidents} detail={data.totals.open_incidents ? 'Recovery may be required' : 'No active disruption'} tone={data.totals.open_incidents ? 'danger' : 'success'} />
      </div>

      <div className="dashboard-grid">
        <Card className="readiness-card">
          <div className="section-heading"><div><span>PREVENT SIGNAL</span><h2>Readiness trajectory</h2></div><Badge tone={data.prevent?.status === 'READY' ? 'success' : data.prevent?.status === 'NOT_READY' ? 'danger' : 'warning'}>{data.prevent?.status.replace('_', ' ') ?? 'NOT RUN'}</Badge></div>
          <div className="readiness-chart">
            <div className="score-block"><strong>{score.toFixed(0)}</strong><span>/100</span><small>{data.prevent ? `${data.prevent.issues.filter((issue) => issue.status === 'OPEN').length} open findings` : 'No baseline yet'}</small></div>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={scoreData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <defs><linearGradient id="scoreFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ef5a3c" stopOpacity={0.35} /><stop offset="100%" stopColor="#ef5a3c" stopOpacity={0} /></linearGradient></defs>
                <XAxis dataKey="name" axisLine={false} tickLine={false} fontSize={11} /><YAxis domain={[0, 100]} axisLine={false} tickLine={false} fontSize={11} /><Tooltip /><Area type="monotone" dataKey="score" stroke="#ef5a3c" fill="url(#scoreFill)" strokeWidth={2.5} /></AreaChart>
            </ResponsiveContainer>
          </div>
          <Button variant="secondary" onClick={onProductionData}><ShieldCheck size={16} />Open readiness in Production Data<ArrowUpRight size={14} /></Button>
        </Card>

        <Card className="today-card">
          <div className="section-heading"><div><span>ACTIVE SCHEDULE</span><h2>Next on set</h2></div>{data.active_schedule && <Badge tone="info">V{data.active_schedule.version_number}</Badge>}</div>
          {nextItems.length ? <div className="timeline-list">{nextItems.map((item, index) => <div className="timeline-row" key={item.id}><div className="timeline-time"><strong>{item.planned_start.slice(0, 5)}</strong><span>{item.shooting_date.slice(5)}</span></div><div className="timeline-line"><span className={index === 0 ? 'current' : ''} /></div><div><Badge tone={item.scene_status === 'COMPLETED' ? 'success' : 'neutral'}>SC {item.scene_number}</Badge><h3>{item.scene_title}</h3><small>{item.planned_duration_minutes} min · {item.scene_status}</small></div></div>)}</div> : <EmptyState title="No active schedule" description="Generate an initial schedule after requirements are ready." action={<Button variant="secondary" onClick={() => onGo('schedule')}>Open schedule</Button>} icon={<CalendarDays size={22} />} />}
        </Card>
      </div>

      <div className="dashboard-lower">
        <Card>
          <div className="section-heading"><div><span>ATTENTION QUEUE</span><h2>Production signals</h2></div></div>
          <div className="signal-list">
            {(data.prevent?.issues.filter((issue) => issue.status === 'OPEN').slice(0, 3) ?? []).map((issue) => <button type="button" key={issue.id} onClick={() => onGo('schedule')}><span className={`signal-icon ${issue.severity.toLowerCase()}`}>{issue.severity === 'CRITICAL' ? <AlertTriangle size={18} /> : <ShieldCheck size={18} />}</span><span><strong>{issue.title}</strong><small>{issue.recommended_action}</small></span><ArrowUpRight size={15} /></button>)}
            {data.recent_incidents.slice(0, 2).map((incident) => <button type="button" key={incident.id} onClick={() => onGo('recovery')}><span className="signal-icon critical"><Activity size={18} /></span><span><strong>{incident.title}</strong><small>{formatDateTime(incident.reported_at)} · {incident.status}</small></span><ArrowUpRight size={15} /></button>)}
            {!data.prevent?.issues.length && !data.recent_incidents.length && <div className="all-clear"><CheckCircle2 size={26} /><div><strong>Production state is clear</strong><p>No readiness findings or reported incidents.</p></div></div>}
          </div>
        </Card>
        <Card>
          <div className="section-heading"><div><span>QUICK CONTROL</span><h2>Action center</h2></div></div>
          <div className="quick-actions">
            <button type="button" onClick={() => onGo('schedule')}><Clock3 /><span><strong>Track live scene</strong><small>Record actual timing and delays</small></span></button>
            <button type="button" onClick={() => onGo('incidents')}><AlertTriangle /><span><strong>Report disruption</strong><small>Confirm impact before recovery</small></span></button>
            <button type="button" onClick={() => onGo('recovery')}><Activity /><span><strong>Recovery & approval</strong><small>Compare and approve plans</small></span></button>
            <button type="button" onClick={() => onGo('recovery')}><Users /><span><strong>Coordinate crew</strong><small>Preview updates and confirmations</small></span></button>
          </div>
        </Card>
      </div>
      <div className="overview-hint"><Badge tone="info">TIP</Badge><span>Readiness scoring and structured data editing live in <strong>Production Data</strong>. {activeProject?.name ?? 'This project'} state v{activeProject?.production_state_version ?? 1}.</span></div>
    </>
  )
}
