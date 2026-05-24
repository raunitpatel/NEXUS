'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { StatusBadge } from '@/components/runs/StatusBadge'
import { AgentsUsedBadge } from '@/components/runs/AgentsUsedBadge'
import type { Run } from '@/lib/types'

interface RunTableProps {
  runs: Run[]
  isLoading: boolean
}

function formatTokens(run: Run): string {
  const total = run.total_tokens ?? (run.input_tokens ?? 0) + (run.output_tokens ?? 0)
  return total > 0 ? total.toLocaleString() : '—'
}

function formatLatency(run: Run): string {
  const latencyMs =
    typeof run.latency_ms === 'number'
      ? run.latency_ms
      : typeof run.duration_seconds === 'number'
        ? run.duration_seconds * 1000
        : null

  if (latencyMs == null) return '—'
  if (latencyMs < 1000) return `${Math.round(latencyMs)}ms`
  return `${(latencyMs / 1000).toFixed(1)}s`
}

function formatStarted(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function RunTableSkeleton() {
  return (
    <tbody>
      {[...Array(8)].map((_, index) => (
        <tr key={index}>
          {[...Array(7)].map((__, cellIndex) => (
            <td key={cellIndex} className="px-[14px] py-[11px] border-b border-black/[0.05]">
              <div className="h-[14px] bg-black/[0.04] rounded-[4px] animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  )
}

export function RunTable({ runs, isLoading }: RunTableProps) {
  const router = useRouter()

  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          {['Run ID', 'Your query', 'Agents', 'Status', 'Latency', 'Started', ''].map((heading) => (
            <th
              key={heading}
              className="text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] px-[14px] py-[10px] text-left border-b border-black/[0.07]"
            >
              {heading}
            </th>
          ))}
        </tr>
      </thead>

      {isLoading ? (
        <RunTableSkeleton />
      ) : runs.length === 0 ? (
        <tbody>
          <tr>
            <td colSpan={7} className="px-4 py-10 text-center text-[13px] text-nexus-muted">
              No runs match these filters.
            </td>
          </tr>
        </tbody>
      ) : (
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.run_id}
              onClick={() => router.push(`/runs/${run.run_id}`)}
              className={`hover:bg-black/[0.01] transition-colors ${run.status === 'failed' ? 'bg-nexus-error/[0.02]' : ''}`}
            >
              <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                <span className="font-mono text-[12px] text-nexus-accent">
                  {run.run_id.slice(0, 10)}
                </span>
              </td>
              <td className="px-[14px] py-[11px] border-b border-black/[0.05] max-w-[260px]">
                <span className="text-[13px] text-nexus-dark overflow-hidden text-ellipsis whitespace-nowrap block">
                  {run.query.length > 80 ? run.query.slice(0, 80) + '…' : run.query}
                </span>
              </td>
              <td className="px-[14px] py-[11px] border-b border-black/[0.05] min-w-[120px]">
                <AgentsUsedBadge agents={run.agents_used} />
              </td>
              <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                <StatusBadge status={run.status} />
              </td>
              <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                <span className="text-[12.5px] text-nexus-muted whitespace-nowrap">
                  {formatLatency(run)}
                </span>
              </td>
              <td className="px-[14px] py-[11px] border-b border-black/[0.05]">
                <span className="text-[12.5px] text-nexus-muted whitespace-nowrap">
                  {formatStarted(run.created_at)}
                </span>
              </td>
              <td
                className="px-[14px] py-[11px] border-b border-black/[0.05]"
                onClick={(e) => e.stopPropagation()}
              >
                <Link
                  href={`/runs/${run.run_id}`}
                  className="text-[12.5px] text-nexus-accent  cursor-pointer font-medium no-underline hover:underline whitespace-nowrap"
                >
                  View →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      )}
    </table>
  )
}