'use client'

/**
 * TokenUsageChart — stacked AreaChart of daily input + output tokens.
 *
 * Since the backend endpoint returns totals per day (not per-agent breakdown),
 * we render two stacked areas: input_tokens and output_tokens.
 * Design reference: docs/design/nexus-all-pages.html — Page 6 Observability.
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { DailyTokenUsage } from '@/lib/types'

interface TokenUsageChartProps {
  data: DailyTokenUsage[]
  isLoading: boolean
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
          <span className="text-nexus-muted">{entry.name}:</span>
          <span className="font-semibold text-nexus-dark">{entry.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  )
}

function SkeletonChart() {
  return (
    <div className="h-[240px] flex items-center justify-center">
      <div className="w-full h-full bg-black/[0.03] rounded-[6px] animate-pulse" />
    </div>
  )
}

function NoDataPlaceholder() {
  return (
    <div className="h-[240px] flex flex-col items-center justify-center gap-2">
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="text-nexus-muted/40">
        <rect x="2" y="18" width="6" height="12" rx="2" fill="currentColor" />
        <rect x="13" y="10" width="6" height="20" rx="2" fill="currentColor" />
        <rect x="24" y="4" width="6" height="26" rx="2" fill="currentColor" />
      </svg>
      <span className="text-[12.5px] text-nexus-muted">No token data yet — run some agents first</span>
    </div>
  )
}

/** Stacked area chart displaying daily input and output token consumption. */
export function TokenUsageChart({ data, isLoading }: TokenUsageChartProps) {
  if (isLoading) return <SkeletonChart />
  if (data.length === 0) return <NoDataPlaceholder />

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="inputGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#534AB7" stopOpacity={0.18} />
            <stop offset="95%" stopColor="#534AB7" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="outputGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#1D9E75" stopOpacity={0.18} />
            <stop offset="95%" stopColor="#1D9E75" stopOpacity={0} />
          </linearGradient>
        </defs>
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
          tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
          width={36}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 12, color: '#888780', paddingTop: 8 }}
        />
        <Area
          type="monotone"
          dataKey="input_tokens"
          name="Input tokens"
          stackId="1"
          stroke="#534AB7"
          strokeWidth={1.5}
          fill="url(#inputGradient)"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="output_tokens"
          name="Output tokens"
          stackId="1"
          stroke="#1D9E75"
          strokeWidth={1.5}
          fill="url(#outputGradient)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}