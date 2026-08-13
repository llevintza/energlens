import { describe, expect, it } from 'vitest'

import { LAYERS } from './layers'

/**
 * The stacking order is an invariant, not a preference — see layers.ts for the bug it
 * exists to prevent.
 */
describe('stacking order', () => {
  it('keeps a dismissal scrim below the tiles it must not intercept', () => {
    expect(LAYERS.scrim).toBeLessThan(LAYERS.popover)
    expect(LAYERS.popover).toBeLessThan(LAYERS.tiles)
  })

  it('keeps the drawer above its own scrim', () => {
    expect(LAYERS.drawerScrim).toBeLessThan(LAYERS.drawer)
  })

  it('puts the drawer above the page chrome it covers', () => {
    expect(LAYERS.drawerScrim).toBeGreaterThan(LAYERS.topbar)
    expect(LAYERS.topbar).toBeGreaterThan(LAYERS.rail)
  })

  it('gives every layer a distinct value, so ordering is never a tie', () => {
    const values = Object.values(LAYERS)
    expect(new Set(values).size).toBe(values.length)
  })
})
