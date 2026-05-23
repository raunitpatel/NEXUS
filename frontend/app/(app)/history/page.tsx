'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import { TopBar } from '@/components/ui/TopBar'
import { apiFetch } from '@/lib/api'
import type { RunListResponse } from '@/lib/types'
import { FilterBar, type HistoryStatusFilter } from './FilterBar'
import { RunTable } from './RunTable'

const PAGE_SIZE = 20

async function fetchRunHistory(url: string): Promise<RunListResponse> {
  return apiFetch<RunListResponse>(url)
}

export default function HistoryPage() {
  const [status, setStatus] = useState<HistoryStatusFilter>('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [page, setPage] = useState(1)

  const historyUrl = useMemo(() => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    params.set('page', String(page))
    params.set('size', String(PAGE_SIZE))
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)

    return `/api/v1/runs?${params.toString()}`
  }, [status, page, startDate, endDate])

  const { data, isLoading, error } = useSWR<RunListResponse>(
    historyUrl,
    fetchRunHistory
  )

  const runs = data?.runs ?? []
  const totalCount = data?.total_count ?? 0
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))
  const startItem = totalCount === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const endItem = Math.min(page * PAGE_SIZE, totalCount)

  function resetPageAndSetStatus(nextStatus: HistoryStatusFilter) {
    setStatus(nextStatus)
    setPage(1)
  }

  function resetPageAndSetStartDate(value: string) {
    setStartDate(value)
    setPage(1)
  }

  function resetPageAndSetEndDate(value: string) {
    setEndDate(value)
    setPage(1)
  }

  return (
    <>
      <TopBar title="My history" />

      <div className="flex-1 bg-nexus-bg overflow-hidden flex flex-col">
        <FilterBar
          status={status}
          startDate={startDate}
          endDate={endDate}
          onStatusChange={resetPageAndSetStatus}
          onStartDateChange={resetPageAndSetStartDate}
          onEndDateChange={resetPageAndSetEndDate}
        />

        <div className="flex-1 p-6 overflow-y-auto">
          <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
            {error ? (
              <div className="px-4 py-10 text-center text-[13px] text-nexus-error">
                Failed to load run history. Please refresh.
              </div>
            ) : (
              <RunTable runs={runs} isLoading={isLoading} />
            )}

            <div className="flex items-center justify-between px-4 py-3 border-t border-black/[0.06] bg-white">
              <span className="text-[12.5px] text-nexus-muted">
                Showing {startItem}-{endItem} of {totalCount} your runs
              </span>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1 || isLoading}
                  className="h-7 px-3 border border-black/[0.1] rounded-[5px] bg-white text-[12.5px] text-nexus-dark disabled:text-nexus-subtle disabled:cursor-not-allowed hover:border-nexus-accent/40 transition-colors"
                >
                  Previous
                </button>
                <span className="h-7 min-w-7 px-2 rounded-[5px] bg-nexus-accent text-white text-[12.5px] inline-flex items-center justify-center">
                  {page}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={page >= totalPages || isLoading}
                  className="h-7 px-3 border border-black/[0.1] rounded-[5px] bg-white text-[12.5px] text-nexus-dark disabled:text-nexus-subtle disabled:cursor-not-allowed hover:border-nexus-accent/40 transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
