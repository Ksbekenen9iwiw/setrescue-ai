import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, LoaderCircle, Sparkles } from 'lucide-react'

export function Button({ className = '', variant = 'primary', loading, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; loading?: boolean }) {
  return (
    <button className={`btn btn-${variant} ${className}`} disabled={loading || props.disabled} {...props}>
      {loading && <LoaderCircle size={16} className="animate-spin" />}
      {children}
    </button>
  )
}

export function Badge({ children, tone = 'neutral', className = '' }: { children: ReactNode; tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'ai' | 'info'; className?: string }) {
  return <span className={`badge badge-${tone} ${className}`}>{children}</span>
}

export function Card({ className = '', children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card ${className}`} {...props}>{children}</div>
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon ?? <Sparkles size={22} />}</div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <Card className="error-state">
      <AlertTriangle size={22} />
      <div><strong>Unable to load this view</strong><p>{message}</p></div>
      {retry && <Button variant="secondary" onClick={retry}>Try again</Button>}
    </Card>
  )
}

export function LoadingState({ label = 'Loading production state…' }: { label?: string }) {
  return <div className="loading-state"><LoaderCircle className="animate-spin" size={22} /><span>{label}</span></div>
}

export function VerifiedLabel({ ai = false }: { ai?: boolean }) {
  return ai ? <span className="fact-label ai"><Sparkles size={12} />AI suggestion</span> : <span className="fact-label verified"><CheckCircle2 size={12} />Verified fact</span>
}

export function Metric({ label, value, detail, tone = 'default' }: { label: string; value: ReactNode; detail?: ReactNode; tone?: 'default' | 'success' | 'warning' | 'danger' }) {
  return <Card className={`metric metric-${tone}`}><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</Card>
}

export function Modal({ title, description, children, onClose }: { title: string; description?: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-header"><div><h2>{title}</h2>{description && <p>{description}</p>}</div><button type="button" className="icon-button" onClick={onClose} aria-label="Close">×</button></div>
        {children}
      </div>
    </div>
  )
}
