'use client'

/**
 * ErrorRateChart — LineChart showing derived error rate % per day.
 *
 * Since the latency endpoint doesn't include failures, we derive error
 * rate from the MetricsSummary (all-time) and display a single flat line.
 * When daily breakdown is available (via AgentStats), we compute it per day.
 *
 * For now: uses DailyTokenUsage run_count vs a synthetic failed estimate
 * based on the user's overall success_rate from MetricsSummary.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { DailyTokenUsage, MetricsSummary } from '@/lib/types'

interface ErrorRateChartProps {
  tokenData: DailyTokenUsage[]
  summary: MetricsSummary | null
  isLoading: boolean
}

interface DerivedErrorPoint {
  date: string
  error_rate: number
  run_count: number
}

interface TooltipPayloadEntry {
  name: string
  value: number
  color: string
}

interface CustomTooltipProps {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-black/[0.08] rounded-[7px] px-3 py-2 shadow-[0_2px_12px_rgba(0,0,0,0.1)]">
      <div className="text-[11.5px] font-semibold text-nexus-muted mb-1">{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 text-[12.5px]">
          <span className="w-[8px] h-[8px] rounded-full flex-shrink-0" style={{ background: entry.color }} />
          <span className="text-nexus-muted">Error rate:</span>
          <span className="font-semibold text-nexus-dark">{entry.value.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

function SkeletonChart() {
  return <div className="h-[240px] bg-black/[0.03] rounded-[6px] animate-pulse" />
}

function NoDataPlaceholder() {
  return (
    <div className="h-[240px] flex flex-col items-center justify-center gap-2">
      <span className="text-[12.5px] text-nexus-muted">No run data yet</span>
    </div>
  )
}

/** Line chart showing estimated error rate % per day based on overall success_rate. */
export function ErrorRateChart({ tokenData, summary, isLoading }: ErrorRateChartProps) {
  if (isLoading) return <SkeletonChart />
  if (tokenData.length === 0 || !summary) return <NoDataPlaceholder />

  // Derive error rate per day using the overall error rate as a constant approximation.
  // When per-day failure data is available from a future endpoint, replace this.
  const overallErrorRate = (1 - summary.success_rate) * 100

  const chartData: DerivedErrorPoint[] = tokenData.map((day) => ({
    date: day.date,
    run_count: day.run_count,
    error_rate: day.run_count > 0 ? parseFloat(overallErrorRate.toFixed(1)) : 0,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: '#888780' }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: string) => {
            const d = new Date(v)
            return `${d.getMonth() + 1}/${d.getDate()}`
          }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#888780' }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          domain={[0, 'auto']}
          width={36}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={10} stroke="#E24B4A" strokeDasharray="4 4" strokeOpacity={0.4} />
        <Line
          type="monotone"
          dataKey="error_rate"
          name="Error rate"
          stroke="#E24B4A"
          strokeWidth={1.5}
          dot={{ r: 3, fill: '#E24B4A', strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}