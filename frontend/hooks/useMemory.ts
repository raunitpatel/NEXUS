'use client'

import useSWR from 'swr'
import { apiFetch } from '@/lib/api'

export interface MemoryEntry {
  embedding_id: string
  run_id: string
  content: string
  model: string
  created_at: string
}

interface UseMemoryOptions {
  limit?: number
  offset?: number
}

interface UseMemoryResult {
  data: MemoryEntry[]
  isLoading: boolean
  isError: boolean
  mutate: () => void
}

async function memoryFetcher(url: string): Promise<MemoryEntry[]> {
  return apiFetch<MemoryEntry[]>(url)
}

export function useMemory(
  options: UseMemoryOptions = {}
): UseMemoryResult {
  const {
    limit = 20,
    offset = 0,
  } = options

  const url = `/api/v1/memory?limit=${limit}&offset=${offset}`

  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR<MemoryEntry[]>(
    url,
    memoryFetcher,
    {
      revalidateOnFocus: false,
    }
  )

  return {
    data: data ?? [],
    isLoading,
    isError: !!error,
    mutate,
  }
}