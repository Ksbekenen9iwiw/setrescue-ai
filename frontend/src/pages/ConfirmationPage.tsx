import { useState } from 'react'
import { CalendarCheck, CheckCircle2, LoaderCircle, ShieldCheck, UserRoundCheck, UserRoundX } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { api, post } from '../lib/api'
import { useLoad } from '../lib/hooks'
import { Button, Card, ErrorState } from '../components/ui'

type Confirmation = { recipient: string; subject: string; response?: 'AVAILABLE' | 'UNAVAILABLE'; expires_at: string }
type Result = { response: 'AVAILABLE' | 'UNAVAILABLE'; schedule_no_longer_valid: boolean }

export function ConfirmationPage() {
  const { token = '' } = useParams()
  const [submitting, setSubmitting] = useState<'AVAILABLE' | 'UNAVAILABLE' | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const { data, loading, error, reload } = useLoad(() => api<Confirmation>(`/confirmations/${encodeURIComponent(token)}`), [token])

  async function respond(response: 'AVAILABLE' | 'UNAVAILABLE') {
    setSubmitting(response)
    try {
      const submitted = await post<Result>(`/confirmations/${encodeURIComponent(token)}`, { response })
      setResult(submitted)
      await reload()
    } finally {
      setSubmitting(null)
    }
  }

  if (loading) return <div className="confirmation-page"><LoaderCircle className="animate-spin" /><span>Opening secure confirmation…</span></div>
  if (error || !data) return <div className="confirmation-page"><div className="confirmation-wrap"><div className="public-brand"><span><CalendarCheck /></span><strong>SETRESCUE</strong></div><ErrorState error={error} /></div></div>
  const response = result?.response ?? data.response
  return (
    <div className="confirmation-page">
      <div className="confirmation-wrap">
        <div className="public-brand"><span><CalendarCheck /></span><strong>SETRESCUE</strong><small>Production availability confirmation</small></div>
        <Card className="confirmation-card">
          {response ? <div className="confirmation-result"><span className={response === 'AVAILABLE' ? 'yes' : 'no'}>{response === 'AVAILABLE' ? <UserRoundCheck /> : <UserRoundX />}</span><BadgeLike>{response}</BadgeLike><h1>Thank you—your response is recorded.</h1><p>{response === 'AVAILABLE' ? 'Production management can see that you are available for the updated schedule.' : 'Production management has been alerted that the active schedule may no longer be valid.'}</p>{result?.schedule_no_longer_valid && <div className="schedule-invalid">The affected schedule is now flagged for manual recovery review.</div>}</div> : <>
            <div className="confirmation-icon"><ShieldCheck /></div><span className="confirmation-kicker">CREW SCHEDULE UPDATE</span><h1>Can you make the updated call?</h1><p className="confirmation-subject">{data.subject}</p><div className="confirmation-recipient"><span>Confirmation for</span><strong>{data.recipient}</strong><small>Link expires {new Date(data.expires_at).toLocaleString()}</small></div><div className="confirmation-actions"><Button loading={submitting === 'AVAILABLE'} disabled={Boolean(submitting)} onClick={() => respond('AVAILABLE')}><CheckCircle2 />I’m available</Button><Button variant="danger" loading={submitting === 'UNAVAILABLE'} disabled={Boolean(submitting)} onClick={() => respond('UNAVAILABLE')}><UserRoundX />I’m unavailable</Button></div><div className="privacy-note"><ShieldCheck size={14} />No account is required. This one-time production link is stored as a secure hash.</div>
          </>}
        </Card>
      </div>
    </div>
  )
}

function BadgeLike({ children }: { children: string }) {
  return <span className="confirmation-badge">{children}</span>
}
