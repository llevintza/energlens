# Handoff: Energlens UI redesign

## Overview

Energlens tracks electricity bills across several properties. The existing app
(React 18 + TypeScript + Vite + React Router + TanStack Query + Recharts, FastAPI
backend) renders three disconnected charts and a bills table. It answers "what did I
pay?" but not the question the product exists for: **am I using more energy, or just
paying more for it?**

This bundle contains a full redesign: a dashboard, a dedicated comparison page, and
seven supporting screens, in two visual registers.

**No backend changes are required.** Every figure is derived from what the existing API
already returns (`/places`, `/bills`, `/series`, `/summary`). The new derivations are
specified in "Derived metrics" below.

## About the design files

The files in this bundle are **design references created in HTML** — prototypes showing
intended look, layout, and behaviour. They are not production code to copy.

The task is to **recreate these designs inside the existing front end**, using its
established patterns: the `useSeries` / `useSummary` / `usePlaces` hooks, the `Layout`
shell, the CSS custom properties in `frontend/src/index.css`, and **Recharts for every
chart**.

The SVG in the prototypes is hand-built for the prototype only. **Do not port the SVG.**
Each chart below names the Recharts composition to use and the geometry to reproduce.

## Fidelity

**High fidelity.** Final colours, typography, spacing, and copy.

Interaction states not drawn in static frames (hover, focus, loading, error, empty) are
specified in "Interactions & behaviour". Responsive behaviour is specified, not drawn —
frames are 1280px.

---

## What is in the file

Open `Energlens Redesign.dc.html` in a browser. It is a scrollable canvas with the
newest work at the top. Every option has a visible id badge.

| id | Screen | Notes |
|---|---|---|
| **5a–5g** | Seven screens, light-only register | Alternative to 3a–3g |
| **4a–4c** | Three ways to plot effective price | 4a and 4b are folded into the build |
| **3a–3g** | Seven screens, light/dark register | **Recommended** |
| **2a** | Dashboard | **Recommended** |
| **2b** | Compare page | **Recommended** |
| 1a / 1b / 1c | Original three directions | Superseded; kept for provenance |

`Current UI (baseline).dc.html` recreates the app as it exists today, from the repo, for
before/after comparison.

### The build to implement

**2a** (dashboard) + **2b** (Compare page) + **3a–3g** (login, first run, places, forms,
PDF import, bill detail, settings).

2a/2b/3x share one palette with a light/dark switch, Helvetica Neue for prose and
**IBM Plex Mono for every figure**. 5a–5g is the same information in Helvetica
throughout, light only — quieter, more document-like, but loses column alignment on the
dense screens. If the team prefers 5's calmer labels, the sensible hybrid is 5's
sentence-case labels with mono retained only for tabular figures.

---

## Screens

### Shell (every screen except login)

- **Top bar**: 46px, `--topbar`, 1px bottom `--rule`, 20px horizontal padding, 16px gap.
  Wordmark "⚡ Energlens" 14px/700 letter-spacing -0.01em. Right: theme switch
  (LIGHT | DARK segmented, 11px mono, letter-spacing 0.08em), "Import bills" button,
  user email 12.5px `--ink3`, 24px circular avatar.
- **Place rail**: 236px, `--rail`, 1px right `--rule`. Section label "PLACES" 10px/500
  mono letter-spacing 0.14em `--ink4`. Rows: 9px/16px padding, 2px left border
  (`--acc` when active, transparent otherwise), `rgba(var(--acc-rgb),.07)` background
  when active. Active row carries a 128×26 sparkline of effective price and a delta chip.
  Below a 1px divider: "+ Add place" (`--acc`, 12.5px/500) and "Manage places" (`--ink3`).
- **Content**: remaining width, 20px/24px padding.

### 2a — Dashboard

Sections top to bottom, separated by 1px `--rule`:

1. **Header** — place name 19px/600 letter-spacing -0.015em; meta line 11px mono
   letter-spacing 0.04em uppercase (address, provider, bill count). Right: two segmented
   controls (`12M | 24M | ALL`, `MONTHLY | PER BILL`), 6px radius, active segment
   `--sel` on `--selink`.
2. **Headline band** — a generated one-sentence finding at 26px/600 letter-spacing
   -0.02em, with a 13px `--ink2` explanation on the same baseline. See
   "Derived metrics → headline selection". Current copy:
   *"Same energy, 13.9% more money."* / *"Last 12 months against the 12 before:
   3,060 kWh both years, €96 more paid. The whole difference is unit price."*
3. **KPI row** — five equal columns, 1px left `--rule2` separators, no card fills.
   Label 10px mono letter-spacing 0.1em; value 21px/500 mono letter-spacing -0.02em;
   then a delta (11.5px/500 mono, coloured) and a comparison note (11px `--ink4`).

   | Label | Value | Delta | Note |
   |---|---|---|---|
   | LAST BILL | €46.17 | +12.2% | vs Jul 2025 |
   | ALL-IN €/kWh | €0.2886 | +28.2% | since Aug 2024 |
   | 12-MO SPEND | €787 | +13.9% | vs prior 12 mo |
   | 12-MO USE | 3,060 | 0.0% | kWh, unchanged |
   | COST PER DAY | €1.49 | +12.2% | period-normalized |

4. **Hero — price vs consumption** (chart 1 below).
5. **Is the rise real?** (chart 2 below) — 600×232 scatter left, read-out right:
   "CONTRACT RATE, SEASONALITY REMOVED" / +€0.0506 at 30px/500 mono /
   "€0.1550 → €0.2056 per kWh" / explanatory paragraph.
6. **Compare entry** — title, one-line description, "Open Compare →" button linking to
   the Compare route.
7. **Recent bills** — five rows. Header 10px mono letter-spacing 0.1em `--ink4`,
   1px `--rule2` borders. Columns: PERIOD, kWh, €/kWh EFF, ENERGY, FIXED, TAXES,
   TOTAL (600), VS LAST YR (600, coloured), SRC. Numerics right-aligned, mono.
   Header row carries "Add bill" and "All 24 bills →".

### 2b — Compare page

Its own route (`/places/:id/compare`). Header breadcrumb "← MAIN RESIDENCE · COMPARE"
with the current metric name as the page title, range segmented control, "Export CSV".

Then: the tile row, the control row, the main chart, the delta ribbon. Fully specified in
"The compare engine" below.

### 3a — Login

The only screen without the shell. 880px, split: 360px left panel (`--panel`, 1px right
`--rule`, 32px/28px padding) holding wordmark, a 21px/600 positioning line, a 300×90
sparkline of the demo account's real price series, and a caption. Right column: Sign in /
Create account segmented toggle, theme switch, email + password fields (labels 10px mono
letter-spacing 0.12em), primary button, "OR" divider, two OAuth buttons, and a closing
reassurance line at 11.5px `--ink4`.

### 3b — First run

Shell intact — rail shows a dashed "Nothing here yet" panel rather than disappearing.
Content column max-width 620px: 24px/600 heading, 13.5px standfirst, then three numbered
steps in a hairline-ruled list (26px circular number, 14px/600 title, 13px body), a
primary "Add your first place" and a "load the demo data" escape hatch.

Step 3 states the payoff rather than assuming it: *"Watch the price, not just the total —
once a year of bills is in, the comparison views separate what you used from what you
were charged for it."*

### 3c — Places

A table, not cards, so several places compare row to row. Columns: PLACE (name 14px/600 +
two address lines 12px `--ink3`), CURRENCY, BILLS, LAST BILL (14px/500 mono), ALL-IN /kWh,
PRICE TREND (108×26 sparkline + delta + date span), actions (Open / Edit / Delete).

Footer note, and it is load-bearing: *"Totals are never added across places — EUR and RON
stay separate."*

### 3d — Forms

Edit place and Add bill as **420px drawers over the page you were on**, not separate
routes. Two-column field grid; name and address lines span both columns.

- **Edit place**: currency select carries the warning *"Set once, at the start. Changing
  it later leaves 24 existing bills denominated in EUR."*
- **Add bill**: an **arithmetic check panel** recomputes `kWh × unit price + fixed +
  taxes` live and compares it to the entered total. Green tick on match, amber on
  mismatch. It does **not** block saving — bills carry adjustments.

### 3e — PDF import

The extraction step made visible. 300px left column: dashed drop zone, then the batch
list (one row per file, 7px radius, name in mono, status badge READY / CHECK). Right:
the selected file's eight extracted fields in a two-column grid, **each with a confidence
percentage above the input**. Fields below the threshold get a `--up` border and a tinted
fill.

Below, split two ways:
- **Source text, page 1** — the extracted text with the matched line highlighted
  (`rgba(var(--acc-rgb),.16)`). Real text extraction, not a rendered PDF preview.
- **Arithmetic check** — computed total vs stated total, with the discrepancy explained
  in words: *"€0.46 apart — consistent with a rounded unit price on the bill. Within
  tolerance, so this saves as-is."*

Actions: "Skip this file" / "Looks right — next", plus "Discard all" / "Save 3 bills" in
the header.

### 3f — Bill detail

Two columns. **Left, what the provider told you**: Total / Used / All-in as 30px/500 mono
figures, then a line-item table (Energy with its `kWh × price` derivation, Fixed charges,
Subtotal, Taxes, Total in 600), then an 8px composition bar with a three-part legend.

**Right, what they leave out**: a 2×2 grid of comparisons (vs previous month, vs same
month last year, vs 12-month average, vs cheapest month) each showing a signed percentage
at 19px/500 and the absolute it is measured against; then a 420×86 bar chart of all 24
bills with **this bill in `--acc` and the same month last year in `--amber`**; then a
one-sentence reading.

### 3g — Settings

Grouped by what each setting affects, not by data model. Four sections, each introduced
by a 10px mono letter-spacing 0.12em label above a 1px `--rule`:

- **Sign-in** — email, password, connected accounts
- **Display** — theme (LIGHT | DARK | SYSTEM), number format, default range
- **Import defaults** — confidence threshold (85/90/95%), arithmetic tolerance
  (±€1.00 / ±€0.50 / ±2%)
- **Data** — export everything, then delete account last, in `--up`, behind its own rule

Rows are 14px vertical padding, label 13.5px + 12.5px `--ink3` description on the left,
control right-aligned.

---

## The compare engine (2b)

The core of the redesign. **Eight metrics × four ways of slicing time.**

### Metrics

| id | Label | Tile | Source | Axis format |
|---|---|---|---|---|
| `total` | Total cost | COST | `total_amount` | €N |
| `kwh` | Consumption | kWh | `consumption_kwh` | N |
| `eff` | All-in price | €/kWh | `total ÷ kWh` | €N.NN |
| `price` | Contract price | UNIT | `unit_price` | €N.NN |
| `energy` | Energy charge | ENERGY | `kWh × unit_price` | €N |
| `taxes` | Taxes | TAX | `taxes` | €N |
| `perDay` | Cost per day | €/DAY | `total ÷ days_in_period` | €N.N |
| `mix` | Bill composition | MIX | *(special, see below)* | €N.NN |

Zero-based axis for `total`, `kwh`, `energy`, `taxes`, `perDay`, `mix`. Padded-minimum
axis for `eff` and `price` — the movement is the point and a zero baseline flattens it.

### Modes

| id | Label | Construction |
|---|---|---|
| `yoy` | Year over year | Trailing 12 months and the 12 before, both plotted at i=0…11 aligned by position. Current `--acc` 2.4px with 2.8px dots; prior `--ink4` 2px, no dots. **Filled band between them** at `rgba(var(--acc-rgb),.11)`. X labels every 2nd month from the current window. |
| `years` | Years overlaid | X axis is Jan…Dec. One line per selected year; year chips toggle membership (minimum one). 2026 `--acc` 2.4px, 2025 `--amber` 2px, 2024 `--ink4` 2px. **Partial years stop where the data stops — never interpolate.** Legend marks partial years "(N mo)". |
| `mom` | Month over month | 23 diverging bars of percent change from the previous month, around a centred zero line. Increase `--up`, decrease `--down`. Symmetric axis: ±`nice(max(abs))`. X labels every 3rd month. |
| `same` | Same month, each year | One bar per year that has the chosen month, value printed above each bar at 12px. Latest year `--acc`, earlier `--acc2`. Month chosen from a 12-chip control (JAN…DEC), not a dropdown. Band divides by `max(rowCount, 3)` so two bars do not become absurdly wide. |

### The tile row *is* the small-multiples view

Eight tiles, `repeat(8, 1fr)`, 8px gap, 8px radius. Each shows: metric short label
(10px mono letter-spacing 0.1em), the current value (14px/500 mono), a trailing-12 delta
(10px/500 mono, coloured), and **a miniature of that metric under the currently selected
mode** (SVG at `width:100%`, `viewBox="0 0 119 40"`, `preserveAspectRatio="none"`,
no axes). Selected tile takes an `--acc` border and a tinted fill.

Clicking a tile selects the metric. The dropdown in the control row selects the same
thing by name. **Both must stay in sync in both directions** — see "Interactions".

### Delta ribbon

A fixed reference strip below the chart, present in every mode: twelve columns, one per
month of the trailing year, each with a signed percentage (11px/500 mono, coloured), a
proportional bar (height scaled to the largest absolute delta, max 26px, 75% opacity),
and the month abbreviation. Titled "Δ <metric> vs same month last year".

Under `mix` the ribbon falls back to total cost and says so in its title.

### MIX is a view, not a metric

`mix` renders the stacked €/kWh decomposition (chart 3) instead of a mode-based chart.
Because "month over month" is meaningless for a composition, selecting `mix`:
- dims the mode group to `opacity: .45`
- sets all four mode buttons to `disabled` with `cursor: not-allowed` — **dimming alone
  is not enough; they must not fire**
- shows the caption *"Composition is always read over time — the comparison modes do not
  apply to it."*

---

## Chart catalogue

Reproduce each with Recharts. Shared: gridlines `--grid`, baseline `--axis`, tick text
10–11px mono `--ink4`, no chart-area fill.

**1. Price vs consumption (dual axis)** — 972×236. `ComposedChart`: `Bar` for kWh on the
left axis (`--barfill`, max 22px wide, 0.62 of band); `Line` for effective €/kWh on the
right axis (`--acc`, 2.25px, 2.4px dots); `Line` for contract unit price on the right
axis (`--amber`, 1.75px, `strokeDasharray="4 3"`, no dots). The widening gap between the
two lines is fixed charges and tax — call it out in the subtitle.

**2. Effective price vs consumption (scatter)** — 600×232 on the dashboard, 420×250 as
4b. `ComposedChart` with a numeric X axis over kWh (domain 150–360): `Scatter` for the 24
bills, fill `rgba(var(--acc-rgb),α)` with α ramped 0.22 → 1.00 by recency, r=4 (latest
r=5); plus two `Line` series sampling `eff(k) = 1.19 × (p + 5.90 ÷ k)` every 5 kWh for
p = first and latest unit price, both `strokeDasharray="4 3"` (`--ink4` old, `--amber`
new). Points sitting off the lower curve and onto the upper one at every consumption
level is the evidence that the rise is a rate change, not lighter usage.

**3. €/kWh decomposition (stacked area)** — the `mix` metric and 4a. `AreaChart` with
three `Area` series sharing a `stackId`: `unit_price` (`--acc`), `5.90 ÷ kWh`
(`--amber`), `0.19 × (unit_price + 5.90 ÷ kWh)` (`--barfill`), plus a 1.6px `--ink`
line on the total. Zero-based. The standing-charge band visibly swells in light months —
€0.0169/kWh in a heavy January, €0.0369/kWh in a light July — which is why cutting
consumption *raises* headline €/kWh.

**4. Cumulative excess cost (4c)** — 420×250 `AreaChart`. Running total of
`(eff_i − eff_0) × kWh_i`. Zero-based with a visible zero line; it runs negative through
the first winter for the reason chart 3 explains. Call out the final total (€101) and the
per-month average (€4.20).

**5–8. The four compare modes** — see the table above. `LineChart` for `yoy` (plus an
`Area` for the band) and `years`; `BarChart` with `ReferenceLine y={0}` for `mom`;
`BarChart` with `LabelList` for `same`.

**9. Sparklines** — `LineChart` in a fixed-size container, no axes, no grid, no tooltip.
108×26 in the places table, 128×26 in the rail, 300×90 on login.

**10. Bill in the run of 24 (3f)** — 420×86 `BarChart`, no axes. This bill `--acc`, same
month last year `--amber`, everything else `--barfill`.

**11. Seasonal heatmap** (1b/1c only, not in the recommended build) — not a Recharts
chart. A CSS grid, 3 rows × 12 columns, 2px radius, fill alpha ramped across the
min–max range, value printed in each cell with the text colour flipping above 55%
intensity.

### Axis rules — two traps we hit

1. **Tick steps must come from a 1 / 2 / 5 × 10ⁿ ladder.** A 2.5 step produces duplicate
   labels once ticks are formatted to two decimals (€0.23, €0.25, €0.28, €0.30 renders
   as €0.23, €0.25, €0.28, €0.30 — but €0.225/€0.25/€0.275 renders €0.23, €0.25, €0.28
   inconsistently across ranges).
2. **On a zero-based scale whose minimum is negative, floor the base to a step multiple.**
   Otherwise the axis starts at the raw minimum and every tick is an odd number
   (−13, 37, 87, 137 instead of −50, 0, 50, 100, 150).

---

## Derived metrics

| Metric | Definition |
|---|---|
| **Effective €/kWh** | `total_amount ÷ consumption_kwh` — all-in, includes fixed charges and tax. Distinct from the contracted `unit_price`; the difference is the whole story. |
| **Trailing-12 spend / use** | Sum of the last 12 monthly buckets, compared against the 12 before. |
| **YoY delta** | Same calendar month, prior year. Rendered as both absolute and percent. |
| **Cost per day** | `total_amount ÷ days_in_period`. Normalizes uneven billing periods — a 36-day bill is not a price increase. |
| **Composition shares** | `energy = kwh × unit_price`; `fixed`; `taxes`. Shares are of the summed period total, not an average of monthly shares. |
| **Index to first month** | `value ÷ first_value × 100`. The only honest way to put two currencies on one axis. |
| **Contract rate change** | Difference between first and latest `unit_price`. Seasonality-free, unlike any effective-price comparison. |
| **Cumulative excess** | Running `Σ (eff_i − eff_baseline) × kwh_i`, baseline = first month's effective price. |
| **Forecast** | Coarse by design. Suggested: latest effective price × trailing 3-month price trend × the same calendar month's kWh last year. Always render visually distinct (dashed, tinted band) — never as a solid series. |
| **Headline selection** | Compare trailing-12 kWh delta against trailing-12 spend delta. Spend moved >5% while kWh moved <3% → price story. Both moved together → consumption story. Spend fell → savings story. Copy is templated per branch. |

### Rounding and formatting

- Currency: 2 decimals in tables and bill figures; 0 decimals in KPI totals and headlines
  (€787, not €787.37).
- Effective price: 4 decimals in KPIs and tables (€0.2886); 2 on axis ticks (€0.29).
- kWh: 0 decimals in summaries, 1 in tables.
- Percentages: 1 decimal, always signed. Use a true minus sign (−), not a hyphen.
- Every currency figure renders in its place's own currency. **Never sum or average
  across places with different currencies** — index instead.
- `font-variant-numeric: tabular-nums` on every numeric run.

---

## Interactions & behaviour

- **Chart hover**: one shared crosshair tooltip per chart listing every series at that
  month with its value and YoY delta. Not one tooltip per series.
- **Metric selection**: tiles and dropdown are two views of one piece of state. Clicking
  a tile must update the dropdown label, and vice versa. In the prototype a native
  `<select>` would not stay in sync, so the dropdown is a custom popover — whichever you
  use, verify both directions.
- **Dropdown dismissal**: the popover needs a click-away path. If you implement it with a
  full-viewport scrim, the scrim must sit **below** the tile row in the stacking order
  (tiles `z-index: 21`, popover 20, scrim 19) or a single click on a tile is swallowed
  and selects nothing. Verify with `elementFromPoint`, not a synthetic `.click()`.
- **Disabled controls must actually be disabled** — see MIX above.
- **Rail**: hover `rgba(11,11,11,.04)` light / `rgba(255,255,255,.04)` dark. Selecting a
  place replaces the content column; URL becomes `/places/:id`.
- **Range controls**: instant client-side refilter. 24 months are already loaded; the 12m
  view is a slice, not a refetch.
- **Table rows**: whole row links to bill detail; Edit/Delete appear on row hover only.
- **Buttons**: 120ms ease background transition; focus ring 2px `--acc` at 40% alpha,
  2px offset.
- **Theme**: one attribute swap on a root element (`data-theme="dark"`) over a single set
  of CSS custom properties. Persist per device. Offer a SYSTEM option honouring
  `prefers-color-scheme`.
- **Loading**: skeleton blocks at each chart's exact height. Never a spinner that
  collapses layout. Charts animate in over 240ms ease-out on first paint only.
- **Empty (no bills)**: keep the shell and section headings; replace each chart with a
  dashed panel of the same height carrying a one-line prompt and an "Import bills" action.
- **Errors**: inline above the affected panel, `--up` text on a tinted background. Never
  a modal.

## Responsive

- **≥1200px**: as drawn.
- **900–1199px**: rail collapses to 64px icon-only; KPI row wraps 3 + 2; compare tiles
  wrap to two rows of four; lower chart pairs stack.
- **<900px**: rail becomes a top dropdown place-picker; all charts full-width and
  stacked; bills table becomes one card per bill showing period, total, kWh and effective
  price only; the compare tile row becomes a horizontally scrolling strip.

Minimum touch target 44px below 900px.

---

## Design tokens

Declare once on a root element and switch with `data-theme`. These are the recommended
build's tokens (2a / 2b / 3a–3g).

```css
[data-theme="light"] {
  --bg:        #f9f9f7;   --panel:   #fcfcfb;   --rail:  #fcfcfb;   --topbar: #fcfcfb;
  --ink:       #0b0b0b;   --ink2:    #52514e;   --ink3:  #6f6d67;   --ink4:   #74726b;
  --rule:      rgba(11,11,11,.14);              --rule2: rgba(11,11,11,.09);
  --grid:      #e1e0d9;   --axis:    #c3c2b7;
  --acc:       #3d3ab0;   --acc-rgb: 61,58,176; --acc2:  #9b99d9;
  --amber:     #c47f1a;   --warn-text: #96591a;
  --barfill:   #d4d3cb;   --up:      #b4471f;   --down:  #1f7a5a;
  --sel:       #0b0b0b;   --selink:  #fcfcfb;   --field: #fcfcfb;
}
[data-theme="dark"] {
  --bg:        #0d0d0d;   --panel:   #1a1a19;   --rail:  #111110;   --topbar: #141413;
  --ink:       #ffffff;   --ink2:    #c3c2b7;   --ink3:  #8a8781;   --ink4:   #96938c;
  --rule:      rgba(255,255,255,.13);           --rule2: rgba(255,255,255,.08);
  --grid:      #2c2c2a;   --axis:    #383835;
  --acc:       #8f8cf0;   --acc-rgb: 143,140,240; --acc2: #5b58a8;
  --amber:     #e6a23c;   --warn-text: #e6a23c;
  --barfill:   #3f3f3c;   --up:      #e07a4c;   --down:  #4fb48c;
  --sel:       #8f8cf0;   --selink:  #0d0d0d;   --field: #0d0d0d;
}
```

### Contrast — do not lighten the muted greys

Every text token meets WCAG AA (4.5:1) at the 10–11px sizes it is used at. Measured:

| Token | On | Ratio |
|---|---|---|
| `--ink3` light `#6f6d67` | `#fcfcfb` | 5.0:1 |
| `--ink4` light `#74726b` | `#fcfcfb` | 4.7:1 |
| `--ink3` dark `#8a8781` | `#1a1a19` | 4.9:1 |
| `--ink4` dark `#96938c` | `#1a1a19` | 5.7:1 |
| `--warn-text` light `#96591a` | `#fcfcfb` | 5.5:1 |
| `--up` light `#b4471f` | `#fcfcfb` | 5.3:1 |
| `--down` light `#1f7a5a` | `#fcfcfb` | 5.1:1 |

`--amber` (`#c47f1a` light, 3.2:1) and `#eb6834` are **strokes and swatches only** and
must never be used on type. Use `--warn-text` for amber text.

Note that 600-weight text under 18.66px does *not* qualify as WCAG "large text" — that
needs 700 — so the 19px/600 comparison figures in 3f are held to 4.5:1.

### Scales

```
radius    5px controls · 6px buttons and segments · 7–8px panels · 10px cards · 20px pills
spacing   2 3 4 5 6 8 10 12 14 16 18 20 22 24 26 28 30 34 44 46
type      9.5 10 10.5 11 11.5 12 12.5 13 13.5 14 14.5 15 17 19 21 24 26 30
weights   400 · 500 · 600 · 700
```

### Fonts

- Prose and UI: Helvetica Neue / Helvetica / Arial (system, no webfont)
- **All figures, axis ticks, and small labels: IBM Plex Mono 400–600** (Google Fonts)
- Uppercase small labels carry letter-spacing 0.08–0.14em

The 5a–5g alternative drops IBM Plex Mono entirely and uses Helvetica Neue with
`tabular-nums` for figures, plus sentence-case labels in place of uppercase mono.

## Assets

None. No images and no icon set — the only glyphs are the ⚡ wordmark mark, ▲ / — delta
indicators, a ▼ dropdown caret and an ✕ close. If you want an icon set for the collapsed
rail, use one already in the project's dependencies.

## Demo data

The prototypes use the same generator as `backend/app/seed.py` — 24 months ending
Jul 2026, Main Residence in EUR, Second Home in RON:

```
kwh_i    = 160 + 190 × (1 + cos(2π(month−1)/12)) / 2
price_i  = 0.1550 + 0.0022 × i          (i = 0…23)
energy_i = kwh_i × price_i
fixed    = 5.90
taxes_i  = (energy_i + fixed) × 0.19
total_i  = energy_i + fixed + taxes_i
```

This yields **exactly 3,060 kWh in each 12-month window** while spend rises €691 → €787
(+13.9%) and effective price €0.2251 → €0.2886 (+28.2%). Keep it as a fixture: it
isolates a pure price story with consumption held flat, which is the case the whole
redesign exists to surface. It also exercises the negative-axis path in chart 4 and the
inverse relationship between consumption and headline €/kWh in chart 3.

## Suggested placement

```
docs/design/
  README.md
  Energlens Redesign.dc.html
  Current UI (baseline).dc.html
  support.js
```

The two HTML files need `support.js` beside them. They open directly in a browser — no
build step, no server.
