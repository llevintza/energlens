// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { HomeRoute } from './HomeRoute'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: vi.fn() }
})

const { api } = await import('../api/client')

afterEach(cleanup)

function renderHome() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/places/:id" element={<div>dashboard</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * Issue #8 in one screen. An empty account and a failed request look identical to a
 * user unless the code distinguishes them, and telling someone their places are gone
 * when the network merely blinked is the bug the whole error-handling pass exists to
 * fix. So: first run is reachable *only* from a query that genuinely succeeded.
 */
describe('empty is not the same as failed', () => {
  it('shows first run when the request succeeded and returned nothing', async () => {
    vi.mocked(api).mockResolvedValue([])
    renderHome()
    expect(await screen.findByText('Nothing here yet.')).toBeDefined()
    expect(screen.getByRole('link', { name: /Add your first place/ })).toBeDefined()
  })

  it('shows an error — never first run — when the request failed', async () => {
    vi.mocked(api).mockRejectedValue(new ApiError(500, 'boom'))
    renderHome()
    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByText('Nothing here yet.')).toBeNull()
    expect(screen.queryByRole('link', { name: /Add your first place/ })).toBeNull()
  })

  it('shows an error, not first run, when the API is unreachable', async () => {
    vi.mocked(api).mockRejectedValue(new TypeError('Failed to fetch'))
    renderHome()
    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByText('Nothing here yet.')).toBeNull()
  })

  it('goes to the first place when there is one', async () => {
    vi.mocked(api).mockResolvedValue([{ id: 'abc', name: 'Main Residence' }])
    renderHome()
    expect(await screen.findByText('dashboard')).toBeDefined()
    expect(screen.queryByText('Nothing here yet.')).toBeNull()
  })
})
