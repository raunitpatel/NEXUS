'use client'

/**
 * NEXUS top bar component.
 *
 * Renders the 52px horizontal bar at the top of every authenticated page.
 * Displays the current page title (passed as prop) and the user avatar.
 * Design reference: docs/design/nexus-all-pages.html — topbar section.
 */

import { useUser } from '@/components/UserContext'
import { useEffect, useState } from 'react'

interface TopBarProps {
  /** Page title displayed in the center-left of the bar. */
  title: string
  /** Optional user initials for the avatar; falls back to context. */
  initials?: string
}

/**
 * Top navigation bar shown on all authenticated NEXUS pages.
 */
export function TopBar({ title, initials }: TopBarProps) {
  const user = useUser()
  const avatar = initials ?? user.initials
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const stored = typeof window !== 'undefined' ? localStorage.getItem('nexus_theme') : null
      if (stored === 'dark' || stored === 'light') return stored
      if (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark'
    } catch {}
    return 'light'
  })

  useEffect(() => {
    try {
      const root = document.documentElement
      if (theme === 'dark') root.classList.add('dark')
      else root.classList.remove('dark')
      localStorage.setItem('nexus_theme', theme)
    } catch {}
  }, [theme])

  function toggleTheme() {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  }

  return (
    <header className="h-[52px] bg-white border-b border-black/[0.08] flex items-center px-5 gap-3 flex-shrink-0">
      <span className="text-[15px] font-medium text-nexus-dark flex-1">{title}</span>
      <div className="flex items-center gap-3">
        <button
          aria-label="Toggle theme"
          onClick={toggleTheme}
          className="flex items-center justify-center w-8 h-8 rounded-md text-nexus-muted hover:text-nexus-dark hover:bg-black/[0.04] transition-colors"
        >
          {theme === 'dark' ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          )}
        </button>

        <div className="w-7 h-7 bg-nexus-accent rounded-full flex items-center justify-center text-[11px] font-semibold text-white flex-shrink-0">
          {avatar}
        </div>
      </div>
    </header>
  )
}