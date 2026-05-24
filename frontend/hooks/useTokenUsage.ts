'use client'

/**
 * SWR hook for daily token usage.
 * Calls GET /api/v1/metrics/token-usage?days=N
 */
import useSWR from 'swr'
import { apiFetch } from '@/lib/api'
import type { DailyTokenUsage } from '@/lib/types'

interface UseTokenUsageResult {
  data: DailyTokenUsage[]
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function tokenUsageFetcher(url: string): Promise<DailyTokenUsage[]> {
  return apiFetch<DailyTokenUsage[]>(url)
}

export function useTokenUsage(days = 7): UseTokenUsageResult {
  const url = `/api/v1/metrics/token-usage?days=${days}`

  const { data, error, isLoading, mutate } = useSWR<DailyTokenUsage[]>(
    url,
    tokenUsageFetcher,
    { refreshInterval: 30_000, revalidateOnFocus: true, keepPreviousData: true }
  )

  return { data: data ?? [], isLoading, isError: !!error, mutate }
}