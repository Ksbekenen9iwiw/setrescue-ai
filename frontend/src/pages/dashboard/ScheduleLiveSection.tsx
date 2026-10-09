import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CalendarDays, CheckCircle2, CircleStop, Clock3, Download, GitBranch, Play, Plus, Radio, TimerReset } from 'lucide-react'
import { api, formatDate, post } from '../../lib/api'
import { useApp } from '../../lib/AppContext'
import { useLoad } from '../../lib/hooks'
import type { Schedule } from '../../lib/types'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../../components/ui'

export function ScheduleLiveSection() {
  const { activeProjectId, toast } = useApp()
  const [generating, setGenerating] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [workingId, setWorkingId] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())
  const { data: schedules, loading, error, reload } = useLoad(
    () => activeProjectId ? api<Schedule[]>(`/projects/${activeProjectId}/schedule`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )
  useEffect(() => { const interval = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(interval) }, [])

  const schedule = schedules?.find((item) => item.status === 'ACTIVE')
  const current = useMemo(() => schedule?.items.find((item) => item.scene_status === 'IN_PROGRESS') ?? schedule?.items.find((item) => !['COMPLETED', 'DEFERRED'].includes(item.scene_status)), [schedule])
  const completed = schedule?.items.filter((item) => item.scene_status === 'COMPLETED').length ?? 0
  const selected = useMemo(() => schedules?.find((s) => s.id === selectedId) ?? schedule ?? schedules?.[0] ?? null, [schedules, selectedId, schedule])
  const byDay = useMemo(() => {
    const groups = new Map<string, NonNullable<typeof selected>['items']>()
    selected?.items.forEach((item) => groups.set(item.shooting_date, [...(groups.get(item.shooting_date) ?? []), item]))
    return groups
  }, [selected])
  const elapsed = current?.scene_status === 'IN_PROGRESS' && current.actual_start
    ? Math.max(0, Math.floor((now - new Date(current.actual_start).getTime()) / 60000)) : 0

  async function generate() {
    if (!activeProjectId) return
    setGenerating(true)
    try {
      const s = await post<Schedule>(`/projects/${activeProjectId}/schedule/generate`)
      toast(`Schedule V${s.version_number} is active.`, 'success')
      setSelectedId(s.id)
      await reload()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Schedule generation failed.', 'error') }
    finally { setGenerating(false) }
  }

  async function act(sceneId: string, action: 'start' | 'complete' | 'block') {
    setWorkingId(sceneId)
    try {
      const result = await post<{ scene_status: string; meaningful_delay: boolean }>(`/scenes/${sceneId}/${action}`)
      toast(`Scene ${result.scene_status.toLowerCase().replace('_', ' ')}.`, 'success')
      if (result.meaningful_delay) toast('Meaningful delay detected. Recovery planning is available.', 'info')
      await reload()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Scene action failed.', 'error') }
    finally { setWorkingId(null) }
  }

  if (loading) return <LoadingState label="Loading schedule…" />
  if (error) return <ErrorState error={error} retry={() => reload().catch(() => undefined)} />

  return (
    <>
      <div className="schedule-actions">
        {schedule && activeProjectId && <Button variant="secondary" onClick={() => window.open(`/api/projects/${activeProjectId}/reports/call-sheet/${schedule.id}`, '_blank', 'noopener,noreferrer')}><Download size={16} />Call sheet PDF</Button>}
        <Button loading={generating} disabled={Boolean(schedules?.some((s) => s.status === 'ACTIVE'))} onClick={generate}><Plus size={16} />Generate initial schedule</Button>
      </div>

      {!schedules?.length ? <EmptyState title="No schedule version" description="Confirm production dependencies, then let the CP-SAT solver build a feasible scene-level schedule." action={<Button loading={generating} onClick={generate}><CalendarDays size={17} />Generate schedule V1</Button>} icon={<CalendarDays size={24} />} /> : <>
        <div className="schedule-version-bar">
          <div className="version-list">{schedules.map((s) => <button key={s.id} className={(selected?.id === s.id ? 'active ' : '') + s.status.toLowerCase()} onClick={() => setSelectedId(s.id)}><span>V{s.version_number}</span><strong>{s.type}</strong><small>{s.status}</small></button>)}</div>
          <div className="version-lineage"><GitBranch size={16} /><span>{schedules.length} immutable version{schedules.length === 1 ? '' : 's'} · recovery always creates a new version</span></div>
        </div>

        {schedule && <div className="live-progress"><div><span>Today's progress</span><strong>{completed} / {schedule.items.length} scenes complete</strong></div><div className="progress-track"><i style={{ width: `${(completed / Math.max(1, schedule.items.length)) * 100}%` }} /></div><span>{Math.round((completed / Math.max(1, schedule.items.length)) * 100)}%</span></div>}

        {schedule && current && <div className="live-hero">
          <div className="live-signal"><span /><small>{current.scene_status === 'IN_PROGRESS' ? 'NOW SHOOTING' : 'UP NEXT'}</small></div>
          <div className="live-scene-info"><Badge>SCENE {current.scene_number}</Badge><h1>{current.scene_title}</h1><div className="live-meta"><span><Clock3 size={14} />Plan {current.planned_start.slice(0, 5)}–{current.planned_end.slice(0, 5)}</span><span><TimerReset size={14} />{current.planned_duration_minutes} min planned</span></div>
            <div className="live-actions">
              {current.scene_status !== 'IN_PROGRESS' && <Button loading={workingId === current.scene_id} onClick={() => act(current.scene_id, 'start')}><Play size={16} />Start scene</Button>}
              {current.scene_status === 'IN_PROGRESS' && <Button loading={workingId === current.scene_id} onClick={() => act(current.scene_id, 'complete')}><CheckCircle2 size={16} />Complete scene</Button>}
              <Button variant="danger" loading={workingId === current.scene_id} onClick={() => act(current.scene_id, 'block')}><CircleStop size={16} />Block scene</Button>
            </div>
          </div>
          <div className="live-timer"><span>{current.scene_status === 'IN_PROGRESS' ? 'Elapsed since actual start' : 'Planned duration'}</span><strong>{String(current.scene_status === 'IN_PROGRESS' ? Math.floor(elapsed / 60) : Math.floor(current.planned_duration_minutes / 60)).padStart(2, '0')}:{String(current.scene_status === 'IN_PROGRESS' ? elapsed % 60 : current.planned_duration_minutes % 60).padStart(2, '0')}</strong><small>{current.scene_status === 'IN_PROGRESS' ? (elapsed > current.planned_duration_minutes ? `+${elapsed - current.planned_duration_minutes} min beyond plan` : 'Within planned window') : 'Timer begins when scene starts'}</small></div>
        </div>}

        {schedule && <div className="live-grid">
          <Card className="live-runlist"><div className="section-heading"><div><span>RUN OF SHOW</span><h2>Scene execution</h2></div></div><div className="live-items">{schedule.items.map((item) => <div key={item.id} className={`live-item ${item.scene_status.toLowerCase()} ${current?.id === item.id ? 'selected' : ''}`}><div className="live-item-time"><strong>{item.planned_start.slice(0, 5)}</strong><span>{item.planned_end.slice(0, 5)}</span></div><span className="live-item-status">{item.scene_status === 'COMPLETED' ? <CheckCircle2 /> : item.scene_status === 'BLOCKED' ? <AlertTriangle /> : item.scene_status === 'IN_PROGRESS' ? <Radio /> : <Clock3 />}</span><div><strong>SC {item.scene_number} · {item.scene_title}</strong><small>{item.planned_duration_minutes} minutes · {item.scene_status.replace('_', ' ')}</small></div></div>)}</div></Card>
          <aside className="live-side">
            <Card className="delay-monitor"><div className="section-heading"><div><span>DELAY MONITOR</span><h2>Schedule health</h2></div></div><div className={current && elapsed > current.planned_duration_minutes ? 'delay-bad' : 'delay-good'}>{current && elapsed > current.planned_duration_minutes ? <AlertTriangle /> : <CheckCircle2 />}<strong>{current && elapsed > current.planned_duration_minutes ? 'Schedule at risk' : 'No meaningful delay'}</strong><p>{current && elapsed > current.planned_duration_minutes ? `${elapsed - current.planned_duration_minutes} minutes beyond the planned scene window.` : 'SetRescue will warn when actual timing creates downstream risk.'}</p></div></Card>
            <Card className="operator-note"><AlertTriangle size={20} /><div><strong>Production Manager remains in control</strong><p>Delay detection never changes the schedule automatically. Continue or open recovery explicitly.</p></div></Card>
          </aside>
        </div>}

      </>}
    </>
  )
}
