// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import type { MetricId } from '../../lib/compare'
import { METRICS } from '../../lib/compare'
import { MetricPicker } from './MetricPicker'

afterEach(cleanup)

/**
 * A stand-in for the compare page's shared state: the picker and a row of tiles, both
 * reading and writing the same `metric`. The handoff calls this out because in the
 * prototype the two drifted apart, so it is asserted in both directions.
 *
 * What this file does NOT test is whether a click on a tile can be swallowed by an
 * overlay — jsdom has no layout engine, so `getBoundingClientRect()` is all zeros and
 * `document.elementFromPoint` does not exist. The picker is built without a scrim
 * precisely so there is nothing to intercept the click; that is verified in a browser.
 */
function Harness() {
  const [metric, setMetric] = useState<MetricId>('total')
  return (
    <div>
      <MetricPicker value={metric} onChange={setMetric} />
      <div>
        {METRICS.map((m) => (
          <button
            key={m.id}
            type="button"
            aria-pressed={m.id === metric}
            onClick={() => setMetric(m.id)}
          >
            tile:{m.short}
          </button>
        ))}
      </div>
    </div>
  )
}

describe('metric selection is one piece of state with two views', () => {
  it('moves the tile selection when the dropdown is used', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: /Total cost/ }))
    await userEvent.click(screen.getByRole('option', { name: /Taxes/ }))

    expect(screen.getByRole('button', { name: 'tile:TAX' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'tile:COST' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('updates the dropdown label when a tile is clicked', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: 'tile:€/DAY' }))
    expect(screen.getByRole('button', { name: /Cost per day/ })).toBeDefined()
  })

  it('closes after a choice rather than leaving the list open', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: /Total cost/ }))
    expect(screen.getByRole('listbox')).toBeDefined()
    await userEvent.click(screen.getByRole('option', { name: /Consumption/ }))
    expect(screen.queryByRole('listbox')).toBeNull()
  })
})

describe('dismissal', () => {
  it('renders no overlay element that could intercept a tile click', async () => {
    const { container } = render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: /Total cost/ }))
    // The prototype's bug was a full-viewport scrim above the tile row. Nothing here
    // may be fixed-position and full-size while the popover is open.
    const fixed = [...container.querySelectorAll('*')].filter((el) => {
      const style = (el as HTMLElement).style
      return style.position === 'fixed' && (style.inset !== '' || style.width === '100vw')
    })
    expect(fixed).toHaveLength(0)
  })

  it('closes on Escape', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: /Total cost/ }))
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('closes on a pointer press outside, and the outside target still gets the click', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: /Total cost/ }))
    // A tile click while the popover is open must both close it AND select the metric.
    await userEvent.click(screen.getByRole('button', { name: 'tile:TAX' }))
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(screen.getByRole('button', { name: 'tile:TAX' }).getAttribute('aria-pressed')).toBe('true')
  })
})
