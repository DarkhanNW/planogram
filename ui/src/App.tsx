import { useState } from 'react'
import { loadIdentity, setIdentity, type Identity, type Role } from './api'
import CataloguePage from './pages/CataloguePage'
import PhotosPage from './pages/PhotosPage'
import StoresPage from './pages/StoresPage'

const PAGES = {
  stores: { label: 'Stores & Fixtures', render: () => <StoresPage /> },
  catalogue: { label: 'Product Catalogue', render: () => <CataloguePage /> },
  photos: { label: 'Shelf Photos', render: () => <PhotosPage /> },
} as const

type PageKey = keyof typeof PAGES

export default function App() {
  const [page, setPage] = useState<PageKey>('stores')
  const [identity, setLocalIdentity] = useState<Identity>(loadIdentity)
  const [version, setVersion] = useState(0)

  function updateIdentity(patch: Partial<Identity>) {
    const next = { ...identity, ...patch }
    setLocalIdentity(next)
    setIdentity(next)
    setVersion((v) => v + 1)
  }

  return (
    <>
      <header>
        <h1>Planogram</h1>
        <nav>
          {(Object.keys(PAGES) as PageKey[]).map((key) => (
            <button key={key} className={key === page ? 'active' : ''} onClick={() => setPage(key)}>
              {PAGES[key].label}
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
      <main key={`${page}-${version}`}>{PAGES[page].render()}</main>
    </>
  )
}
