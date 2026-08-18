import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { applyTheme, storedTheme, type Theme } from '../../lib/theme'

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => storedTheme())

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const next = theme === 'dark' ? 'light' : 'dark'

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="btn-ghost"
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      {theme === 'dark' ? <Moon size={15} /> : <Sun size={15} />}
      <span className="hidden sm:inline capitalize">{theme}</span>
    </button>
  )
}
