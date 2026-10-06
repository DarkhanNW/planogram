/** A fraction 0..1 as a whole percentage; '—' for none. */
export function percent(fraction: number | null) {
  return fraction === null ? '—' : `${Math.round(fraction * 100)}%`
}
