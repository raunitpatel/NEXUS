/**
 * SWR hook for fetching the authenticated user's aggregate metrics.
 *
 * Dashboard cards use this instead of the paginated recent-runs list so
 * totals are not capped by the "10 most recent runs" table query.
 */
import useSWR from 'swr'
import { apiFetch } from '@/lib/api'
import type { MetricsSummary } from '@/lib/types'

interface UseMetricsSummaryOptions {
  days?: number
}

interface UseMetricsSummaryResult {
  summary: MetricsSummary | null
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function metricsSummaryFetcher(url: string): Promise<MetricsSummary> {
  return apiFetch<MetricsSummary>(url)
}

export function useMetricsSummary(
  options: UseMetricsSummaryOptions = {}
): UseMetricsSummaryResult {
  const { days = 7 } = options
  const url = `/api/v1/metrics/summary?days=${days}`

  const { data, error, isLoading, mutate } = useSWR<MetricsSummary>(
    url,
    metricsSummaryFetcher,
    {
      refreshInterval: 5000,
      revalidateOnFocus: true,
      keepPreviousData: true,
    }
  )

  return {
    summary: data ?? null,
    isLoading,
    isError: !!error,
    mutate,
  }
}
