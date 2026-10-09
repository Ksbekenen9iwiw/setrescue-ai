import { useState, type FormEvent } from 'react'
import { ArrowRight, CalendarRange, Clapperboard, FolderPlus, PlayCircle, WalletCards } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { post } from '../lib/api'
import { useApp } from '../lib/AppContext'
import type { Project } from '../lib/types'
import { Badge, Button, Card, EmptyState, Modal } from '../components/ui'

export function ProjectsPage() {
  const { projects, setActiveProjectId, refreshProjects, loadingProjects, toast, t, language, setLanguage } = useApp()
  const [creating, setCreating] = useState(false)
  const [loadingDemo, setLoadingDemo] = useState(false)
  const [saving, setSaving] = useState(false)
  const navigate = useNavigate()
  const localDate = (daysAhead: number) => {
    const day = new Date()
    day.setDate(day.getDate() + daysAhead)
    return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
  }
  const today = localDate(0)
  const tomorrow = localDate(1)

  function openProject(id: string, path = 'dashboard') {
    setActiveProjectId(id)
    navigate(`/project/${id}/${path}`)
  }

  async function loadDemo() {
    setLoadingDemo(true)
    try {
      const project = await post<Project>('/demo/realistic')
      await refreshProjects()
      toast('Project Rainfall is ready for the demo flow.', 'success')
      openProject(project.id)
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to load demo.', 'error')
    } finally {
      setLoadingDemo(false)
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setSaving(true)
    try {
      const project = await post<Project>('/projects', {
        name: String(form.get('name')),
        description: String(form.get('description')),
        start_date: String(form.get('start_date')),
        end_date: String(form.get('end_date')),
        budget: Number(form.get('budget') || 0),
        currency: 'IDR',
        workday_start: '08:00:00',
        workday_end: '18:00:00',
      })
      await refreshProjects()
      setCreating(false)
      toast('Project created.', 'success')
      openProject(project.id, 'production-data')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to create project.', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="home-shell">
      <header className="home-topbar">
        <div className="home-brand"><div className="brand-mark"><Clapperboard size={22} strokeWidth={2.4} /></div><div><strong>SETRESCUE</strong><span>AI production control</span></div></div>
        <div className="language-toggle" aria-label="Language">
          <button type="button" className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>EN</button>
          <button type="button" className={language === 'id' ? 'active' : ''} onClick={() => setLanguage('id')}>ID</button>
        </div>
      </header>
      <main className="home-content">
        <div className="page-header home-header">
          <div>
            <div className="eyebrow">LOCAL PRODUCTION WORKSPACE</div>
            <h1>{t('projects')}</h1>
            <p>Each production keeps its documents, dependencies, schedule versions, and exports locally.</p>
          </div>
          <div className="page-actions">
            <Button variant="secondary" loading={loadingDemo} onClick={loadDemo}><PlayCircle size={16} />{t('loadDemo')}</Button>
            <Button onClick={() => setCreating(true)}><FolderPlus size={16} />{t('newProject')}</Button>
          </div>
        </div>
        {loadingProjects ? <div className="skeleton-grid"><div /><div /><div /></div> : projects.length === 0 ? (
          <EmptyState title="Start with a production" description="Create a blank project or load Project Rainfall to walk through the complete PREVENT → RECOVER story." action={<Button loading={loadingDemo} onClick={loadDemo}><PlayCircle size={16} />Load Project Rainfall</Button>} icon={<Clapperboard size={24} />} />
        ) : (
          <div className="project-grid">
            {projects.map((project, index) => (
              <Card key={project.id} className="project-card" onClick={() => openProject(project.id)}>
                <div className="project-visual"><span>{String(index + 1).padStart(2, '0')}</span><Clapperboard size={28} /></div>
                <div className="project-card-body">
                  <div className="project-title"><div><h2>{project.name}</h2><p>{project.description || 'No production description yet.'}</p></div><ArrowRight size={20} /></div>
                  <div className="project-meta">
                    <span><CalendarRange size={14} />{project.start_date} — {project.end_date}</span>
                    <span><WalletCards size={14} />{new Intl.NumberFormat('id-ID', { notation: 'compact' }).format(project.budget)} {project.currency}</span>
                  </div>
                  <div className="project-footer"><Badge tone={project.status === 'PRODUCTION' ? 'success' : 'neutral'}>{project.status}</Badge><small>Production state v{project.production_state_version}</small></div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>
      {creating && <Modal title="Create production" description="Set the boundaries used by deterministic readiness and schedule checks." onClose={() => setCreating(false)}>
        <form className="form-grid" onSubmit={createProject}>
          <label className="span-2">Project name<input name="name" required maxLength={120} placeholder="Commercial — Sunrise" autoFocus /></label>
          <label className="span-2">Description<textarea name="description" maxLength={2000} placeholder="A short production brief" /></label>
          <label>Start date<input type="date" name="start_date" defaultValue={today} required /></label>
          <label>End date<input type="date" name="end_date" defaultValue={tomorrow} required /></label>
          <label className="span-2">Budget (IDR)<input type="number" min="0" max="1000000000000" name="budget" defaultValue="50000000" /></label>
          <div className="form-actions span-2"><Button type="button" variant="ghost" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" loading={saving}>Create project</Button></div>
        </form>
      </Modal>}
    </div>
  )
}
