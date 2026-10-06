import { api, type Box, type ShelfPhoto } from './api'
import AuthImage from './AuthImage'
import { useAsync } from './useAsync'

export interface Outline {
  key: string
  box: Box
  className?: string
  title?: string
}

/** A Shelf Photo with boxes drawn over it, positioned relative to the photo's pixel size.
 * `imagePath` shows another image of the same size in its place, such as an Annotated Photo. */
export default function BoxedPhoto({ photoId, imagePath, outlines = [] }: { photoId: string; imagePath?: string; outlines?: Outline[] }) {
  const photo = useAsync(() => api.get<ShelfPhoto>(`/shelf-photos/${photoId}`), [photoId])
  const p = photo.data
  if (!p) return <span className="muted">{photo.error ?? 'loading…'}</span>
  if (!p.image_url) return <p className="muted">The Shelf Photo has been deleted.</p>
  const pct = (value: number, total: number) => `${(value / total) * 100}%`
  return (
    <div className="photo">
      <AuthImage path={imagePath ?? p.image_url} />
      {outlines.map((o) => (
        <div
          key={o.key}
          className={`box ${o.className ?? ''}`}
          title={o.title}
          style={{ left: pct(o.box.x, p.width), top: pct(o.box.y, p.height), width: pct(o.box.w, p.width), height: pct(o.box.h, p.height) }}
        />
      ))}
    </div>
  )
}
