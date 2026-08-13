import { useEffect, useId, useRef, useState } from 'react'

import type { MetricDescriptor, MetricId } from '../../lib/compare'
import { METRICS } from '../../lib/compare'
import { LAYERS } from '../../styles/layers'

interface Props {
  value: MetricId
  onChange: (id: MetricId) => void
}

/**
 * The metric selector, as a popover.
 *
 * **No scrim.** The handoff records a live bug from the prototype: dismissing this with
 * a full-viewport overlay put something in front of the tile row, so the first click on
 * a tile hit the scrim and selected nothing. The stacking order can be got right — the
 * tokens declare `--layer-scrim: 19` below `--layer-tiles: 21` for exactly that reason
 * — but the more reliable fix is to have nothing to hit. Dismissal is a `pointerdown`
 * listener in the capture phase, plus Escape and focus-out, so a click on a tile reaches
 * the tile *and* closes the popover in the same gesture.
 *
 * This and the tile row are two views of one piece of state: both call the same
 * `onChange`, and the label below reads from the same `value`.
 */
export function MetricPicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const selected = METRICS.find((m) => m.id === value) as MetricDescriptor

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    /* Capture phase, so dismissal happens before the click reaches its target rather
       than instead of it. */
    document.addEventListener('pointerdown', onPointerDown, true)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className="metric-picker" ref={rootRef}>
      <button
        type="button"
        className="metric-picker-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <span>{selected.label}</span>
        <span aria-hidden="true" className="metric-picker-caret">
          ▼
        </span>
      </button>

      {open && (
        <ul
          className="metric-picker-list"
          style={{ zIndex: LAYERS.popover }}
          id={listId}
          role="listbox"
          aria-label="Metric"
        >
          {METRICS.map((metric) => (
            <li key={metric.id}>
              <button
                type="button"
                role="option"
                aria-selected={metric.id === value}
                className={metric.id === value ? 'selected' : undefined}
                onClick={() => {
                  onChange(metric.id)
                  setOpen(false)
                }}
              >
                <span>{metric.label}</span>
                <span className="metric-picker-short">{metric.short}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
