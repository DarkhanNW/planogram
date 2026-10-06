import { useCallback, useEffect, useState } from 'react'

/** Loads data when `deps` change and exposes a reload; errors are kept for display. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | undefined>()
  const [error, setError] = useState<string | undefined>()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps)
  const reload = useCallback(() => {
    run().then(
      (value) => {
        setData(value)
        setError(undefined)
      },
      (e: unknown) => setError(errorText(e)),
    )
  }, [run])
  useEffect(reload, [reload])
  return { data, error, reload, setError }
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
