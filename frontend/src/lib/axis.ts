/**
 * Axis domains and ticks.
 *
 * These live here as tested functions rather than inline in chart components because
 * both of the traps below produce charts that look plausible and are wrong, which is
 * the kind of bug that survives review.
 *
 * Charts must pass **both** `domain` and `ticks` to Recharts' `YAxis`. Passing only the
 * domain lets Recharts derive its own ticks and both traps come straight back.
 */

export interface Domain {
  min: number
  max: number
  ticks: number[]
  /** The chosen step, exposed so a caller can format ticks to a matching precision. */
  step: number
}

/**
 * A step from the 1 / 2 / 5 × 10ⁿ ladder.
 *
 * Trap one: an "even" step like 2.5 produces duplicate labels the moment ticks are
 * formatted to two decimals — 0.225 / 0.25 / 0.275 all render as €0.23 / €0.25 / €0.28
 * in one range and collide in another. Restricting the ladder to 1, 2 and 5 means a
 * step is always representable at the precision it will be shown at.
 */
export function niceStep(span: number, targetTicks = 4): number {
  if (!Number.isFinite(span) || span <= 0) return 1
  const rough = span / Math.max(1, targetTicks)
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const normalized = rough / magnitude
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return factor * magnitude
}

function ticksBetween(min: number, max: number, step: number): number[] {
  const out: number[] = []
  /* Accumulating `value += step` drifts on non-terminating binary fractions (0.1 added
     ten times is not 1), which shows up as a tick labelled €0.30000000000000004. */
  const count = Math.round((max - min) / step)
  for (let i = 0; i <= count; i++) {
    out.push(Number((min + i * step).toPrecision(12)))
  }
  return out
}

function finite(values: readonly (number | null | undefined)[]): number[] {
  return values.filter((v): v is number => v !== null && v !== undefined && Number.isFinite(v))
}

/**
 * Zero-based, for the metrics where the quantity's size is the point — cost, kWh,
 * energy, taxes, cost per day.
 *
 * Trap two: when the data goes negative the axis must not simply start at the raw
 * minimum, or every tick is an odd number (−13, 37, 87, 137) instead of landing on
 * round ones (−50, 0, 50, 100, 150). Flooring the base to a multiple of the step fixes
 * it, and matters because the cumulative-excess chart runs negative through its first
 * winter by design.
 */
export function zeroBasedDomain(
  values: readonly (number | null | undefined)[],
  targetTicks = 4,
): Domain {
  const nums = finite(values)
  if (nums.length === 0) return { min: 0, max: 1, ticks: [0, 1], step: 1 }
  const dataMax = Math.max(...nums, 0)
  const dataMin = Math.min(...nums, 0)
  const step = niceStep(dataMax - dataMin, targetTicks)
  const min = Math.floor(dataMin / step) * step
  const max = min + Math.ceil((dataMax - min) / step) * step
  const top = max === min ? min + step : max
  return { min, max: top, ticks: ticksBetween(min, top, step), step }
}

/**
 * Padded minimum, for effective price and contracted tariff.
 *
 * A zero baseline flattens a series that only moves between €0.22 and €0.29 into a
 * straight line — and that movement is the entire finding the redesign exists to show.
 */
export function paddedDomain(
  values: readonly (number | null | undefined)[],
  targetTicks = 4,
  padFraction = 0.015,
): Domain {
  const nums = finite(values)
  if (nums.length === 0) return { min: 0, max: 1, ticks: [0, 1], step: 1 }
  const dataMax = Math.max(...nums)
  const dataMin = Math.min(...nums)
  const floor = dataMin * (1 - padFraction)
  const step = niceStep(dataMax - floor, targetTicks)
  const min = Math.floor(floor / step) * step
  const max = min + Math.ceil((dataMax - min) / step) * step
  const top = max === min ? min + step : max
  return { min, max: top, ticks: ticksBetween(min, top, step), step }
}

/**
 * Symmetric about zero, for the diverging month-over-month bars. An asymmetric axis
 * would make a −8% month look smaller than a +8% one.
 */
export function symmetricDomain(
  values: readonly (number | null | undefined)[],
  targetTicks = 4,
): Domain {
  const nums = finite(values)
  const peak = nums.length === 0 ? 0 : Math.max(...nums.map(Math.abs))
  if (peak === 0) return { min: -1, max: 1, ticks: [-1, 0, 1], step: 1 }
  const step = niceStep(peak * 2, targetTicks)
  const bound = Math.ceil(peak / step) * step
  return { min: -bound, max: bound, ticks: ticksBetween(-bound, bound, step), step }
}
