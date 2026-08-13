import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import { usePlaces } from '../api/hooks'
import type { Bill } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Segmented } from '../components/ui/Segmented'
import { usePreferences } from '../prefs/PreferencesProvider'
import type { ThemeChoice } from '../theme/ThemeProvider'
import { useTheme } from '../theme/ThemeProvider'

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="settings-section">
      <h2 className="settings-label">{label}</h2>
      {children}
    </section>
  )
}

function Row({
  label,
  description,
  children,
}: {
  label: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div className="settings-row">
      <div>
        <div className="settings-row-label">{label}</div>
        {description && <div className="settings-row-desc">{description}</div>}
      </div>
      <div className="settings-row-control">{children}</div>
    </div>
  )
}

/**
 * 3g — settings, grouped by what each setting affects rather than by data model.
 *
 * That is the organising decision, and it is why theme sits beside number format rather
 * than under "account".
 *
 * **Three sections, not the handoff's four.** "Import defaults" — the confidence
 * threshold and arithmetic tolerance — configures the PDF import screen, which is
 * deferred to #24 because there is no upload API to build it against. Settings that
 * configure a feature nobody can reach are worse than no settings, so the section is
 * left out entirely rather than shipped disabled.
 */
export function SettingsPage() {
  const { user, logout } = useAuth()
  const { choice, setChoice } = useTheme()
  const { prefs, setPrefs } = usePreferences()
  const places = usePlaces()
  const navigate = useNavigate()

  const [email, setEmail] = useState(user?.email ?? '')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState<null | 'email' | 'password'>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const patchMe = async (body: Record<string, string>, what: 'email' | 'password') => {
    setSaving(what)
    setNotice(null)
    setFailure(null)
    try {
      await api('/users/me', { method: 'PATCH', body })
      setNotice(what === 'email' ? 'Email updated.' : 'Password updated.')
      if (what === 'password') setPassword('')
    } catch (error) {
      setFailure(
        error instanceof ApiError && error.status === 400
          ? 'That was rejected — the email may already be in use, or the password too weak.'
          : 'Could not save that change.',
      )
    } finally {
      setSaving(null)
    }
  }

  /**
   * Export runs client-side. `/places` and `/places/{id}/bills` together *are* the
   * account, so there is nothing a backend endpoint would add — and the label says
   * exactly what comes out rather than implying a server-side archive.
   */
  const exportAll = async () => {
    setExporting(true)
    setFailure(null)
    try {
      const list = places.data ?? (await api<Awaited<ReturnType<typeof api>>>('/places'))
      const withBills = await Promise.all(
        (list as { id: string }[]).map(async (place) => ({
          ...place,
          bills: await api<Bill[]>(`/places/${place.id}/bills`),
        })),
      )
      const payload = {
        exported_at: new Date().toISOString(),
        account: user?.email,
        places: withBills,
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'energlens-export.json'
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      setFailure('Could not build the export.')
    } finally {
      setExporting(false)
    }
  }

  const deleteAccount = async () => {
    if (
      !window.confirm(
        'Delete your account? Every place and every bill goes with it, and this cannot be undone.',
      )
    ) {
      return
    }
    setDeleting(true)
    try {
      await api('/users/me', { method: 'DELETE' })
      logout()
      navigate('/login', { replace: true })
    } catch {
      setFailure('Could not delete the account.')
      setDeleting(false)
    }
  }

  return (
    <div className="settings">
      <h1 className="dash-title">Settings</h1>

      {notice && <p className="settings-notice">{notice}</p>}
      {failure && (
        <p className="settings-failure" role="alert">
          {failure}
        </p>
      )}

      <Section label="Sign-in">
        <Row label="Email" description="Used to sign in, and nowhere else.">
          <div className="settings-inline">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-label="Email"
            />
            <button
              type="button"
              className="btn small"
              disabled={saving !== null || email === user?.email || email.trim() === ''}
              onClick={() => patchMe({ email }, 'email')}
            >
              {saving === 'email' ? 'Saving…' : 'Save'}
            </button>
          </div>
        </Row>

        <Row label="Password" description="At least 8 characters.">
          <div className="settings-inline">
            <input
              type="password"
              value={password}
              placeholder="New password"
              autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)}
              aria-label="New password"
            />
            <button
              type="button"
              className="btn small"
              disabled={saving !== null || password.length < 8}
              onClick={() => patchMe({ password }, 'password')}
            >
              {saving === 'password' ? 'Saving…' : 'Change'}
            </button>
          </div>
        </Row>

        {/* Read-only on purpose. There is no endpoint to link or unlink a provider, and
            the handoff's own rule is not to build a control that cannot act. */}
        <Row
          label="Connected accounts"
          description="Linking and unlinking providers is not available yet."
        >
          <span className="settings-readonly">
            {user?.is_verified ? 'Verified' : 'Email and password'}
          </span>
        </Row>
      </Section>

      <Section label="Display">
        <Row
          label="Theme"
          description="SYSTEM follows your device, and keeps following it when it changes."
        >
          <Segmented
            ariaLabel="Theme"
            monoLabels
            options={[
              { value: 'light', label: 'LIGHT' },
              { value: 'dark', label: 'DARK' },
              { value: 'system', label: 'SYSTEM' },
            ]}
            value={choice}
            onChange={(next) => setChoice(next as ThemeChoice)}
          />
        </Row>

        <Row label="Number format" description="How figures are grouped and separated.">
          <Segmented
            ariaLabel="Number format"
            options={[
              { value: 'locale', label: 'Match my device' },
              { value: 'plain', label: '1234.56' },
            ]}
            value={prefs.numberFormat}
            onChange={(numberFormat) => setPrefs({ numberFormat })}
          />
        </Row>

        <Row label="Default range" description="Which window a place opens on.">
          <Segmented
            ariaLabel="Default range"
            monoLabels
            options={[
              { value: '12m', label: '12M' },
              { value: '24m', label: '24M' },
              { value: 'all', label: 'ALL' },
            ]}
            value={prefs.defaultRange}
            onChange={(defaultRange) => setPrefs({ defaultRange })}
          />
        </Row>
      </Section>

      <Section label="Data">
        <Row
          label="Export everything"
          description="Every place and every bill, as JSON, built in your browser."
        >
          <button type="button" className="btn small" onClick={exportAll} disabled={exporting}>
            {exporting ? 'Building…' : 'Download'}
          </button>
        </Row>
      </Section>

      {/* Behind its own rule, and last. An irreversible action should not sit adjacent
          to a reversible one. */}
      <section className="settings-section settings-danger">
        <Row
          label="Delete account"
          description="Your account, every place and every bill. This cannot be undone."
        >
          <button
            type="button"
            className="btn small danger"
            onClick={deleteAccount}
            disabled={deleting}
          >
            {deleting ? 'Deleting…' : 'Delete account'}
          </button>
        </Row>
      </section>
    </div>
  )
}
