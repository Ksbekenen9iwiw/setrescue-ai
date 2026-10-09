import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ConfirmationPage } from './pages/ConfirmationPage'
import { DashboardPage } from './pages/DashboardPage'
import { ProductionDataPage } from './pages/ProductionDataPage'
import { ProjectsPage } from './pages/ProjectsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/confirm/:token" element={<ConfirmationPage />} />
      <Route path="/" element={<ProjectsPage />} />
      <Route path="/project/:projectId" element={<Layout />}>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="production-data" element={<ProductionDataPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
