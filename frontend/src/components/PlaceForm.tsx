import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { ApiError } from '../api/client'
import type { Place, PlaceInput } from '../api/types'
import { CURRENCIES } from '../lib/currencies'

interface Props {
  initial?: Place
  onSubmit: (data: PlaceInput) => Promise<unknown>
  onCancel?: () => void
  submitLabel?: string
  /** Bills already denominated in this place's currency. Drives the warning below;
   *  omitted when creating, where there is nothing to strand. */
  billCount?: number
}

type FormValues = PlaceInput

export function PlaceForm({ initial, onSubmit, onCancel, submitLabel, billCount }: Props) {
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: initial ?? {
      name: '',
      address_line1: '',
      address_line2: null,
      city: '',
      region: null,
      postal_code: '',
      country_code: '',
      currency_code: 'EUR',
    },
  })

  const submit = async (values: FormValues) => {
    setError(null)
    try {
      await onSubmit({
        ...values,
        address_line2: values.address_line2 || null,
        region: values.region || null,
        country_code: values.country_code.toUpperCase(),
      })
    } catch (e) {
      if (e instanceof ApiError) {
        setError(
          typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail),
        )
      } else {
        setError('Saving failed')
      }
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)}>
      <div className="form-grid">
        <div className="field">
          <label>Name</label>
          <input
            placeholder="Main Residence"
            {...register('name', { required: 'Required' })}
          />
          {errors.name && <span className="err">{errors.name.message}</span>}
        </div>
        <div className="field">
          <label>Address line 1</label>
          <input {...register('address_line1', { required: 'Required' })} />
          {errors.address_line1 && (
            <span className="err">{errors.address_line1.message}</span>
          )}
        </div>
        <div className="field">
          <label>Address line 2 (optional)</label>
          <input {...register('address_line2')} />
        </div>
        <div className="field">
          <label>City</label>
          <input {...register('city', { required: 'Required' })} />
          {errors.city && <span className="err">{errors.city.message}</span>}
        </div>
        <div className="field">
          <label>Region (optional)</label>
          <input {...register('region')} />
        </div>
        <div className="field">
          <label>Postal code</label>
          <input {...register('postal_code', { required: 'Required' })} />
          {errors.postal_code && (
            <span className="err">{errors.postal_code.message}</span>
          )}
        </div>
        <div className="field">
          <label>Country code</label>
          <input
            placeholder="PT"
            maxLength={2}
            {...register('country_code', {
              required: 'Required',
              pattern: { value: /^[A-Za-z]{2}$/, message: '2 letters (ISO)' },
            })}
          />
          {errors.country_code && (
            <span className="err">{errors.country_code.message}</span>
          )}
        </div>
        <div className="field">
          <label>Billing currency</label>
          <select {...register('currency_code', { required: true })}>
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {/* Accurate as written: bills snapshot the place's currency when they are
              created (backend/app/routers/bills.py), so changing it here never rewrites
              history — it strands what is already recorded. */}
          {billCount !== undefined && billCount > 0 && (
            <span className="field-warn">
              Set once, at the start. Changing it later leaves {billCount}{' '}
              {billCount === 1 ? 'existing bill' : 'existing bills'} denominated in{' '}
              {initial?.currency_code ?? 'the old currency'}.
            </span>
          )}
        </div>
      </div>
      {error && <div className="form-error">{error}</div>}
      <div className="form-actions">
        <button className="btn primary" disabled={isSubmitting}>
          {submitLabel ?? 'Save place'}
        </button>
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
