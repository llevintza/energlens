export interface User {
  id: string
  email: string
  is_active: boolean
  is_verified: boolean
}

export interface Place {
  id: string
  name: string
  address_line1: string
  address_line2: string | null
  city: string
  region: string | null
  postal_code: string
  country_code: string
  currency_code: string
  created_at: string
  updated_at: string
}

export type PlaceInput = Omit<Place, 'id' | 'created_at' | 'updated_at'>

export type UtilityType = 'electricity' | 'gas' | 'water'
export type BillSource = 'manual' | 'script' | 'ai'

// Money/decimal fields arrive as strings to preserve precision.
export interface Bill {
  id: string
  place_id: string
  utility_type: UtilityType
  period_start: string
  period_end: string
  consumption: string | null
  unit: string
  unit_price: string | null
  fixed_charges: string | null
  taxes: string | null
  total_amount: string
  currency_code: string
  provider_name: string | null
  raw_file_ref: string | null
  source: BillSource
  notes: string | null
  created_at: string
  updated_at: string
}

export interface BillInput {
  utility_type: UtilityType
  period_start: string
  period_end: string
  consumption: string | null
  unit: string
  unit_price: string | null
  fixed_charges: string | null
  taxes: string | null
  total_amount: string
  provider_name: string | null
  source: BillSource
  notes: string | null
}

export type Metric = 'consumption' | 'cost' | 'unit_price'
export type Granularity = 'month' | 'bill'

export interface SeriesPoint {
  period: string
  value: number
}

export interface SeriesResponse {
  place_id: string
  metric: Metric
  granularity: Granularity
  unit: string
  currency_code: string | null
  points: SeriesPoint[]
}

export interface CompareSeries {
  place_id: string
  place_name: string
  currency_code: string
  points: SeriesPoint[]
}

export interface CompareResponse {
  metric: Metric
  granularity: Granularity
  series: CompareSeries[]
}

export interface PlaceSummary {
  place_id: string
  currency_code: string
  bill_count: number
  total_consumption: string | null
  total_cost: string | null
  avg_effective_unit_price: string | null
  first_period_start: string | null
  last_period_end: string | null
  last_bill_total: string | null
  last_bill_consumption: string | null
}
