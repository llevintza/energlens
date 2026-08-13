// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DeltaChip } from './DeltaChip'
import { Segmented } from './Segmented'

afterEach(cleanup)

describe('DeltaChip', () => {
  it('signs a percentage with a true minus, not a hyphen', () => {
    render(<DeltaChip value={-13.94} />)
    const text = screen.getByText(/13\.9%/).textContent ?? ''
    // U+2212, not U+002D. A hyphen renders shorter and higher than the plus it pairs
    // with, so a column of deltas looks ragged.
    expect(text.startsWith('−')).toBe(true)
    expect(text.includes('-')).toBe(false)
  })

  it('colours by direction', () => {
    const { container, rerender } = render(<DeltaChip value={13.9} />)
    expect(container.querySelector('.delta')?.className).toContain('up')
    rerender(<DeltaChip value={-13.9} />)
    expect(container.querySelector('.delta')?.className).toContain('down')
  })

  it('treats anything that prints as flat as flat', () => {
    // 12-MO USE on the demo data is exactly 0.0%; tinting it by an invisible sign
    // would tell the reader something the number does not say.
    const { container } = render(<DeltaChip value={0.01} />)
    expect(container.querySelector('.delta')?.className).toContain('flat')
    expect(screen.getByText('+0.0%')).toBeDefined()
  })

  it('shows no comparison rather than 0% when there is no counterpart', () => {
    const { container } = render(<DeltaChip value={null} />)
    expect(screen.getByText('—')).toBeDefined()
    expect(container.textContent).not.toContain('0.0%')
  })

  it('shows no comparison for a non-finite delta', () => {
    render(<DeltaChip value={Number.POSITIVE_INFINITY} />)
    expect(screen.getByText('—')).toBeDefined()
  })
})

describe('Segmented', () => {
  const options = [
    { value: 'yoy' as const, label: 'Year over year' },
    { value: 'mom' as const, label: 'Month over month' },
  ]

  it('marks exactly one option pressed', () => {
    render(<Segmented ariaLabel="Mode" options={options} value="yoy" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Year over year' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Month over month' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('reports the value the user picked', async () => {
    const onChange = vi.fn()
    render(<Segmented ariaLabel="Mode" options={options} value="yoy" onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'Month over month' }))
    expect(onChange).toHaveBeenCalledWith('mom')
  })

  it('does not fire when disabled — dimming alone is not enough', async () => {
    // 2b disables the whole mode group under `mix`, where comparison modes are
    // meaningless. The handoff calls this out because in the prototype the buttons were
    // only dimmed, and still fired.
    const onChange = vi.fn()
    render(
      <Segmented ariaLabel="Mode" options={options} value="yoy" onChange={onChange} disabled />,
    )
    const button = screen.getByRole('button', { name: 'Month over month' })
    expect((button as HTMLButtonElement).disabled).toBe(true)
    await userEvent.click(button)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('can disable a single option without disabling the group', async () => {
    const onChange = vi.fn()
    render(
      <Segmented
        ariaLabel="Range"
        options={[
          { value: 'a' as const, label: 'Twelve' },
          { value: 'b' as const, label: 'Twenty-four', disabled: true },
        ]}
        value="a"
        onChange={onChange}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Twenty-four' }))
    expect(onChange).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Twelve' }))
    expect(onChange).toHaveBeenCalledWith('a')
  })
})
