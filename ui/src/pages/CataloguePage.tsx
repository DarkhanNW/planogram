import { useState, type FormEvent } from 'react'
import { api, type ImportReport, type Product } from '../api'
import AuthImage from '../AuthImage'
import { errorText, useAsync } from '../useAsync'

export default function CataloguePage() {
  const products = useAsync(() => api.get<Product[]>('/products'))
  const [report, setReport] = useState<ImportReport>()
  const [csv, setCsv] = useState<File | null>(null)
  const [images, setImages] = useState<FileList | null>(null)

  async function runImport(e: FormEvent) {
    e.preventDefault()
    if (!csv) return
    const form = new FormData()
    form.append('csv', csv)
    for (const image of Array.from(images ?? [])) form.append('images', image, image.name)
    try {
      setReport(await api.post<ImportReport>('/products/import', form))
      products.reload()
    } catch (err) {
      products.setError(errorText(err))
    }
  }

  return (
    <>
      <section>
        <h2>Bulk import</h2>
        <p className="muted">
          CSV columns: <code>sku</code>, <code>name</code>, <code>images</code> (reference image file names separated
          by <code>;</code>). Re-importing a SKU renames it and adds its images.
        </p>
        <form className="inline" onSubmit={runImport}>
          <label>CSV <input type="file" accept=".csv,text/csv" onChange={(e) => setCsv(e.target.files?.[0] ?? null)} required /></label>
          <label>
            Reference images folder{' '}
            <input type="file" multiple accept="image/*" {...{ webkitdirectory: '' }} onChange={(e) => setImages(e.target.files)} />
          </label>
          <button className="primary">Import</button>
        </form>
        {report && (
          <div>
            <p>Created {report.created.length}, updated {report.updated.length}, failed {report.failed.length}.</p>
            {report.failed.length > 0 && (
              <table>
                <thead><tr><th>Row</th><th>SKU</th><th>Reason</th></tr></thead>
                <tbody>
                  {report.failed.map((f) => (
                    <tr key={f.row}><td>{f.row}</td><td>{f.sku}</td><td className="error">{f.reason}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
        {products.error && <p className="error">{products.error}</p>}
      </section>
      <section>
        <h2>Product Catalogue</h2>
        <table>
          <thead><tr><th>SKU</th><th>Name</th><th>Reference images</th></tr></thead>
          <tbody>
            {products.data?.map((p) => (
              <tr key={p.sku}>
                <td>{p.sku}</td>
                <td>{p.name}</td>
                <td className="row">
                  {p.reference_images.map((i) => <AuthImage key={i.id} path={i.url} className="thumb" />)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {products.data?.length === 0 && <p className="muted">The catalogue is empty.</p>}
      </section>
    </>
  )
}
