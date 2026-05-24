'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import { TopBar } from '@/components/ui/TopBar'
import { apiFetch } from '@/lib/api'
import type { Run, RunListResponse } from '@/lib/types'
import { FilterBar, type HistoryStatusFilter, type HistoryAgentFilter } from './FilterBar'
import { RunTable } from './RunTable'

const PAGE_SIZE = 20

// --- AGNT history page fix: agent filtering applied client-side since backend
// groups by agent name string. We filter runs whose agents_used contains
// a name matching the selected agent type slug.
const AGENT_NAME_MAP: Record<string, string> = {
  search: 'Search Agent',
  code: 'Code Agent',
  memory: 'Memory Agent',
  tool: 'Tool Agent',
}

async function fetchRunHistory(url: string): Promise<RunListResponse> {
  return apiFetch<RunListResponse>(url)
}

export default function HistoryPage() {
  const [status, setStatus] = useState<HistoryStatusFilter>('')
  const [agentFilter, setAgentFilter] = useState<HistoryAgentFilter>('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [page, setPage] = useState(1)

  // Fetch a larger batch when agent filter is active so client-side filtering
  // has enough data. The backend doesn't support agent_type query param yet.
  const fetchSize = agentFilter ? 200 : PAGE_SIZE

  const historyUrl = useMemo(() => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    // Always fetch page 1 from backend when agent filter active — we paginate client-side
    params.set('page', agentFilter ? '1' : String(page))
    params.set('size', String(fetchSize))
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)

    return `/api/v1/runs?${params.toString()}`
  }, [status, page, startDate, endDate, agentFilter, fetchSize])

  const { data, isLoading, error } = useSWR<RunListResponse>(
    historyUrl,
    fetchRunHistory
  )

  // Client-side agent filter applied on top of backend results
  const filteredRuns: Run[] = useMemo(() => {
    const all = data?.runs ?? []
    if (!agentFilter) return all
    const targetName = AGENT_NAME_MAP[agentFilter]
    return all.filter((run) =>
      run.agents_used?.some((a) => a === targetName)
    )
  }, [data?.runs, agentFilter])

  // Pagination over filtered results
  const totalFilteredCount = agentFilter ? filteredRuns.length : (data?.total_count ?? 0)
  const totalPages = Math.max(1, Math.ceil(totalFilteredCount / PAGE_SIZE))
  const pagedRuns = agentFilter
    ? filteredRuns.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
    : filteredRuns

  const startItem = totalFilteredCount === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const endItem = Math.min(page * PAGE_SIZE, totalFilteredCount)

  // Build visible page numbers — show at most 5 around current
  const pageNumbers = useMemo(() => {
    if (totalPages <= 5) return Array.from({ length: totalPages }, (_, i) => i + 1)
    const nums: number[] = []
    if (page > 2) nums.push(1)
    if (page > 3) nums.push(-1) // ellipsis
    for (let i = Math.max(1, page - 1); i <= Math.min(totalPages, page + 1); i++) {
      nums.push(i)
    }
    if (page < totalPages - 2) nums.push(-2) // ellipsis
    if (page < totalPages - 1) nums.push(totalPages)
    return nums
  }, [page, totalPages])

  function resetPage() { setPage(1) }

  return (
    <>
      <TopBar title="My history" />

      <div className="flex-1 bg-nexus-bg overflow-hidden flex flex-col">
        <FilterBar
          status={status}
          agentFilter={agentFilter}
          startDate={startDate}
          endDate={endDate}
          onStatusChange={(v) => { setStatus(v); resetPage() }}
          onAgentFilterChange={(v) => { setAgentFilter(v); resetPage() }}
          onStartDateChange={(v) => { setStartDate(v); resetPage() }}
          onEndDateChange={(v) => { setEndDate(v); resetPage() }}
        />

        <div className="flex-1 p-6 overflow-y-auto">
          {/* Ownership badge matching design doc */}
          <div className="flex items-center justify-between mb-4">
            <div
              className="text-[12px] text-nexus-muted bg-[#F0EFE9] border border-black/[0.08] px-[10px] py-[3px] rounded-[5px] font-medium"
            >
              {totalFilteredCount} total runs · yours only
            </div>
          </div>

          <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
            {error ? (
              <div className="px-4 py-10 text-center text-[13px] text-nexus-error">
                Failed to load run history. Please refresh.
              </div>
            ) : (
              <RunTable runs={pagedRuns} isLoading={isLoading} />
            )}

            {/* Pagination footer — matches design doc exactly */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-black/[0.06] bg-white">
              <span className="text-[12.5px] text-nexus-muted">
                Showing {startItem}–{endItem} of {totalFilteredCount} your runs
              </span>

              <div className="flex items-center gap-1">
                {/* Prev button */}
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || isLoading}
                  className="w-7 h-7 flex items-center justify-center border border-black/[0.1] rounded-[5px] bg-white text-[12.5px] text-nexus-dark disabled:text-nexus-subtle disabled:cursor-not-allowed hover:border-nexus-accent/40 transition-colors"
                  aria-label="Previous page"
                >
                  ←
                </button>

                {/* Page number pills */}
                {pageNumbers.map((num, idx) =>
                  num < 0 ? (
                    <span
                      key={`ellipsis-${idx}`}
                      className="w-7 h-7 flex items-center justify-center text-[12.5px] text-nexus-subtle"
                    >
                      …
                    </span>
                  ) : (
                    <button
                      key={num}
                      type="button"
                      onClick={() => setPage(num)}
                      disabled={isLoading}
                      className={`w-7 h-7 flex items-center justify-center rounded-[5px] text-[12.5px] transition-colors ${
                        num === page
                          ? 'bg-nexus-accent text-white border border-nexus-accent'
                          : 'border border-black/[0.1] bg-white text-nexus-dark hover:border-nexus-accent/40'
                      }`}
                    >
                      {num}
                    </button>
                  )
                )}

                {/* Next button */}
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || isLoading}
                  className="w-7 h-7 flex items-center justify-center border border-black/[0.1] rounded-[5px] bg-white text-[12.5px] text-nexus-dark disabled:text-nexus-subtle disabled:cursor-not-allowed hover:border-nexus-accent/40 transition-colors"
                  aria-label="Next page"
                >
                  →
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}