/**
 * Stacking order, in one place.
 *
 * The handoff records a live bug from the prototype: a dismissal scrim sitting above
 * 2b's metric tiles swallowed the first click on a tile, so selecting a metric did
 * nothing. The metric picker now avoids that structurally — it has no scrim at all — but
 * the drawer in 3d does need one, and the next component reaching for an overlay will
 * invent a number unless the scale is written down.
 *
 * Kept in TypeScript rather than as CSS custom properties so the ordering is a tested
 * invariant. (Reading the values back out of CSS is not available to us: Vite's CSS
 * plugin claims `.css` imports before `?raw` sees them, so a stylesheet parse returns
 * an empty string, and jsdom has no layout engine to resolve them at runtime.)
 */
export const LAYERS = {
  rail: 5,
  topbar: 10,
  /** Any full-viewport dismissal scrim. Must stay below the tiles. */
  scrim: 19,
  popover: 20,
  /** Above `popover` and `scrim`, so a click on a tile is never intercepted. */
  tiles: 21,
  drawerScrim: 39,
  drawer: 40,
} as const

export type LayerName = keyof typeof LAYERS
