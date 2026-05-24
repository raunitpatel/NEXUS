'use client'

import { useState } from 'react'
import { TopBar } from '@/components/ui/TopBar'
import { SearchBar } from './SearchBar'
import { MemoryResultCard } from './MemoryResultCard'
import { useMemory } from '@/hooks/useMemory'
import { useMemorySearch } from '@/hooks/useMemorySearch'

const SUGGESTIONS = [
  'LLM reasoning',
  'Python quicksort',
  'diffusion models',
  'weather Tokyo',
]

function MemoryResultSkeleton() {
  return (
    <div className="bg-white rounded-[8px] border border-black/[0.07] p-4">
      <div className="flex items-center gap-2 mb-[10px]">
        <div className="h-[20px] w-[58px] bg-black/[0.04] rounded-[4px] animate-pulse" />
        <div className="h-[12px] w-[80px] bg-black/[0.04] rounded-[4px] animate-pulse" />
      </div>

      <div className="h-[13px] w-full bg-black/[0.04] rounded-[4px] animate-pulse mb-2" />
      <div className="h-[13px] w-[88%] bg-black/[0.04] rounded-[4px] animate-pulse mb-[10px]" />

      <div className="h-[3px] w-full bg-black/[0.04] rounded-[2px] animate-pulse" />
    </div>
  )
}

function EmptyState({ hasQuery }: { hasQuery: boolean }) {
  return (
    <div className="flex flex-col items-center text-center py-12">
      <div className="w-12 h-12 bg-[#F0EFE9] rounded-[11px] flex items-center justify-center mb-[14px]">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-nexus-muted">
          <ellipse cx="12" cy="8" rx="8" ry="4.5" stroke="currentColor" strokeWidth="1.5" />
          <path d="M4 8v8c0 2.49 3.58 4.5 8 4.5s8-2.01 8-4.5V8" stroke="currentColor" strokeWidth="1.5" />
          <path d="M4 12c0 2.49 3.58 4.5 8 4.5s8-2.01 8-4.5" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </div>

      <div className="text-[14px] font-semibold text-nexus-dark mb-[6px]">
        {hasQuery ? 'No memories found' : 'No memories yet'}
      </div>

      <div className="text-[12.5px] text-nexus-muted leading-[1.55] max-w-[300px]">
        {hasQuery
          ? 'Try a different search term or broaden your query.'
          : 'Agent memory appears here after runs complete and embeddings are stored.'}
      </div>
    </div>
  )
}

export default function MemoryPage() {
  const [query, setQuery] = useState('')

  const hasQuery = query.trim().length > 0

  const {
    data: memoryData,
    isLoading: memoryLoading,
    isError: memoryError,
  } = useMemory()

  const {
    data: searchData,
    isLoading: searchLoading,
    isError: searchError,
  } = useMemorySearch(query)

  const searchResults = searchData?.results ?? []

  const results =
  hasQuery && searchResults.length > 0
    ? searchResults.map((item: any) => ({
        ...item,
        similarity: item.similarity ?? 1,
      }))
    : memoryData.map((item: any) => ({
        ...item,
        similarity: 1,
      }))

  const isLoading = hasQuery
    ? searchLoading
    : memoryLoading

  const isError = hasQuery
    ? searchError
    : memoryError

  const showSkeleton = isLoading

  const showEmpty =
    !isLoading &&
    !isError &&
    results.length === 0

  const showResults =
    !isLoading &&
    !isError &&
    results.length > 0

  return (
    <>
      <TopBar title="My memory" />

      <div className="flex-1 bg-nexus-bg overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-[16px] font-semibold text-nexus-dark">
              Your agent memory
            </h2>

            <p className="text-[12.5px] text-nexus-muted mt-[2px]">
              Search across outputs from your past runs — powered by pgvector semantic similarity.
            </p>
          </div>

          {showResults && (
            <div className="text-[12px] text-nexus-muted bg-white border border-black/[0.08] px-[10px] py-[4px] rounded-[5px]">
              {results.length} result{results.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>

        <SearchBar
          onDebouncedChange={setQuery}
          suggestions={SUGGESTIONS}
        />

        {isError && (
          <div className="bg-[#FDECEA] border border-nexus-error/20 rounded-[7px] px-4 py-3 flex items-center gap-2 text-[13px] text-nexus-error mb-4">
            Failed to load memory.
          </div>
        )}

        {showSkeleton && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-[14px]">
            {[...Array(4)].map((_, i) => (
              <MemoryResultSkeleton key={i} />
            ))}
          </div>
        )}

        {showResults && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-[14px]">
            {results.map((result) => (
              <MemoryResultCard
                key={result.embedding_id}
                result={result}
              />
            ))}
          </div>
        )}

        {showEmpty && (
          <EmptyState hasQuery={hasQuery} />
        )}
      </div>
    </>
  )
}