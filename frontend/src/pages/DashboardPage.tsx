import { useState } from 'react'
import { Activity, AlertTriangle, CircleGauge, Clock3 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../lib/AppContext'
import { OverviewSection } from './dashboard/OverviewSection'
import { ScheduleLiveSection } from './dashboard/ScheduleLiveSection'
import { IncidentsSection } from './dashboard/IncidentsSection'
import { RecoverySection } from './dashboard/RecoverySection'
import type { DashboardTab } from './dashboard/types'

const TABS: Array<{ key: DashboardTab; label: string; icon: typeof CircleGauge }> = [
  { key: 'overview', label: 'Overview', icon: CircleGauge },
  { key: 'schedule', label: 'Schedule & Live', icon: Clock3 },
  { key: 'incidents', label: 'Incidents', icon: AlertTriangle },
  { key: 'recovery', label: 'Recovery', icon: Activity },
]

export function DashboardPage() {
  const { activeProject } = useApp()
  const navigate = useNavigate()
  const [tab, setTab] = useState<DashboardTab>('overview')
  const [recoveryIncident, setRecoveryIncident] = useState<string | null>(null)

  function go(t: DashboardTab) { setTab(t) }
  function onProductionData() { navigate('production-data') }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">{activeProject?.status ?? 'PLANNING'} · STATE V{activeProject?.production_state_version ?? 1}</div>
          <h1>{activeProject?.name ?? 'Production'}</h1>
          <p>Verified production state, schedule, live control, incidents, and recovery in one workspace.</p>
        </div>
      </div>
      <div className="tabbar dash-tabs">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} className={tab === key ? 'active' : ''} onClick={() => { setRecoveryIncident(null); go(key) }}><Icon size={16} />{label}</button>
        ))}
      </div>
      {tab === 'overview' && <OverviewSection onGo={go} onProductionData={onProductionData} />}
      {tab === 'schedule' && <ScheduleLiveSection />}
      {tab === 'incidents' && <IncidentsSection onReported={(id: string) => { setRecoveryIncident(id); go('recovery') }} />}
      {tab === 'recovery' && <RecoverySection seedIncidentId={recoveryIncident} onGo={go} />}
    </>
  )
}