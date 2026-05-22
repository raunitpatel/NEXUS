'use client'

/**
 * NEXUS sidebar navigation component.
 *
 * Renders the persistent left navigation shell visible on all authenticated
 * pages. Active route is highlighted with the nexus-accent left border.
 * Design reference: docs/design/nexus-all-pages.html — sidebar anatomy section.
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import clsx from 'clsx'

// ── Nav item definition ───────────────────────────────────────────────────────

interface NavItem {
  label: string
  href: string
  icon: React.ReactNode
}

// ── Icons (inline SVGs matching design doc) ───────────────────────────────────

const OrchestratorIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 flex-shrink-0">
    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5"/>
    <polygon points="6,5 11,8 6,11" fill="currentColor"/>
  </svg>
)

const DashboardIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 flex-shrink-0">
    <rect x="1" y="1" width="6" height="6" rx="1.5" fill="currentColor"/>
    <rect x="9" y="1" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.5"/>
    <rect x="1" y="9" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.5"/>
    <rect x="9" y="9" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.5"/>
  </svg>
)

const RunsIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 flex-shrink-0">
    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5"/>
    <polyline points="8,5 8,8 10,10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
)

const HistoryIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 flex-shrink-0">
    <rect x="2" y="4" width="12" height="1.5" rx=".75" fill="currentColor"/>
    <rect x="2" y="7.25" width="12" height="1.5" rx=".75" fill="currentColor"/>
    <rect x="2" y="10.5" width="8" height="1.5" rx=".75" fill="currentColor"/>
  </svg>
)

const MemoryIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 flex-shrink-0">
    <ellipse cx="8" cy="6" rx="5.5" ry="4" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M2.5 6c0 2.5 2.5 5 5.5 5s5.5-2.5 5.5-5" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
)

const ObservabilityIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 flex-shrink-0">
    <polyline
      points="2,11 5,7 8,9 11,4 14,6"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

const LogoutIcon = () => (
  <svg viewBox="0 0 15 15" fill="none" className="w-4 h-4">
    <path d="M10 10l4-3-4-3v2H5v2h5v2z" fill="currentColor"/>
    <path d="M8 13H3a1 1 0 01-1-1V3a1 1 0 011-1h5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
  </svg>
)

const NexusIcon = () => (
  <svg viewBox="0 0 14 14" fill="none" className="w-[18px] h-[18px]">
    <rect x="1" y="1" width="5" height="5" rx="1" fill="white"/>
    <rect x="8" y="1" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
    <rect x="1" y="8" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
    <rect x="8" y="8" width="5" height="5" rx="1" fill="white" opacity="0.3"/>
  </svg>
)

// ── Navigation config ─────────────────────────────────────────────────────────

const PRIMARY_NAV: NavItem = {
  label: 'Orchestrator',
  href: '/orchestrator',
  icon: <OrchestratorIcon />,
}

const WORKSPACE_NAV: NavItem[] = [
  { label: 'Dashboard',     href: '/dashboard',     icon: <DashboardIcon /> },
  { label: 'Runs',          href: '/runs',           icon: <RunsIcon /> },
  { label: 'History',       href: '/history',        icon: <HistoryIcon /> },
  { label: 'Memory',        href: '/memory',         icon: <MemoryIcon /> },
  { label: 'Observability', href: '/observability',  icon: <ObservabilityIcon /> },
]

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Props for the Sidebar component.
 */
export interface SidebarProps {
  /** Display name of the authenticated user (shown in the footer). */
  displayName?: string
  /** User initials for the avatar (e.g. "AK"). */
  initials?: string
}

/**
 * Persistent sidebar navigation for all authenticated NEXUS pages.
 *
 * Renders wordmark, primary action (Orchestrator), workspace nav, and
 * user footer with logout. Active route is highlighted via left border.
 */
export function Sidebar({ displayName = 'User', initials = 'U' }: SidebarProps) {
  const pathname = usePathname()

  function isActive(href: string): boolean {
    return pathname === href || pathname.startsWith(href + '/')
  }

  function navLinkClass(href: string): string {
    return clsx(
      'flex items-center gap-[10px] px-4 py-[9px]',
      'text-[13.5px] font-medium border-l-[3px] no-underline transition-colors',
      isActive(href)
        ? 'border-l-nexus-accent text-nexus-accent bg-nexus-accent/[0.08]'
        : 'border-l-transparent text-nexus-muted hover:bg-white/5 hover:text-white'
    )
  }

  return (
    <aside className="w-[220px] bg-nexus-sidebar flex flex-col flex-shrink-0 h-full">

      {/* Wordmark */}
      <div className="px-4 pt-[18px] pb-[14px] flex items-center gap-[9px] border-b border-white/[0.06]">
        <div className="w-6 h-6 bg-nexus-accent rounded-[5px] flex items-center justify-center flex-shrink-0">
          <NexusIcon />
        </div>
        <span className="text-[14px] font-semibold text-white tracking-[0.08em]">
          NEXUS
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-2 flex flex-col gap-px">

        {/* Primary action — Orchestrator */}
        <Link href={PRIMARY_NAV.href} className={navLinkClass(PRIMARY_NAV.href)}>
          {PRIMARY_NAV.icon}
          {PRIMARY_NAV.label}
        </Link>

        {/* Divider + section label */}
        <div className="h-px bg-white/[0.06] my-[6px]" />
        <div className="px-4 py-1 text-[10px] font-bold text-white/25 uppercase tracking-[0.1em]">
          My workspace
        </div>

        {/* Workspace links */}
        {WORKSPACE_NAV.map((item) => (
          <Link key={item.href} href={item.href} className={navLinkClass(item.href)}>
            {item.icon}
            {item.label}
          </Link>
        ))}
      </nav>

      {/* User footer */}
      <div className="px-4 py-[14px] border-t border-white/[0.06] flex items-center gap-[9px]">
        <div className="w-7 h-7 bg-nexus-accent rounded-full flex items-center justify-center text-[11px] font-semibold text-white flex-shrink-0">
          {initials}
        </div>
        <span className="text-[13px] font-medium text-[#C8C7C3] flex-1 truncate">
          {displayName}
        </span>
        <button
          onClick={() => {
            // removeToken and redirect — full logout wired in AGNT-020
            if (typeof window !== 'undefined') {
              localStorage.removeItem('nexus_jwt')
              window.location.href = '/login'
            }
          }}
          className="text-nexus-muted hover:text-white transition-colors"
          aria-label="Sign out"
        >
          <LogoutIcon />
        </button>
      </div>
    </aside>
  )
}