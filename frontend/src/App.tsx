import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { ApiError } from './api/client'
import { AuthProvider } from './auth/AuthContext'
import { OAuthCallbackPage } from './auth/OAuthCallbackPage'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { ErrorBoundary } from './components/ErrorBoundary'
import { AppShell } from './components/shell/AppShell'
import { AuthPage } from './pages/AuthPage'
import { BillDetailPage } from './pages/BillDetailPage'
import { ComparePage } from './pages/ComparePage'
import { DashboardPage } from './pages/DashboardPage'
import { HomeRoute } from './pages/HomeRoute'
import { SettingsPage } from './pages/SettingsPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlaceDetailPage } from './pages/PlaceDetailPage'
import { PlacesPage } from './pages/PlacesPage'
import { PreferencesProvider } from './prefs/PreferencesProvider'
import { ThemeProvider } from './theme/ThemeProvider'

// Where error handling lives, decided once so the app does not grow three
// variants of it: every user-facing word comes from `<QueryError>`, rendered
// inline by the page that owns the failed query. The cache handlers below are
// diagnostics only and never render — a global banner could not put the
// message beside the panel that actually failed.
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) =>
      console.error(`Query ${JSON.stringify(query.queryKey)} failed:`, error),
  }),
  mutationCache: new MutationCache({
    onError: (error) => console.error('Mutation failed:', error),
  }),
  defaultOptions: {
    queries: {
      // Retry the failures that time can fix and none of the ones it cannot.
      // A 4xx says the server understood and refused, so repeating the same
      // request just delays the message; a network failure or a 5xx is very
      // often the free tier waking up, which takes 30-60s.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false
        return failureCount < 3
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8_000),
      staleTime: 30_000,
      // The default, 'online', parks a query at fetchStatus 'paused' the moment
      // the browser believes it is offline: no request is sent, no error is
      // ever produced, and the page sits on "Loading…" indefinitely. That is
      // the same silent failure this whole change exists to remove, so let the
      // fetch run and fail instead — `describeError` reads navigator.onLine and
      // says "You're offline", and the user gets a Retry button rather than a
      // spinner that resolves only if connectivity happens to return.
      networkMode: 'always',
    },
    // Mutations keep the default of no retry: they are not idempotent, and a
    // silently repeated POST would create a second bill. They do need the same
    // networkMode, though — a paused mutation never reports failure either.
    mutations: { networkMode: 'always' },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <PreferencesProvider>
        {/* Outermost net. Anything thrown by the router, the auth provider or a
            page that the inner boundary in AppShell does not cover lands here —
            without it, a render throw leaves an empty #root and no message. */}
        <ErrorBoundary>
          <BrowserRouter basename={import.meta.env.BASE_URL}>
            <AuthProvider>
              <Routes>
                {/* Both paths mount one screen: the path sets the initial mode and the
                    toggle switches without navigating. Keeping both means the links and
                    bookmarks that already exist keep working. */}
                <Route path="/login" element={<AuthPage />} />
                <Route path="/register" element={<AuthPage />} />
                <Route path="/auth/callback" element={<OAuthCallbackPage />} />
                <Route element={<ProtectedRoute />}>
                  <Route element={<AppShell />}>
                    <Route path="/" element={<HomeRoute />} />
                    <Route path="/places" element={<PlacesPage />} />
                    <Route path="/places/:placeId" element={<DashboardPage />} />
                    <Route
                      path="/places/:placeId/compare"
                      element={<ComparePage />}
                    />
                    <Route
                      path="/places/:placeId/bills/:billId"
                      element={<BillDetailPage />}
                    />
                    {/* Bill and place CRUD still lives on the old detail page until
                        #21 turns both forms into drawers over the page you were on.
                        Keeping it routed means "Add bill" leads somewhere real in the
                        meantime, rather than being a control with nothing behind it. */}
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route
                      path="/places/:placeId/manage"
                      element={<PlaceDetailPage />}
                    />
                  </Route>
                </Route>
                {/* GitHub Pages serves 404.html for unknown paths, so a mistyped
                    deep link lands here rather than 404ing at the CDN. Render a
                    page instead of redirecting: a redirect would erase the bad
                    URL from the address bar and the back stack, leaving the
                    visitor on the dashboard with no idea the link was wrong. */}
                <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </AuthProvider>
          </BrowserRouter>
        </ErrorBoundary>
        </PreferencesProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
