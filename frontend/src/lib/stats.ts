const DASH = '—'

export const pct = (x: number | null | undefined) => (x == null ? DASH : `${Math.round(x * 100)}%`)
export const num = (x: number | null | undefined, digits = 1) => (x == null ? DASH : x.toFixed(digits))

/** Sort rows by a numeric (or string) key. Missing values always go last, whichever direction. */
export function sortRows<T>(rows: T[], key: (row: T) => number | string | null | undefined, desc: boolean): T[] {
  return [...rows].sort((a, b) => {
    const x = key(a)
    const y = key(b)
    if (x == null && y == null) return 0
    if (x == null) return 1
    if (y == null) return -1
    const cmp = typeof x === 'string' ? x.localeCompare(String(y)) : x - (y as number)
    return desc ? -cmp : cmp
  })
}
