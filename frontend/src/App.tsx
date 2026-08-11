import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { AuthProvider } from './auth/AuthContext'
import { OAuthCallbackPage } from './auth/OAuthCallbackPage'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { Layout } from './components/Layout'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlaceDetailPage } from './pages/PlaceDetailPage'
import { PlacesPage } from './pages/PlacesPage'
import { RegisterPage } from './pages/RegisterPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/auth/callback" element={<OAuthCallbackPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<Layout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/places" element={<PlacesPage />} />
                <Route path="/places/:placeId" element={<PlaceDetailPage />} />
              </Route>
            </Route>
            {/* GitHub Pages serves 404.html for unknown paths, so a mistyped
                deep link lands here rather than 404ing at the CDN. Render a
                page instead of redirecting: a redirect would erase the bad URL
                from the address bar and the back stack, leaving the visitor on
                the dashboard with no idea the link was wrong. */}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
