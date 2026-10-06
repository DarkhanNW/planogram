import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type BayLayout, type Block, type Planogram, type Product } from '../api'
import AuthImage from '../AuthImage'
import BoxedPhoto from '../BoxedPhoto'
import { errorText, useAsync } from '../useAsync'

type Edit = (change: () => Promise<unknown>) => Promise<boolean>

interface UnknownBlock {
  bay: number
  shelf: number
  position: number
  block: Block
}

function unknownBlocks(p: Planogram): UnknownBlock[] {
  return p.bays.flatMap((bay) =>
    bay.shelves.flatMap((shelf) =>
      shelf.blocks.flatMap((block, position) => (block.unknown ? [{ bay: bay.bay, shelf: shelf.number, position, block }] : [])),
    ),
  )
}

export default function PlanogramPage({ id }: { id: string }) {
  const planogram = useAsync(() => api.get<Planogram>(`/planograms/${id}`), [id])
  const products = useAsync(() => api.get<Product[]>('/products'))
  const [error, setError] = useState<string>()
  const [approvalRefused, setApprovalRefused] = useState(false)
  const [resolving, setResolving] = useState<string>()

  const p = planogram.data
  if (!p) return <p className={planogram.error ? 'error' : 'muted'}>{planogram.error ?? 'loading…'}</p>
  const editable = p.status === 'Draft'
  // Derived from the current Draft so the list shrinks as the Manager resolves each one.
  const unresolved = approvalRefused ? unknownBlocks(p) : []

  const edit: Edit = async (change) => {
    try {
      await change()
      setError(undefined)
      planogram.reload()
      return true
    } catch (err) {
      setError(errorText(err))
      // A Conflict may mean the Draft changed since it was loaded (an Extraction or another
      // Manager's edit), so show the latest one for the Manager to redo the edit on.
      if (err instanceof ApiError && err.status === 409) planogram.reload()
      return false
    }
  }

  async function approve() {
    try {
      await api.post(`/planograms/${id}/approve`)
      setApprovalRefused(false)
      setError(undefined)
      planogram.reload()
    } catch (err) {
      const unknown = err instanceof ApiError ? (err.body as { unknown_blocks?: unknown[] } | null)?.unknown_blocks : undefined
      setApprovalRefused(!!unknown?.length)
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
          <div>
            <p>
              Approval needs every Unknown Product resolved. Probably the Product is missing from the catalogue: add it
              from its crop, or add the crop to the Product it really is.
            </p>
            <ul>
              {unresolved.map((u) => (
                <li key={u.block.id}>
                  Bay {u.bay}, Shelf {u.shelf}, position {u.position + 1}{' '}
                  <button
                    className="small"
                    onClick={() => {
                      setResolving(u.block.id)
                      // Without a crop there is no resolve flow; the Product is chosen on the Block itself.
                      // An already open panel won't scroll itself back into view either.
                      if (!u.block.box || resolving === u.block.id) document.getElementById(`block-${u.block.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                    }}
                  >
                    Resolve
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
      {p.bays.map((bay) => (
        <BaySection
          key={bay.bay}
          planogram={p}
          bay={bay}
          products={products.data ?? []}
          editable={editable}
          edit={edit}
          onCatalogueChange={products.reload}
          resolving={resolving}
          setResolving={setResolving}
        />
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
  edit: Edit
  onCatalogueChange: () => void
  resolving: string | undefined
  setResolving: (blockId: string | undefined) => void
}

function BaySection({ planogram, bay, products, editable, edit, onCatalogueChange, resolving, setResolving }: BayProps) {
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
                  <li key={b.id} id={`block-${b.id}`} onMouseEnter={() => setSelected(b.id)} onMouseLeave={() => setSelected(undefined)}>
                    <BlockRow
                      block={b}
                      products={products}
                      names={names}
                      editable={editable}
                      edit={edit}
                      url={`${base}/blocks/${b.id}`}
                      onResolve={b.unknown && b.box && resolving !== b.id ? () => setResolving(b.id) : undefined}
                    />
                    {editable && b.unknown && b.box && resolving === b.id && (
                      <ResolvePanel url={`${base}/blocks/${b.id}`} products={products} edit={edit} onCatalogueChange={onCatalogueChange} onClose={() => setResolving(undefined)} />
                    )}
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
  edit: Edit
  url: string
  onResolve?: () => void
}

/** Grow the catalogue from the shelf: a new Product from the crop, or the crop added to an existing one. */
function ResolvePanel({ url, products, edit, onCatalogueChange, onClose }: { url: string; products: Product[]; edit: Edit; onCatalogueChange: () => void; onClose: () => void }) {
  const [sku, setSku] = useState('')
  const [name, setName] = useState('')
  const [existing, setExisting] = useState('')
  const panel = useRef<HTMLDivElement>(null)
  const skuInput = useRef<HTMLInputElement>(null)

  // Opened from the refused-approval prompt, the Block may be far down the page.
  useEffect(() => {
    panel.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    skuInput.current?.focus({ preventScroll: true })
  }, [])

  async function resolve(body: object) {
    await edit(() => api.post(`${url}/resolve`, body))
    onCatalogueChange()
  }

  return (
    <div ref={panel} className="row" style={{ margin: '.4rem 0 .8rem' }}>
      <AuthImage path={`${url}/crop`} className="thumb" />
      <div>
        <form className="inline" onSubmit={(e) => { e.preventDefault(); resolve({ new_product: { sku, name } }) }}>
          <input ref={skuInput} placeholder="New SKU" value={sku} onChange={(e) => setSku(e.target.value)} required style={{ width: '7rem' }} />
          <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
          <button className="small">Add new Product</button>
        </form>
        <form className="inline" onSubmit={(e) => { e.preventDefault(); if (existing) resolve({ existing_sku: existing }) }}>
          <select value={existing} onChange={(e) => setExisting(e.target.value)}>
            <option value="">It is an existing Product…</option>
            {products.map((p) => <option key={p.sku} value={p.sku}>{p.name} ({p.sku})</option>)}
          </select>
          <button className="small" disabled={!existing}>Add crop as reference image</button>
        </form>
        <button type="button" className="small" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

function BlockRow({ block, products, names, editable, edit, url, onResolve }: BlockRowProps) {
  const [facings, setFacings] = useState(String(block.facings))
  // Follow the Block's count after any edit or reload, without wiping what is typed in other rows.
  const [syncedFacings, setSyncedFacings] = useState(block.facings)
  if (syncedFacings !== block.facings) {
    setSyncedFacings(block.facings)
    setFacings(String(block.facings))
  }

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
      {onResolve && <button className="small" onClick={onResolve}>Resolve</button>}
      <select value={block.sku ?? ''} onChange={(e) => e.target.value && edit(() => api.patch(url, { sku: e.target.value }))}>
        <option value="">{block.unknown ? 'Choose Product…' : ''}</option>
        {products.map((p) => <option key={p.sku} value={p.sku}>{p.name} ({p.sku})</option>)}
      </select>
      ×
      <input
        type="number"
        min={1}
        value={facings}
        style={{ width: '3.5rem' }}
        onChange={(e) => setFacings(e.target.value)}
        onBlur={async () => {
          if (Number(facings) === block.facings) return
          if (!(await edit(() => api.patch(url, { facings: Number(facings) })))) setFacings(String(block.facings))
        }}
      />
      <button className="danger small" onClick={() => edit(() => api.del(url))}>Delete</button>
    </span>
  )
}

function InsertForm({ products, onInsert, max }: { products: Product[]; onInsert: (sku: string, facings: number, position: number) => Promise<boolean>; max: number }) {
  const [sku, setSku] = useState('')
  const [facings, setFacings] = useState(1)
  const [position, setPosition] = useState(max)
  // An insert or delete changes the Shelf's length; the default goes back to the end.
  const [syncedMax, setSyncedMax] = useState(max)
  if (syncedMax !== max) {
    setSyncedMax(max)
    setPosition(max)
  }

  async function insert() {
    // An insert merged into a neighbouring Block leaves the length unchanged, so reset here too.
    if (await onInsert(sku, facings, position)) setPosition(max)
  }
  return (
    <form className="inline" onSubmit={(e) => { e.preventDefault(); if (sku) insert() }}>
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
