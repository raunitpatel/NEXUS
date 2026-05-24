'use client'

/**
 * MemoryResultCard — displays a single memory result.
 *
 * Shows:
 * - content preview
 * - similarity score
 * - memory chip
 * - source run link
 */

import Link from 'next/link'
import type { MemorySearchResult } from '@/lib/types'

interface MemoryResultCardProps {
  /** The memory result to display. */
  result: MemorySearchResult
}

// Similarity score colour thresholds
function getSimilarityColor(score: number): string {
  if (score >= 0.9) return '#1D9E75'
  if (score >= 0.75) return '#BA7517'
  return '#888780'
}

// Similarity label derived from numeric score
function getSimilarityLabel(score: number): string {
  if (score >= 0.9) return 'Highly relevant'
  if (score >= 0.75) return 'Relevant'
  return 'Loosely related'
}

const MEMORY_CHIP = {
  bg: '#E6F1FB',
  text: '#0C447C',
  dot: '#378ADD',
  label: 'Search',
}

/**
 * Card component for a single memory result.
 */
export function MemoryResultCard({
  result,
}: MemoryResultCardProps) {
  const similarityPct = Math.round(result.similarity * 100)

  const similarityColor = getSimilarityColor(result.similarity)

  const preview =
    result.content.length > 200
      ? result.content.slice(0, 200) + '…'
      : result.content

  return (
    <div
      className="
        bg-white
        rounded-[8px]
        border border-black/[0.07]
        p-4
        relative
        hover:border-nexus-accent/22
        hover:shadow-[0_2px_10px_rgba(83,74,183,0.07)]
        transition-[border-color,box-shadow]
      "
    >
      {/* Similarity score badge */}
      <span
        className="
          absolute
          top-[14px]
          right-[14px]
          px-[8px]
          py-[2px]
          rounded-[4px]
          text-[11.5px]
          font-bold
        "
        style={{
          background:
            similarityColor === '#1D9E75'
              ? '#D4F3E6'
              : similarityColor === '#BA7517'
                ? '#FEF3E2'
                : '#F1EFE8',
          color: similarityColor,
        }}
      >
        {result.similarity.toFixed(2)}
      </span>

      {/* Agent chip + run id */}
      <div className="flex items-center gap-2 mb-[10px]">
        <span
          className="
            inline-flex
            items-center
            gap-[4px]
            px-[7px]
            py-[2px]
            rounded-[4px]
            text-[11px]
            font-semibold
          "
          style={{
            background: MEMORY_CHIP.bg,
            color: MEMORY_CHIP.text,
          }}
        >
          <span
            className="w-[5px] h-[5px] rounded-full flex-shrink-0"
            style={{
              background: MEMORY_CHIP.dot,
            }}
          />

          {MEMORY_CHIP.label}
        </span>

        <span className="font-mono text-[11.5px] text-nexus-muted">
          run_{result.run_id.slice(0, 6)}
        </span>
      </div>

      {/* Query context */}
      <div className="text-[12px] text-nexus-muted italic mb-2 line-clamp-1">
        "
        {preview.slice(0, 70)}
        {preview.length > 70 ? '...' : ''}
        "
      </div>

      {/* Main content */}
      <div className="text-[13px] text-nexus-dark leading-[1.7] mb-[14px]">
        {preview}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between">
        <span className="text-[12px] text-nexus-muted">
          {new Date(result.created_at).toLocaleDateString([], {
            month: 'short',
            day: 'numeric',
          })}
          {' · '}
          {new Date(result.created_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>

        <Link
          href={`/runs/${result.run_id}`}
          className="
            text-[13px]
            font-medium
            text-nexus-accent
            hover:text-nexus-accent-hover
            transition-colors
            no-underline
          "
        >
          View run →
        </Link>
      </div>
    </div>
  )
}