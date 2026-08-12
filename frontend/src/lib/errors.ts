import { ApiError } from '../api/client'

export type ErrorKind =
  | 'offline'
  | 'unreachable'
  | 'notFound'
  | 'server'
  | 'client'
  | 'unknown'

export interface ErrorDescription {
  kind: ErrorKind
  /** One short line naming what went wrong. */
  title: string
  /** A sentence saying what it means and what to do about it. */
  detail: string
  /** False when retrying the identical request cannot plausibly help. */
  canRetry: boolean
}

/**
 * Turn a thrown value into copy a user can act on.
 *
 * The distinction that matters is unreachable-vs-error. `api()` awaits `fetch`
 * bare, so a network-level failure — DNS, connection refused, CORS, offline —
 * propagates as a raw `TypeError` and is never an `ApiError`. Anything that
 * *is* an `ApiError` means the request arrived somewhere and came back with a
 * status. The two need different wording: the first is usually a sleeping
 * server, the second is usually a bug or a misconfiguration.
 */
export function describeError(error: unknown): ErrorDescription {
  // Checked before anything else: when the browser knows the network is down,
  // that is more useful than any guess drawn from the exception.
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return {
      kind: 'offline',
      title: "You're offline",
      detail: 'Check your connection, then retry.',
      canRetry: true,
    }
  }

  if (error instanceof ApiError) {
    if (error.status === 404) {
      return {
        kind: 'notFound',
        title: 'Not found',
        detail: 'That item does not exist, or it has been deleted.',
        canRetry: false,
      }
    }
    if (error.status >= 500) {
      return {
        kind: 'server',
        title: 'The server had a problem',
        detail: `The API answered ${error.status}. This is a fault on our side, not your data — nothing has been lost.`,
        canRetry: true,
      }
    }
    return {
      kind: 'client',
      title: 'That request was rejected',
      // ApiError.message is the server's `detail` when it sent a string one,
      // and "Request failed (422)" otherwise — either way it beats a generic.
      detail: `${error.message} (${error.status})`,
      canRetry: false,
    }
  }

  // A rejected fetch. Every browser reports this as a TypeError, as does an
  // unparseable API_URL, which is the same problem from the user's side: no
  // request reached a server.
  if (error instanceof TypeError) {
    return {
      kind: 'unreachable',
      title: "Can't reach the server",
      detail:
        'No response from the API. It may be waking up — the server sleeps when idle and takes 30–60s to start. Retry in a moment.',
      canRetry: true,
    }
  }

  return {
    kind: 'unknown',
    title: 'Something went wrong',
    detail:
      error instanceof Error && error.message
        ? error.message
        : 'The request failed for an unknown reason.',
    canRetry: true,
  }
}
