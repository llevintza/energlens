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
export type DocumentType = 'invoice' | 'credit_note'
/** How the meter index behind the consumption figure was arrived at. */
export type ReadMethod =
  | 'actual'
  | 'self_read'
  | 'estimated'
  | 'regularisation'
  | 'mixed'

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
  /** The invoice's own value. What is payable is `total_due`. */
  total_amount: string
  currency_code: string
  provider_name: string | null
  raw_file_ref: string | null
  source: BillSource
  notes: string | null
  // What the invoice itself says. Everything here is null on a bill typed in by
  // hand or uploaded before the extraction agent existed.
  provider_invoice_series: string | null
  provider_invoice_number: string | null
  issued_on: string | null
  due_on: string | null
  net_amount: string | null
  vat_base: string | null
  /** A fraction, not a percentage: '0.1900', and '0.2100' from July 2026. */
  vat_rate: string | null
  vat_amount: string | null
  balance_brought_forward: string | null
  /** total_amount plus any balance carried forward — what is actually owed. */
  total_due: string | null
  read_method: ReadMethod | null
  document_type: DocumentType
  corrects_bill_id: string | null
  customer_code: string | null
  provider_tax_id: string | null
  /** The uploaded PDF this bill came from. Null once the document is deleted —
   *  the bill outlives it. Nothing renders this yet; #61 is where it surfaces. */
  document_id: string | null
  created_at: string
  updated_at: string
}

/** A stored bill PDF. `storage_key` is deliberately absent — it is internal to
 *  the backend's storage layer and never leaves it. */
export interface BillDocument {
  id: string
  place_id: string
  sha256: string
  filename: string
  media_type: string
  byte_size: number
  /** Null when the PDF could not be parsed. It is still stored. */
  page_count: number | null
  uploaded_by: string
  created_at: string
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
  // Optional: the API defaults document_type and leaves the rest null, so a
  // hand-filled form need not carry an invoice it never saw.
  provider_invoice_series?: string | null
  provider_invoice_number?: string | null
  issued_on?: string | null
  due_on?: string | null
  net_amount?: string | null
  vat_base?: string | null
  vat_rate?: string | null
  vat_amount?: string | null
  balance_brought_forward?: string | null
  total_due?: string | null
  read_method?: ReadMethod | null
  document_type?: DocumentType
  corrects_bill_id?: string | null
  customer_code?: string | null
  provider_tax_id?: string | null
  document_id?: string | null
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
