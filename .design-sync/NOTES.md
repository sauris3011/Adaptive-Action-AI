# design-sync notes — adaptive-action-copilot-ui

Repo-specific gotchas for future syncs. Read this before re-running.

## Shape

- **This is an app, not a published component library.** No `main`/`module`/`exports`,
  no barrel, and `frontend/dist/` is a Vite *app* bundle. The converter runs in
  synth-entry mode (`[NO_DIST]` on every build — expected, not an error).
- **`srcDir` is `src/components`, deliberately not `src`.** Synth-entry does
  `export * from` every source file it walks, so pointing at `src` pulls in
  `main.tsx`, whose top-level `createRoot(document.getElementById('root')!)`
  throws in the preview page. Narrowing to `src/components` also drops the three
  route pages (`CopilotPage`/`GroundingPage`/`MetricsPage`), which are app
  screens rather than design-system surface.
- **`frontend/node_modules/adaptive-action-copilot-ui` is a junction back to
  `frontend/`.** The converter resolves `PKG_DIR` as `<node_modules>/<pkg>`, and
  a package never self-installs. Recreate it on a fresh clone:
  `New-Item -ItemType Junction -Path frontend/node_modules/adaptive-action-copilot-ui -Target frontend`
  (PowerShell, no admin needed) or `ln -s ../.. frontend/node_modules/adaptive-action-copilot-ui`.
  **Consequence:** every package-relative config path resolves from the junction,
  so repo-root paths need `../../../` (see `docsDir`, `extraFonts`).

## Build

- `cfg.buildCmd` is `node .design-sync/prepare.mjs`, which does three things the
  app's own build doesn't:
  1. **Tailwind → a stable path.** The app's dist CSS is content-hashed, so it
     can't be named in config. `prepare` compiles to `frontend/.ds-css/ds.css`
     via `.design-sync/tailwind.ds.config.mjs`, which wraps the app's own config
     and adds a **safelist for the full semantic-token matrix**. Without the
     safelist the shipped CSS is tree-shaken to the utilities *this app* happens
     to use, and a token the design agent reaches for (`bg-info-subtle`,
     `ring-accent`) resolves to nothing.
  2. **`.d.ts` emit** (`frontend/tsconfig.ds.json`). Without real declarations
     every component ships `[key: string]: unknown` as its API contract — the
     components use inline destructured prop types with no named `<Name>Props`
     interface, and the ts-morph fallback can't resolve `.tsx` through the
     synthesized `.mjs` entry. `frontend/package.json` has `"types":
     ".ds-types/index.d.ts"` pointing at the generated barrel.
  3. **Barrel generation** over `.ds-types/components/**` only.
- `prepare.mjs` spawns npx with `shell: true` — required on Windows since the
  Node 18.20/20.12 fix made `spawnSync` of a `.cmd` shim fail with `EINVAL`.

## Environment (Windows)

- **chromium: use the installed Chrome, not a playwright download.** Set
  `DS_CHROMIUM_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"` on
  every `package-validate.mjs` / `package-capture.mjs` run. Playwright is
  installed in `.ds-sync/` with `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`, so there
  is no 200MB browser cache to maintain.
- **curl needs `--ssl-no-revoke`.** Plain https fetches fail with
  `CRYPT_E_REVOCATION_OFFLINE` behind this network's TLS-intercepting proxy
  (same reason the backend ships `SSL_VERIFY=false`).
- Heredocs through the shell tool eat one level of backslash escaping — write
  JS/Python that avoids literal backslashes (e.g. `path.sep`, `[.]` in regex)
  or patch the file afterwards.

## Fonts

- The app's `tailwind.config.js` names **Inter** first in the sans stack but the
  app never loaded it — no `@font-face`, no font files, no `<link>` in
  `index.html`. The running app has always fallen through to system-ui.
- Resolved for the design system by vendoring Inter (SIL OFL) into
  `.design-sync/fonts/` (latin + latin-ext, weights 400/500/600/700, ~520 KB)
  and wiring `cfg.extraFonts`. **The app itself was deliberately left alone** —
  if someone later adds the same `@font-face` to `frontend/`, the app and the
  design system will finally agree.

## Previews

- **`_fixtures.ts` and `_open.tsx` in `.design-sync/previews/` are shared
  helpers, not components.** The converter only compiles `<Name>.tsx` matching a
  discovered component, so underscore-prefixed siblings are safe to import.
- **Components that own disclosure state internally need `OpenOnMount`**
  (`_open.tsx`). `EvidencePanel` has no `open` prop, so every static cell renders
  collapsed and identical. `OpenOnMount` clicks the real header control once on
  mount — the component's own expanded render, not a reimplementation.
- Fixtures use the repo's own banking domain pack (TXN-9002 / REG-E-2 / BDP-3.4 /
  Northwind Electronics) so every card tells one coherent dispute story.

## Previews (continued)

- **`_api.ts` stubs `window.fetch`** for the three components that fetch their own
  data instead of taking it as props: `KpiStrip` and `SettingsDrawer` (on mount)
  and `RetrievalPreview` (on submit). Without it those cards render "Loading…"
  or a connection error. The stub supplies the response the backend would have
  given — the components still render themselves.
  **If a component's API route or response shape changes, the stub goes stale
  silently**: the card keeps rendering, just with wrong-shaped data that Zod may
  reject. Re-check `_api.ts` against `frontend/src/lib/schemas.ts` on any sync
  that touches the wire format.
- **`SettingsDrawer` needs a staging wrapper.** It is a `fixed inset-0` overlay,
  so on its own the preview root has zero measurable height and the card
  captures blank (`[RENDER_BLANK]`, 4.5 KB PNG). The `Stage` wrapper in its
  preview sets `transform: translateZ(0)`, which makes the element a containing
  block for fixed descendants. Same fix applies to any future overlay.
- **Card modes** in `cfg.overrides`: `AppHeader`, `HeaderMonitor`, `KpiStrip`,
  `StatsPanel`, `RetrievalPreview` and `ForceGraph` are `cardMode: "column"`
  (full-width surfaces that otherwise crop in a multi-column grid — `HeaderMonitor`
  only surfaced this via `[GRID_OVERFLOW]` after its previews were authored).
  `SettingsDrawer` is `cardMode: "single"` with a `1100x760` viewport.

## Known render warns

- `[NO_DIST] no built entry — synthesizing from 16 src files` — expected, see Shape.
- `tokens: N defined, M referenced (1 missing, below threshold)` — expected; the
  safelist defines more tokens than the components currently consume.
- Everything else was clean on the final run: validate exited 0 with **zero**
  warnings, 16/16 previews rendering, 0 bad / 0 thin / 0 variantsIdentical.
  **A warn not in this list is new** — look at it before recording it.

## Re-sync risks

Things that can go stale quietly. Check these before trusting a fast re-sync.

- **The fetch stub** (`_api.ts`) — see above. Highest-risk item here: it fails
  silently rather than loudly.
- **Fixture data drifts from the schemas.** `_fixtures.ts` hand-builds `Run`,
  `Recommendation`, `Conflict`, `Evidence` and `TelemetrySummary` objects. A new
  required field in `frontend/src/lib/schemas.ts` will not fail the build — the
  preview just renders `undefined` somewhere. Grep the fixtures when schemas move.
- **The junction is not in git.** A fresh clone has no
  `frontend/node_modules/adaptive-action-copilot-ui`, and the build dies with
  ENOENT on its package.json. Recreate it (see Shape).
- **`frontend/package.json` carries a `"types"` field that only design-sync
  uses.** If someone removes it as unused, every component silently reverts to
  a `[key: string]: unknown` contract. The build will still exit 0.
- **Inter is vendored, not tracked upstream.** `.design-sync/fonts/` holds a
  point-in-time copy from Google Fonts. Nothing re-fetches it.
- **Opacity utilities are enumerated, not derived.** `tailwind.ds.config.mjs`
  safelists `bg-<role>/<step>` for a fixed step list. A design using a step
  outside it (e.g. `bg-surface/35`) gets no rule. Widen `STEPS` if that shows up.
- **Only `bg-` has opacity variants** — `text-`/`border-`/`ring-` do not.
- The app itself still ships no Inter `@font-face`, so **the running app and the
  design system render in different fonts**. Worth closing one day; deliberately
  out of scope for the sync.
- Toolchain assumed by this run: Node 25.6.1, chromadb-free frontend, Tailwind
  3.4, playwright driving system Chrome (no browser cache).
