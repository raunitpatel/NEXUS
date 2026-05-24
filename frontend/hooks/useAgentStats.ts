'use client'

/**
 * SWR hook for per-agent task statistics.
 * Calls GET /api/v1/metrics/agent-stats?days=N
 */
import useSWR from 'swr'
import { apiFetch } from '@/lib/api'
import type { AgentStat } from '@/lib/types'

interface UseAgentStatsOptions {
  days?: number
}

interface UseAgentStatsResult {
  stats: AgentStat[]
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function agentStatsFetcher(url: string): Promise<AgentStat[]> {
  return apiFetch<AgentStat[]>(url)
}

export function useAgentStats(options: UseAgentStatsOptions = {}): UseAgentStatsResult {
  const { days = 7 } = options
  const url = `/api/v1/metrics/agent-stats?days=${days}`

  const { data, error, isLoading, mutate } = useSWR<AgentStat[]>(
    url,
    agentStatsFetcher,
    { refreshInterval: 30_000, revalidateOnFocus: true, keepPreviousData: true }
  )

  return { stats: data ?? [], isLoading, isError: !!error, mutate }
}