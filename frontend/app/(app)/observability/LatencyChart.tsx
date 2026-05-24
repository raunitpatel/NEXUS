'use client'

/**
 * LatencyChart — grouped BarChart showing avg and p95 latency per day.
 *
 * Data from GET /api/v1/metrics/latency which returns daily avg_duration_ms
 * and p95_duration_ms. Two bars per day show the spread between median
 * and tail latency.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { DailyLatency } from '@/lib/types'

interface LatencyChartProps {
  data: DailyLatency[]
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
          <span className="font-semibold text-nexus-dark">{entry.value.toFixed(0)} ms</span>
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
      <span className="text-[12.5px] text-nexus-muted">No latency data yet</span>
    </div>
  )
}

/** Grouped bar chart displaying avg and p95 run latency per calendar day. */
export function LatencyChart({ data, isLoading }: LatencyChartProps) {
  if (isLoading) return <SkeletonChart />
  if (data.length === 0) return <NoDataPlaceholder />

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }} barCategoryGap="30%">
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
          tickFormatter={(v: number) => `${v.toFixed(0)}ms`}
          width={44}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 12, color: '#888780', paddingTop: 8 }}
        />
        <Bar dataKey="avg_duration_ms" name="Avg latency" fill="#534AB7" radius={[3, 3, 0, 0]} maxBarSize={20} />
        <Bar dataKey="p95_duration_ms" name="p95 latency" fill="#B0AFA9" radius={[3, 3, 0, 0]} maxBarSize={20} />
      </BarChart>
    </ResponsiveContainer>
  )
}