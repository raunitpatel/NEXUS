/**
 * Run list card / table row for the NEXUS dashboard and history pages.
 *
 * Displays:
 * - run ID
 * - query
 * - agents used
 * - status badge
 * - execution duration
 * - relative timestamp
 */

'use client'

import Link from 'next/link'

import type { Run } from '@/lib/types'

import { StatusBadge } from './StatusBadge'
import { AgentsUsedBadge } from './AgentsUsedBadge'

interface RunCardProps {
  /** Run data from the API. */
  run: Run
}

/**
 * Format duration in seconds into a human-readable form.
 */
function formatDuration(
  seconds?: number | null
): string {
  if (seconds == null) return '—'

  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60

  if (hrs > 0) {
    return `${hrs}h ${mins}m`
  }

  if (mins > 0) {
    return `${mins}m ${secs}s`
  }

  return `${secs}s`
}

/**
 * Format an ISO timestamp as a relative "time ago" string.
 */
function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()

  const mins = Math.floor(diff / 60_000)
  const hours = Math.floor(diff / 3_600_000)

  if (mins < 1) return 'just now'

  if (mins < 60) {
    return `${mins} min ago`
  }

  if (hours < 24) {
    return `Today ${new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    })}`
  }

  return 'Yesterday'
}

/**
 * Truncate a string to maxLen chars, appending ellipsis if needed.
 */
function truncate(str: string, maxLen: number): string {
  return str.length > maxLen
    ? str.slice(0, maxLen) + '…'
    : str
}

/**
 * Run row matching the NEXUS dashboard/history table design.
 */
export function RunCard({ run }: RunCardProps) {
  return (
    <tr className="hover:bg-black/[0.01] transition-colors group">
      {/* Run ID */}
      <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
        <span className="font-mono text-[12px] text-nexus-accent">
          {run.run_id.slice(0, 10)}
        </span>
      </td>

      {/* Query */}
      <td className="px-[14px] py-[11px] border-b border-black/[0.05] max-w-[260px]">
        <span className="text-[13px] text-nexus-dark overflow-hidden text-ellipsis whitespace-nowrap block">
          {truncate(run.query, 80)}
        </span>
      </td>

      {/* Agents Used */}
      <td className="px-[14px] py-[11px] border-b border-black/[0.05] min-w-[180px]">
        <AgentsUsedBadge agents={run.agents_used} />
      </td>

      {/* Status */}
      <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
        <StatusBadge status={run.status} />
      </td>

      {/* Duration */}
      <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
        <span className="text-[12.5px] text-nexus-muted whitespace-nowrap">
          {formatDuration(run.duration_seconds)}
        </span>
      </td>

      {/* Time */}
      <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
        <span className="text-[12.5px] text-nexus-muted whitespace-nowrap">
          {timeAgo(run.created_at)}
        </span>
      </td>

      {/* View link */}
      <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
        <Link
          href={`/runs/${run.run_id}`}
          className="text-[12.5px] text-nexus-accent font-medium no-underline hover:underline whitespace-nowrap"
        >
          View →
        </Link>
      </td>
    </tr>
  )
}
