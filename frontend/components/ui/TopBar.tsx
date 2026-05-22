'use client'

/**
 * NEXUS top bar component.
 *
 * Renders the 52px horizontal bar at the top of every authenticated page.
 * Displays the current page title (passed as prop) and the user avatar.
 * Design reference: docs/design/nexus-all-pages.html — topbar section.
 */

interface TopBarProps {
  /** Page title displayed in the center-left of the bar. */
  title: string
  /** User initials for the avatar. */
  initials?: string
}

/**
 * Top navigation bar shown on all authenticated NEXUS pages.
 */
export function TopBar({ title, initials = 'U' }: TopBarProps) {
  return (
    <header className="h-[52px] bg-white border-b border-black/[0.08] flex items-center px-5 gap-3 flex-shrink-0">
      <span className="text-[15px] font-medium text-nexus-dark flex-1">{title}</span>
      <div className="w-7 h-7 bg-nexus-accent rounded-full flex items-center justify-center text-[11px] font-semibold text-white flex-shrink-0">
        {initials}
      </div>
    </header>
  )
}