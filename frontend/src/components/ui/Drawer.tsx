import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { LAYERS } from '../../styles/layers'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  /** 420px in the handoff. */
  width?: number
  children: ReactNode
}

/**
 * A panel over the page you were on, rather than a route.
 *
 * The handoff is specific about this: editing a place from the places table should not
 * lose the table. A route would unmount it, scroll to the top, and make "cancel" a
 * back-navigation.
 *
 * Portalled to `document.body`, which is why `data-theme` lives on `documentElement` and
 * not on a wrapper inside `#root` — a wrapper would leave this rendering in the default
 * palette.
 *
 * Unlike the metric popover in 2b, this *does* have a scrim: a modal edit should stop
 * you clicking the table underneath. It takes its z-index from `LAYERS`, below the
 * panel, and the ordering is asserted in styles/layers.test.ts.
 */
export function Drawer({ open, onClose, title, width = 420, children }: Props) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreFocusTo = useRef<Element | null>(null)

  useEffect(() => {
    if (!open) return
    restoreFocusTo.current = document.activeElement

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    /* Focus the first field rather than the panel, so a keyboard user starts typing
       instead of tabbing. */
    const firstField = panelRef.current?.querySelector<HTMLElement>(
      'input, select, textarea, button',
    )
    firstField?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      /* Send focus back where it came from — otherwise it lands on <body> and the next
         Tab starts from the top of the page. */
      ;(restoreFocusTo.current as HTMLElement | null)?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="drawer-root">
      <div
        className="drawer-scrim"
        style={{ zIndex: LAYERS.drawerScrim }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className="drawer-panel"
        style={{ width, zIndex: LAYERS.drawer }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={panelRef}
      >
        <div className="drawer-head">
          <h2>{title}</h2>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
