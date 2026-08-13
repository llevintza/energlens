import { describe, expect, it } from 'vitest'

import type { ChartTokens } from '../components/charts/chartTheme'
import { METRICS, METRIC_BY_ID, MODE_BY_ID, buildMix, toCsv } from './compare'
import { MAIN_RESIDENCE, seedBillsNewestFirst } from './fixtures'
import { monthlyBuckets, parseBills } from './metrics'

/* Colours are data to the builders, so they are testable in node with no DOM. */
const tokens: ChartTokens = {
  acc: '#acc',
  acc2: '#acc2',
  amber: '#amber',
  barfill: '#bar',
  up: '#up',
  down: '#down',
  grid: '#grid',
  axis: '#axis',
  ink: '#ink',
  ink2: '#ink2',
  ink3: '#ink3',
  ink4: '#ink4',
  panel: '#panel',
  rule: '#rule',
  accRgb: '1, 2, 3',
  series: [],
}

const buckets = monthlyBuckets(parseBills(seedBillsNewestFirst(MAIN_RESIDENCE)))
const format = { currency: 'EUR' }
const base = { buckets, tokens, format }

describe('every metric × every mode', () => {
  it('builds without throwing, for all 28 combinations', () => {
    for (const metric of METRICS.filter((m) => m.view !== 'mix')) {
      for (const mode of ['yoy', 'years', 'mom', 'same'] as const) {
        const data = MODE_BY_ID[mode].build({ ...base, metric, month: 1 })
        expect(data.rows.length).toBeGreaterThan(0)
        expect(data.series.length).toBeGreaterThan(0)
      }
    }
  })

  it('takes the axis type from the metric, not the mode', () => {
    for (const mode of ['yoy', 'years'] as const) {
      // Prices get a padded minimum: a zero baseline flattens the movement.
      const price = MODE_BY_ID[mode].build({ ...base, metric: METRIC_BY_ID.eff })
      expect(price.domain.min).toBeGreaterThan(0)
      // Quantities get a zero base, because their size is the point.
      const cost = MODE_BY_ID[mode].build({ ...base, metric: METRIC_BY_ID.total })
      expect(cost.domain.min).toBe(0)
    }
  })
})

describe('yoy', () => {
  const data = MODE_BY_ID.yoy.build({ ...base, metric: METRIC_BY_ID.total })

  it('aligns both years at the same twelve positions', () => {
    expect(data.rows).toHaveLength(12)
    expect(data.rows.every((r) => 'current' in r && 'prior' in r)).toBe(true)
  })

  it('fills the band between the two years', () => {
    expect(data.band).toEqual({
      upperKey: 'current',
      lowerKey: 'prior',
      fill: 'rgba(1, 2, 3, 0.11)',
    })
  })

  it('draws this year heavier than last', () => {
    const current = data.series.find((s) => s.key === 'current')
    const prior = data.series.find((s) => s.key === 'prior')
    expect(current!.strokeWidth).toBeGreaterThan(prior!.strokeWidth)
    expect(prior!.dotRadius).toBe(false)
  })
})

describe('years overlaid', () => {
  it('puts every month on a Jan–Dec axis', () => {
    const data = MODE_BY_ID.years.build({ ...base, metric: METRIC_BY_ID.total })
    expect(data.rows).toHaveLength(12)
    expect(data.rows[0].x).toBe('JAN')
    expect(data.rows[11].x).toBe('DEC')
  })

  it('stops a partial year where the data stops instead of interpolating', () => {
    // The seed ends in July 2026, so 2026 has seven months and no August.
    const data = MODE_BY_ID.years.build({ ...base, metric: METRIC_BY_ID.total })
    const august = data.rows[7]
    expect(august.y2026).toBeNull()
    const july = data.rows[6]
    expect(typeof july.y2026).toBe('number')
  })

  it('marks partial years in the legend with their month count', () => {
    const data = MODE_BY_ID.years.build({ ...base, metric: METRIC_BY_ID.total })
    expect(data.legend.some((l) => l.label === '2026 (7 mo)')).toBe(true)
    expect(data.legend.some((l) => l.label === '2025')).toBe(true)
  })

  it('honours the year chips', () => {
    const data = MODE_BY_ID.years.build({
      ...base,
      metric: METRIC_BY_ID.total,
      years: [2025],
    })
    expect(data.series).toHaveLength(1)
    expect(data.series[0].key).toBe('y2025')
  })
})

describe('month over month', () => {
  const data = MODE_BY_ID.mom.build({ ...base, metric: METRIC_BY_ID.total })

  it('yields one fewer row than there are months', () => {
    expect(data.rows).toHaveLength(buckets.length - 1)
    expect(data.rows).toHaveLength(23)
  })

  it('centres a symmetric axis on zero', () => {
    expect(data.domain.min).toBe(-data.domain.max)
    expect(data.domain.ticks).toContain(0)
    expect(data.zeroLine).toBe(true)
  })

  it('colours by direction', () => {
    expect(new Set(data.cellColors)).toEqual(new Set(['#up', '#down']))
  })
})

describe('same month, each year', () => {
  it('gives one bar per year that has the chosen month', () => {
    const data = MODE_BY_ID.same.build({ ...base, metric: METRIC_BY_ID.total, month: 1 })
    // January appears in 2025 and 2026 in a window ending July 2026.
    expect(data.rows.map((r) => r.x)).toEqual(['2025', '2026'])
    expect(data.valueLabels).toBe(true)
  })

  it('gives the latest year the accent and earlier ones the muted tone', () => {
    const data = MODE_BY_ID.same.build({ ...base, metric: METRIC_BY_ID.total, month: 1 })
    expect(data.cellColors).toEqual(['#acc2', '#acc'])
  })

  it('handles a month that only one year has', () => {
    const data = MODE_BY_ID.same.build({ ...base, metric: METRIC_BY_ID.total, month: 8 })
    // August 2024 and 2025 are in range; August 2026 is not.
    expect(data.rows.length).toBeGreaterThan(0)
  })
})

describe('mix', () => {
  it('decomposes the price into three bands that sum to the effective price', () => {
    const { rows } = buildMix(buckets)
    const july = rows[rows.length - 1]
    const total = (july.energy ?? 0) + (july.standing ?? 0) + (july.tax ?? 0)
    expect(total).toBeCloseTo(0.2886, 3)
  })

  it('shows the standing charge swelling in light months', () => {
    // The whole reason the chart exists: the same fixed fee over fewer kWh is a bigger
    // number per unit, which is why cutting consumption raises the headline price.
    const { rows } = buildMix(buckets)
    const january = rows.find((r) => r.x === 'JAN')
    const july = rows.find((r) => r.x === 'JUL')
    expect(july!.standing).toBeGreaterThan(january!.standing!)
  })

  it('is zero-based, so the bands are read as proportions', () => {
    expect(buildMix(buckets).domain.min).toBe(0)
  })
})

describe('CSV export', () => {
  it('emits the selected metric and mode', () => {
    const data = MODE_BY_ID.yoy.build({ ...base, metric: METRIC_BY_ID.total })
    const csv = toCsv(data, METRIC_BY_ID.total, MODE_BY_ID.yoy)
    expect(csv.split('\n')[0]).toBe('# Total cost — Year over year')
    expect(csv).toContain('"Previous 12 months"')
    expect(csv.split('\n')).toHaveLength(14) // comment + header + 12 months
  })
})
