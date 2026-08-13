import { fmtCurrency } from '../../lib/format'

interface Props {
  consumption: string
  unitPrice: string
  fixedCharges: string
  taxes: string
  total: string
  currency: string
}

function num(value: string): number | null {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * `kWh × unit price + fixed + taxes`, recomputed as you type and compared with the total
 * you entered.
 *
 * **It never blocks saving.** Real bills carry adjustments, credits, and rounding on the
 * provider's own unit price, and a form that refuses them is worse than one that flags
 * them. So this reports and gets out of the way.
 *
 * Amber text is `--warn-text`, not `--amber` — the latter is a stroke and swatch colour
 * and fails contrast on type.
 */
export function ArithmeticCheck({
  consumption,
  unitPrice,
  fixedCharges,
  taxes,
  total,
  currency,
}: Props) {
  const kwh = num(consumption)
  const price = num(unitPrice)
  const fixed = num(fixedCharges)
  const tax = num(taxes)
  const stated = num(total)

  if (kwh === null || price === null || stated === null) {
    return (
      <div className="arith arith-idle">
        <span className="arith-title">Arithmetic check</span>
        <span className="arith-body">
          Enter consumption, unit price and total and this checks them against each other.
        </span>
      </div>
    )
  }

  const energy = kwh * price
  const computed = energy + (fixed ?? 0) + (tax ?? 0)
  const difference = stated - computed
  /* A cent either way is rounding on the provider's own unit price, not a mistake. */
  const matches = Math.abs(difference) < 0.015

  return (
    <div className={`arith ${matches ? 'arith-ok' : 'arith-warn'}`}>
      <span className="arith-title">
        {matches ? '✓ Adds up' : '⚠ Does not add up'}
      </span>
      <span className="arith-sum">
        {fmtCurrency(energy, currency, 2)}
        {fixed !== null && ` + ${fmtCurrency(fixed, currency, 2)}`}
        {tax !== null && ` + ${fmtCurrency(tax, currency, 2)}`} ={' '}
        {fmtCurrency(computed, currency, 2)}
      </span>
      {!matches && (
        <span className="arith-body">
          {fmtCurrency(Math.abs(difference), currency, 2)}{' '}
          {difference > 0 ? 'more than' : 'less than'} the line items come to. Bills carry
          adjustments and rounded unit prices — this saves either way.
        </span>
      )}
      {(fixed === null || tax === null) && (
        <span className="arith-body">
          {fixed === null && tax === null
            ? 'Fixed charges and taxes are blank, so they count as zero here.'
            : fixed === null
              ? 'Fixed charges are blank, so they count as zero here.'
              : 'Taxes are blank, so they count as zero here.'}
        </span>
      )}
    </div>
  )
}
