import { useEffect, useState } from 'react'
import { api, type Fixture, type Store } from './api'
import { useAsync } from './useAsync'

export interface Selection {
  store?: Store
  fixture?: Fixture
  bay?: number
}

/** Store → Fixture (→ Bay) selector shared by the pages. */
export default function FixturePicker({
  value,
  onChange,
  withBay = false,
}: {
  value: Selection
  onChange: (s: Selection) => void
  withBay?: boolean
}) {
  const stores = useAsync(() => api.get<Store[]>('/stores'))
  const [fixtures, setFixtures] = useState<Fixture[]>([])

  useEffect(() => {
    if (!value.store) return setFixtures([])
    api.get<Fixture[]>(`/stores/${value.store.id}/fixtures`).then(setFixtures, () => setFixtures([]))
  }, [value.store])

  return (
    <span className="inline">
      <select
        value={value.store?.id ?? ''}
        onChange={(e) => onChange({ store: stores.data?.find((s) => s.id === e.target.value) })}
      >
        <option value="">Store…</option>
        {stores.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <select
        value={value.fixture?.id ?? ''}
        onChange={(e) => onChange({ store: value.store, fixture: fixtures.find((f) => f.id === e.target.value), bay: undefined })}
        disabled={!value.store}
      >
        <option value="">Fixture…</option>
        {fixtures.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
      </select>
      {withBay && (
        <select
          value={value.bay ?? ''}
          onChange={(e) => onChange({ ...value, bay: e.target.value ? Number(e.target.value) : undefined })}
          disabled={!value.fixture}
        >
          <option value="">Bay…</option>
          {value.fixture?.bays.map((b) => <option key={b} value={b}>Bay {b}/{value.fixture?.bay_count}</option>)}
        </select>
      )}
    </span>
  )
}
