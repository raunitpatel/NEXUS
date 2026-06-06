'use client'

/**
 * SWR hook for daily run error rate.
 * Calls GET /api/v1/metrics/error-rate?days=N
 */
import useSWR from 'swr'
import { apiFetch } from '@/lib/api'
import type { DailyErrorRate } from '@/lib/types'

interface UseErrorRateResult {
  data: DailyErrorRate[]
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function errorRateFetcher(url: string): Promise<DailyErrorRate[]> {
  return apiFetch<DailyErrorRate[]>(url)
}

export function useErrorRate(days = 7): UseErrorRateResult {
  const url = `/api/v1/metrics/error-rate?days=${days}`

  const { data, error, isLoading, mutate } = useSWR<DailyErrorRate[]>(
    url,
    errorRateFetcher,
    { refreshInterval: 30_000, revalidateOnFocus: true, keepPreviousData: true }
  )

  return { data: data ?? [], isLoading, isError: !!error, mutate }
}
