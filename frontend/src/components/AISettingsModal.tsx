import { useEffect, useState, type FormEvent } from 'react'
import { Bot, CheckCircle2, Database, KeyRound, LockKeyhole, PlugZap, RefreshCw, ServerCog, ShieldCheck } from 'lucide-react'
import { api, post, put } from '../lib/api'
import { useApp } from '../lib/AppContext'
import { useLoad } from '../lib/hooks'
import { Badge, Button, Card, Modal } from './ui'

type AISettings = { id?: string; provider_name: string; base_url: string; model: string; enabled: boolean; api_key_configured: boolean; updated_at?: string }
type Usage = { logs: Array<{ id: string; operation: string; model: string; input_tokens: number; output_tokens: number; total_tokens: number; duration_ms: number; cache_hit: boolean; created_at: string }>; totals: { tokens: number; calls: number; cache_hits: number } }

export function AISettingsModal({ onClose }: { onClose: () => void }) {
  const { toast } = useApp()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [connected, setConnected] = useState(false)
  const { data: settings, loading, error, reload } = useLoad(() => api<AISettings>('/settings/ai'), [])
  const { data: usage, reload: reloadUsage } = useLoad(() => api<Usage>('/settings/ai/usage'), [])
  const [form, setForm] = useState({ provider_name: 'siaptuan.my.id', base_url: '', model: '', api_key: '', enabled: true })
  useEffect(() => {
    if (settings) setForm({ provider_name: settings.provider_name, base_url: settings.base_url, model: settings.model, api_key: '', enabled: settings.enabled })
  }, [settings])

  async function save(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      await put<AISettings>('/settings/ai', { ...form, api_key: form.api_key || null })
      setForm((current) => ({ ...current, api_key: '' }))
      setConnected(false)
      await reload()
      toast('AI settings encrypted and saved locally.', 'success')
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Unable to save settings.', 'error') }
    finally { setSaving(false) }
  }

  async function test() {
    setTesting(true)
    try {
      await post('/settings/ai/test')
      setConnected(true)
      toast('AI provider connection verified.', 'success')
      await reloadUsage()
    } catch (caught) { setConnected(false); toast(caught instanceof Error ? caught.message : 'Connection failed.', 'error') }
    finally { setTesting(false) }
  }

  return (
    <Modal title="AI settings" description="Configure an OpenAI-compatible provider. AI is used for interpretation and explanation — not authoritative scheduling." onClose={onClose}>
      {loading ? <div className="loading-state"><span>Loading local settings…</span></div> : error ? <div className="modal-error">Unable to load settings.</div> : (
        <div className="settings-modal">
          <div className="settings-heading"><span className="settings-icon"><Bot size={22} /></span><div><h2>AI provider</h2><p>OpenAI-compatible API settings for document interpretation.</p></div><Badge tone={connected ? 'success' : settings?.enabled && settings.api_key_configured ? 'info' : 'neutral'}>{connected ? 'CONNECTED' : settings?.api_key_configured ? 'CONFIGURED' : 'NOT CONFIGURED'}</Badge></div>
          <form className="settings-form" onSubmit={save}>
            <label>Provider name<input value={form.provider_name} required maxLength={100} onChange={(event) => setForm({ ...form, provider_name: event.target.value })} /></label>
            <label>Base URL<input type="url" value={form.base_url} required maxLength={500} placeholder="https://your-provider.example/v1" onChange={(event) => setForm({ ...form, base_url: event.target.value })} /><small>Enter your provider's actual OpenAI-compatible API URL. Public HTTPS only.</small></label>
            <label>Model<input value={form.model} required maxLength={160} placeholder="Provider model ID" onChange={(event) => setForm({ ...form, model: event.target.value })} /></label>
            <label>API key<div className="secret-input"><KeyRound size={16} /><input type="password" autoComplete="new-password" value={form.api_key} minLength={8} maxLength={4096} placeholder={settings?.api_key_configured ? 'Stored securely — enter only to replace' : 'Enter API key'} onChange={(event) => setForm({ ...form, api_key: event.target.value })} /></div><small>The stored key is never returned to this browser after save.</small></label>
            <label className="toggle-row"><span><strong>Enable AI features</strong><small>Normal rule engine and solver remain deterministic.</small></span><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} /></label>
            <div className="form-actions"><Button type="button" variant="secondary" loading={testing} disabled={!settings?.api_key_configured} onClick={test}><PlugZap size={15} />Test connection</Button><Button type="submit" loading={saving}><ShieldCheck size={15} />Save securely</Button></div>
          </form>
          <div className="settings-security"><LockKeyhole size={18} /><div><strong>Local key protection</strong><p>Encrypted at rest in SQLite. No endpoint returns the API key.</p></div><CheckCircle2 size={16} /></div>
          <section className="usage-section modal-usage"><div className="section-title-row"><div><span>OBSERVABILITY</span><h2>AI usage & cache</h2></div><Button variant="ghost" onClick={() => reloadUsage().catch(() => undefined)}><RefreshCw size={15} />Refresh</Button></div><div className="usage-metrics"><Card><ServerCog /><span>Actual provider calls</span><strong>{usage?.totals.calls ?? 0}</strong></Card><Card><Database /><span>Valid cache hits</span><strong>{usage?.totals.cache_hits ?? 0}</strong></Card><Card><Bot /><span>Recorded tokens</span><strong>{new Intl.NumberFormat().format(usage?.totals.tokens ?? 0)}</strong></Card></div>{usage?.logs.length ? <div className="resource-table-wrap"><table className="data-table"><thead><tr><th>Operation</th><th>Model</th><th>Tokens</th><th>Duration</th><th>Cache</th><th>Timestamp</th></tr></thead><tbody>{usage.logs.map((log) => <tr key={log.id}><td><strong>{log.operation}</strong></td><td>{log.model || '—'}</td><td>{log.total_tokens}</td><td>{log.duration_ms} ms</td><td><Badge tone={log.cache_hit ? 'success' : 'neutral'}>{log.cache_hit ? 'HIT' : 'API'}</Badge></td><td>{new Date(log.created_at).toLocaleString()}</td></tr>)}</tbody></table></div> : <Card className="compact-empty"><Bot /><span><strong>No AI usage recorded</strong><small>Metrics appear after a document analysis or explanation request.</small></span></Card>}</section>
        </div>
      )}
    </Modal>
  )
}
