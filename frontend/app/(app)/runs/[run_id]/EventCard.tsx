// frontend/app/(app)/runs/[run_id]/EventCard.tsx
'use client'

/**
 * EventCard — renders a single orchestrator event in the thought trace timeline.
 *
 * Improvements:
 * - Handles deeply nested payloads
 * - Supports raw_response / summary / completed_tasks
 * - Better payload rendering
 * - Better overflow handling
 * - Safer content extraction
 */

import { useState } from 'react'
import type { RunEvent } from '@/lib/types'
import { MarkdownRenderer } from '@/components/ui/MarkdownRenderer'

interface EventCardProps {
  event: RunEvent
  index: number
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge config
// ─────────────────────────────────────────────────────────────────────────────

interface BadgeConfig {
  label: string
  bg: string
  text: string
  borderColor: string
}

const EVENT_BADGE: Record<string, BadgeConfig> = {
  thought:                  { label: 'Thought',      bg: '#EEEDFE', text: '#3C3489', borderColor: '#534AB7' },
  tool_call:                { label: 'Tool call',    bg: '#FEF3E2', text: '#884A05', borderColor: '#BA7517' },
  tool_result:              { label: 'Tool result',  bg: '#E1F5EE', text: '#085041', borderColor: '#1D9E75' },
  agent_start:              { label: 'Agent start',  bg: '#E6F1FB', text: '#0C447C', borderColor: '#378ADD' },
  agent_end:                { label: 'Agent end',    bg: '#E6F1FB', text: '#0C447C', borderColor: '#378ADD' },
  orchestrator_plan:        { label: 'Plan',         bg: '#EEEDFE', text: '#3C3489', borderColor: '#534AB7' },
  orchestrator_dispatch:    { label: 'Dispatch',     bg: '#EEEDFE', text: '#3C3489', borderColor: '#534AB7' },
  orchestrator_synthesize:  { label: 'Synthesize',   bg: '#D4F3E6', text: '#0A5E3A', borderColor: '#1D9E75' },
  run_start:                { label: 'Run start',    bg: '#E8F8F2', text: '#1D9E75', borderColor: '#1D9E75' },
  run_complete:             { label: 'Complete',     bg: '#D4F3E6', text: '#0A5E3A', borderColor: '#1D9E75' },
  run_error:                { label: 'Error',        bg: '#FDECEA', text: '#E24B4A', borderColor: '#E24B4A' },
  memory_read:              { label: 'Memory read',  bg: '#EEEDFE', text: '#3C3489', borderColor: '#7F77DD' },
  memory_write:             { label: 'Memory write', bg: '#EEEDFE', text: '#3C3489', borderColor: '#7F77DD' },
  llm_response:             { label: 'LLM',          bg: '#D4F3E6', text: '#0A5E3A', borderColor: '#1D9E75' },
  code_iteration:           { label: 'Code iter.',   bg: '#FAEEDA', text: '#633806', borderColor: '#EF9F27' },
}

const DEFAULT_BADGE: BadgeConfig = {
  label: 'Event',
  bg: '#F0EFE9',
  text: '#888780',
  borderColor: '#888780',
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatTime(isoString: string): string {
  try {
    return new Date(isoString)
      .toLocaleTimeString('en-US', {
        hour12: true,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
      .toLowerCase()
  } catch {
    return isoString
  }
}

function extractContent(data: unknown): string | null {
  if (!data) return null

  // direct string
  if (typeof data === 'string') {
    const cleaned = data.trim()
    return cleaned || null
  }

  // arrays
  if (Array.isArray(data)) {
    for (const item of data) {
      const result = extractContent(item)
      if (result) return result
    }
    return null
  }

  // objects
  if (typeof data === 'object') {
    const obj = data as Record<string, unknown>

    const priorityKeys = [
      'summary',
      'content',
      'answer',
      'result',
      'response',
      'message',
      'text',
      'snippet',
      'output_preview',
      'final_answer',
      'stdout',
      'stderr',
      'execution_result',
      'run_output',
      'synthesize',
    ]

    // prioritized extraction
    for (const key of priorityKeys) {
      const value = obj[key]
      if (typeof value === 'string' && value.trim()) {
        return value
      }
    }

    // recursive extraction
    for (const value of Object.values(obj)) {
      const result = extractContent(value)
      if (result) return result
    }
  }

  return null
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export function EventCard({ event, index }: EventCardProps) {

  const badge = EVENT_BADGE[event.event_type] ?? DEFAULT_BADGE

  const payload = (event.payload ?? {}) as Record<string, unknown>

  const hasPayload = Object.keys(payload).length > 0

  // Deep extraction from all possible payload locations
  const content =
    extractContent(payload.summary) ??
    extractContent(payload.output) ??
    extractContent(payload.raw_response) ??
    extractContent(payload.completed_tasks) ??
    extractContent(payload) ??
    null

  const toolName =
    (payload.agent_type as string | undefined) ??
    (payload.tool as string | undefined)

  // Temporary debugging
  console.log('EVENT PAYLOAD', event)

  return (
    <div
      className="border-l-[3px] bg-white border-b border-black/[0.05] px-4 py-3 last:border-b-0 transition-all"
      style={{
        borderLeftColor: badge.borderColor,
        animationDelay: `${index * 40}ms`,
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-[7px]">
        <span
          className="inline-flex items-center gap-1 px-[7px] py-[1px] rounded-[3px] text-[10.5px] font-bold tracking-[0.04em] uppercase"
          style={{
            background: badge.bg,
            color: badge.text,
          }}
        >
          {badge.label}
        </span>

        <span className="text-[11px] text-nexus-subtle font-mono">
          {formatTime(event.created_at)}
        </span>
      </div>

      {/* Body */}
      <div className="text-[13px] text-nexus-body leading-[1.6] min-w-0">
        {toolName && (
          <div className="text-[12px] font-semibold text-nexus-dark mb-1 break-words">
            {event.event_type === 'orchestrator_dispatch'
              ? `Dispatch → ${toolName}`
              : toolName}
          </div>
        )}

        {content && event.event_type !== 'orchestrator_dispatch' && (
          <div className="mt-2 break-words overflow-hidden">
            <MarkdownRenderer content={content} />
          </div>
        )}
      </div>

    </div>
  )
}