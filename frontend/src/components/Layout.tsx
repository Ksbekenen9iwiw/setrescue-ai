import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Bot, CircleGauge, ClipboardCheck, Database, Menu, Settings, X } from 'lucide-react'
import { api } from '../lib/api'
import { useApp } from '../lib/AppContext'
import { AISettingsModal } from './AISettingsModal'

type AIStatus = { enabled: boolean; api_key_configured: boolean; provider_name: string }

export function Layout() {
  const { t, language, setLanguage, projects, activeProjectId, activeProject, setActiveProjectId, backendOnline, loadingProjects } = useApp()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { projectId = '' } = useParams()

  useEffect(() => setMobileOpen(false), [location.pathname])
  useEffect(() => {
    api<AIStatus>('/settings/ai').then(setAiStatus).catch(() => undefined)
  }, [location.pathname])

  // Sync URL param to context
  useEffect(() => {
    if (projectId && projectId !== activeProjectId) setActiveProjectId(projectId)
  }, [projectId, activeProjectId, setActiveProjectId])

  // Redirect home if project doesn't exist (after projects loaded)
  useEffect(() => {
    if (!loadingProjects && projects.length > 0 && projectId && !projects.some((p) => p.id === projectId)) {
      navigate('/', { replace: true })
    }
  }, [loadingProjects, projects, projectId, navigate])

  const ready = !projectId || activeProjectId === projectId
  const sidebar = (
    <>
      {/* Back to projects */}
      <nav className="project-back" aria-label="Back to projects">
        <NavLink to="/"><ArrowLeft size={16} /><span>{t('allProjects')}</span></NavLink>
      </nav>
      <div className="brand">
        <div className="brand-mark"><ClipboardCheck size={23} strokeWidth={2.4} /></div>
        <div><strong>SETRESCUE</strong><span>AI production control</span></div>
        <button className="mobile-close" type="button" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={20} /></button>
      </div>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        <NavLink to="dashboard" className={({ isActive }) => isActive ? 'active' : ''}>
          <CircleGauge size={18} /><span>{t('dashboard')}</span>
        </NavLink>
        <NavLink to="production-data" className={({ isActive }) => isActive ? 'active' : ''}>
          <Database size={18} /><span>{t('productionData')}</span>
        </NavLink>
      </nav>
      <div className="sidebar-footer">
        <div className="system-pulse"><span className={backendOnline ? 'online' : 'offline'} /><div><strong>{backendOnline ? 'Local system online' : 'Backend offline'}</strong><small>SQLite · local storage</small></div></div>
      </div>
    </>
  )

  return (
    <div className="app-shell">
      <aside className="sidebar">{sidebar}</aside>
      {mobileOpen && <div className="mobile-sidebar"><div className="mobile-overlay" onClick={() => setMobileOpen(false)} /><aside>{sidebar}</aside></div>}
      <main className="main-shell">
        <header className="topbar">
          <button className="menu-button" type="button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={21} /></button>
          <div className="topbar-title"><span>{activeProject?.name ?? 'SetRescue workspace'}</span><small>{t('projectControl')}</small></div>
          <div className="topbar-actions">
            <button type="button" className="ai-settings-btn" onClick={() => setSettingsOpen(true)} aria-label="AI settings">
              <span className={aiStatus?.enabled && aiStatus.api_key_configured ? 'ai-dot' : 'ai-dot-off'} />
              <Bot size={13} /><span className="ai-label">{aiStatus?.enabled && aiStatus.api_key_configured ? 'AI configured' : 'AI not configured'}</span>
              <Settings size={14} />
            </button>
            <div className="language-toggle" aria-label="Language">
              <button type="button" className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>EN</button>
              <button type="button" className={language === 'id' ? 'active' : ''} onClick={() => setLanguage('id')}>ID</button>
            </div>
          </div>
        </header>
        <div className="page-content">{ready ? <Outlet /> : <div className="loading-state"><span>Loading project…</span></div>}</div>
      </main>
      {settingsOpen && <AISettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}