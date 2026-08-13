import { useMemo } from 'react'
import { useTheme } from '../../theme/ThemeProvider'

/** Chart colours, read from the CSS custom properties so there is one palette and not
 *  a second copy of every hex in TypeScript. Names follow docs/design/README.md. */
export interface ChartTokens {
  acc: string
  acc2: string
  amber: string
  barfill: string
  up: string
  down: string
  grid: string
  axis: string
  ink: string
  ink2: string
  ink3: string
  ink4: string
  panel: string
  rule: string
  /** "61, 58, 176" — the accent as an rgb triple, for `alpha()`. */
  accRgb: string
  /** Arbitrary-N ramp, for the place-vs-place compare chart only. */
  series: string[]
}

/**
 * `rgba(61, 58, 176, 0.11)` as a literal string.
 *
 * Recharts sets `fill` and `stroke` as SVG presentation attributes, where `var()`
 * substitution is not dependable — so the tinted fills the handoff specifies
 * (`rgba(var(--acc-rgb), .11)` for the year-over-year band, the scatter's 0.22 → 1.00
 * recency ramp) have to be resolved in JS rather than handed to the browser as CSS.
 */
export function alpha(rgb: string, a: number): string {
  return `rgba(${rgb}, ${a})`
}

function readTokens(): ChartTokens {
  const style = getComputedStyle(document.documentElement)
  const get = (name: string) => style.getPropertyValue(name).trim()
  const acc = get('--acc')
  const acc2 = get('--acc2')
  const amber = get('--amber')
  const down = get('--down')
  return {
    acc,
    acc2,
    amber,
    down,
    barfill: get('--barfill'),
    up: get('--up'),
    grid: get('--grid'),
    axis: get('--axis'),
    ink: get('--ink'),
    ink2: get('--ink2'),
    ink3: get('--ink3'),
    ink4: get('--ink4'),
    panel: get('--panel'),
    rule: get('--rule'),
    accRgb: get('--acc-rgb'),
    series: [acc, amber, down, acc2],
  }
}

/**
 * Recharts takes colours as props, not CSS, so it cannot inherit a theme swap the way
 * styled elements do — the values have to be re-read and the charts re-rendered.
 *
 * This keys off the *resolved* theme rather than subscribing to
 * `prefers-color-scheme` directly. Subscribing to the media query was correct while
 * the OS was the only input; now that the top bar can set `data-theme` by hand, a
 * manual toggle fires no media-query event and every chart would keep its boot-time
 * colours against the new background.
 *
 * Read during render, not in an effect. An effect that sets state on mount costs an
 * extra render of every chart on every page load, and that is not free: it lands while
 * Recharts' entry animation is starting and orphans it, leaving each line stuck at a
 * few percent of its `stroke-dasharray`. Reading here is safe because ThemeProvider
 * writes `data-theme` imperatively *before* the state update that gets us here, so the
 * computed style is already the incoming palette.
 */
export function useChartTokens(): ChartTokens {
  const { resolved } = useTheme()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- readTokens reads the DOM
  // attribute that `resolved` drives; `resolved` is the real dependency.
  return useMemo(readTokens, [resolved])
}

export const MAX_COMPARE_SERIES = 4
