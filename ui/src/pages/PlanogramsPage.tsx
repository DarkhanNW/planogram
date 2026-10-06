import { useState } from 'react'
import { api, type Planogram } from '../api'
import FixturePicker, { type Selection } from '../FixturePicker'
import { useNav } from '../nav'
import { useAsync } from '../useAsync'

/** A Fixture's Planogram history: Drafts, the Approved Planogram and Superseded ones. */
export default function PlanogramsPage() {
  const nav = useNav()
  const [selection, setSelection] = useState<Selection>({})
  const fixtureId = selection.fixture?.id
  const planograms = useAsync(
    () => (fixtureId ? api.get<Planogram[]>(`/fixtures/${fixtureId}/planograms`) : Promise.resolve([])),
    [fixtureId],
  )

  return (
    <section>
      <h2>Planograms</h2>
      <FixturePicker value={selection} onChange={setSelection} />
      {planograms.error && <p className="error">{planograms.error}</p>}
      <table>
        <thead><tr><th>Status</th><th>Created</th><th>Approved</th><th>Bays</th><th /></tr></thead>
        <tbody>
          {planograms.data?.map((p) => (
            <tr key={p.id}>
              <td>{p.status}</td>
              <td>{new Date(p.created_at).toLocaleString()}</td>
              <td>{p.approved_at ? `${new Date(p.approved_at).toLocaleString()} by ${p.approved_by}` : '—'}</td>
              <td>{p.bays.map((b) => b.bay).join(', ')}</td>
              <td><button className="small" onClick={() => nav({ page: 'planogram', id: p.id })}>Open</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {fixtureId && planograms.data?.length === 0 && <p className="muted">No Planograms for this Fixture yet.</p>}
    </section>
  )
}
