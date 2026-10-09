import { useMemo, useState } from 'react'
import { AlertOctagon, CheckCircle2, ChevronRight, Download, Eye, RefreshCw, ShieldCheck, Sparkles, XCircle } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, post } from '../../lib/api'
import { useApp } from '../../lib/AppContext'
import { useLoad } from '../../lib/hooks'
import type { PreventIssue, PreventRun, Project, Requirement, Scene } from '../../lib/types'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, Modal, VerifiedLabel } from '../../components/ui'

type ProjectDetail = Project & { scenes: Scene[] }

export function ReadinessSection() {
  const { activeProjectId, toast } = useApp()
  const [running, setRunning] = useState(false)
  const [workingId, setWorkingId] = useState<string | null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [preview, setPreview] = useState<PreventIssue | null>(null)
  const { data: run, loading, error, reload, setData: setRun } = useLoad(
    () => activeProjectId ? api<PreventRun | null>(`/projects/${activeProjectId}/prevent`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )
  const { data: detail, reload: reloadDetail } = useLoad(
    () => activeProjectId ? api<ProjectDetail>(`/projects/${activeProjectId}`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )

  const suggestions = useMemo(() => detail?.scenes.flatMap((scene) => scene.requirements.filter((req) => req.confirmation_status === 'SUGGESTED').map((req) => ({ ...req, scene }))) ?? [], [detail])
  const chartData = Object.entries(run?.category_scores ?? {}).map(([name, score]) => ({ name: name.replaceAll('_', ' '), score }))

  async function runCheck() {
    if (!activeProjectId) return
    setRunning(true)
    try {
      const result = await post<PreventRun>(`/projects/${activeProjectId}/prevent/run`)
      setRun(result)
      toast(`PREVENT completed: ${result.status.replace('_', ' ')} at ${result.overall_score.toFixed(1)}.`, result.status === 'READY' ? 'success' : 'info')
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'PREVENT could not run.', 'error') }
    finally { setRunning(false) }
  }

  async function runAiReview() {
    if (!activeProjectId) return
    setReviewing(true)
    try {
      const result = await post<PreventRun>(`/projects/${activeProjectId}/prevent/ai-review`)
      setRun(result)
      toast('AI readiness review updated. Advisory only — the score stays deterministic.', 'success')
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'AI review failed.', 'error') }
    finally { setReviewing(false) }
  }

  async function decide(requirement: Requirement, decision: 'CONFIRMED' | 'REJECTED', hard = false) {
    if (!activeProjectId) return
    setWorkingId(requirement.id)
    try {
      await post(`/projects/${activeProjectId}/requirements/${requirement.id}/decision`, { decision, is_hard_constraint: decision === 'CONFIRMED' ? hard : null })
      toast(decision === 'CONFIRMED' ? 'Suggestion confirmed. Run PREVENT again to refresh the score.' : 'Suggestion rejected.', 'success')
      await reloadDetail()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Decision failed.', 'error') }
    finally { setWorkingId(null) }
  }

  async function resolveIssue(issue: PreventIssue, confirmPatch = false) {
    if (!activeProjectId) return
    setWorkingId(issue.id)
    try {
      await post(`/projects/${activeProjectId}/prevent/issues/${issue.id}`, { action: 'RESOLVED', confirm_patch: confirmPatch })
      toast(confirmPatch ? 'Previewed patch applied and issue marked resolved.' : 'Issue marked resolved.', 'success')
      setPreview(null)
      await reload()
      if (confirmPatch) await reloadDetail()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Unable to resolve finding.', 'error') }
    finally { setWorkingId(null) }
  }

  if (loading) return <LoadingState label="Loading readiness model…" />
  if (error) return <ErrorState error={error} retry={() => reload().catch(() => undefined)} />
  const statusTone = run?.status === 'READY' ? 'success' : run?.status === 'NOT_READY' ? 'danger' : 'warning'
  const openIssues = run?.issues.filter((issue) => issue.status === 'OPEN') ?? []

  return (
    <>
      <div className="section-toolbar"><div><span className="eyebrow">PREVENT · READINESS CONTROL</span><h2>Is this production actually ready?</h2><p>Shot-level completeness and confirmed dependencies are scored deterministically. Blockers always override the number.</p></div><div className="page-actions"><Button variant="secondary" disabled={!run} onClick={() => activeProjectId && window.open(`/api/projects/${activeProjectId}/reports/prevent`, '_blank', 'noopener,noreferrer')}><Download size={16} />Export report</Button><Button loading={running} onClick={runCheck}><RefreshCw size={16} />{run ? 'Run again' : 'Run PREVENT'}</Button></div></div>

      {!run ? <EmptyState title="No readiness baseline" description="Run PREVENT to calculate category scores, blockers, and required actions from verified production data." action={<Button loading={running} onClick={runCheck}><ShieldCheck size={17} />Run deterministic check</Button>} icon={<ShieldCheck size={25} />} /> : <>
        <div className={`prevent-hero ${run.status.toLowerCase().replace('_', '-')}`}>
          <div className="readiness-ring" style={{ '--score': `${run.overall_score * 3.6}deg` } as React.CSSProperties}><div><strong>{Math.round(run.overall_score)}</strong><span>/100</span></div></div>
          <div className="prevent-summary"><Badge tone={statusTone}>{run.status.replace('_', ' ')}</Badge><h2>{run.status === 'READY' ? 'Production dependencies are verified.' : run.status === 'NOT_READY' ? 'A hard blocker prevents production.' : 'Review remaining gaps before the camera rolls.'}</h2><p>{openIssues.filter((issue) => issue.severity === 'CRITICAL').length} critical · {openIssues.filter((issue) => issue.severity === 'WARNING').length} warnings · {suggestions.length} suggestions awaiting review</p><div className="rule-note"><ShieldCheck size={15} />Calculated locally from confirmed requirements. AI confidence does not affect this score.</div></div>
          <div className="prevent-legend"><span><i className="good" />85–100 Ready</span><span><i className="review" />Review required</span><span><i className="bad" />Hard blocker</span></div>
        </div>

        <div className="prevent-grid">
          <Card className="category-chart-card"><div className="section-heading"><div><span>WEIGHTED CATEGORIES</span><h2>Readiness by discipline</h2></div><VerifiedLabel /></div><ResponsiveContainer width="100%" height={310}><BarChart data={chartData} layout="vertical" margin={{ left: 18, right: 24 }}><CartesianGrid horizontal={false} stroke="#eaecf0" /><XAxis type="number" domain={[0, 100]} tickLine={false} axisLine={false} /><YAxis dataKey="name" type="category" width={150} tickLine={false} axisLine={false} fontSize={10} /><Tooltip cursor={{ fill: '#f8fafc' }} /><Bar dataKey="score" fill="#ef5a3c" radius={[0, 5, 5, 0]} barSize={15} /></BarChart></ResponsiveContainer></Card>
          <Card className="blocker-card"><div className="section-heading"><div><span>BLOCKER LOGIC</span><h2>Why this status?</h2></div></div><div className="blocker-rules"><div className={run.status !== 'NOT_READY' ? 'pass' : 'fail'}>{run.status !== 'NOT_READY' ? <CheckCircle2 /> : <AlertOctagon />}<span><strong>No failed hard constraint</strong><small>Overrides numerical readiness</small></span></div><div className={!openIssues.some((issue) => issue.severity === 'CRITICAL') ? 'pass' : 'fail'}>{!openIssues.some((issue) => issue.severity === 'CRITICAL') ? <CheckCircle2 /> : <XCircle />}<span><strong>No open critical finding</strong><small>{openIssues.filter((issue) => issue.severity === 'CRITICAL').length} currently open</small></span></div><div className={!suggestions.length ? 'pass' : 'review'}>{!suggestions.length ? <CheckCircle2 /> : <Sparkles />}<span><strong>Suggestions reviewed</strong><small>{suggestions.length} need human confirmation</small></span></div><div className={run.overall_score >= 85 ? 'pass' : 'review'}>{run.overall_score >= 85 ? <CheckCircle2 /> : <ShieldCheck />}<span><strong>Score at least 85</strong><small>Current weighted score {run.overall_score.toFixed(1)}</small></span></div></div></Card>
        </div>

        <Card className="blocker-card ai-review-card">
          <div className="section-heading"><div><span>AI READINESS REVIEW</span><h2>Executive summary</h2></div><div className="page-actions"><Button variant="secondary" loading={reviewing} onClick={runAiReview}><Sparkles size={16} />{run.ai_summary ? 'Regenerate' : 'Generate AI summary'}</Button></div></div>
          {!run.ai_summary ? <p className="ai-review-hint">Generate a plain-language briefing of the current findings. The narrative is advisory and never changes the deterministic score above.</p> : <><p className="ai-review-summary">{run.ai_summary.summary}</p>
            {run.ai_summary.top_risks.length > 0 && <div className="ai-review-block"><span>Top risks</span><ul>{run.ai_summary.top_risks.map((risk, index) => <li key={index}><Badge tone={risk.severity === 'CRITICAL' ? 'danger' : risk.severity === 'WARNING' ? 'warning' : 'neutral'}>{risk.severity}</Badge><strong>{risk.title}</strong><p>{risk.detail}</p></li>)}</ul></div>}
            {run.ai_summary.next_actions.length > 0 && <div className="ai-review-block"><span>Next actions</span><ol>{run.ai_summary.next_actions.map((action, index) => <li key={index}>{action}</li>)}</ol></div>}
          </>}
        </Card>
      </>}

      <div className="prevent-columns">
        <section>
          <div className="section-title-row"><div><span>VERIFICATION QUEUE</span><h2>AI & document suggestions</h2></div><Badge tone={suggestions.length ? 'ai' : 'success'}>{suggestions.length} pending</Badge></div>
          {!suggestions.length ? <Card className="compact-empty"><CheckCircle2 /><span><strong>Suggestion queue clear</strong><small>No unconfirmed AI requirements remain.</small></span></Card> : <div className="suggestion-list">{suggestions.map(({ scene, ...requirement }) => <Card key={requirement.id} className="suggestion-card"><div className="suggestion-top"><VerifiedLabel ai /><span className={`confidence ${(requirement.confidence ?? 0) >= .8 ? 'high' : (requirement.confidence ?? 0) >= .6 ? 'medium' : 'low'}`}>{Math.round((requirement.confidence ?? 0) * 100)}% confidence</span></div><h3>{requirement.name}</h3><p>Scene {scene.scene_number} · {scene.title}</p><div className="suggestion-meta"><Badge>{requirement.category}</Badge><span>Suggested hard constraint: <b>{requirement.is_hard_constraint ? 'yes' : 'not yet'}</b></span></div><div className="suggestion-actions"><Button variant="ghost" loading={workingId === requirement.id} onClick={() => decide(requirement, 'REJECTED')}>Reject</Button><Button variant="secondary" loading={workingId === requirement.id} onClick={() => decide(requirement, 'CONFIRMED', false)}>Confirm soft</Button><Button loading={workingId === requirement.id} onClick={() => decide(requirement, 'CONFIRMED', true)}>Confirm hard</Button></div></Card>)}</div>}
        </section>
        <section>
          <div className="section-title-row"><div><span>ACTION QUEUE</span><h2>Readiness findings</h2></div><Badge tone={openIssues.length ? 'warning' : 'success'}>{openIssues.length} open</Badge></div>
          {!openIssues.length ? <Card className="compact-empty"><CheckCircle2 /><span><strong>No open findings</strong><small>Run PREVENT after any production-state change.</small></span></Card> : <div className="issue-list">{openIssues.map((issue) => <Card key={issue.id} className={`issue-card ${issue.severity.toLowerCase()}`}><div className="issue-severity"><span>{issue.severity}</span><Badge tone={issue.source === 'AI_SUGGESTED' ? 'ai' : 'neutral'}>{issue.source}</Badge></div><h3>{issue.title}</h3><p>{issue.description}</p><div className="recommendation"><strong>Recommended action</strong><span>{issue.recommended_action}</span></div><div className="issue-actions">{issue.proposed_patch ? <Button variant="secondary" onClick={() => setPreview(issue)}><Eye size={15} />Preview suggestion</Button> : <Button variant="secondary" loading={workingId === issue.id} onClick={() => resolveIssue(issue)}>Mark resolved</Button>}<ChevronRight size={16} /></div></Card>)}</div>}
        </section>
      </div>

      {preview && <Modal title="Preview proposed patch" description="Nothing changes until you explicitly confirm this preview." onClose={() => setPreview(null)}><div className="patch-preview"><div className="patch-warning"><Eye size={20} /><div><strong>Human approval required</strong><p>AI/rule suggestions never mutate production data directly.</p></div></div><div className="diff-block"><span>PROPOSED CHANGE</span><code>+ Add placeholder shot to scene {preview.proposed_patch?.scene_id}<br />+ description: “Placeholder shot — edit before production”<br />+ frame / movement: TBD<br />+ estimated duration: 10 minutes</code></div><p>This resolves the completeness finding, but you should edit the placeholder details before production.</p><div className="form-actions"><Button variant="ghost" onClick={() => setPreview(null)}>Cancel</Button><Button loading={workingId === preview.id} onClick={() => resolveIssue(preview, true)}>Confirm & apply patch</Button></div></div></Modal>}
    </>
  )
}
