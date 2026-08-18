/* Explicit light/dark toggle (FR-12).
   The choice is written to documentElement[data-theme], which is the single
   selector every token block keys off. Persisted, with the system preference as
   the first-run default only. */

export type Theme = 'light' | 'dark'
const STORAGE_KEY = 'copilot.theme'

export function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function storedTheme(): Theme {
  const saved = localStorage.getItem(STORAGE_KEY)
  return saved === 'light' || saved === 'dark' ? saved : systemTheme()
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem(STORAGE_KEY, theme)
}
