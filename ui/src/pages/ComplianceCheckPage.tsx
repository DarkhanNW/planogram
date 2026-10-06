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

function percent(fraction: number | null) {
  return fraction === null ? '—' : `${Math.round(fraction * 100)}%`
}

export default function ComplianceCheckPage({ id }: { id: string }) {
  const check = useAsync(() => api.get<ComplianceCheck>(`/compliance-checks/${id}`), [id])
  const products = useAsync(() => api.get<Product[]>('/products'))
  const [selected, setSelected] = useState<string>()
  const nav = useNav()

  const c = check.data
  if (!c) return <p className={check.error ? 'error' : 'muted'}>{check.error ?? 'loading…'}</p>
  const names = new Map((products.data ?? []).map((p) => [p.sku, p.name]))
  const product = (sku: string | null) => (sku ? names.get(sku) ?? sku : 'Unknown Product')
  const hover = (key: string) => ({ onMouseEnter: () => setSelected(key), onMouseLeave: () => setSelected(undefined) })
  // Unverified areas first, so Deviations are drawn on top of them.
  const outlines = [
    ...c.unverified.map((u, i) => ({
      key: `u${i}`,
      box: u.box,
      className: `unverified ${`u${i}` === selected ? 'selected' : ''}`,
      title: `Unverified: Shelf ${u.shelf}`,
    })),
    ...c.deviations.map((d, i) => ({
      key: `d${i}`,
      box: d.box,
      className: `${kindClass(d.kind)} ${`d${i}` === selected ? 'selected' : ''}`,
      title: `${d.kind}: ${product(d.sku)} ×${d.facings}`,
    })),
  ]

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
          <span className="score">{percent(c.compliance_score)}</span>
          <span className="muted" style={{ marginRight: '1.5rem' }}>Compliance Score</span>
          <span className="score">{percent(c.coverage)}</span>
          <span className="muted">Coverage</span>
        </p>
      </section>
      <section>
        <div className="row">
          <div style={{ flex: '1 1 420px' }}>
            <BoxedPhoto photoId={c.shelf_photo_id} outlines={outlines} />
          </div>
          <div style={{ flex: '1 1 420px' }}>
            {c.deviations.length === 0 ? (
              <p>{c.unverified.length === 0 ? 'No Deviations: the Bay is as planned.' : 'No Deviations where the Bay could be verified.'}</p>
            ) : (
              <table>
                <thead>
                  <tr><th>Deviation</th><th>Product</th><th>Facings</th><th>Planned</th><th>Observed</th><th>Confidence</th></tr>
                </thead>
                <tbody>
                  {c.deviations.map((d, i) => (
                    <tr key={i} {...hover(`d${i}`)}>
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
            {c.unverified.length > 0 && (
              <>
                <h3>Unverified</h3>
                <p className="muted">Recognition was not confident enough here to report a Deviation or confirm compliance.</p>
                <table>
                  <thead>
                    <tr><th>Area</th><th>Shelf</th><th>Confidence</th></tr>
                  </thead>
                  <tbody>
                    {c.unverified.map((u, i) => (
                      <tr key={i} {...hover(`u${i}`)}>
                        <td><span className="tag unverified">Unverified</span></td>
                        <td>{u.shelf}</td>
                        <td>{percent(u.confidence)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      </section>
    </>
  )
}
