import { useState } from 'react'
import { api, ApiError, type BayLayout, type Block, type Planogram, type Product } from '../api'
import BoxedPhoto from '../BoxedPhoto'
import { errorText, useAsync } from '../useAsync'

interface UnknownBlock {
  bay: number
  shelf: number
  position: number
  block_id: string
}

export default function PlanogramPage({ id }: { id: string }) {
  const planogram = useAsync(() => api.get<Planogram>(`/planograms/${id}`), [id])
  const products = useAsync(() => api.get<Product[]>('/products'))
  const [error, setError] = useState<string>()
  const [unresolved, setUnresolved] = useState<UnknownBlock[]>([])

  const p = planogram.data
  if (!p) return <p className={planogram.error ? 'error' : 'muted'}>{planogram.error ?? 'loading…'}</p>
  const editable = p.status === 'Draft'

  async function edit(change: () => Promise<unknown>) {
    try {
      await change()
      setError(undefined)
      planogram.reload()
    } catch (err) {
      setError(errorText(err))
    }
  }

  async function approve() {
    try {
      await api.post(`/planograms/${id}/approve`)
      setUnresolved([])
      setError(undefined)
      planogram.reload()
    } catch (err) {
      const unknown = err instanceof ApiError ? (err.body as { unknown_blocks?: UnknownBlock[] }).unknown_blocks : undefined
      setUnresolved(unknown ?? [])
      setError(errorText(err))
    }
  }

  return (
    <>
      <section>
        <h2>{p.status} Planogram</h2>
        <p className="muted">
          Created {new Date(p.created_at).toLocaleString()}
          {p.approved_at && ` · approved ${new Date(p.approved_at).toLocaleString()} by ${p.approved_by}`}
          {p.superseded_at && ` · superseded ${new Date(p.superseded_at).toLocaleString()}`}
        </p>
        {editable && <button className="primary" onClick={approve}>Approve</button>}
        {error && <p className="error">{error}</p>}
        {unresolved.length > 0 && (
          <p>
            {unresolved.length} Unknown Product{unresolved.length > 1 ? 's' : ''} still need resolving: choose the Product
            for each one marked below, or add it to the catalogue from its crop.
          </p>
        )}
      </section>
      {p.bays.map((bay) => (
        <BaySection key={bay.bay} planogram={p} bay={bay} products={products.data ?? []} editable={editable} edit={edit} onCatalogueChange={products.reload} />
      ))}
      {p.bays.length === 0 && <p className="muted">No Bays extracted yet.</p>}
    </>
  )
}

interface BayProps {
  planogram: Planogram
  bay: BayLayout
  products: Product[]
  editable: boolean
  edit: (change: () => Promise<unknown>) => Promise<void>
  onCatalogueChange: () => void
}

function BaySection({ planogram, bay, products, editable, edit, onCatalogueChange }: BayProps) {
  const [selected, setSelected] = useState<string>()
  const names = new Map(products.map((p) => [p.sku, p.name]))
  const base = `/planograms/${planogram.id}/bays/${bay.bay}`
  const outlines = bay.shelves.flatMap((shelf) =>
    shelf.blocks.filter((b) => b.box).map((b) => ({
      key: b.id,
      box: b.box!,
      className: `${b.unknown ? 'unknown' : ''} ${b.id === selected ? 'selected' : ''}`,
      title: b.sku ? `${names.get(b.sku) ?? b.sku} ×${b.facings}` : 'Unknown Product',
    })),
  )
  const nextShelf = Math.max(0, ...bay.shelves.map((s) => s.number)) + 1

  return (
    <section>
      <h2>Bay {bay.bay}</h2>
      <div className="row">
        <div style={{ flex: '1 1 420px' }}>
          {bay.shelf_photo_id ? <BoxedPhoto photoId={bay.shelf_photo_id} outlines={outlines} /> : <p className="muted">No Shelf Photo.</p>}
        </div>
        <div style={{ flex: '1 1 380px' }}>
          {[...bay.shelves].reverse().map((shelf) => (
            <div key={shelf.number}>
              <h3>Shelf {shelf.number}</h3>
              <ol>
                {shelf.blocks.map((b) => (
                  <li key={b.id} onMouseEnter={() => setSelected(b.id)} onMouseLeave={() => setSelected(undefined)}>
                    <BlockRow block={b} products={products} names={names} editable={editable} edit={edit} url={`${base}/blocks/${b.id}`} planogramId={planogram.id} bay={bay.bay} onCatalogueChange={onCatalogueChange} />
                  </li>
                ))}
              </ol>
              {editable && <InsertForm products={products} onInsert={(sku, facings, position) => edit(() => api.post(`${base}/shelves/${shelf.number}/blocks`, { sku, facings, position }))} max={shelf.blocks.length} />}
            </div>
          ))}
          {editable && (
            <div>
              <h3>New Shelf {nextShelf}</h3>
              <InsertForm products={products} onInsert={(sku, facings) => edit(() => api.post(`${base}/shelves/${nextShelf}/blocks`, { sku, facings, position: 0 }))} max={0} />
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

interface BlockRowProps {
  block: Block
  products: Product[]
  names: Map<string, string>
  editable: boolean
  edit: (change: () => Promise<unknown>) => Promise<void>
  url: string
  planogramId: string
  bay: number
  onCatalogueChange: () => void
}

function BlockRow({ block, products, names, editable, edit, url }: BlockRowProps) {
  if (!editable) {
    return (
      <>
        {block.unknown ? <span className="tag unknown">Unknown Product</span> : names.get(block.sku!) ?? block.sku}{' '}
        <span className="muted">×{block.facings}</span>
      </>
    )
  }
  return (
    <span className="inline">
      {block.unknown && <span className="tag unknown">Unknown Product</span>}
      <select value={block.sku ?? ''} onChange={(e) => e.target.value && edit(() => api.patch(url, { sku: e.target.value }))}>
        <option value="">{block.unknown ? 'Choose Product…' : ''}</option>
        {products.map((p) => <option key={p.sku} value={p.sku}>{p.name} ({p.sku})</option>)}
      </select>
      ×
      <input
        type="number"
        min={1}
        defaultValue={block.facings}
        style={{ width: '3.5rem' }}
        onBlur={(e) => Number(e.target.value) !== block.facings && edit(() => api.patch(url, { facings: Number(e.target.value) }))}
      />
      <button className="danger small" onClick={() => edit(() => api.del(url))}>Delete</button>
    </span>
  )
}

function InsertForm({ products, onInsert, max }: { products: Product[]; onInsert: (sku: string, facings: number, position: number) => void; max: number }) {
  const [sku, setSku] = useState('')
  const [facings, setFacings] = useState(1)
  const [position, setPosition] = useState(max)
  return (
    <form className="inline" onSubmit={(e) => { e.preventDefault(); if (sku) onInsert(sku, facings, position) }}>
      <select value={sku} onChange={(e) => setSku(e.target.value)}>
        <option value="">Insert Product…</option>
        {products.map((p) => <option key={p.sku} value={p.sku}>{p.name}</option>)}
      </select>
      ×<input type="number" min={1} value={facings} onChange={(e) => setFacings(Number(e.target.value))} style={{ width: '3.5rem' }} />
      {max > 0 && (
        <label>at position <input type="number" min={1} max={max + 1} value={position + 1} onChange={(e) => setPosition(Number(e.target.value) - 1)} style={{ width: '3.5rem' }} /></label>
      )}
      <button className="small" disabled={!sku}>Insert</button>
    </form>
  )
}
