'use client'

/**
 * SWR hook for daily average and p95 run latency.
 * Calls GET /api/v1/metrics/latency?days=N
 */
import useSWR from 'swr'
import { apiFetch } from '@/lib/api'
import type { DailyLatency } from '@/lib/types'

interface UseLatencyResult {
  data: DailyLatency[]
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function latencyFetcher(url: string): Promise<DailyLatency[]> {
  return apiFetch<DailyLatency[]>(url)
}

export function useLatency(days = 7): UseLatencyResult {
  const url = `/api/v1/metrics/latency?days=${days}`

  const { data, error, isLoading, mutate } = useSWR<DailyLatency[]>(
    url,
    latencyFetcher,
    { refreshInterval: 30_000, revalidateOnFocus: true, keepPreviousData: true }
  )

  return { data: data ?? [], isLoading, isError: !!error, mutate }
}