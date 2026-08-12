import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { describeError } from './errors'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('describeError', () => {
  it('reports a rejected fetch as unreachable, not as an error response', () => {
    // What `api()` actually throws when the server is down: fetch rejects with
    // a TypeError, never an ApiError.
    const d = describeError(new TypeError('Failed to fetch'))
    expect(d.kind).toBe('unreachable')
    expect(d.canRetry).toBe(true)
    expect(d.detail).toContain('30–60s')
  })

  it('prefers offline over every other reading', () => {
    vi.stubGlobal('navigator', { onLine: false })
    expect(describeError(new TypeError('Failed to fetch')).kind).toBe('offline')
    expect(describeError(new ApiError(500, 'boom')).kind).toBe('offline')
  })

  it('does not claim offline when the browser reports a connection', () => {
    vi.stubGlobal('navigator', { onLine: true })
    expect(describeError(new TypeError('Failed to fetch')).kind).toBe(
      'unreachable',
    )
  })

  it('treats 404 as a real absence, with no retry offered', () => {
    const d = describeError(new ApiError(404, 'Not Found'))
    expect(d.kind).toBe('notFound')
    expect(d.canRetry).toBe(false)
  })

  it('separates a server fault from an unreachable server', () => {
    const d = describeError(new ApiError(503, 'Service Unavailable'))
    expect(d.kind).toBe('server')
    expect(d.canRetry).toBe(true)
    expect(d.detail).toContain('503')
    expect(d.detail).toContain('nothing has been lost')
  })

  it('surfaces the API detail for a rejected request, and offers no retry', () => {
    const d = describeError(new ApiError(422, 'period_end before period_start'))
    expect(d.kind).toBe('client')
    expect(d.canRetry).toBe(false)
    expect(d.detail).toContain('period_end before period_start')
    expect(d.detail).toContain('422')
  })

  it('falls back to the message when the value is an unrecognised Error', () => {
    const d = describeError(new SyntaxError('Unexpected end of JSON input'))
    expect(d.kind).toBe('unknown')
    expect(d.detail).toBe('Unexpected end of JSON input')
  })

  it('survives a thrown non-Error', () => {
    const d = describeError('just a string')
    expect(d.kind).toBe('unknown')
    expect(d.title).toBe('Something went wrong')
  })
})
