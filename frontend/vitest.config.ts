import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * Kept separate from vite.config.ts so the app's build config stays about the build.
 *
 * The default environment is `node`: the metrics and axis specs are pure arithmetic
 * and there is no reason to pay for a DOM to run them. The handful of specs that
 * render a component opt in with a `@vitest-environment jsdom` docblock at the top of
 * the file.
 *
 * A note on what jsdom can and cannot settle, because it is easy to write a test here
 * that passes while the bug ships: **jsdom has no layout engine.**
 * `getBoundingClientRect()` returns all zeros and `document.elementFromPoint` does not
 * exist. So it can prove that a control is genuinely disabled, that two views of one
 * piece of state stay in sync, and that an error state is not mistaken for an empty
 * one — but it cannot answer "does this click land on the tile or on an overlay". That
 * question is settled by not building the overlay, and confirmed in a real browser.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
})
