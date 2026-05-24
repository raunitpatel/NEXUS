'use client'

/**
 * AgentStatsTable — per-agent breakdown table linking to filtered History.
 *
 * Rows: agent_type, total_tasks, success_rate, avg_duration_ms, failed_tasks.
 * Each row links to /history?agent=<agent_type> to filter the Run History page.
 * Design reference: docs/design/nexus-all-pages.html — Page 6 Observability table.
 */

import Link from 'next/link'
import type { AgentStat } from '@/lib/types'

interface AgentStatsTableProps {
  stats: AgentStat[]
  isLoading: boolean
}

const AGENT_CHIP_STYLE: Record<string, { bg: string; text: string; dot: string; label: string }> = {
  search:       { bg: '#E6F1FB', text: '#0C447C', dot: '#378ADD', label: 'Search' },
  code:         { bg: '#FAEEDA', text: '#633806', dot: '#EF9F27', label: 'Code' },
  memory_read:  { bg: '#EEEDFE', text: '#3C3489', dot: '#7F77DD', label: 'Memory Read' },
  memory_write: { bg: '#EEEDFE', text: '#3C3489', dot: '#7F77DD', label: 'Memory Write' },
  tool:         { bg: '#E1F5EE', text: '#085041', dot: '#1D9E75', label: 'Tool' },
  synthesize:   { bg: '#D4F3E6', text: '#0A5E3A', dot: '#1D9E75', label: 'Synthesize' },
}

const DEFAULT_CHIP = { bg: '#F0EFE9', text: '#888780', dot: '#B0AFA9', label: 'Unknown' }

/** Maps agent task type slug to a history filter value. */
function agentTypeToHistoryFilter(agentType: string): string {
  if (agentType.startsWith('memory')) return 'memory'
  return agentType
}

function SkeletonRow() {
  return (
    <tr>
      {[...Array(5)].map((_, i) => (
        <td key={i} className="px-[14px] py-[11px] border-b border-black/[0.05]">
          <div className="h-[14px] bg-black/[0.04] rounded-[4px] animate-pulse" />
        </td>
      ))}
    </tr>
  )
}

/** Table displaying per-agent task metrics with History deep-links. */
export function AgentStatsTable({ stats, isLoading }: AgentStatsTableProps) {
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          {['Agent', 'My runs', 'Success rate', 'Avg latency', 'Failures', ''].map((h) => (
            <th
              key={h}
              className="text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] px-[14px] py-[10px] text-left border-b border-black/[0.07]"
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {isLoading ? (
          <>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </>
        ) : stats.length === 0 ? (
          <tr>
            <td colSpan={6} className="px-4 py-8 text-center text-[13px] text-nexus-muted">
              No agent activity in the selected period.
            </td>
          </tr>
        ) : (
          stats.map((stat) => {
            const chip = AGENT_CHIP_STYLE[stat.agent_type] ?? DEFAULT_CHIP
            const successPct = (stat.success_rate * 100).toFixed(1)
            const successColor =
              stat.success_rate >= 0.9
                ? 'text-nexus-success'
                : stat.success_rate >= 0.7
                  ? 'text-nexus-warning'
                  : 'text-nexus-error'
            const historyHref = `/history?agent=${agentTypeToHistoryFilter(stat.agent_type)}`

            return (
              <tr
                key={stat.agent_type}
                className="hover:bg-black/[0.01] transition-colors cursor-pointer"
              >
                <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                  <span
                    className="inline-flex items-center gap-[5px] px-[9px] py-[3px] rounded-[5px] text-[12px] font-semibold"
                    style={{ background: chip.bg, color: chip.text }}
                  >
                    <span
                      className="w-[6px] h-[6px] rounded-full flex-shrink-0"
                      style={{ background: chip.dot }}
                    />
                    {chip.label}
                  </span>
                </td>
                <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                  <span className="text-[13px] font-medium text-nexus-dark">{stat.total_tasks}</span>
                </td>
                <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                  <span className={`text-[13px] font-semibold ${successColor}`}>{successPct}%</span>
                </td>
                <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                  <span className="text-[12.5px] text-nexus-muted">
                    {stat.avg_duration_ms > 0 ? `${(stat.avg_duration_ms / 1000).toFixed(1)}s` : '—'}
                  </span>
                </td>
                <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                  <span className={`text-[12.5px] ${stat.failed_tasks > 0 ? 'text-nexus-error font-medium' : 'text-nexus-muted'}`}>
                    {stat.failed_tasks}
                  </span>
                </td>
                <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                  <Link
                    href={historyHref}
                    className="text-[12.5px] text-nexus-accent font-medium no-underline hover:underline whitespace-nowrap"
                    onClick={(e) => e.stopPropagation()}
                  >
                    View runs →
                  </Link>
                </td>
              </tr>
            )
          })
        )}
      </tbody>
    </table>
  )
}