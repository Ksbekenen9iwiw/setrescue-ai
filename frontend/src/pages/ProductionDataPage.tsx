import { useMemo, useState, type FormEvent } from 'react'
import { BrainCircuit, Check, FileSpreadsheet, FileText, Plus, ShieldCheck, UploadCloud, UsersRound } from 'lucide-react'
import { api, post } from '../lib/api'
import { useApp } from '../lib/AppContext'
import { useLoad } from '../lib/hooks'
import type { DocumentRecord, Project, Resource, Scene } from '../lib/types'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, Modal, VerifiedLabel } from '../components/ui'
import { ReadinessSection } from './production/ReadinessSection'

type ProjectDetail = Project & { scenes: Scene[]; resources: Resource[]; documents: DocumentRecord[] }
type StructuredPreview = { document_id: string; version_id: string; type: string; count: number; can_apply: boolean; notes: string[]; items: Record<string, string | number | null>[] }
const docTypes = ['SCRIPT', 'SHOT_LIST', 'CALL_SHEET', 'RESOURCE_SHEET'] as const
type Tab = 'documents' | 'scenes' | 'resources' | 'readiness'

export function ProductionDataPage() {
  const { activeProjectId, toast } = useApp()
  const [activeTab, setActiveTab] = useState<Tab>('documents')
  const [uploading, setUploading] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [modal, setModal] = useState<'scene' | 'resource' | null>(null)
  const [saving, setSaving] = useState(false)
  const [importPreview, setImportPreview] = useState<StructuredPreview | null>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)
  const { data, loading, error, reload } = useLoad(
    () => activeProjectId ? api<ProjectDetail>(`/projects/${activeProjectId}`) : Promise.reject(new Error('Select a project first.')),
    [activeProjectId],
  )
  const locations = useMemo(() => data?.resources.filter((resource) => resource.type === 'LOCATION') ?? [], [data])

  async function upload(type: string, file?: File) {
    if (!activeProjectId || !file) return
    const form = new FormData()
    form.set('document_type', type)
    form.set('file', file)
    setUploading(type)
    try {
      await api(`/projects/${activeProjectId}/documents`, { method: 'POST', body: form })
      toast(`${type.replace('_', ' ')} uploaded and parsed locally.`, 'success')
      await reload()
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : 'Upload failed.', 'error')
    } finally {
      setUploading(null)
    }
  }

  async function analyze() {
    if (!activeProjectId) return
    setAnalyzing(true)
    try {
      const result = await post<{ suggestions_created: number; unknown_scene_references: string[]; cache_hit: boolean }>(`/projects/${activeProjectId}/documents/analyze`)
      toast(`${result.suggestions_created} AI suggestions created${result.cache_hit ? ' from cache' : ''}.`, 'success')
      await reload()
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : 'AI analysis failed.', 'error')
    } finally {
      setAnalyzing(false)
    }
  }

  async function previewImport(documentId: string) {
    if (!activeProjectId) return
    setPreviewing(documentId)
    try {
      const result = await api<StructuredPreview>(`/projects/${activeProjectId}/documents/${documentId}/import-preview`)
      setImportPreview(result)
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Unable to preview this spreadsheet.', 'error') }
    finally { setPreviewing(null) }
  }

  async function applyImport() {
    if (!activeProjectId || !importPreview?.can_apply) return
    setSaving(true)
    try {
      const result = await post<{ created: number; skipped: number; unknown_scene_numbers: string[] }>(
        `/projects/${activeProjectId}/documents/${importPreview.document_id}/apply-import`,
        { version_id: importPreview.version_id },
      )
      toast(`${result.created} verified records imported; ${result.skipped} duplicates skipped.${result.unknown_scene_numbers.length ? ` ${result.unknown_scene_numbers.length} unknown scene references skipped.` : ''}`, 'success')
      const kind = importPreview.type
      setImportPreview(null)
      setActiveTab(kind === 'RESOURCE_SHEET' ? 'resources' : 'scenes')
      await reload()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Import could not be applied.', 'error') }
    finally { setSaving(false) }
  }

  async function createScene(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!activeProjectId) return
    const form = new FormData(event.currentTarget)
    setSaving(true)
    try {
      await post(`/projects/${activeProjectId}/scenes`, {
        scene_number: String(form.get('scene_number')), title: String(form.get('title')),
        description: String(form.get('description')), location_id: String(form.get('location_id')) || null,
        estimated_duration_minutes: Number(form.get('duration')), setup_minutes: Number(form.get('setup')), priority: Number(form.get('priority')),
      })
      toast('Scene added to structured production data.', 'success')
      setModal(null)
      await reload()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Unable to add scene.', 'error') }
    finally { setSaving(false) }
  }

  async function createResource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!activeProjectId) return
    const form = new FormData(event.currentTarget)
    setSaving(true)
    try {
      await post(`/projects/${activeProjectId}/resources`, {
        name: String(form.get('name')), type: String(form.get('type')), subtype: String(form.get('subtype')),
        email: String(form.get('email')) || null, default_cost: Number(form.get('default_cost') || 0),
        address: String(form.get('address')) || null,
      })
      toast('Resource added.', 'success')
      setModal(null)
      await reload()
    } catch (caught) { toast(caught instanceof Error ? caught.message : 'Unable to add resource.', 'error') }
    finally { setSaving(false) }
  }

  if (loading) return <LoadingState label="Loading production data…" />
  if (error || !data) return <ErrorState error={error} retry={() => reload().catch(() => undefined)} />

  const documentByType = new Map(data.documents.map((document) => [document.type, document]))
  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">INGEST · STRUCTURE · VERIFY</div>
          <h1>Production Data</h1>
          <p>Upload documents, verify structured scenes and resources, and run deterministic readiness checks.</p>
        </div>
        {/* {activeTab !== 'readiness' && <div className="page-actions"><Button variant="secondary" loading={analyzing} disabled={!data.documents.length} onClick={analyze}><BrainCircuit size={16} />Analyze with AI</Button></div>} */}
      </div>
      <div className="tabbar">
        <button className={activeTab === 'documents' ? 'active' : ''} onClick={() => setActiveTab('documents')}><FileText size={16} />Documents <span>{data.documents.length}</span></button>
        <button className={activeTab === 'scenes' ? 'active' : ''} onClick={() => setActiveTab('scenes')}><FileSpreadsheet size={16} />Scenes & shots <span>{data.scenes.length}</span></button>
        <button className={activeTab === 'resources' ? 'active' : ''} onClick={() => setActiveTab('resources')}><UsersRound size={16} />Resources <span>{data.resources.length}</span></button>
        <button className={activeTab === 'readiness' ? 'active' : ''} onClick={() => setActiveTab('readiness')}><ShieldCheck size={16} />Readiness</button>
      </div>

      {activeTab === 'documents' && <div className="document-grid">
        {docTypes.map((type) => {
          const document = documentByType.get(type)
          const current = document?.versions.find((version) => version.version_number === document.current_version)
          return <Card key={type} className="document-card">
            <div className="document-icon">{type === 'SCRIPT' ? <FileText /> : <FileSpreadsheet />}</div>
            <div className="document-card-head"><div><span>{type.replace('_', ' ')}</span><h2>{current?.original_filename ?? 'Not uploaded'}</h2></div>{document ? <Badge tone="success"><Check size={12} />V{document.current_version}</Badge> : <Badge>REQUIRED INPUT</Badge>}</div>
            <p>{type === 'SCRIPT' ? 'Scene descriptions and narrative context.' : type === 'SHOT_LIST' ? 'Shot-level framing, movement, setup and duration.' : type === 'CALL_SHEET' ? 'Existing schedule, call times and locations.' : 'Cast, crew, equipment and availability.'}</p>
            {current && <div className="file-facts"><span>SHA-256 <code>{current.file_hash.slice(0, 10)}…</code></span><span>{new Date(current.created_at).toLocaleString()}</span></div>}
            <label className={`upload-button ${uploading === type ? 'disabled' : ''}`}><UploadCloud size={16} />{uploading === type ? 'Parsing locally…' : document ? 'Upload new version' : 'Choose PDF or XLSX'}<input type="file" accept=".pdf,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={Boolean(uploading)} onChange={(event) => { const file = event.target.files?.[0]; void upload(type, file); event.currentTarget.value = '' }} /></label>
            {document && current?.file_type === '.xlsx' && <Button variant="secondary" loading={previewing === document.id} onClick={() => previewImport(document.id)}><Check size={15} />Preview structured import</Button>}
          </Card>
        })}
        <Card className="document-note"><BrainCircuit size={20} /><div><VerifiedLabel ai /><h3>AI never writes authoritative constraints</h3><p>Detected requirements appear as suggestions. A Production Manager must confirm them before solver enforcement.</p></div></Card>
      </div>}

      {activeTab === 'scenes' && <>
        <div className="list-toolbar"><div><strong>{data.scenes.length} scenes</strong><span>{data.scenes.reduce((sum, scene) => sum + scene.shots.length, 0)} shots extracted or entered</span></div><Button onClick={() => setModal('scene')}><Plus size={16} />Add scene</Button></div>
        {!data.scenes.length ? <EmptyState title="No structured scenes" description="Upload a script/shot list or add a scene manually." action={<Button onClick={() => setModal('scene')}>Add first scene</Button>} /> : <div className="scene-list">{data.scenes.map((scene) => <Card key={scene.id} className="scene-row"><div className="scene-number">SC<br /><strong>{scene.scene_number}</strong></div><div className="scene-main"><div><h3>{scene.title}</h3><VerifiedLabel /></div><p>{scene.description}</p><div className="scene-tags"><Badge>{scene.estimated_duration_minutes} min</Badge><Badge>{scene.setup_minutes} min setup</Badge><Badge tone={scene.status === 'COMPLETED' ? 'success' : scene.status === 'BLOCKED' ? 'danger' : 'neutral'}>{scene.status}</Badge></div></div><div className="shot-stack"><strong>{scene.shots.length} shots</strong>{scene.shots.slice(0, 3).map((shot) => <span key={shot.id}>{shot.shot_number} · {shot.frame_size} · {shot.estimated_duration_minutes}m</span>)}{scene.shots.length > 3 && <small>+{scene.shots.length - 3} more</small>}</div></Card>)}</div>}
      </>}

      {activeTab === 'resources' && <>
        <div className="list-toolbar"><div><strong>{data.resources.length} resources</strong><span>Availability is enforced by the schedule solver.</span></div><Button onClick={() => setModal('resource')}><Plus size={16} />Add resource</Button></div>
        <div className="resource-table-wrap"><table className="data-table"><thead><tr><th>Resource</th><th>Type</th><th>Contact / address</th><th>Availability</th><th>Status</th></tr></thead><tbody>{data.resources.map((resource) => <tr key={resource.id}><td><strong>{resource.name}</strong><small>{resource.subtype || '—'}</small></td><td><Badge tone={resource.type === 'LOCATION' ? 'info' : 'neutral'}>{resource.type}</Badge></td><td>{resource.email ?? resource.address ?? '—'}</td><td>{resource.availability?.length ?? 0} window(s)</td><td><Badge tone={resource.status === 'AVAILABLE' ? 'success' : 'danger'}>{resource.status}</Badge></td></tr>)}</tbody></table></div>
      </>}

      {activeTab === 'readiness' && <ReadinessSection />}

      {modal === 'scene' && <Modal title="Add structured scene" description="This verified data becomes eligible for readiness and scheduling." onClose={() => setModal(null)}><form className="form-grid" onSubmit={createScene}><label>Scene number<input name="scene_number" required maxLength={20} placeholder="09" autoFocus /></label><label>Priority<select name="priority" defaultValue="3"><option value="1">1 — Low</option><option value="3">3 — Normal</option><option value="5">5 — Hero</option></select></label><label className="span-2">Title<input name="title" required maxLength={160} /></label><label className="span-2">Description<textarea name="description" maxLength={5000} /></label><label>Location<select name="location_id"><option value="">Unassigned</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label><label>Estimated duration<input name="duration" type="number" min="1" max="1440" defaultValue="30" /></label><label>Setup minutes<input name="setup" type="number" min="0" max="480" defaultValue="10" /></label><div className="form-actions span-2"><Button type="button" variant="ghost" onClick={() => setModal(null)}>Cancel</Button><Button type="submit" loading={saving}>Add scene</Button></div></form></Modal>}
      {modal === 'resource' && <Modal title="Add production resource" description="Resource identities are project-scoped and can be referenced by hard requirements." onClose={() => setModal(null)}><form className="form-grid" onSubmit={createResource}><label className="span-2">Name<input name="name" required maxLength={160} autoFocus /></label><label>Type<select name="type"><option>CAST</option><option>CREW</option><option>EQUIPMENT</option><option>LOCATION</option></select></label><label>Subtype<input name="subtype" maxLength={80} placeholder="Lead / Camera / Set" /></label><label>Email<input name="email" type="email" maxLength={254} /></label><label>Default cost<input name="default_cost" type="number" min="0" defaultValue="0" /></label><label className="span-2">Address (locations)<input name="address" maxLength={400} /></label><div className="form-actions span-2"><Button type="button" variant="ghost" onClick={() => setModal(null)}>Cancel</Button><Button type="submit" loading={saving}>Add resource</Button></div></form></Modal>}
      {importPreview && <Modal title={`Review ${importPreview.type.replaceAll('_', ' ')} import`} description={`${importPreview.count} rows parsed locally. Existing records are preserved; only explicitly confirmed new records are applied.`} onClose={() => setImportPreview(null)}>
        <div className="import-preview">
          {importPreview.notes.map((note) => <p key={note}>{note}</p>)}
          <div className="resource-table-wrap"><table className="data-table"><thead><tr><th>#</th><th>Identifier</th><th>Contents</th></tr></thead><tbody>
            {importPreview.items.slice(0, 15).map((row, index) => <tr key={index}><td>{index + 1}</td><td><strong>{row.scene_number ?? row.name ?? '—'}</strong></td><td>{[row.title, row.shot_number, row.description, row.type, row.start].filter(Boolean).join(' · ') || '—'}</td></tr>)}
          </tbody></table></div>
          {importPreview.count > 15 && <small>Preview shows the first 15 of {importPreview.count} rows.</small>}
          <div className="form-actions"><Button variant="ghost" onClick={() => setImportPreview(null)}>Cancel</Button>{importPreview.can_apply && <Button loading={saving} disabled={importPreview.count === 0} onClick={applyImport}>Confirm & import verified rows</Button>}</div>
        </div>
      </Modal>}
    </>
  )
}
