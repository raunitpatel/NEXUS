/**
 * Colour-coded status badge for NEXUS run and task statuses.
 *
 * Maps DB status strings to the NEXUS design system colours:
 *   running   → green (#1D9E75) with pulse animation
 *   completed → green (#1D9E75) with checkmark
 *   failed    → red (#E24B4A) with ✕
 *   pending   → amber (#BA7517) with clock
 *   cancelled → grey (#888780) with dash
 */
import type { ReactNode } from 'react'
import type { RunStatus } from '@/lib/types'

interface StatusBadgeProps {
  /** Run lifecycle status from the API. */
  status: RunStatus
}

const CONFIG: Record<RunStatus, { bg: string; text: string; icon: ReactNode }> = {
  running: {
    bg: 'bg-[#E8F8F2]',
    text: 'text-[#1D9E75]',
    icon: (
      <span className="w-[6px] h-[6px] rounded-full bg-[#1D9E75] flex-shrink-0 animate-pulse" />
    ),
  },
  completed: {
    bg: 'bg-[#E8F8F2]',
    text: 'text-[#1D9E75]',
    icon: (
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
        <path
          d="M2 5.5l2.5 2.5L9 3"
          stroke="#1D9E75"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  failed: {
    bg: 'bg-[#FDECEA]',
    text: 'text-[#E24B4A]',
    icon: (
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
        <path
          d="M3 3l5 5M8 3l-5 5"
          stroke="#E24B4A"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  pending: {
    bg: 'bg-[#FEF3E2]',
    text: 'text-[#BA7517]',
    icon: (
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
        <circle cx="5.5" cy="5.5" r="4" stroke="#BA7517" strokeWidth="1.3" />
        <path
          d="M5.5 3.5v2l1.5 1"
          stroke="#BA7517"
          strokeWidth="1.3"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  cancelled: {
    bg: 'bg-[#F1EFE8]',
    text: 'text-[#888780]',
    icon: (
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
        <circle cx="5.5" cy="5.5" r="4" stroke="#888780" strokeWidth="1.3" />
        <path
          d="M3.5 5.5h4"
          stroke="#888780"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
}

/**
 * Pill-shaped status badge matching the NEXUS design system.
 */
export function StatusBadge({ status }: StatusBadgeProps) {
  const { bg, text, icon } = CONFIG[status as RunStatus] ?? CONFIG.pending

  return (
    <span
      className={`inline-flex items-center gap-[5px] px-[10px] py-[3px] rounded-[4px] text-[12px] font-semibold whitespace-nowrap ${bg} ${text}`}
    >
      {icon}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}