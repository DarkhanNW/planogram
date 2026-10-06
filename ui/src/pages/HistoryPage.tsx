import { useState } from 'react'
import { api, type ScoreHistory, type ScorePoint } from '../api'
import { percent } from '../format'
import FixturePicker, { type Selection } from '../FixturePicker'
import { useNav } from '../nav'
import { useAsync } from '../useAsync'

const BAY_COLOURS = ['#2463eb', '#c62828', '#0e7490', '#7c3aed', '#b45309', '#15803d', '#be185d', '#475569']

function bayColour(bay: number) {
  return BAY_COLOURS[(bay - 1) % BAY_COLOURS.length]
}

const WIDTH = 760
const HEIGHT = 260
const PAD = { left: 40, right: 16, top: 24, bottom: 28 }

/** Compliance Score per Bay (solid) and Coverage (dashed) over time, with a vertical marker
 * wherever a newly Approved Planogram changed a Bay's layout. */
function HistoryChart({ history }: { history: ScoreHistory }) {
  const times = [...history.points.map((p) => p.submitted_at), ...history.planogram_changes.map((c) => c.approved_at)].map(
    (t) => new Date(t).getTime(),
  )
  const [min, max] = [Math.min(...times), Math.max(...times)]
  const x = (t: string) =>
    max === min ? (PAD.left + WIDTH - PAD.right) / 2 : PAD.left + ((new Date(t).getTime() - min) / (max - min)) * (WIDTH - PAD.left - PAD.right)
  const y = (fraction: number) => PAD.top + (1 - fraction) * (HEIGHT - PAD.top - PAD.bottom)
  const byBay = new Map<number, ScorePoint[]>()
  for (const p of history.points) byBay.set(p.bay, [...(byBay.get(p.bay) ?? []), p])
  const line = (points: ScorePoint[], value: (p: ScorePoint) => number | null) =>
    points.flatMap((p) => {
      const v = value(p)
      return v === null ? [] : [`${x(p.submitted_at)},${y(v)}`]
    }).join(' ')

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} style={{ width: '100%', maxWidth: WIDTH }} role="img" aria-label="Score history">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(f)} y2={y(f)} stroke="var(--border)" />
          <text x={PAD.left - 6} y={y(f) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{percent(f)}</text>
        </g>
      ))}
      {history.planogram_changes.map((c) => (
        <g key={c.planogram_id}>
          <line x1={x(c.approved_at)} x2={x(c.approved_at)} y1={PAD.top - 8} y2={HEIGHT - PAD.bottom} stroke="var(--muted)" strokeDasharray="2 3" />
          <text x={x(c.approved_at) + 3} y={PAD.top - 10} fontSize="10" fill="var(--muted)">
            <title>{`New Approved Planogram ${new Date(c.approved_at).toLocaleString()}`}</title>
            New Approved Planogram · Bay {c.bays.join(', ')}
          </text>
        </g>
      ))}
      {[...byBay].map(([bay, points]) => (
        <g key={bay} stroke={bayColour(bay)} fill={bayColour(bay)}>
          <polyline points={line(points, (p) => p.coverage)} fill="none" strokeDasharray="5 4" opacity={0.6} />
          <polyline points={line(points, (p) => p.compliance_score)} fill="none" strokeWidth={2} />
          {points.map((p) =>
            p.compliance_score === null ? null : (
              <circle key={p.check_id} cx={x(p.submitted_at)} cy={y(p.compliance_score)} r={3}>
                <title>{`Bay ${bay} · ${new Date(p.submitted_at).toLocaleString()} · ${percent(p.compliance_score)} (Coverage ${percent(p.coverage)})`}</title>
              </circle>
            ),
          )}
        </g>
      ))}
      <text x={PAD.left} y={HEIGHT - 8} fontSize="11" fill="var(--muted)">{new Date(min).toLocaleDateString()}</text>
      <text x={WIDTH - PAD.right} y={HEIGHT - 8} fontSize="11" fill="var(--muted)" textAnchor="end">{new Date(max).toLocaleDateString()}</text>
    </svg>
  )
}

/** Compliance Score and Coverage over time for a Fixture's Bays, or one Bay. */
export default function HistoryPage() {
  const nav = useNav()
  const [selection, setSelection] = useState<Selection>({})
  const fixtureId = selection.fixture?.id
  const bay = selection.bay
  const history = useAsync(
    () =>
      fixtureId
        ? api.get<ScoreHistory>(`/fixtures/${fixtureId}${bay ? `/bays/${bay}` : ''}/score-history`)
        : Promise.resolve(undefined),
    [fixtureId, bay],
  )
  const data = history.data
  const bays = [...new Set(data?.points.map((p) => p.bay))].sort((a, b) => a - b)

  return (
    <section>
      <h2>Score history</h2>
      <FixturePicker value={selection} onChange={setSelection} withBay />
      <span className="muted">Pick a Bay, or leave it blank to compare every Bay of the Fixture.</span>
      {history.error && <p className="error">{history.error}</p>}
      {data && data.points.length === 0 && <p className="muted">No Compliance Checks yet.</p>}
      {data && data.points.length > 0 && (
        <>
          <HistoryChart history={data} />
          <p className="inline muted">
            {bays.map((b) => (
              <span key={b} style={{ color: bayColour(b) }}>■ Bay {b}</span>
            ))}
            <span>solid: Compliance Score · dashed: Coverage · dotted vertical: new Approved Planogram</span>
          </p>
          <table>
            <thead><tr><th>Submitted</th><th>Bay</th><th>Compliance Score</th><th>Coverage</th><th /></tr></thead>
            <tbody>
              {[...data.points].reverse().map((p) => (
                <tr key={p.check_id}>
                  <td>{new Date(p.submitted_at).toLocaleString()}</td>
                  <td>{p.bay}</td>
                  <td>{percent(p.compliance_score)}</td>
                  <td>{percent(p.coverage)}</td>
                  <td><button className="small" onClick={() => nav({ page: 'compliance-check', id: p.check_id })}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
