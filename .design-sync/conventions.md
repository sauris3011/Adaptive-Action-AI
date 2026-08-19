## Building with this design system

A banking dispute-resolution console. The visual language is restrained and
information-dense: hairline borders, small type, tabular numerals for anything
that changes, and colour reserved for state rather than decoration.

### Setup

Components are on `window.AdaptiveCopilotUI`. Two things must be true or they
render wrong:

1. **Wrap the tree in `MemoryRouter`** (or any react-router router). `AppHeader`
   uses `NavLink` and throws outside a router context. It is exported from the
   bundle alongside the components.
2. **Load `styles.css`.** It is the only entry point — it `@import`s the Inter
   faces and the compiled component CSS. Loading `_ds_bundle.css` alone gives
   you components without fonts.

```jsx
const { MemoryRouter, RecommendationCard } = window.AdaptiveCopilotUI

<MemoryRouter>
  <div className="min-h-screen bg-bg p-6">…</div>
</MemoryRouter>
```

**Theme** is an attribute on the document root, not a prop or a context:
`document.documentElement.dataset.theme = 'dark'`. Every colour resolves through
CSS variables, so the whole tree flips with that one write — never hardcode a
hex value or a Tailwind palette name like `slate-800`, because it will not
follow the theme.

### Styling idiom: Tailwind utilities over semantic tokens

There are **no raw palette names** — no `blue-500`, no `gray-200`. The theme
exposes semantic roles only, and every one works with the usual `bg-` / `text-` /
`border-` / `ring-` prefixes plus Tailwind opacity modifiers (`bg-surface/60`).

| Role | Names | Use for |
|---|---|---|
| Ground | `bg`, `surface`, `surface-raised` | page, panel, raised card |
| Line | `border`, `border-strong` | hairlines, emphasised dividers |
| Text | `text`, `text-muted`, `text-subtle` | body, secondary, metadata |
| Brand | `accent`, `accent-hover`, `accent-fg`, `accent-subtle` | primary action, active nav |
| State | `success`, `warning`, `danger`, `info` (each with a `-subtle` pair) | outcome, caution, error, note |
| Scrim | `overlay` | modal backdrops |

So: `bg-surface-raised`, `text-text-muted`, `border-border-strong`,
`bg-danger-subtle text-danger`, `ring-accent`. The `-subtle` variant is a tinted
background meant to sit under its solid counterpart as text.

**Component classes** exist for the recurring shapes — prefer them over
re-deriving the same utility stack:

- `card` — rounded panel, hairline border, raised surface
- `btn-primary` / `btn-ghost` — the two button treatments (both include `btn`)
- `field` — text input and select styling
- `label-eyebrow` — the small uppercase letterspaced label above a control or stat
- `tnum` — tabular numerals; use on **any** number that updates in place

### Where the truth is

- `_ds/<folder>/styles.css` and the files it imports — the real compiled CSS.
  Grep it before inventing a class.
- `components/<group>/<Name>/<Name>.prompt.md` and `<Name>.d.ts` — per-component
  usage and the exact prop contract.

### Composition

Components are presentational and take their data as props — `RecommendationCard`,
`EvidencePanel`, `ConflictBanner`, `StatsPanel`, `ForceGraph` and `HeaderMonitor`
all render whatever you pass. Three exceptions fetch their own data from the
backend and take no data props: `KpiStrip`, `RetrievalPreview` and
`SettingsDrawer` (which does take `open`).

Groups: **primitives** (Field, Select, Toggle), **header** (AppHeader,
HeaderMonitor, ThemeToggle), **copilot** (RecommendationCard, EvidencePanel,
ApprovalPanel, ConflictBanner), **grounding** (StatsPanel, RetrievalPreview,
UploadCard, ForceGraph), **kpi** (KpiStrip), **settings** (SettingsDrawer).

```jsx
const { MemoryRouter, AppHeader, RecommendationCard, EvidencePanel } =
  window.AdaptiveCopilotUI

function ReviewScreen({ run, telemetry }) {
  return (
    <MemoryRouter>
      <div className="min-h-screen bg-bg">
        <AppHeader telemetry={telemetry} offline={false} onOpenSettings={() => {}} />
        <main className="mx-auto max-w-3xl space-y-4 p-6">
          <p className="label-eyebrow">Case {run.case_id}</p>
          <RecommendationCard
            recommendation={run.recommendation}
            evidence={run.evidence}
            elapsedMs={run.elapsed_ms}
          />
          <EvidencePanel evidence={run.evidence} />
          <div className="card p-4">
            <p className="label-eyebrow">Elapsed</p>
            <p className="tnum mt-1 text-lg font-semibold text-text">
              {(run.elapsed_ms / 1000).toFixed(1)}s
            </p>
          </div>
        </main>
      </div>
    </MemoryRouter>
  )
}
```
