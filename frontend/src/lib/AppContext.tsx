import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { Project } from './types'
import { translate, type Language, type TranslationKey } from '../i18n/translations'

type Toast = { id: number; kind: 'success' | 'error' | 'info'; message: string }

type AppContextValue = {
  language: Language
  setLanguage: (language: Language) => void
  t: (key: TranslationKey) => string
  projects: Project[]
  activeProjectId: string | null
  activeProject: Project | null
  setActiveProjectId: (id: string | null) => void
  refreshProjects: () => Promise<Project[]>
  loadingProjects: boolean
  backendOnline: boolean
  toast: (message: string, kind?: Toast['kind']) => void
}

const AppContext = createContext<AppContextValue | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => (localStorage.getItem('setrescue-language') === 'id' ? 'id' : 'en'))
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProjectId, setActiveProjectIdState] = useState<string | null>(() => localStorage.getItem('setrescue-project'))
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [backendOnline, setBackendOnline] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((message: string, kind: Toast['kind'] = 'info') => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, kind, message }])
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 4200)
  }, [])

  const refreshProjects = useCallback(async () => {
    setLoadingProjects(true)
    try {
      const data = await api<Project[]>('/projects')
      setProjects(data)
      setBackendOnline(true)
      setActiveProjectIdState((current) => {
        if (current && data.some((project) => project.id === current)) return current
        return data[0]?.id ?? null
      })
      return data
    } catch (error) {
      setBackendOnline(false)
      throw error
    } finally {
      setLoadingProjects(false)
    }
  }, [])

  useEffect(() => {
    refreshProjects().catch(() => undefined)
  }, [refreshProjects])

  useEffect(() => {
    if (activeProjectId) localStorage.setItem('setrescue-project', activeProjectId)
    else localStorage.removeItem('setrescue-project')
  }, [activeProjectId])

  const setLanguage = (next: Language) => {
    setLanguageState(next)
    localStorage.setItem('setrescue-language', next)
    document.documentElement.lang = next
  }

  const setActiveProjectId = (id: string | null) => setActiveProjectIdState(id)
  const activeProject = projects.find((project) => project.id === activeProjectId) ?? null
  const value = useMemo<AppContextValue>(() => ({
    language, setLanguage, t: (key) => translate(language, key), projects, activeProjectId,
    activeProject, setActiveProjectId, refreshProjects, loadingProjects, backendOnline, toast,
  }), [language, projects, activeProjectId, activeProject, refreshProjects, loadingProjects, backendOnline, toast])

  return (
    <AppContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[100] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {toasts.map((item) => (
          <div key={item.id} className={`toast pointer-events-auto ${item.kind}`}>
            <span className="toast-dot" />
            <span>{item.message}</span>
            <button type="button" aria-label="Dismiss notification" onClick={() => setToasts((current) => current.filter((row) => row.id !== item.id))}>×</button>
          </div>
        ))}
      </div>
    </AppContext.Provider>
  )
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext)
  if (!value) throw new Error('useApp must be used within AppProvider')
  return value
}
