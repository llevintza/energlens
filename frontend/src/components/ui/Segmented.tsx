export interface SegmentedOption<T extends string> {
  value: T
  label: string
  disabled?: boolean
}

interface Props<T extends string> {
  options: SegmentedOption<T>[]
  value: T
  onChange: (value: T) => void
  /** 11px mono caps with 0.08em tracking — the register the handoff uses for the theme
   *  switch and the other small controls. */
  monoLabels?: boolean
  /** Required: on its own a row of three-letter buttons says nothing. */
  ariaLabel: string
  /** Dims the whole group and disables every option. Used by 2b's `mix`, where the
   *  comparison modes genuinely do not apply — dimming alone is not enough, the
   *  buttons must not fire. */
  disabled?: boolean
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  monoLabels,
  ariaLabel,
  disabled,
}: Props<T>) {
  return (
    <div
      className={`segmented${monoLabels ? ' mono-labels' : ''}`}
      role="group"
      aria-label={ariaLabel}
      style={disabled ? { opacity: 0.45 } : undefined}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          disabled={disabled || option.disabled}
          style={disabled || option.disabled ? { cursor: 'not-allowed' } : undefined}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
