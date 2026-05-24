'use client'

/**
 * SWR hook for semantic memory search.
 *
 * Calls GET /api/v1/memory/search?q=QUERY&limit=LIMIT.
 * Pass the debounced query string as `query` — this hook does not debounce itself.
 * When `query` is empty, no request is made (SWR key is null).
 */
import useSWR from 'swr'
import { apiFetch } from '@/lib/api'
import type { MemorySearchResponse } from '@/lib/types'

interface UseMemorySearchOptions {
  limit?: number
}

interface UseMemorySearchResult {
  data: MemorySearchResponse | null
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function memorySearchFetcher(url: string): Promise<MemorySearchResponse> {
  return apiFetch<MemorySearchResponse>(url)
}

/**
 * Perform a semantic similarity search over the authenticated user's memory.
 *
 * @param query - Debounced search string. Empty string suppresses the request.
 * @param options - Optional limit (default 10, max 50).
 */
export function useMemorySearch(
  query: string,
  options: UseMemorySearchOptions = {}
): UseMemorySearchResult {
  const { limit = 10 } = options

  const url =
    query.trim().length > 0
      ? `/api/v1/memory/search?q=${encodeURIComponent(query.trim())}&limit=${limit}`
      : null

  const { data, error, isLoading, mutate } = useSWR<MemorySearchResponse>(
    url,
    memorySearchFetcher,
    {
      revalidateOnFocus: false,
      keepPreviousData: true,
    }
  )

  return {
    data: data ?? null,
    isLoading,
    isError: !!error,
    mutate,
  }
}