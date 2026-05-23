/**
 * SWR hook for fetching the authenticated user's runs list.
 *
 * Polls every 5 seconds to reflect status changes (running → completed/failed).
 * Used by the Dashboard page and the History page.
 */
import useSWR from 'swr'
import { apiFetch } from '@/lib/api'
import type { Run } from '@/lib/types'

interface UseRunsOptions {
  limit?: number
  offset?: number
  status?: string
}

interface UseRunsResult {
  runs: Run[]
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function runsFetcher(url: string): Promise<Run[]> {
  return apiFetch<Run[]>(url)
}

/**
 * Fetch the current user's run list with automatic polling.
 *
 * @param options - Pagination and filter options.
 * @returns Runs array, loading/error state, and manual mutate trigger.
 */
export function useRuns(options: UseRunsOptions = {}): UseRunsResult {
  const { limit = 10, offset = 0, status } = options

  const params = new URLSearchParams()
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  if (status) params.set('status', status)

  const url = `/api/v1/runs?${params.toString()}`

  const { data, error, isLoading, mutate } = useSWR<Run[]>(url, runsFetcher, {
    refreshInterval: 5000,
    revalidateOnFocus: true,
    keepPreviousData: true,
  })

  return {
    runs: data ?? [],
    isLoading,
    isError: !!error,
    mutate,
  }
}