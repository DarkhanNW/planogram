import { useEffect, useState, type ImgHTMLAttributes } from 'react'
import { api } from './api'

/** An <img> for a service image URL; the request carries the API key and user headers. */
export default function AuthImage({ path, ...props }: { path: string } & ImgHTMLAttributes<HTMLImageElement>) {
  const [src, setSrc] = useState<string>()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let url: string | undefined
    let cancelled = false
    api.blobUrl(path).then(
      (u) => {
        url = u
        if (cancelled) URL.revokeObjectURL(u)
        else setSrc(u)
      },
      () => !cancelled && setFailed(true),
    )
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [path])

  if (failed) return <span className="muted">(image unavailable)</span>
  return src ? <img src={src} {...props} /> : <span className="muted">loading…</span>
}
