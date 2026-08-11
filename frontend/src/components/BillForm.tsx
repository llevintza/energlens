import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { ApiError } from '../api/client'
import type { Bill, BillInput } from '../api/types'
import { fmtCurrency } from '../lib/format'

interface Props {
  currency: string
  initial?: Bill
  onSubmit: (data: BillInput) => Promise<unknown>
  onCancel: () => void
}

interface FormValues {
  period_start: string
  period_end: string
  consumption: string
  unit_price: string
  fixed_charges: string
  taxes: string
  total_amount: string
  provider_name: string
  notes: string
}

export function BillForm({ currency, initial, onSubmit, onCancel }: Props) {
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: {
      period_start: initial?.period_start ?? '',
      period_end: initial?.period_end ?? '',
      consumption: initial?.consumption ?? '',
      unit_price: initial?.unit_price ?? '',
      fixed_charges: initial?.fixed_charges ?? '',
      taxes: initial?.taxes ?? '',
      total_amount: initial?.total_amount ?? '',
      provider_name: initial?.provider_name ?? '',
      notes: initial?.notes ?? '',
    },
  })

  // Soft consistency check — warn, never block: bills routinely include
  // rounding and adjustments the components don't fully explain.
  const values = watch()
  let warning: string | null = null
  const kwh = parseFloat(values.consumption)
  const price = parseFloat(values.unit_price)
  const total = parseFloat(values.total_amount)
  if (!Number.isNaN(kwh) && !Number.isNaN(price) && !Number.isNaN(total) && total !== 0) {
    const expected =
      kwh * price +
      (parseFloat(values.fixed_charges) || 0) +
      (parseFloat(values.taxes) || 0)
    if (Math.abs(expected - total) / Math.abs(total) > 0.05) {
      warning = `Heads up: consumption × price + charges ≈ ${fmtCurrency(expected, currency)}, but total is ${fmtCurrency(total, currency)}`
    }
  }

  const submit = async (v: FormValues) => {
    setError(null)
    try {
      await onSubmit({
        utility_type: 'electricity',
        period_start: v.period_start,
        period_end: v.period_end,
        consumption: v.consumption || null,
        unit: 'kWh',
        unit_price: v.unit_price || null,
        fixed_charges: v.fixed_charges || null,
        taxes: v.taxes || null,
        total_amount: v.total_amount,
        provider_name: v.provider_name || null,
        source: initial?.source ?? 'manual',
        notes: v.notes || null,
      })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setError('A bill for this exact period already exists')
      } else if (e instanceof ApiError && e.status === 422) {
        setError('Check the fields: ' + JSON.stringify(e.detail))
      } else {
        setError('Saving failed')
      }
    }
  }

  const num = { inputMode: 'decimal' as const, placeholder: '0.00' }

  return (
    <form onSubmit={handleSubmit(submit)}>
      <div className="form-grid">
        <div className="field">
          <label>Period start</label>
          <input type="date" {...register('period_start', { required: 'Required' })} />
          {errors.period_start && (
            <span className="err">{errors.period_start.message}</span>
          )}
        </div>
        <div className="field">
          <label>Period end</label>
          <input
            type="date"
            {...register('period_end', {
              required: 'Required',
              validate: (v) =>
                !watch('period_start') ||
                v >= watch('period_start') ||
                'Must be after period start',
            })}
          />
          {errors.period_end && (
            <span className="err">{errors.period_end.message}</span>
          )}
        </div>
        <div className="field">
          <label>Consumption (kWh)</label>
          <input {...num} {...register('consumption')} />
        </div>
        <div className="field">
          <label>Unit price ({currency}/kWh)</label>
          <input {...num} {...register('unit_price')} />
        </div>
        <div className="field">
          <label>Fixed charges ({currency})</label>
          <input {...num} {...register('fixed_charges')} />
        </div>
        <div className="field">
          <label>Taxes ({currency})</label>
          <input {...num} {...register('taxes')} />
        </div>
        <div className="field">
          <label>Total amount ({currency})</label>
          <input
            {...num}
            {...register('total_amount', { required: 'Required' })}
          />
          {errors.total_amount && (
            <span className="err">{errors.total_amount.message}</span>
          )}
        </div>
        <div className="field">
          <label>Provider (optional)</label>
          <input {...register('provider_name')} />
        </div>
        <div className="field">
          <label>Notes (optional)</label>
          <input {...register('notes')} />
        </div>
      </div>
      {warning && <div className="form-warn">{warning}</div>}
      {error && <div className="form-error">{error}</div>}
      <div className="form-actions">
        <button className="btn primary" disabled={isSubmitting}>
          {initial ? 'Save changes' : 'Add bill'}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
