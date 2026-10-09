import { useMemo, useState } from 'react'
import { BellRing, CheckCircle2, ExternalLink, Mail, Send, UsersRound } from 'lucide-react'
import { api, post } from '../../lib/api'
import { useApp } from '../../lib/AppContext'
import { useLoad } from '../../lib/hooks'
import type { Notification, Schedule } from '../../lib/types'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../../components/ui'

type CrewImpact = { resource_id: string; name: string; email?: string; can_notify: boolean; changed_scenes: Array<{ scene_id: string; date: string; start: string }> }
type SentResult = { notification_id: string; status: string; recipient_email: string; confirmation_url?: string }

export function CrewPanel() {
  const { activeProjectId, toast } = useApp()
  const [previews, setPreviews] = useState<Notification[]>([])
  const [sent, setSent] = useState<SentResult[]>([])
  const [working, setWorking] = useState(false)
  const { data: schedules, loading, error, reload } = useLoad(
    () => activeProjectId ? api<Schedule[]>(`/projects/${activeProjectId}/schedule`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )
  const active = useMemo(() => schedules?.find((schedule) => schedule.status === 'ACTIVE') ?? null, [schedules])
  const { data: impact, loading: impactLoading, reload: reloadImpact } = useLoad(
    () => active?.id ? api<CrewImpact[]>(`/schedules/${active.id}/crew-impact`) : Promise.resolve([]),
    [active?.id],
  )

  async function generatePreviews() {
    if (!active) return
    setWorking(true)
    try {
      const rows = await post<Notification[]>(`/schedules/${active.id}/notifications/preview`)
      setPreviews(rows)
      toast(`${rows.length} crew update preview(s) prepared.`, rows.length ? 'success' : 'info')
      await reloadImpact()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Unable to generate previews.', 'error') }
    finally { setWorking(false) }
  }

  async function sendAll() {
    if (!active || !previews.length) return
    setWorking(true)
    try {
      const rows = await post<SentResult[]>(`/schedules/${active.id}/notifications/send`, { notification_ids: previews.map((item) => item.id) })
      setSent(rows)
      setPreviews((current) => current.map((item) => ({ ...item, status: 'SENT' })))
      toast('Crew updates sent in demo email mode.', 'success')
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Unable to send updates.', 'error') }
    finally { setWorking(false) }
  }

  if (loading || impactLoading) return <LoadingState label="Calculating crew impact…" />
  if (error) return <ErrorState error={error} retry={() => reload().catch(() => undefined)} />
  if (!active) return <EmptyState title="No active schedule" description="Crew impact is available after an active schedule exists." icon={<UsersRound size={24} />} />
  if (!active.parent_schedule_id) return <EmptyState title="Crew updates begin after recovery" description="The baseline schedule has no previous version to compare. Approve a recovery plan to identify affected cast and crew." icon={<BellRing size={24} />} />

  return (
    <section className="crew-panel">
      <div className="section-toolbar"><div><span className="eyebrow">SCHEDULE V{active.version_number} · CREW COORDINATION</span><h2>Crew updates</h2><p>Preview impact and collect availability through account-free confirmation links.</p></div><div className="page-actions"><Button variant="secondary" loading={working} onClick={generatePreviews}><Mail size={16} />Generate previews</Button><Button loading={working} disabled={!previews.length} onClick={sendAll}><Send size={16} />Send all</Button></div></div>
      <div className="crew-summary"><div><span>IMPACTED PEOPLE</span><strong>{impact?.length ?? 0}</strong><small>Confirmed cast/crew dependencies on moved scenes</small></div><div><span>NOTIFIABLE</span><strong>{impact?.filter((item) => item.can_notify).length ?? 0}</strong><small>Resources with valid email addresses</small></div><div><span>PREVIEWS</span><strong>{previews.length}</strong><small>Generated but never sent automatically</small></div><div><span>DELIVERY MODE</span><strong>DEMO</strong><small>Confirmation links shown locally</small></div></div>
      {!impact?.length ? <EmptyState title="No cast or crew affected" description="The active recovery schedule did not move scenes tied to contactable cast or crew resources." /> : <div className="crew-layout">
        <div className="impact-list">{impact.map((person) => <Card key={person.resource_id} className="impact-person"><div className="person-avatar">{person.name.split(' ').map((part) => part[0]).slice(0, 2).join('')}</div><div className="person-main"><div><h3>{person.name}</h3><Badge tone={person.can_notify ? 'success' : 'warning'}>{person.can_notify ? person.email : 'No email'}</Badge></div><p>{person.changed_scenes.length} changed scene call{person.changed_scenes.length === 1 ? '' : 's'}</p><div className="changed-calls">{person.changed_scenes.map((scene) => <span key={scene.scene_id}><strong>{scene.date}</strong> at {scene.start}</span>)}</div></div></Card>)}</div>
        <aside><Card className="notification-workflow"><div className="section-heading"><div><span>CONTROLLED WORKFLOW</span><h2>From preview to response</h2></div></div><ol><li className={previews.length ? 'done' : 'active'}><span>{previews.length ? <CheckCircle2 /> : '1'}</span><div><strong>Preview update</strong><small>Review subject, body, and recipients</small></div></li><li className={sent.length ? 'done' : previews.length ? 'active' : ''}><span>{sent.length ? <CheckCircle2 /> : '2'}</span><div><strong>Explicit send</strong><small>Demo email or optional Resend adapter</small></div></li><li className={sent.length ? 'active' : ''}><span>3</span><div><strong>Crew confirms</strong><small>Available / unavailable without login</small></div></li><li><span>4</span><div><strong>Schedule signal</strong><small>Unavailable responses invalidate affected schedule</small></div></li></ol></Card></aside>
      </div>}
      {previews.length > 0 && <section className="preview-section"><div className="section-title-row"><div><span>EMAIL PREVIEW</span><h2>Review before sending</h2></div><Badge>{previews.length} messages</Badge></div><div className="email-previews">{previews.map((notification) => {
        const delivery = sent.find((row) => row.notification_id === notification.id)
        return <Card key={notification.id} className="email-card"><div className="email-header"><span className="email-avatar"><Mail size={17} /></span><div><strong>{notification.recipient_email}</strong><small>{notification.status}</small></div><Badge tone={notification.status === 'SENT' ? 'success' : 'neutral'}>{notification.status}</Badge></div><div className="email-content"><span>SUBJECT</span><h3>{notification.subject}</h3><p>{notification.body}</p>{delivery?.confirmation_url && <a href={delivery.confirmation_url} target="_blank" rel="noreferrer">Open demo confirmation link <ExternalLink size={13} /></a>}</div></Card>
      })}</div></section>}
    </section>
  )
}
