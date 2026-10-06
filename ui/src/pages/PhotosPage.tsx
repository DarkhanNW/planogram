import { useState, type FormEvent } from 'react'
import { api, type Job, type ShelfPhoto } from '../api'
import AuthImage from '../AuthImage'
import FixturePicker, { type Selection } from '../FixturePicker'
import { waitForJob } from '../jobs'
import { useNav } from '../nav'
import { errorText, useAsync } from '../useAsync'

/** What a Shelf Photo can be submitted for, and the page showing each job's result. */
const SUBMISSIONS = {
  extraction: { label: 'Extraction', path: '/extractions', page: 'planogram' },
  'compliance-check': { label: 'Compliance Check', path: '/compliance-checks', page: 'compliance-check' },
} as const

export default function PhotosPage() {
  const [selection, setSelection] = useState<Selection>({})
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string>()
  const [status, setStatus] = useState<string>()
  const nav = useNav()
  const fixtureId = selection.fixture?.id
  const photos = useAsync(
    () => (fixtureId ? api.get<ShelfPhoto[]>(`/shelf-photos?fixture_id=${fixtureId}`) : Promise.resolve([])),
    [fixtureId],
  )

  async function upload(e: FormEvent) {
    e.preventDefault()
    if (!file || !selection.store || !selection.fixture || !selection.bay) return
    const form = new FormData()
    form.append('image', file)
    form.append('store_id', selection.store.id)
    form.append('fixture_id', selection.fixture.id)
    form.append('bay', String(selection.bay))
    try {
      await api.post('/shelf-photos', form)
      setError(undefined)
      photos.reload()
    } catch (err) {
      setError(errorText(err))
    }
  }

  async function submit(photo: ShelfPhoto, kind: keyof typeof SUBMISSIONS) {
    const { label, path, page } = SUBMISSIONS[kind]
    try {
      setStatus(`${label} queued…`)
      const job = await waitForJob(await api.post<Job>(path, { shelf_photo_id: photo.id }), (j) =>
        setStatus(`${label} ${j.status}…`),
      )
      if (job.status === 'failed' || !job.result_id) throw new Error(job.error ?? `${label} failed`)
      setStatus(undefined)
      nav({ page, id: job.result_id })
    } catch (err) {
      setStatus(undefined)
      setError(errorText(err))
    }
  }

  async function remove(photo: ShelfPhoto) {
    if (!confirm('Delete this Shelf Photo? This cannot be undone.')) return
    try {
      await api.del(`/shelf-photos/${photo.id}`)
      photos.reload()
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <>
      <section>
        <h2>Upload a Shelf Photo</h2>
        <p className="muted">One whole Bay per photo. People in the photo are blurred before it is stored.</p>
        <form className="inline" onSubmit={upload}>
          <FixturePicker value={selection} onChange={setSelection} withBay />
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          <button className="primary" disabled={!selection.bay}>Upload</button>
        </form>
        {status && <p>{status}</p>}
        {(error || photos.error) && <p className="error">{error ?? photos.error}</p>}
      </section>
      {photos.data?.map((photo) => (
        <section key={photo.id}>
          <div className="inline">
            <strong>Bay {photo.bay}</strong>
            <span className="muted">uploaded {new Date(photo.uploaded_at).toLocaleString()} by {photo.uploaded_by}</span>
            <button className="small" onClick={() => submit(photo, 'extraction')} disabled={!photo.image_url || !!status}>Extract Draft Planogram</button>
            <button className="small" onClick={() => submit(photo, 'compliance-check')} disabled={!photo.image_url || !!status}>Check compliance</button>
            <button className="danger small" onClick={() => remove(photo)} disabled={!photo.image_url}>Delete</button>
          </div>
          {photo.image_url ? <AuthImage path={photo.image_url} style={{ maxWidth: '100%' }} /> : <p className="muted">Image deleted.</p>}
        </section>
      ))}
    </>
  )
}
