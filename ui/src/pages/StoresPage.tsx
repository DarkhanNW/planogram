import { useState, type FormEvent } from 'react'
import { api, type Fixture, type Store } from '../api'
import { errorText, useAsync } from '../useAsync'

export default function StoresPage() {
  const stores = useAsync(() => api.get<Store[]>('/stores'))
  const [name, setName] = useState('')

  async function register(e: FormEvent) {
    e.preventDefault()
    try {
      await api.post('/stores', { name })
      setName('')
      stores.reload()
    } catch (err) {
      stores.setError(errorText(err))
    }
  }

  return (
    <>
      <section>
        <h2>Register a Store</h2>
        <form className="inline" onSubmit={register}>
          <input placeholder="Store name" value={name} onChange={(e) => setName(e.target.value)} required />
          <button className="primary">Register</button>
        </form>
        {stores.error && <p className="error">{stores.error}</p>}
      </section>
      {stores.data?.map((store) => <StoreSection key={store.id} store={store} />)}
      {stores.data?.length === 0 && <p className="muted">No Stores yet.</p>}
    </>
  )
}

function StoreSection({ store }: { store: Store }) {
  const fixtures = useAsync(() => api.get<Fixture[]>(`/stores/${store.id}/fixtures`), [store.id])
  const [name, setName] = useState('')
  const [bays, setBays] = useState(1)

  async function register(e: FormEvent) {
    e.preventDefault()
    try {
      await api.post(`/stores/${store.id}/fixtures`, { name, bay_count: bays })
      setName('')
      fixtures.reload()
    } catch (err) {
      fixtures.setError(errorText(err))
    }
  }

  return (
    <section>
      <h2>{store.name}</h2>
      <table>
        <thead>
          <tr><th>Fixture</th><th>Bays</th></tr>
        </thead>
        <tbody>
          {fixtures.data?.map((f) => (
            <tr key={f.id}><td>{f.name}</td><td>{f.bays.join(', ')}</td></tr>
          ))}
        </tbody>
      </table>
      <form className="inline" onSubmit={register}>
        <input placeholder="Fixture name, e.g. Drinks" value={name} onChange={(e) => setName(e.target.value)} required />
        <label>
          Bays <input type="number" min={1} value={bays} onChange={(e) => setBays(Number(e.target.value))} style={{ width: '4rem' }} />
        </label>
        <button>Register Fixture</button>
      </form>
      {fixtures.error && <p className="error">{fixtures.error}</p>}
    </section>
  )
}
