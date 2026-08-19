/* Design-sync build config. Wraps the app's own tailwind.config.js and adds a
   safelist for the full semantic-token matrix.

   Why: the app's compiled CSS is tree-shaken to the utilities the app happens
   to use today, so a token the design agent reaches for (bg-info-subtle,
   ring-accent) would resolve to nothing. The design system's contract is the
   token set, not the subset this app consumed — so the shipped stylesheet
   carries every token utility. Run from frontend/ with -c. */
import base from '../frontend/tailwind.config.js'

const COLORS = 'bg|surface|border|text|accent|success|warning|danger|info|overlay'
const SHADES = 'raised|strong|muted|subtle|hover|fg'
const NAMES = [
  'bg', 'surface', 'surface-raised', 'border', 'border-strong',
  'accent', 'accent-subtle', 'success', 'success-subtle', 'warning',
  'warning-subtle', 'danger', 'danger-subtle', 'info', 'info-subtle', 'overlay',
]
const STEPS = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]

export default {
  ...base,
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  safelist: [
    { pattern: new RegExp(`^(bg|text|border|ring|fill|stroke|divide)-(${COLORS})(-(${SHADES}))?$`) },
    // Opacity modifiers are generated from content, not from the pattern above,
    // so translucent surfaces and scrims are enumerated. Without these,
    // `bg-surface/90` (which the app's own header uses) resolves to nothing in
    // any design built after this sync.
    ...NAMES.flatMap((n) => STEPS.map((o) => `bg-${n}/${o}`)),
    'card', 'btn', 'btn-primary', 'btn-ghost', 'field', 'label-eyebrow', 'tnum',
  ],
}
