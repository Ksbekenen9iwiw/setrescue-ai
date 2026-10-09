export type DashboardTab = 'overview' | 'schedule' | 'incidents' | 'recovery'

export type GoToTab = (tab: DashboardTab) => void
