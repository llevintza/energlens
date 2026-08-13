import { Link } from 'react-router-dom'

const STEPS = [
  {
    title: 'Add a place',
    body: 'A home, a rental, an office — anywhere you get an electricity bill. Each one keeps its own currency, and figures are never added across them.',
  },
  {
    title: 'Enter a few bills',
    body: 'Period, total and kWh are enough to start. Add the contracted unit price, standing charge and tax when you have them, and the breakdown gets sharper.',
  },
  {
    title: 'Watch the price, not just the total',
    body: 'Once a year of bills is in, the comparison views separate what you used from what you were charged for it.',
  },
]

/**
 * 3b — first run.
 *
 * The shell stays put: the rail shows a dashed "Nothing here yet" panel rather than
 * disappearing, so a new account looks empty rather than broken.
 *
 * This renders **only** when the places query genuinely succeeded and returned nothing.
 * A failed request must never land here — telling someone their places are gone when
 * the network merely blinked is the whole of issue #8.
 *
 * There is no "load the demo data" button. `backend/app/seed.py` is not exposed over
 * HTTP, and #20 is explicit that a button with nothing behind it should be dropped
 * rather than shipped dead. The seeded `demo@example.com` account already exists for
 * anyone who wants to look around.
 */
export function FirstRunPage() {
  return (
    <div className="firstrun">
      <h1>Nothing here yet.</h1>
      <p className="firstrun-standfirst">
        Energlens tracks what you pay for electricity and what you actually got for it.
        Three steps to something worth looking at.
      </p>

      <ol className="firstrun-steps">
        {STEPS.map((step, i) => (
          <li key={step.title}>
            <span className="firstrun-num" aria-hidden="true">
              {i + 1}
            </span>
            <div>
              <h2 className="firstrun-step-title">{step.title}</h2>
              <p className="firstrun-step-body">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <Link className="btn primary" to="/places">
        Add your first place
      </Link>
    </div>
  )
}
