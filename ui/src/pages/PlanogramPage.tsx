import { api, type BayLayout, type Planogram, type Product } from '../api'
import BoxedPhoto from '../BoxedPhoto'
import { useAsync } from '../useAsync'

export default function PlanogramPage({ id }: { id: string }) {
  const planogram = useAsync(() => api.get<Planogram>(`/planograms/${id}`), [id])
  const products = useAsync(() => api.get<Product[]>('/products'))
  const names = new Map(products.data?.map((p) => [p.sku, p.name]))

  const p = planogram.data
  if (!p) return <p className={planogram.error ? 'error' : 'muted'}>{planogram.error ?? 'loading…'}</p>
  return (
    <>
      <section>
        <h2>{p.status} Planogram</h2>
        <p className="muted">
          Created {new Date(p.created_at).toLocaleString()}
          {p.approved_at && ` · approved ${new Date(p.approved_at).toLocaleString()} by ${p.approved_by}`}
          {p.superseded_at && ` · superseded ${new Date(p.superseded_at).toLocaleString()}`}
        </p>
      </section>
      {p.bays.map((bay) => <BaySection key={bay.bay} bay={bay} names={names} />)}
      {p.bays.length === 0 && <p className="muted">No Bays extracted yet.</p>}
    </>
  )
}

function BaySection({ bay, names }: { bay: BayLayout; names: Map<string, string> }) {
  const outlines = bay.shelves.flatMap((shelf) =>
    shelf.blocks.filter((b) => b.box).map((b) => ({
      key: b.id,
      box: b.box!,
      className: b.unknown ? 'unknown' : '',
      title: b.sku ? `${names.get(b.sku) ?? b.sku} ×${b.facings}` : 'Unknown Product',
    })),
  )
  return (
    <section>
      <h2>Bay {bay.bay}</h2>
      <div className="row">
        <div style={{ flex: '1 1 420px' }}>
          {bay.shelf_photo_id ? <BoxedPhoto photoId={bay.shelf_photo_id} outlines={outlines} /> : <p className="muted">No Shelf Photo.</p>}
        </div>
        <div style={{ flex: '1 1 320px' }}>
          {[...bay.shelves].reverse().map((shelf) => (
            <div key={shelf.number}>
              <h3>Shelf {shelf.number}</h3>
              <ol>
                {shelf.blocks.map((b) => (
                  <li key={b.id}>
                    {b.unknown ? <span className="tag unknown">Unknown Product</span> : <span>{names.get(b.sku!) ?? b.sku}</span>}{' '}
                    <span className="muted">×{b.facings}</span>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
