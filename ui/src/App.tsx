import { useState } from 'react'
import { loadIdentity, setIdentity, type Identity, type Role } from './api'
import { NavContext, type Route } from './nav'
import CataloguePage from './pages/CataloguePage'
import ComplianceCheckPage from './pages/ComplianceCheckPage'
import HistoryPage from './pages/HistoryPage'
import PhotosPage from './pages/PhotosPage'
import PlanogramPage from './pages/PlanogramPage'
import PlanogramsPage from './pages/PlanogramsPage'
import StoresPage from './pages/StoresPage'

const TABS: { route: Route; label: string }[] = [
  { route: { page: 'stores' }, label: 'Stores & Fixtures' },
  { route: { page: 'catalogue' }, label: 'Product Catalogue' },
  { route: { page: 'photos' }, label: 'Shelf Photos' },
  { route: { page: 'planograms' }, label: 'Planograms' },
  { route: { page: 'history' }, label: 'Score history' },
]

function render(route: Route) {
  switch (route.page) {
    case 'stores':
      return <StoresPage />
    case 'catalogue':
      return <CataloguePage />
    case 'photos':
      return <PhotosPage />
    case 'planograms':
      return <PlanogramsPage />
    case 'planogram':
      return <PlanogramPage id={route.id} />
    case 'compliance-check':
      return <ComplianceCheckPage id={route.id} />
    case 'history':
      return <HistoryPage />
  }
}

export default function App() {
  const [route, setRoute] = useState<Route>({ page: 'stores' })
  const [identity, setLocalIdentity] = useState<Identity>(loadIdentity)
  const [version, setVersion] = useState(0)

  function updateIdentity(patch: Partial<Identity>) {
    const next = { ...identity, ...patch }
    setLocalIdentity(next)
    setIdentity(next)
    setVersion((v) => v + 1)
  }

  function navigate(next: Route) {
    setRoute(next)
    setVersion((v) => v + 1)
  }

  return (
    <NavContext.Provider value={navigate}>
      <header>
        <h1>Planogram</h1>
        <nav>
          {TABS.map((tab) => (
            <button key={tab.label} className={tab.route.page === route.page ? 'active' : ''} onClick={() => navigate(tab.route)}>
              {tab.label}
            </button>
          ))}
        </nav>
        <div className="identity">
          <label>API key <input value={identity.apiKey} onChange={(e) => updateIdentity({ apiKey: e.target.value })} /></label>
          <label>User ID <input value={identity.userId} onChange={(e) => updateIdentity({ userId: e.target.value })} /></label>
          <select value={identity.role} onChange={(e) => updateIdentity({ role: e.target.value as Role })}>
            <option>Viewer</option>
            <option>Operator</option>
            <option>Manager</option>
          </select>
        </div>
      </header>
      <main key={version}>{render(route)}</main>
    </NavContext.Provider>
  )
}
