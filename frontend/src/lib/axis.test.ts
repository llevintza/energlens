import { describe, expect, it } from 'vitest'

import { niceStep, paddedDomain, symmetricDomain, zeroBasedDomain } from './axis'

describe('the 1 / 2 / 5 ladder', () => {
  it('only ever picks 1, 2 or 5 times a power of ten', () => {
    for (let span = 0.001; span < 100000; span *= 1.07) {
      const step = niceStep(span)
      const mantissa = step / 10 ** Math.floor(Math.log10(step))
      expect([1, 2, 5, 10]).toContain(Math.round(mantissa * 1e6) / 1e6)
    }
  })

  it('never picks 2.5, which is the step that produced duplicate labels', () => {
    for (let span = 0.001; span < 100000; span *= 1.01) {
      const step = niceStep(span)
      const mantissa = step / 10 ** Math.floor(Math.log10(step))
      expect(Math.round(mantissa * 100) / 100).not.toBe(2.5)
    }
  })

  it('produces distinct labels once ticks are formatted the way the design asks', () => {
    // The trap in the handoff: effective price ticks are shown to two decimals, so a
    // step that is not representable at two decimals collides.
    const domain = paddedDomain([0.2251, 0.2886], 3)
    const labels = domain.ticks.map((t) => `€${t.toFixed(2)}`)
    expect(new Set(labels).size).toBe(labels.length)
  })
})

describe('zero-based domains', () => {
  it('starts at zero for all-positive data', () => {
    const domain = zeroBasedDomain([12, 46, 31])
    expect(domain.min).toBe(0)
    expect(domain.ticks[0]).toBe(0)
    expect(domain.max).toBeGreaterThanOrEqual(46)
  })

  it('floors a negative base to a step multiple so ticks land on round numbers', () => {
    // The handoff's own example: −13 must not produce −13, 37, 87, 137.
    const domain = zeroBasedDomain([-13, 137], 3)
    expect(domain.ticks).toContain(0)
    for (const tick of domain.ticks) {
      expect(Math.abs(tick / domain.step - Math.round(tick / domain.step))).toBeLessThan(1e-9)
    }
    expect(domain.min).toBeLessThanOrEqual(-13)
    expect(domain.max).toBeGreaterThanOrEqual(137)
  })

  it('always includes zero, so a negative series is read against its baseline', () => {
    expect(zeroBasedDomain([-40, -10]).ticks).toContain(0)
    expect(zeroBasedDomain([10, 40]).ticks).toContain(0)
  })

  it('survives an empty or all-null series without producing NaN', () => {
    const domain = zeroBasedDomain([null, undefined])
    expect(Number.isFinite(domain.min)).toBe(true)
    expect(Number.isFinite(domain.max)).toBe(true)
    expect(domain.max).toBeGreaterThan(domain.min)
  })
})

describe('padded domains', () => {
  it('does not flatten a price series against a zero baseline', () => {
    const domain = paddedDomain([0.2251, 0.2886])
    expect(domain.min).toBeGreaterThan(0)
    // The movement should occupy a real share of the axis, not a sliver.
    const span = domain.max - domain.min
    expect((0.2886 - 0.2251) / span).toBeGreaterThan(0.3)
  })

  it('keeps every value inside the axis', () => {
    const values = [0.2251, 0.2886, 0.24, 0.31]
    const domain = paddedDomain(values)
    for (const v of values) {
      expect(v).toBeGreaterThanOrEqual(domain.min)
      expect(v).toBeLessThanOrEqual(domain.max)
    }
  })
})

describe('symmetric domains', () => {
  it('is symmetric about zero so equal moves look equal', () => {
    const domain = symmetricDomain([-8.2, 3.1, 5.5])
    expect(domain.min).toBe(-domain.max)
    expect(domain.ticks).toContain(0)
  })

  it('covers the largest excursion in either direction', () => {
    const domain = symmetricDomain([-8.2, 3.1])
    expect(domain.max).toBeGreaterThanOrEqual(8.2)
  })

  it('does not collapse when every change is zero', () => {
    const domain = symmetricDomain([0, 0, 0])
    expect(domain.max).toBeGreaterThan(domain.min)
  })
})
