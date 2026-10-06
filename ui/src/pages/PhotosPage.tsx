import { useState, type FormEvent } from 'react'
import { api, type ShelfPhoto } from '../api'
import AuthImage from '../AuthImage'
import FixturePicker, { type Selection } from '../FixturePicker'
import { errorText, useAsync } from '../useAsync'

export default function PhotosPage() {
  const [selection, setSelection] = useState<Selection>({})
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string>()
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
        {(error || photos.error) && <p className="error">{error ?? photos.error}</p>}
      </section>
      {photos.data?.map((photo) => (
        <section key={photo.id}>
          <div className="inline">
            <strong>Bay {photo.bay}</strong>
            <span className="muted">uploaded {new Date(photo.uploaded_at).toLocaleString()} by {photo.uploaded_by}</span>
            <button className="danger small" onClick={() => remove(photo)} disabled={!photo.image_url}>Delete</button>
          </div>
          {photo.image_url ? <AuthImage path={photo.image_url} style={{ maxWidth: '100%' }} /> : <p className="muted">Image deleted.</p>}
        </section>
      ))}
    </>
  )
}
