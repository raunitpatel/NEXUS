// frontend/app/(app)/runs/[run_id]/ThoughtTrace.tsx
'use client'

/**
 * ThoughtTrace — renders the live event timeline for a run.
 *
 * Two modes:
 *   - Live:   run.status === 'running' → mounts useSSEStream, events arrive in real time
 *   - Static: run.status === 'completed'|'failed' → renders initialEvents from DB, no SSE
 *
 * Design reference: Page 3 and 3b in docs/design/nexus-all-pages.html.
 */

import { useEffect, useMemo, useRef } from 'react'
import type { Run, RunEvent } from '@/lib/types'
import { useSSEStream } from '@/hooks/useSSEStream'
import { EventCard } from './EventCard'
import { RunSummary } from './RunSummary'
import { MarkdownRenderer } from '@/components/ui/MarkdownRenderer'

interface ThoughtTraceProps {
  run: Run
  /** Pre-loaded events from DB for completed runs. Empty array for active runs. */
  initialEvents: RunEvent[]
}

/**
 * Final answer block shown after run_complete.
 */
function FinalAnswer({ output }: { output: string }) {
  return (
    <div className="bg-white rounded-[8px] border-[1.5px] border-nexus-success/20 px-[22px] py-5 mb-4">
      <div className="flex items-center gap-[7px] text-[11.5px] font-bold text-nexus-success uppercase tracking-[0.06em] mb-3">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7l4 4L12 3" stroke="#1D9E75" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
        Your answer
      </div>
      <div className="text-[14px] text-nexus-dark leading-[1.8]">
        <MarkdownRenderer content={output} />
      </div>
    </div>
  )
}

/**
 * ThoughtTrace renders the complete live or historical event timeline.
 */
export function ThoughtTrace({ run, initialEvents }: ThoughtTraceProps) {
  const isLive = run.status === 'running'
  const bottomRef = useRef<HTMLDivElement>(null)

  const { events: liveEvents, status, finalOutput, error, retry } = useSSEStream(
    run.run_id,
    isLive
  )

  const displayEvents = isLive ? liveEvents : initialEvents
  const completedOutput = useMemo(() => {
    const terminalEvent = [...displayEvents]
      .reverse()
      .find((event) => event.event_type === 'run_complete')
    const terminalOutput =
      terminalEvent?.payload?.final_answer ??
      terminalEvent?.payload?.output ??
      terminalEvent?.payload?.response
    if (typeof terminalOutput === 'string' && terminalOutput.trim()) return terminalOutput

    const llmEvent = [...displayEvents]
      .reverse()
      .find((event) => event.event_type === 'llm_response' || event.event_type === 'orchestrator_synthesize')
    const llmContent = llmEvent?.payload?.content
    return typeof llmContent === 'string' && llmContent.trim() ? llmContent : null
  }, [displayEvents])

  // Auto-scroll to bottom as new events arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [displayEvents.length])

  return (
    <div className="grid grid-cols-[1fr_288px] gap-4 items-start">
      {/* Left: event trace */}
      <div>
        {/* Final answer (completed run or completed stream) */}
        {(finalOutput || completedOutput) && (
          <FinalAnswer output={finalOutput ?? completedOutput ?? ''} />
        )}

        {/* Error banner */}
        {error && isLive && (
          <div className="bg-[#FDECEA] border border-nexus-error/20 rounded-[8px] px-4 py-3 mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2 text-[13px] text-nexus-error">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.3"/><path d="M7 4.5v3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><circle cx="7" cy="9.5" r="0.7" fill="currentColor"/></svg>
              {error}
            </div>
            <button onClick={retry} className="text-[12px] text-nexus-error font-medium hover:underline">Retry</button>
          </div>
        )}

        {/* Event cards */}
        <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
          <div className="px-[18px] py-3 border-b border-black/[0.06] flex items-center gap-2">
            {isLive && status === 'open' && (
              <span className="w-[7px] h-[7px] bg-nexus-success rounded-full animate-pulse" />
            )}
            <span className="text-[13px] font-semibold text-nexus-dark">Thought trace</span>
            {isLive && status === 'open' && (
              <span className="text-[11.5px] text-nexus-success font-medium">streaming live</span>
            )}
          </div>

          {displayEvents.length === 0 ? (
            <div className="px-4 py-8 text-center text-[13px] text-nexus-muted">
              {isLive ? 'Waiting for first event…' : 'No events recorded for this run.'}
            </div>
          ) : (
            <>
              {displayEvents.map((ev, i) => (
                <EventCard key={ev.event_id ?? i} event={ev} index={i} />
              ))}
              <div ref={bottomRef} />
            </>
          )}
        </div>
      </div>

      {/* Right: summary panel */}
      <RunSummary
        run={run}
        events={displayEvents}
        connectionStatus={isLive ? status : 'closed'}
      />
    </div>
  )
}
