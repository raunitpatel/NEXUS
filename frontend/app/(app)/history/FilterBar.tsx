'use client'

import type { RunStatus } from '@/lib/types'

export type HistoryStatusFilter = RunStatus | ''
export type HistoryAgentFilter = 'search' | 'code' | 'memory' | 'tool' | ''

interface FilterBarProps {
  status: HistoryStatusFilter
  agentFilter: HistoryAgentFilter
  startDate: string
  endDate: string
  onStatusChange: (status: HistoryStatusFilter) => void
  onAgentFilterChange: (agent: HistoryAgentFilter) => void
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
}

const STATUS_OPTIONS: Array<{ label: string; value: HistoryStatusFilter }> = [
  { label: 'All statuses', value: '' },
  { label: 'Pending', value: 'pending' },
  { label: 'Running', value: 'running' },
  { label: 'Completed', value: 'completed' },
  { label: 'Failed', value: 'failed' },
  { label: 'Cancelled', value: 'cancelled' },
]

const AGENT_OPTIONS: Array<{ label: string; value: HistoryAgentFilter }> = [
  { label: 'All agents', value: '' },
  { label: 'Search Agent', value: 'search' },
  { label: 'Code Agent', value: 'code' },
  { label: 'Memory Agent', value: 'memory' },
  { label: 'Tool Agent', value: 'tool' },
]

export function FilterBar({
  status,
  agentFilter,
  startDate,
  endDate,
  onStatusChange,
  onAgentFilterChange,
  onStartDateChange,
  onEndDateChange,
}: FilterBarProps) {
  return (
    <div className="bg-white border-b border-black/[0.08] px-6 py-[11px] flex items-center gap-[10px] flex-shrink-0 flex-wrap">
      <label className="sr-only" htmlFor="history-status-filter">
        Status
      </label>
      <select
        id="history-status-filter"
        value={status}
        onChange={(event) => onStatusChange(event.target.value as HistoryStatusFilter)}
        className="h-8 border border-black/[0.12] rounded-[6px] px-[10px] text-[12.5px] text-nexus-dark bg-white font-sans outline-none cursor-pointer focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)]"
      >
        {STATUS_OPTIONS.map((option) => (
          <option key={option.value || 'all'} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <label className="sr-only" htmlFor="history-agent-filter">
        Agent
      </label>
      <select
        id="history-agent-filter"
        value={agentFilter}
        onChange={(event) => onAgentFilterChange(event.target.value as HistoryAgentFilter)}
        className="h-8 border border-black/[0.12] rounded-[6px] px-[10px] text-[12.5px] text-nexus-dark bg-white font-sans outline-none cursor-pointer focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)]"
      >
        {AGENT_OPTIONS.map((option) => (
          <option key={option.value || 'all-agents'} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <div className="w-px h-5 bg-black/[0.1] flex-shrink-0" />

      <label className="text-[12.5px] text-nexus-muted" htmlFor="history-start-date">
        From
      </label>
      <input
        id="history-start-date"
        type="date"
        value={startDate}
        onChange={(event) => onStartDateChange(event.target.value)}
        className="h-8 border border-black/[0.12] rounded-[6px] px-[10px] text-[12.5px] text-nexus-dark bg-white font-sans outline-none focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)]"
      />

      <label className="text-[12.5px] text-nexus-muted" htmlFor="history-end-date">
        To
      </label>
      <input
        id="history-end-date"
        type="date"
        value={endDate}
        onChange={(event) => onEndDateChange(event.target.value)}
        className="h-8 border border-black/[0.12] rounded-[6px] px-[10px] text-[12.5px] text-nexus-dark bg-white font-sans outline-none focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)]"
      />
    </div>
  )
}