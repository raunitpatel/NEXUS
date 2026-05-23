// frontend/app/(app)/runs/[run_id]/EventCard.tsx
'use client'

/**
 * EventCard — renders a single orchestrator event in the thought trace timeline.
 *
 * Matches the `.ev` / `.evb` CSS classes in docs/design/nexus-all-pages.html.
 * Expandable JSON payload viewer shown for tool_call / tool_result events.
 */

import { useState } from 'react'
import type { RunEvent, EventType } from '@/lib/types'
import clsx from 'clsx'

interface EventCardProps {
  event: RunEvent
  /** Index used for animation delay (stagger effect). */
  index: number
}

// ── Badge config ──────────────────────────────────────────────────────────────

interface BadgeConfig {
  label: string
  bg: string
  text: string
  borderColor: string
}

const EVENT_BADGE: Record<string, BadgeConfig> = {
  thought:                  { label: 'Thought',    bg: '#EEEDFE', text: '#3C3489', borderColor: '#534AB7' },
  tool_call:                { label: 'Tool call',  bg: '#FEF3E2', text: '#884A05', borderColor: '#BA7517' },
  tool_result:              { label: 'Tool result',bg: '#E1F5EE', text: '#085041', borderColor: '#1D9E75' },
  agent_start:              { label: 'Agent start',bg: '#E6F1FB', text: '#0C447C', borderColor: '#378ADD' },
  agent_end:                { label: 'Agent end',  bg: '#E6F1FB', text: '#0C447C', borderColor: '#378ADD' },
  orchestrator_plan:        { label: 'Plan',       bg: '#EEEDFE', text: '#3C3489', borderColor: '#534AB7' },
  orchestrator_dispatch:    { label: 'Dispatch',   bg: '#EEEDFE', text: '#3C3489', borderColor: '#534AB7' },
  orchestrator_synthesize:  { label: 'Synthesize', bg: '#D4F3E6', text: '#0A5E3A', borderColor: '#1D9E75' },
  run_start:                { label: 'Run start',  bg: '#E8F8F2', text: '#1D9E75', borderColor: '#1D9E75' },
  run_complete:             { label: 'Complete',   bg: '#D4F3E6', text: '#0A5E3A', borderColor: '#1D9E75' },
  run_error:                { label: 'Error',      bg: '#FDECEA', text: '#E24B4A', borderColor: '#E24B4A' },
  memory_read:              { label: 'Memory read',bg: '#EEEDFE', text: '#3C3489', borderColor: '#7F77DD' },
  memory_write:             { label: 'Memory write',bg:'#EEEDFE', text: '#3C3489', borderColor: '#7F77DD' },
  llm_response:             { label: 'LLM',        bg: '#D4F3E6', text: '#0A5E3A', borderColor: '#1D9E75' },
  code_iteration:           { label: 'Code iter.', bg: '#FAEEDA', text: '#633806', borderColor: '#EF9F27' },
}

const DEFAULT_BADGE: BadgeConfig = { label: 'Event', bg: '#F0EFE9', text: '#888780', borderColor: '#888780' }

function formatTime(isoString: string): string {
  try {
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return isoString
  }
}

/**
 * Renders one event in the thought trace timeline with expandable payload.
 */
export function EventCard({ event, index }: EventCardProps) {
  const [expanded, setExpanded] = useState(false)
  const badge = EVENT_BADGE[event.event_type] ?? DEFAULT_BADGE
  const hasPayload = event.payload && Object.keys(event.payload).length > 0

  // Extract human-readable content for display
  const payload = event.payload as Record<string, unknown>
  const content =
    (payload.content as string | undefined) ??
    (payload.message as string | undefined) ??
    (payload.error as string | undefined) ??
    (typeof payload.output === 'string' ? payload.output : undefined)
  const toolName =
    (payload.tool as string | undefined) ??
    (payload.agent_type as string | undefined)

  return (
    <div
      className="border-l-[3px] bg-white border-b border-black/[0.05] px-4 py-3 last:border-b-0 transition-all"
      style={{
        borderLeftColor: badge.borderColor,
        animationDelay: `${index * 40}ms`,
      }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-[7px]">
        <span
          className="inline-flex items-center gap-1 px-[7px] py-[1px] rounded-[3px] text-[10.5px] font-bold tracking-[0.04em] uppercase"
          style={{ background: badge.bg, color: badge.text }}
        >
          {badge.label}
        </span>
        <span className="text-[11px] text-nexus-subtle font-mono">{formatTime(event.created_at)}</span>
      </div>

      {/* Event body */}
      <div className="text-[13px] text-nexus-body leading-[1.6]">
        {toolName && (
          <div className="text-[12px] font-semibold text-nexus-dark mb-1">
            {toolName} · <span className="text-nexus-muted font-normal">{event.source}</span>
          </div>
        )}
        {content && (
          <span className="italic text-nexus-body">{content}</span>
        )}
      </div>

      {/* Expandable JSON payload */}
      {hasPayload && (
        <div className="mt-[5px]">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[11.5px] text-nexus-accent font-medium hover:underline"
          >
            {expanded ? 'Hide' : 'Show'} payload
          </button>
          {expanded && (
            <pre className="mt-[5px] bg-nexus-bg border border-black/[0.07] rounded-[5px] px-[10px] py-[7px] text-[11.5px] font-mono text-nexus-dark overflow-x-auto leading-[1.6]">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
