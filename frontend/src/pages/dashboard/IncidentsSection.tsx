import { useMemo, useState, type FormEvent } from 'react'
import { AlertTriangle, CloudRain, Cpu, MapPin, Plus, RadioTower, UserRoundX, Wrench } from 'lucide-react'
import { api, formatDateTime, post } from '../../lib/api'
import { useApp } from '../../lib/AppContext'
import { useLoad } from '../../lib/hooks'
import type { Incident, Project, Resource, Scene } from '../../lib/types'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, Modal } from '../../components/ui'

type Detail = Project & { scenes: Scene[]; resources: Resource[] }
const categories = [
  { value: 'WEATHER', label: 'Weather / rain', icon: CloudRain, description: 'Rain, wind, heat or unsafe conditions' },
  { value: 'EQUIPMENT_FAILURE', label: 'Equipment failure', icon: Wrench, description: 'Camera, lighting or sound failure' },
  { value: 'EQUIPMENT_DELAY', label: 'Equipment delay', icon: Cpu, description: 'Rental or delivery unavailable' },
  { value: 'CAST_DELAY', label: 'Cast delay', icon: UserRoundX, description: 'Late or unavailable cast member' },
  { value: 'LOCATION', label: 'Location issue', icon: MapPin, description: 'Access, permit or operational disruption' },
  { value: 'OTHER', label: 'Other disruption', icon: AlertTriangle, description: 'Any verified production interruption' },
] as const

export function IncidentsSection({ onReported }: { onReported: (incidentId: string) => void }) {
  const { activeProjectId, toast } = useApp()
  const [reporting, setReporting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [category, setCategory] = useState('WEATHER')
  const [selectedScenes, setSelectedScenes] = useState<string[]>([])
  const { data: incidents, loading, error, reload } = useLoad(
    () => activeProjectId ? api<Incident[]>(`/projects/${activeProjectId}/incidents`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )
  const { data: detail } = useLoad(
    () => activeProjectId ? api<Detail>(`/projects/${activeProjectId}`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )
  const resourceMap = useMemo(() => new Map(detail?.resources.map((resource) => [resource.id, resource])), [detail])

  function openReport() {
    const current = detail?.scenes.find((scene) => scene.status === 'IN_PROGRESS' || scene.status === 'BLOCKED') ?? detail?.scenes[0]
    setSelectedScenes(current ? [current.id] : [])
    setCategory('WEATHER')
    setReporting(true)
  }

  async function submitIncident(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!activeProjectId || !detail) return
    const form = new FormData(event.currentTarget)
    if (!selectedScenes.length) { toast('Confirm at least one affected scene.', 'error'); return }
    setSaving(true)
    try {
      if (category === 'WEATHER') {
        const firstScene = detail.scenes.find((scene) => scene.id === selectedScenes[0])
        const location = firstScene?.location_id ? resourceMap.get(firstScene.location_id) : detail.resources.find((resource) => resource.type === 'LOCATION')
        if (location) {
          await post(`/projects/${activeProjectId}/weather/manual`, {
            location_id: location.id,
            temperature: form.get('temperature') ? Number(form.get('temperature')) : null,
            rain_probability: Number(form.get('rain_probability') || 100),
            weather_code: String(form.get('weather_code') || 'RAIN'),
          })
        }
      }
      const incident = await post<Incident>(`/projects/${activeProjectId}/incidents`, {
        category,
        resource_id: String(form.get('resource_id')) || null,
        scene_id: selectedScenes[0],
        title: String(form.get('title')),
        description: String(form.get('description')),
        estimated_duration_minutes: form.get('duration') ? Number(form.get('duration')) : null,
        affected_scene_ids: selectedScenes,
        impact_type: 'BLOCKED',
      })
      toast('Incident confirmed. Production state version advanced.', 'success')
      setReporting(false)
      await reload()
      onReported(incident.id)
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Incident could not be reported.', 'error') }
    finally { setSaving(false) }
  }

  if (loading) return <LoadingState label="Loading incident log…" />
  if (error) return <ErrorState error={error} retry={() => reload().catch(() => undefined)} />

  return (
    <>
      <div className="section-toolbar"><div><span className="eyebrow">CONFIRM IMPACT BEFORE RECOVERY</span><h2>Incident command</h2><p>Capture verified disruption facts. Only confirmed fields become solver input.</p></div><Button onClick={openReport}><Plus size={16} />Report incident</Button></div>
      <div className="incident-banner"><div className="incident-radar"><span /><i /><RadioTower size={25} /></div><div><span>OPERATIONAL PRINCIPLE</span><h2>Report what changed. SetRescue verifies what can still be shot.</h2><p>Current manual conditions override forecasts. No recovery plan is generated or applied without your action.</p></div></div>
      {!incidents?.length ? <EmptyState title="No disruptions reported" description="The incident log is clear. Report weather, cast, equipment, or location changes when they affect production." action={<Button onClick={openReport}><AlertTriangle size={16} />Report first incident</Button>} /> : <div className="incident-layout">
        <div className="incident-log">{incidents.map((incident) => {
          const config = categories.find((item) => item.value === incident.category) ?? categories[5]
          const Icon = config.icon
          return <Card key={incident.id} className="incident-row"><div className="incident-type"><Icon size={21} /></div><div className="incident-content"><div><Badge tone="danger">{incident.category.replace('_', ' ')}</Badge><span>{formatDateTime(incident.reported_at)}</span></div><h3>{incident.title}</h3><p>{incident.description || 'No additional description.'}</p><div className="incident-impact"><span>{incident.impacts?.length ?? 0} affected scene(s)</span><span>{incident.estimated_duration_minutes ? `${incident.estimated_duration_minutes} min estimate` : 'Duration unknown'}</span><span>{incident.status}</span></div></div><Button variant="secondary" onClick={() => onReported(incident.id)}>Plan recovery</Button></Card>
        })}</div>
        <aside><Card><div className="section-heading"><div><span>INCIDENT CATEGORIES</span><h2>Structured signal</h2></div></div><div className="category-key">{categories.map(({ value, label, icon: Icon }) => <div key={value}><Icon size={16} /><span>{label}</span><strong>{incidents.filter((incident) => incident.category === value).length}</strong></div>)}</div></Card></aside>
      </div>}

      {reporting && <Modal title="Confirm production incident" description="Only confirmed fields below become authoritative recovery constraints." onClose={() => setReporting(false)}><form className="incident-form" onSubmit={submitIncident}>
        <fieldset><legend>1 · What changed?</legend><div className="category-picker">{categories.map(({ value, label, icon: Icon, description }) => <button type="button" key={value} className={category === value ? 'active' : ''} onClick={() => setCategory(value)}><Icon size={19} /><span><strong>{label}</strong><small>{description}</small></span></button>)}</div></fieldset>
        <fieldset><legend>2 · Confirm impact</legend><div className="form-grid"><label className="span-2">Incident title<input name="title" required maxLength={180} defaultValue={category === 'WEATHER' ? 'Unexpected heavy rain' : ''} /></label><label>Estimated duration (minutes)<input name="duration" type="number" min="0" max="10080" defaultValue="180" /></label><label>Affected resource<select name="resource_id"><option value="">No single resource</option>{detail?.resources.map((resource: Resource) => <option key={resource.id} value={resource.id}>{resource.name} · {resource.type}</option>)}</select></label><label className="span-2">Description<textarea name="description" maxLength={5000} defaultValue={category === 'WEATHER' ? 'Heavy rain has blocked exterior photography and creates unacceptable rain noise for dialogue.' : ''} /></label></div>
          <div className="scene-checklist"><span>Affected scenes</span>{detail?.scenes.map((scene) => <label key={scene.id} className={selectedScenes.includes(scene.id) ? 'selected' : ''}><input type="checkbox" checked={selectedScenes.includes(scene.id)} onChange={(event) => setSelectedScenes((current) => event.target.checked ? [...current, scene.id] : current.filter((id) => id !== scene.id))} /><span><strong>SC {scene.scene_number}</strong>{scene.title}<small>{resourceMap.get(scene.location_id ?? '')?.name ?? 'No location'} · {scene.status}</small></span></label>)}</div>
        </fieldset>
        {category === 'WEATHER' && <fieldset><legend>3 · Actual weather (authoritative now)</legend><div className="form-grid"><label>Condition<select name="weather_code" defaultValue="RAIN"><option value="RAIN">Rain</option><option value="HEAVY_RAIN">Heavy rain</option><option value="DRY">Dry</option><option value="WIND">Strong wind</option></select></label><label>Rain probability / intensity<input name="rain_probability" type="number" min="0" max="100" defaultValue="100" /></label><label>Temperature °C<input name="temperature" type="number" min="-100" max="100" step="0.1" defaultValue="27" /></label></div></fieldset>}
        <div className="authority-note"><span className="confirm-icon">✓</span><div><strong>Production Manager confirmation</strong><p>Submitting updates production state and makes this incident available to the deterministic recovery solver.</p></div></div>
        <div className="form-actions"><Button type="button" variant="ghost" onClick={() => setReporting(false)}>Cancel</Button><Button type="submit" loading={saving}>Confirm incident & continue</Button></div>
      </form></Modal>}
    </>
  )
}
