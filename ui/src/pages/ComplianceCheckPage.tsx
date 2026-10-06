import { useState } from 'react'
import { api, type ComplianceCheck, type DeviationKind, type Position, type Product } from '../api'
import BoxedPhoto from '../BoxedPhoto'
import { useNav } from '../nav'
import { useAsync } from '../useAsync'

function kindClass(kind: DeviationKind) {
  return kind.toLowerCase().replaceAll(' ', '-')
}

function position(p: Position | null) {
  return p ? `Shelf ${p.shelf}, Block ${p.order}, ×${p.facings}` : '—'
}

export default function ComplianceCheckPage({ id }: { id: string }) {
  const check = useAsync(() => api.get<ComplianceCheck>(`/compliance-checks/${id}`), [id])
  const products = useAsync(() => api.get<Product[]>('/products'))
  const [selected, setSelected] = useState<number>()
  const nav = useNav()

  const c = check.data
  if (!c) return <p className={check.error ? 'error' : 'muted'}>{check.error ?? 'loading…'}</p>
  const names = new Map((products.data ?? []).map((p) => [p.sku, p.name]))
  const product = (sku: string | null) => (sku ? names.get(sku) ?? sku : 'Unknown Product')
  const outlines = c.deviations.map((d, i) => ({
    key: String(i),
    box: d.box,
    className: `${kindClass(d.kind)} ${i === selected ? 'selected' : ''}`,
    title: `${d.kind}: ${product(d.sku)} ×${d.facings}`,
  }))

  return (
    <>
      <section>
        <h2>Compliance Check · Bay {c.bay}</h2>
        <p className="muted">
          Submitted {new Date(c.submitted_at).toLocaleString()} by {c.submitted_by} · measured against{' '}
          <a href="#" onClick={(e) => { e.preventDefault(); nav({ page: 'planogram', id: c.planogram_id }) }}>
            this Approved Planogram
          </a>
        </p>
        <p>
          <span className="score">{Math.round(c.compliance_score * 100)}%</span>
          <span className="muted">Compliance Score</span>
        </p>
      </section>
      <section>
        <div className="row">
          <div style={{ flex: '1 1 420px' }}>
            <BoxedPhoto photoId={c.shelf_photo_id} outlines={outlines} />
          </div>
          <div style={{ flex: '1 1 420px' }}>
            {c.deviations.length === 0 ? (
              <p>No Deviations: the Bay is as planned.</p>
            ) : (
              <table>
                <thead>
                  <tr><th>Deviation</th><th>Product</th><th>Facings</th><th>Planned</th><th>Observed</th><th>Confidence</th></tr>
                </thead>
                <tbody>
                  {c.deviations.map((d, i) => (
                    <tr key={i} onMouseEnter={() => setSelected(i)} onMouseLeave={() => setSelected(undefined)}>
                      <td><span className={`tag ${kindClass(d.kind)}`}>{d.kind}</span></td>
                      <td>{product(d.sku)}</td>
                      <td>{d.facings}</td>
                      <td>{position(d.planned)}</td>
                      <td>{position(d.observed)}</td>
                      <td>{Math.round(d.confidence * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </section>
    </>
  )
}
