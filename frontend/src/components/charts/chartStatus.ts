export type ChartStatus = 'pending' | 'error' | 'empty' | 'ready'

/** Resolve a TanStack Query into a chart status, with the error-before-empty ordering
 *  applied once so no caller has to remember it. */
export function chartStatus(
  query: { isError: boolean; isPending: boolean },
  hasData: boolean,
): ChartStatus {
  if (query.isError) return 'error'
  if (query.isPending) return 'pending'
  return hasData ? 'ready' : 'empty'
}
