'use client'

/**
 * Observability page — personal usage metrics for the authenticated user.
 *
 * Four sections:
 *  1. Token usage over time (stacked AreaChart)
 *  2. Run latency trends (grouped BarChart)
 *  3. Error rate over time (LineChart)
 *  4. Per-agent stats table with History deep-links
 *
 * All data fetched via SWR with 30s refresh from /api/v1/metrics/*.
 * Design reference: docs/design/nexus-all-pages.html — Page 6 Observability.
 */

import { TopBar } from '@/components/ui/TopBar'
import { useMetricsSummary } from '@/hooks/useMetrics'
import { useAgentStats } from '@/hooks/useAgentStats'
import { useTokenUsage } from '@/hooks/useTokenUsage'
import { useLatency } from '@/hooks/useLatency'
import { TokenUsageChart } from './TokenUsageChart'
import { LatencyChart } from './LatencyChart'
import { ErrorRateChart } from './ErrorRateChart'
import { AgentStatsTable } from './AgentStatsTable'

interface SectionCardProps {
  title: string
  subtitle?: string
  children: React.ReactNode
}

/** Wrapper card matching the NEXUS dashboard card style. */
function SectionCard({ title, subtitle, children }: SectionCardProps) {
  return (
    <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
      <div className="px-[18px] py-[12px] border-b border-black/[0.06] flex items-center justify-between">
        <span className="text-[13px] font-semibold text-nexus-dark">{title}</span>
        {subtitle && (
          <span className="text-[12px] text-nexus-muted">{subtitle}</span>
        )}
      </div>
      <div className="px-[18px] py-[14px]">{children}</div>
    </div>
  )
}

/** Personal summary metric pill. */
function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-[8px] border border-black/[0.07] px-[18px] py-4">
      <div className="text-[12px] text-nexus-muted font-medium mb-2">{label}</div>
      <div className="text-[24px] font-medium text-nexus-dark leading-none">{value}</div>
    </div>
  )
}

export default function ObservabilityPage() {
  const DAYS = 7

  const { summary, isLoading: summaryLoading } = useMetricsSummary({ days: DAYS })
  const { stats, isLoading: statsLoading } = useAgentStats({ days: DAYS })
  const { data: tokenData, isLoading: tokenLoading } = useTokenUsage(DAYS)
  const { data: latencyData, isLoading: latencyLoading } = useLatency(DAYS)

  const successPct = summary ? `${(summary.success_rate * 100).toFixed(0)}%` : '—'
  const avgLatency = summary ? `${(summary.avg_run_duration_ms / 1000).toFixed(1)}s` : '—'
  const totalTokens = summary
    ? `${((summary.total_input_tokens + summary.total_output_tokens) / 1000).toFixed(0)}k`
    : '—'

  return (
    <>
      <TopBar title="My observability" />

      <div className="flex-1 bg-nexus-bg overflow-y-auto p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-[16px] font-semibold text-nexus-dark">My observability</h2>
            <p className="text-[12.5px] text-nexus-muted mt-[2px]">
              Personal token usage, latency, and agent performance — last {DAYS} days. Private to your account.
            </p>
          </div>
          <div
            className="text-[12px] text-nexus-muted bg-[#F0EFE9] border border-black/[0.08] px-[10px] py-[3px] rounded-[5px] font-medium"
          >
            Last {DAYS} days · yours only
          </div>
        </div>

        {/* Summary pills */}
        <div className="grid grid-cols-3 gap-3 mb-5">
          <MetricPill label={`My tokens (${DAYS}d)`} value={summaryLoading ? '…' : totalTokens} />
          <MetricPill label="My avg latency" value={summaryLoading ? '…' : avgLatency} />
          <MetricPill label="My success rate" value={summaryLoading ? '…' : successPct} />
        </div>

        {/* Charts grid */}
        <div className="grid grid-cols-2 gap-5 mb-5">
          <SectionCard title="Token usage" subtitle="input + output per day">
            <TokenUsageChart data={tokenData} isLoading={tokenLoading} />
          </SectionCard>

          <SectionCard title="Run latency" subtitle="avg vs p95 per day">
            <LatencyChart data={latencyData} isLoading={latencyLoading} />
          </SectionCard>
        </div>

        <div className="mb-5">
          <SectionCard title="Error rate" subtitle="% of failed runs per day">
            <ErrorRateChart
              tokenData={tokenData}
              summary={summary}
              isLoading={tokenLoading || summaryLoading}
            />
          </SectionCard>
        </div>

        {/* Agent stats table */}
        <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
          <div className="px-[18px] py-[12px] border-b border-black/[0.06] flex items-center justify-between">
            <span className="text-[13px] font-semibold text-nexus-dark">My agent usage — {DAYS} days</span>
            <span className="text-[12px] text-nexus-muted">Click a row to view filtered history</span>
          </div>
          <AgentStatsTable stats={stats} isLoading={statsLoading} />
        </div>
      </div>
    </>
  )
}