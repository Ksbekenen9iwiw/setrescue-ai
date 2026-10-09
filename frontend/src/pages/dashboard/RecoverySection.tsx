import { useEffect, useMemo, useState } from 'react'
import { Activity, ArrowRight, Banknote, CheckCircle2, Clock3, Download, GitCompareArrows, LockKeyhole, ShieldAlert, Shuffle, Sparkles, TriangleAlert } from 'lucide-react'
import { api, currency, formatDateTime, post } from '../../lib/api'
import { useApp } from '../../lib/AppContext'
import { useLoad } from '../../lib/hooks'
import type { Incident, RecoveryPlan } from '../../lib/types'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, Modal, VerifiedLabel } from '../../components/ui'
import { CrewPanel } from './CrewPanel'
import type { GoToTab } from './types'

type Generated = { priority: 'TIME' | 'COST' | 'STABILITY'; recommended_type: string; plans: RecoveryPlan[] }
type Approval = { schedule: { id: string; version_number: number }; crew_impact: unknown[]; notification_previews: unknown[] }

export function RecoverySection({ seedIncidentId, onGo }: { seedIncidentId: string | null; onGo: GoToTab }) {
  const { activeProjectId, activeProject, toast, refreshProjects } = useApp()
  const [selectedIncident, setSelectedIncident] = useState<string | null>(seedIncidentId)
  const [priority, setPriority] = useState<'TIME' | 'COST' | 'STABILITY'>('TIME')
  const [generating, setGenerating] = useState(false)
  const [approving, setApproving] = useState<string | null>(null)
  const [approved, setApproved] = useState(false)
  const [detailPlan, setDetailPlan] = useState<RecoveryPlan | null>(null)
  const [confirmPlan, setConfirmPlan] = useState<RecoveryPlan | null>(null)
  const [explaining, setExplaining] = useState(false)
  const { data: incidents, loading: loadingIncidents, error, reload: reloadIncidents } = useLoad(
    () => activeProjectId ? api<Incident[]>(`/projects/${activeProjectId}/incidents`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )
  const { data: savedPlans, reload: reloadPlans, setData: setPlans } = useLoad(
    () => activeProjectId ? api<RecoveryPlan[]>(`/projects/${activeProjectId}/recovery`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )

  useEffect(() => {
    if (seedIncidentId) { setSelectedIncident(seedIncidentId); setApproved(false) }
  }, [seedIncidentId])
  useEffect(() => {
    if (!selectedIncident && incidents?.length) setSelectedIncident(incidents[0].id)
  }, [incidents, selectedIncident])

  const plans = useMemo(() => savedPlans?.filter((plan) => {
    const planWithIncident = plan as RecoveryPlan & { incident_id?: string }
    return !selectedIncident || planWithIncident.incident_id === selectedIncident
  }).slice(0, 3) ?? [], [savedPlans, selectedIncident])
  const incident = incidents?.find((row) => row.id === selectedIncident)
  const recommendedType = priority === 'TIME' ? 'FASTEST' : priority === 'COST' ? 'CHEAPEST' : 'MINIMUM_CHANGE'

  async function generate() {
    if (!selectedIncident) return
    setGenerating(true)
    try {
      const result = await post<Generated>(`/incidents/${selectedIncident}/recovery/generate`, { priority })
      setPlans(result.plans as RecoveryPlan[])
      toast('Three deterministic recovery objectives evaluated.', 'success')
      await reloadPlans()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Recovery generation failed.', 'error') }
    finally { setGenerating(false) }
  }

  async function explainAi() {
    if (!selectedIncident) return
    setExplaining(true)
    try {
      const result = await post<{ plans: RecoveryPlan[]; recommendation: string; cache_hit: boolean }>(`/incidents/${selectedIncident}/recovery/ai-explain`)
      setPlans(result.plans)
      toast(result.cache_hit ? 'AI explanations loaded from cache.' : 'AI trade-off explanations ready.', 'success')
      await reloadPlans()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'AI explanation failed.', 'error') }
    finally { setExplaining(false) }
  }

  async function approve(plan: RecoveryPlan) {
    setApproving(plan.id)
    try {
      const result = await post<Approval>(`/recovery-plans/${plan.id}/approve`)
      toast(`Schedule V${result.schedule.version_number} is now active.`, 'success')
      setConfirmPlan(null)
      setApproved(true)
      await Promise.all([reloadPlans(), refreshProjects()])
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Plan approval failed.', 'error') }
    finally { setApproving(null) }
  }

  if (loadingIncidents) return <LoadingState label="Verifying production incidents…" />
  if (error) return <ErrorState error={error} retry={() => reloadIncidents().catch(() => undefined)} />
  if (!incidents?.length) return <EmptyState title="Recovery starts with a confirmed incident" description="Report the production change and affected scenes before asking the solver for recovery options." action={<Button onClick={() => onGo('incidents')}>Report incident</Button>} icon={<Activity size={24} />} />

  return (
    <>
      <div className="section-toolbar"><div><span className="eyebrow">RECOVER · VERIFIED SHOOTABILITY</span><h2>Recovery planner</h2><p>SetRescue solves the same confirmed dependency graph three ways, then compares finish time, cost, and disruption.</p></div><Button variant="secondary" disabled={!plans.length || !activeProjectId} onClick={() => activeProjectId && window.open(`/api/projects/${activeProjectId}/reports/recovery?incident_id=${selectedIncident}`, '_blank', 'noopener,noreferrer')}><Download size={16} />Comparison PDF</Button></div>
      <Card className="recovery-control">
        <div className="control-incident"><span>RECOVERY INPUT</span><label><select value={selectedIncident ?? ''} onChange={(event) => setSelectedIncident(event.target.value)}>{incidents.map((row) => <option key={row.id} value={row.id}>{row.title} · {row.category.replace('_', ' ')}</option>)}</select></label>{incident && <small>{formatDateTime(incident.reported_at)} · {incident.impacts?.length ?? 0} confirmed impact(s)</small>}</div>
        <div className="control-priority"><span>RECOMMEND FOR</span><div>{(['TIME', 'COST', 'STABILITY'] as const).map((value) => <button key={value} className={priority === value ? 'active' : ''} onClick={() => setPriority(value)}>{value === 'TIME' ? <Clock3 /> : value === 'COST' ? <Banknote /> : <Shuffle />}<span>{value}<small>{value === 'TIME' ? 'Earliest finish' : value === 'COST' ? 'Lowest extra cost' : 'Fewest changes'}</small></span></button>)}</div></div>
        <Button loading={generating} onClick={generate}><Sparkles size={16} />Generate 3 recovery plans</Button>
      </Card>

      {!plans.length ? <div className="recovery-empty"><div className="solver-visual"><span className="node n1">Incident</span><i /><span className="node n2">Verified state</span><i /><span className="node n3">CP-SAT</span><div className="branches"><b>Fastest</b><b>Cheapest</b><b>Minimum change</b></div></div><h2>Ready to find the next shootable sequence</h2><p>Confirmed hard constraints, locked scenes, availability, current weather, setup and work hours will be enforced.</p><Button loading={generating} onClick={generate}>Run recovery solver</Button></div> : <>
        <div className="comparison-heading"><div><span>PLAN COMPARISON</span><h2>Three valid objectives. One management decision.</h2></div><div className="comparison-key"><Button variant="secondary" loading={explaining} onClick={explainAi}><Sparkles size={15} />Explain with AI</Button><VerifiedLabel /><span>Numbers calculated internally</span></div></div>
        <div className="recovery-cards">{plans.map((plan) => {
          const recommended = plan.type === recommendedType
          const icon = plan.type === 'FASTEST' ? Clock3 : plan.type === 'CHEAPEST' ? Banknote : Shuffle
          const Icon = icon
          return <Card key={plan.id} className={`recovery-card ${recommended ? 'recommended' : ''} ${plan.status.toLowerCase()}`}>
            {recommended && <div className="recommended-ribbon">RECOMMENDED FOR {priority}</div>}
            <div className="plan-title"><span><Icon size={21} /></span><div><small>OBJECTIVE</small><h2>{plan.type.replace('_', ' ')}</h2></div><Badge tone={plan.status === 'VALID' ? 'success' : plan.status === 'APPROVED' ? 'info' : 'warning'}>{plan.status}</Badge></div>
            <div className="plan-finish"><span>Estimated finish</span><strong>{formatDateTime(plan.estimated_finish_time)}</strong><small>{plan.estimated_delay_minutes} min delay vs baseline</small></div>
            <div className="plan-metrics"><div><span>Extra cost</span><strong>{currency(plan.estimated_extra_cost, activeProject?.currency)}</strong></div><div><span>Scenes moved</span><strong>{plan.moved_scene_count}</strong></div><div><span>Unresolved</span><strong className={plan.unresolved_scene_count ? 'danger-text' : ''}>{plan.unresolved_scene_count}</strong></div></div>
            <div className="plan-explanation"><Sparkles size={15} /><p>{plan.ai_explanation}</p></div>
            {plan.unresolved_scene_count > 0 && <div className="draft-warning"><TriangleAlert size={16} /><span>Hard constraints leave unresolved scenes. Approval is disabled.</span></div>}
            <div className="plan-actions"><Button variant="secondary" onClick={() => setDetailPlan(plan)}><GitCompareArrows size={15} />Inspect plan</Button><Button disabled={plan.status !== 'VALID' || plan.unresolved_scene_count > 0} onClick={() => setConfirmPlan(plan)}><CheckCircle2 size={15} />Approve</Button></div>
          </Card>
        })}</div>
        <Card className="solver-proof"><LockKeyhole size={21} /><div><strong>Final validation runs again at approval</strong><p>State version, active base schedule, zero unresolved scenes, fixed completed scenes, overlaps, and every confirmed hard constraint are rechecked inside one transaction.</p></div><Badge>STATE V{activeProject?.production_state_version}</Badge></Card>
      </>}

      {approved && <CrewPanel />}

      {detailPlan && <Modal title={`${detailPlan.type.replace('_', ' ')} plan`} description="Solver output and auditable deterministic cost breakdown." onClose={() => setDetailPlan(null)}><div className="plan-detail"><div className="plan-item-list"><div className="detail-heading"><h3>Scene sequence</h3><Badge tone={detailPlan.unresolved_scene_count ? 'warning' : 'success'}>{detailPlan.items.length} scenes</Badge></div>{detailPlan.items.map((item) => <div key={item.id} className={`plan-item ${item.action.toLowerCase()}`}><Badge tone={item.action === 'UNRESOLVED' ? 'danger' : item.action === 'KEEP' ? 'success' : 'info'}>{item.action}</Badge><div><strong>SC {item.scene_number} · {item.scene_title}</strong><span>{item.shooting_date ? `${item.shooting_date} · ${item.start_time?.slice(0, 5)}–${item.end_time?.slice(0, 5)}` : 'No feasible slot'}</span><small>{item.reason}</small></div></div>)}</div><div className="cost-table"><div className="detail-heading"><h3>Cost breakdown</h3><strong>{currency(detailPlan.estimated_extra_cost, activeProject?.currency)}</strong></div>{detailPlan.cost_breakdown.length ? detailPlan.cost_breakdown.map((cost) => <div key={cost.id}><span><strong>{cost.category.replace('_', ' ')}</strong><small>{cost.description}</small></span><b>{currency(cost.amount, activeProject?.currency)}</b></div>) : <p>No incremental recovery cost calculated.</p>}</div><div className="form-actions"><Button variant="ghost" onClick={() => setDetailPlan(null)}>Close</Button>{detailPlan.status === 'VALID' && <Button onClick={() => { setDetailPlan(null); setConfirmPlan(detailPlan) }}>Approve this plan<ArrowRight size={15} /></Button>}</div></div></Modal>}

      {confirmPlan && <Modal title="Approve and activate recovery?" description="This is a sensitive production action and cannot overwrite the prior version." onClose={() => setConfirmPlan(null)}><div className="approval-confirm"><div className="approval-shield"><ShieldAlert size={24} /></div><h3>{confirmPlan.type.replace('_', ' ')} will become the new active schedule</h3><p>SetRescue will atomically revalidate constraints, create a new version, supersede the current active schedule, increment production state, and generate crew-update previews.</p><div className="approval-summary"><span><small>Delay</small><strong>{confirmPlan.estimated_delay_minutes} min</strong></span><span><small>Extra cost</small><strong>{currency(confirmPlan.estimated_extra_cost, activeProject?.currency)}</strong></span><span><small>Moved</small><strong>{confirmPlan.moved_scene_count}</strong></span></div><div className="form-actions"><Button variant="ghost" onClick={() => setConfirmPlan(null)}>Cancel</Button><Button loading={approving === confirmPlan.id} onClick={() => approve(confirmPlan)}>Approve & create schedule V-next</Button></div></div></Modal>}
    </>
  )
}
