import { useEffect, useState } from 'react'

export interface ChartTokens {
  series: string[]
  grid: string
  baseline: string
  muted: string
  surface: string
  ink: string
  inkSecondary: string
  border: string
}

function readTokens(): ChartTokens {
  const style = getComputedStyle(document.documentElement)
  const get = (name: string) => style.getPropertyValue(name).trim()
  return {
    series: [get('--series-1'), get('--series-2'), get('--series-3'), get('--series-4')],
    grid: get('--gridline'),
    baseline: get('--baseline'),
    muted: get('--muted-ink'),
    surface: get('--surface-1'),
    ink: get('--text-primary'),
    inkSecondary: get('--text-secondary'),
    border: get('--hairline'),
  }
}

/** Chart colors come from the CSS custom properties so light/dark stay in sync. */
export function useChartTokens(): ChartTokens {
  const [tokens, setTokens] = useState<ChartTokens>(readTokens)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => requestAnimationFrame(() => setTokens(readTokens()))
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [])
  return tokens
}

/** Series color follows the place's position in the full place list (stable
 * identity), never its position in a filtered view. */
export function seriesColor(tokens: ChartTokens, index: number): string {
  return tokens.series[index] ?? tokens.series[tokens.series.length - 1]
}

export const MAX_COMPARE_SERIES = 4
